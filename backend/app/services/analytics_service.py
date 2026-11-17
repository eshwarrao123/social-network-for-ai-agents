"""
Analytics Service — SQL aggregation engine for tenant-scoped agent analytics,
date-bucketed activity timelines, and cross-company network intelligence.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.comment import Comment
from app.models.interaction import AgentInteraction
from app.models.notification import Notification
from app.models.post import Post
from app.models.preference import AgentPreference
from app.schemas.analytics import (
    AgentActivityBucket,
    AgentActivityResponse,
    AgentAnalyticsOverview,
    AgentPartnershipInsights,
    PartnerCompanyInsight,
    PartnerIndustryInsight,
    PreferenceAnalyticsSummary,
    PublisherMetrics,
    RecipientMetrics,
)
from app.services.preference_service import cosine_similarity, dot_product, normalize_vector

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """
    Executes high-performance SQL aggregations for agent analytics.
    Strictly tenant-scoped: every query filters on the authenticated agent ID.
    """

    async def get_agent_overview(
        self,
        db: AsyncSession,
        agent: Agent,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AgentAnalyticsOverview:
        """
        Computes high-level analytics overview for the authenticated agent.
        Supports optional UTC date range filtering.
        """
        now_utc = datetime.now(timezone.utc)

        # ─────────────────────────────────────────────────────────────────────
        # 1. Publisher Metrics Aggregation
        # ─────────────────────────────────────────────────────────────────────
        post_filters = [Post.author_agent_id == agent.id]
        if start_date:
            post_filters.append(Post.created_at >= start_date)
        if end_date:
            post_filters.append(Post.created_at <= end_date)

        # Post counts by status and lifecycle
        post_stats_stmt = select(
            func.count().label("total_all"),
            func.count(case((Post.status != "deleted", 1))).label("total_non_deleted"),
            func.count(
                case(
                    (
                        and_(
                            Post.status == "published",
                            or_(Post.expires_at.is_(None), Post.expires_at > now_utc),
                        ),
                        1,
                    )
                )
            ).label("active_count"),
            func.count(
                case(
                    (
                        and_(
                            Post.status == "published",
                            Post.expires_at.is_not(None),
                            Post.expires_at <= now_utc,
                        ),
                        1,
                    )
                )
            ).label("expired_count"),
            func.count(case((Post.status == "deleted", 1))).label("deleted_count"),
        ).where(and_(*post_filters))

        post_stats = (await db.execute(post_stats_stmt)).one()
        total_posts_published = int(post_stats.total_non_deleted or 0)
        active_posts = int(post_stats.active_count or 0)
        expired_posts = int(post_stats.expired_count or 0)
        deleted_posts = int(post_stats.deleted_count or 0)

        # Notifications sent for published posts authored by agent
        notifs_sent_filters = [
            Post.author_agent_id == agent.id,
            Post.status != "deleted",
        ]
        if start_date:
            notifs_sent_filters.append(Notification.created_at >= start_date)
        if end_date:
            notifs_sent_filters.append(Notification.created_at <= end_date)

        notifs_sent_stmt = (
            select(func.count(Notification.id))
            .select_from(Notification)
            .join(Post, Notification.post_id == Post.id)
            .where(and_(*notifs_sent_filters))
        )
        total_notifications_sent = int((await db.execute(notifs_sent_stmt)).scalar() or 0)

        # Delivered/read notifications for published posts authored by agent
        notifs_dlv_filters = [
            Post.author_agent_id == agent.id,
            Post.status != "deleted",
            or_(
                Notification.status.in_(["delivered", "read"]),
                Notification.delivered_at.is_not(None),
            ),
        ]
        if start_date:
            notifs_dlv_filters.append(Notification.created_at >= start_date)
        if end_date:
            notifs_dlv_filters.append(Notification.created_at <= end_date)

        notifs_dlv_stmt = (
            select(func.count(Notification.id))
            .select_from(Notification)
            .join(Post, Notification.post_id == Post.id)
            .where(and_(*notifs_dlv_filters))
        )
        delivered_notifications_sent = int((await db.execute(notifs_dlv_stmt)).scalar() or 0)

        # Comments received on posts authored by agent (excluding self-comments)
        comments_rcvd_filters = [
            Post.author_agent_id == agent.id,
            Post.status != "deleted",
            Comment.author_agent_id != agent.id,
        ]
        if start_date:
            comments_rcvd_filters.append(Comment.created_at >= start_date)
        if end_date:
            comments_rcvd_filters.append(Comment.created_at <= end_date)

        comments_rcvd_stmt = (
            select(func.count(Comment.id))
            .select_from(Comment)
            .join(Post, Comment.post_id == Post.id)
            .where(and_(*comments_rcvd_filters))
        )
        total_comments_received = int((await db.execute(comments_rcvd_stmt)).scalar() or 0)

        # Publisher comment conversion:
        # 1. Against all notifications created/routed
        publisher_conversion = (
            round(total_comments_received / total_notifications_sent, 4)
            if total_notifications_sent > 0
            else 0.0
        )
        # 2. Against successfully delivered notifications
        delivered_conversion = (
            round(total_comments_received / delivered_notifications_sent, 4)
            if delivered_notifications_sent > 0
            else 0.0
        )

        publisher_metrics = PublisherMetrics(
            total_posts_published=total_posts_published,
            active_posts_count=active_posts,
            expired_posts_count=expired_posts,
            deleted_posts_count=deleted_posts,
            total_notifications_sent=total_notifications_sent,
            delivered_notifications_sent=delivered_notifications_sent,
            total_comments_received=total_comments_received,
            publisher_comment_conversion=publisher_conversion,
            delivered_comment_conversion=delivered_conversion,
        )

        # ─────────────────────────────────────────────────────────────────────
        # 2. Recipient Metrics Aggregation
        # ─────────────────────────────────────────────────────────────────────
        notif_rcvd_filters = [Notification.recipient_agent_id == agent.id]
        if start_date:
            notif_rcvd_filters.append(Notification.created_at >= start_date)
        if end_date:
            notif_rcvd_filters.append(Notification.created_at <= end_date)

        notif_rcvd_stats_stmt = select(
            func.count().label("total"),
            func.count(
                case(
                    (
                        or_(
                            Notification.status.in_(["delivered", "read"]),
                            Notification.delivered_at.is_not(None),
                        ),
                        1,
                    )
                )
            ).label("delivered"),
            func.count(
                case(
                    (
                        or_(
                            Notification.status == "read",
                            Notification.read_at.is_not(None),
                        ),
                        1,
                    )
                )
            ).label("read_cnt"),
            func.count(case((Notification.status == "pending", 1))).label("pending_cnt"),
            func.count(case((Notification.status == "failed", 1))).label("failed_cnt"),
        ).where(and_(*notif_rcvd_filters))

        notif_stats = (await db.execute(notif_rcvd_stats_stmt)).one()
        total_notifications_received = int(notif_stats.total or 0)
        delivered_count = int(notif_stats.delivered or 0)
        read_count = int(notif_stats.read_cnt or 0)
        pending_count = int(notif_stats.pending_cnt or 0)
        failed_count = int(notif_stats.failed_cnt or 0)

        # Autonomous interactions evaluated for this agent
        int_filters = [AgentInteraction.receiving_agent_id == agent.id]
        if start_date:
            int_filters.append(AgentInteraction.created_at >= start_date)
        if end_date:
            int_filters.append(AgentInteraction.created_at <= end_date)

        int_stats_stmt = select(
            func.count().label("total"),
            func.count(case((AgentInteraction.status == "engaged", 1))).label("engaged"),
            func.count(case((AgentInteraction.status == "ignored", 1))).label("ignored"),
            func.count(case((AgentInteraction.status.in_(["pending", "processing"]), 1))).label("pending_int"),
            func.count(case((AgentInteraction.status == "failed", 1))).label("failed_int"),
        ).where(and_(*int_filters))

        int_stats = (await db.execute(int_stats_stmt)).one()
        total_interactions_evaluated = int(int_stats.total or 0)
        interactions_engaged = int(int_stats.engaged or 0)
        interactions_ignored = int(int_stats.ignored or 0)
        interactions_pending = int(int_stats.pending_int or 0)
        interactions_failed = int(int_stats.failed_int or 0)

        # Comments written by this agent
        comm_written_filters = [Comment.author_agent_id == agent.id]
        if start_date:
            comm_written_filters.append(Comment.created_at >= start_date)
        if end_date:
            comm_written_filters.append(Comment.created_at <= end_date)

        comm_written_stmt = select(func.count(Comment.id)).where(and_(*comm_written_filters))
        comments_written = int((await db.execute(comm_written_stmt)).scalar() or 0)

        # Recipient response rate:
        # 1. Against all notifications received (routed)
        recipient_response_rate = (
            round(interactions_engaged / total_notifications_received, 4)
            if total_notifications_received > 0
            else 0.0
        )
        # 2. Against successfully delivered notifications
        delivered_response_rate = (
            round(interactions_engaged / delivered_count, 4)
            if delivered_count > 0
            else 0.0
        )

        recipient_metrics = RecipientMetrics(
            total_notifications_received=total_notifications_received,
            delivered_notifications_count=delivered_count,
            read_notifications_count=read_count,
            pending_notifications_count=pending_count,
            failed_notifications_count=failed_count,
            total_interactions_evaluated=total_interactions_evaluated,
            interactions_engaged=interactions_engaged,
            interactions_ignored=interactions_ignored,
            interactions_pending=interactions_pending,
            interactions_failed=interactions_failed,
            comments_written=comments_written,
            recipient_response_rate=recipient_response_rate,
            delivered_response_rate=delivered_response_rate,
        )

        # ─────────────────────────────────────────────────────────────────────
        # 3. Preference Analytics (P7 State — Zero Vector Disclosure)
        # ─────────────────────────────────────────────────────────────────────
        pref_stmt = select(AgentPreference).where(AgentPreference.agent_id == agent.id)
        pref = (await db.execute(pref_stmt)).scalar_one_or_none()

        pref_summary: PreferenceAnalyticsSummary | None = None
        if pref:
            drift = 0.0
            if pref.learned_vector is not None and agent.interest_embedding is not None:
                sim = cosine_similarity(list(pref.learned_vector), list(agent.interest_embedding))
                drift = round(max(0.0, min(2.0, 1.0 - sim)), 4)

            learned_topics = dict(pref.learned_topics or {})
            pref_summary = PreferenceAnalyticsSummary(
                learning_enabled=True,
                learning_version=pref.learning_version or 1,
                total_feedback_count=pref.total_feedback_count or 0,
                positive_interactions_count=pref.positive_interactions_count or 0,
                negative_interactions_count=pref.negative_interactions_count or 0,
                engagement_rate=round(pref.engagement_rate or 0.0, 4),
                drift_from_anchor=drift,
                top_positive_topics=list(learned_topics.get("top_positive", [])),
                top_negative_topics=list(learned_topics.get("top_negative", [])),
                last_updated_at=pref.last_updated_at,
            )

        return AgentAnalyticsOverview(
            agent_id=agent.id,
            agent_name=agent.name,
            company=agent.company,
            period_start=start_date,
            period_end=end_date,
            publisher=publisher_metrics,
            recipient=recipient_metrics,
            preferences=pref_summary,
            generated_at=now_utc,
        )

    async def get_agent_activity(
        self,
        db: AsyncSession,
        agent: Agent,
        start_date: datetime,
        end_date: datetime,
    ) -> AgentActivityResponse:
        """
        Computes date-bucketed daily activity timeline for the authenticated agent.
        Returns continuous zero-filled daily buckets over the specified date range.
        """
        # Ensure UTC and normalize to date
        start_d = start_date.date() if isinstance(start_date, datetime) else start_date
        end_d = end_date.date() if isinstance(end_date, datetime) else end_date

        if end_d < start_d:
            raise ValueError(f"end_date ({end_d}) must be >= start_date ({start_d})")

        total_days = (end_d - start_d).days + 1
        if total_days > 90:
            raise ValueError("Activity timeline range cannot exceed 90 days")

        # Initialize continuous daily bucket map
        daily_map: dict[str, dict[str, int]] = {}
        for day_offset in range(total_days):
            current_day = start_d + timedelta(days=day_offset)
            daily_map[current_day.isoformat()] = {
                "posts_published": 0,
                "notifications_received": 0,
                "interactions_engaged": 0,
                "interactions_ignored": 0,
                "comments_written": 0,
                "comments_received": 0,
            }

        start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_d, datetime.max.time(), tzinfo=timezone.utc)

        # 1. Posts published daily
        posts_q = (
            select(
                cast(Post.created_at, Date).label("day"),
                func.count().label("cnt"),
            )
            .where(
                and_(
                    Post.author_agent_id == agent.id,
                    Post.status != "deleted",
                    Post.created_at >= start_dt,
                    Post.created_at <= end_dt,
                )
            )
            .group_by(cast(Post.created_at, Date))
        )
        for row in (await db.execute(posts_q)).all():
            day_str = str(row[0])
            if day_str in daily_map:
                daily_map[day_str]["posts_published"] = int(row[1])

        # 2. Notifications received daily
        notifs_q = (
            select(
                cast(Notification.created_at, Date).label("day"),
                func.count().label("cnt"),
            )
            .where(
                and_(
                    Notification.recipient_agent_id == agent.id,
                    Notification.created_at >= start_dt,
                    Notification.created_at <= end_dt,
                )
            )
            .group_by(cast(Notification.created_at, Date))
        )
        for row in (await db.execute(notifs_q)).all():
            day_str = str(row[0])
            if day_str in daily_map:
                daily_map[day_str]["notifications_received"] = int(row[1])

        # 3. Interactions daily (engaged & ignored)
        ints_q = (
            select(
                cast(AgentInteraction.created_at, Date).label("day"),
                AgentInteraction.status,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    AgentInteraction.receiving_agent_id == agent.id,
                    AgentInteraction.created_at >= start_dt,
                    AgentInteraction.created_at <= end_dt,
                )
            )
            .group_by(cast(AgentInteraction.created_at, Date), AgentInteraction.status)
        )
        for row in (await db.execute(ints_q)).all():
            day_str = str(row[0])
            status_val = str(row[1])
            count_val = int(row[2])
            if day_str in daily_map:
                if status_val == "engaged":
                    daily_map[day_str]["interactions_engaged"] = count_val
                elif status_val == "ignored":
                    daily_map[day_str]["interactions_ignored"] = count_val

        # 4. Comments written daily
        comm_w_q = (
            select(
                cast(Comment.created_at, Date).label("day"),
                func.count().label("cnt"),
            )
            .where(
                and_(
                    Comment.author_agent_id == agent.id,
                    Comment.created_at >= start_dt,
                    Comment.created_at <= end_dt,
                )
            )
            .group_by(cast(Comment.created_at, Date))
        )
        for row in (await db.execute(comm_w_q)).all():
            day_str = str(row[0])
            if day_str in daily_map:
                daily_map[day_str]["comments_written"] = int(row[1])

        # 5. Comments received on published posts daily
        comm_r_q = (
            select(
                cast(Comment.created_at, Date).label("day"),
                func.count().label("cnt"),
            )
            .select_from(Comment)
            .join(Post, Comment.post_id == Post.id)
            .where(
                and_(
                    Post.author_agent_id == agent.id,
                    Post.status != "deleted",
                    Comment.author_agent_id != agent.id,
                    Comment.created_at >= start_dt,
                    Comment.created_at <= end_dt,
                )
            )
            .group_by(cast(Comment.created_at, Date))
        )
        for row in (await db.execute(comm_r_q)).all():
            day_str = str(row[0])
            if day_str in daily_map:
                daily_map[day_str]["comments_received"] = int(row[1])

        buckets = [
            AgentActivityBucket(
                date=day_key,
                posts_published=data["posts_published"],
                notifications_received=data["notifications_received"],
                interactions_engaged=data["interactions_engaged"],
                interactions_ignored=data["interactions_ignored"],
                comments_written=data["comments_written"],
                comments_received=data["comments_received"],
            )
            for day_key, data in sorted(daily_map.items())
        ]

        return AgentActivityResponse(
            agent_id=agent.id,
            period_start=start_dt,
            period_end=end_dt,
            total_days=total_days,
            daily_activity=buckets,
        )

    async def get_agent_partners(
        self,
        db: AsyncSession,
        agent: Agent,
        limit: int = 10,
    ) -> AgentPartnershipInsights:
        """
        Extracts cross-company partnership insights based on actual interactions and comment exchanges.
        Strictly tenant-scoped: only computes aggregates for interactions involving the authenticated agent.
        """
        limit = max(1, min(50, limit))
        agent_primary_industries = [i.strip().lower() for i in (agent.industries or [])]

        # 1. Partner agents who authored posts this agent interacted with
        # Load interactions with post and author
        int_stmt = (
            select(
                AgentInteraction.status,
                Agent.company.label("partner_company"),
                Agent.industries.label("partner_industries"),
                Post.target_industries.label("target_industries"),
                Post.tags.label("post_tags"),
            )
            .select_from(AgentInteraction)
            .join(Post, AgentInteraction.post_id == Post.id)
            .join(Agent, Post.author_agent_id == Agent.id)
            .where(
                and_(
                    AgentInteraction.receiving_agent_id == agent.id,
                    Post.author_agent_id != agent.id,
                )
            )
        )
        interaction_rows = (await db.execute(int_stmt)).all()

        industry_stats: dict[str, dict[str, int]] = {}
        company_stats: dict[str, dict[str, int]] = {}
        category_counts: dict[str, int] = {}
        cross_industry_interactions = 0
        all_partner_identities: set[str] = set()

        for row in interaction_rows:
            int_status = row.status
            comp = row.partner_company or "Unknown"
            partner_inds = [i.strip().lower() for i in (row.partner_industries or []) if i.strip()]
            post_inds = [i.strip().lower() for i in (row.target_industries or []) if i.strip()]
            post_tags = [t.strip().lower() for t in (row.post_tags or []) if t.strip()]

            all_partner_identities.add(comp)

            # Check cross-industry
            if partner_inds and not (set(partner_inds) & set(agent_primary_industries)):
                cross_industry_interactions += 1

            # Company stats
            if comp not in company_stats:
                company_stats[comp] = {"interaction_count": 0, "engaged_count": 0, "comments_exchanged": 0}
            company_stats[comp]["interaction_count"] += 1
            if int_status == "engaged":
                company_stats[comp]["engaged_count"] += 1

            # Combine post and partner industries for industry insights
            combined_industries = set(partner_inds + post_inds)
            for ind in combined_industries:
                if ind not in industry_stats:
                    industry_stats[ind] = {"interaction_count": 0, "engaged_count": 0, "ignored_count": 0}
                industry_stats[ind]["interaction_count"] += 1
                if int_status == "engaged":
                    industry_stats[ind]["engaged_count"] += 1
                elif int_status == "ignored":
                    industry_stats[ind]["ignored_count"] += 1

            # Category / tag frequency
            for tag in post_tags:
                category_counts[tag] = category_counts.get(tag, 0) + 1

        # 2. Add comments received on this agent's posts (partner authors commenting)
        comm_rcvd_stmt = (
            select(
                Agent.company.label("partner_company"),
                Agent.industries.label("partner_industries"),
            )
            .select_from(Comment)
            .join(Post, Comment.post_id == Post.id)
            .join(Agent, Comment.author_agent_id == Agent.id)
            .where(
                and_(
                    Post.author_agent_id == agent.id,
                    Comment.author_agent_id != agent.id,
                )
            )
        )
        comment_partner_rows = (await db.execute(comm_rcvd_stmt)).all()

        for row in comment_partner_rows:
            comp = row.partner_company or "Unknown"
            all_partner_identities.add(comp)
            if comp not in company_stats:
                company_stats[comp] = {"interaction_count": 0, "engaged_count": 0, "comments_exchanged": 0}
            company_stats[comp]["comments_exchanged"] += 1

            for ind in (row.partner_industries or []):
                clean_ind = ind.strip().lower()
                if clean_ind not in industry_stats:
                    industry_stats[clean_ind] = {"interaction_count": 0, "engaged_count": 0, "ignored_count": 0}

        # Build sorted list of PartnerIndustryInsight
        partner_industries: list[PartnerIndustryInsight] = []
        for ind, stats in sorted(
            industry_stats.items(), key=lambda item: item[1]["interaction_count"], reverse=True
        )[:limit]:
            tot = stats["interaction_count"]
            eng = stats["engaged_count"]
            ign = stats["ignored_count"]
            rate = round(eng / tot, 4) if tot > 0 else 0.0
            partner_industries.append(
                PartnerIndustryInsight(
                    industry=ind,
                    interaction_count=tot,
                    engaged_count=eng,
                    ignored_count=ign,
                    engagement_rate=rate,
                )
            )

        # Build sorted list of PartnerCompanyInsight
        partner_companies: list[PartnerCompanyInsight] = []
        for comp, stats in sorted(
            company_stats.items(), key=lambda item: item[1]["interaction_count"], reverse=True
        )[:limit]:
            partner_companies.append(
                PartnerCompanyInsight(
                    company=comp,
                    interaction_count=stats["interaction_count"],
                    engaged_count=stats["engaged_count"],
                    comments_exchanged=stats["comments_exchanged"],
                )
            )

        # Build sorted categories
        top_categories = [
            {"category": k, "frequency": v}
            for k, v in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

        return AgentPartnershipInsights(
            agent_id=agent.id,
            primary_industries=agent_primary_industries,
            top_partner_industries=partner_industries,
            top_partner_companies=partner_companies,
            top_partner_categories=top_categories,
            cross_industry_interactions_count=cross_industry_interactions,
            total_partners_count=len(all_partner_identities),
            generated_at=datetime.now(timezone.utc),
        )


_analytics_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
