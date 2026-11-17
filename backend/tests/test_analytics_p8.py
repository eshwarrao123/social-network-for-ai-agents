"""
Unit and integration test suite for P8: Advanced Agent Analytics, Network Intelligence & Operational Observability.
Tests tenant isolation, metric accuracy, zero-division protection, soft-delete semantics,
cross-company partnership intelligence, zero-vector disclosure, and liveness/readiness probes.
"""
from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.interaction import AgentInteraction
from app.models.notification import Notification
from app.models.post import Post
from app.models.preference import AgentPreference
from app.schemas.analytics import (
    AgentActivityResponse,
    AgentAnalyticsOverview,
    AgentPartnershipInsights,
    PublisherMetrics,
    RecipientMetrics,
    SystemMetricsResponse,
    SystemReadinessResponse,
)
from app.services.analytics_service import AnalyticsService, get_analytics_service
from app.services.preference_service import normalize_vector


# ─────────────────────────────────────────────────────────────────────────────
# Test Helpers & Deterministic Factories
# ─────────────────────────────────────────────────────────────────────────────

def make_unit_vector(seed_val: float = 1.0, dim: int = 768) -> list[float]:
    v = [math.sin(seed_val + i * 0.1) for i in range(dim)]
    return normalize_vector(v)


def make_test_agent(
    agent_id: uuid.UUID | None = None,
    name: str = "AnalyticsTestAgent",
    company: str = "ApexAnalytics Corp",
    is_active: bool = True,
    industries: list[str] | None = None,
) -> Agent:
    agent = Agent()
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.description = "Agent specialized in real-time liquidity analytics and cross-border risk models."
    agent.industries = industries or ["fintech", "banking"]
    agent.tags = ["liquidity", "derivatives"]
    agent.capabilities = ["risk-modeling"]
    agent.trust_score = 0.95
    agent.is_active = is_active
    agent.interest_embedding = make_unit_vector(1.0)
    agent.embedding_status = "completed"
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


# ─────────────────────────────────────────────────────────────────────────────
# 1. Overview Analytics & Exact Formula Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_analytics_overview_zero_activity_agent():
    """
    P8-1: An agent with zero historical activity returns all zero metrics cleanly
    without division-by-zero errors, null crashes, or 404s.
    """
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    # Mock empty returns for SQL aggregate executions
    # 1. post_stats: tuple of (total_all, total_non_deleted, active_count, expired_count, deleted_count)
    mock_post_stats = MagicMock()
    mock_post_stats.total_all = 0
    mock_post_stats.total_non_deleted = 0
    mock_post_stats.active_count = 0
    mock_post_stats.expired_count = 0
    mock_post_stats.deleted_count = 0

    mock_post_res = MagicMock()
    mock_post_res.one.return_value = mock_post_stats

    # 2. total_notifications_sent scalar: 0
    mock_notif_sent_res = MagicMock()
    mock_notif_sent_res.scalar.return_value = 0

    # 3. delivered_notifications_sent scalar: 0
    mock_notif_dlv_res = MagicMock()
    mock_notif_dlv_res.scalar.return_value = 0

    # 4. total_comments_received scalar: 0
    mock_comm_rcvd_res = MagicMock()
    mock_comm_rcvd_res.scalar.return_value = 0

    # 5. notif_rcvd_stats: (total, delivered, read_cnt, pending_cnt, failed_cnt)
    mock_notif_stats = MagicMock()
    mock_notif_stats.total = 0
    mock_notif_stats.delivered = 0
    mock_notif_stats.read_cnt = 0
    mock_notif_stats.pending_cnt = 0
    mock_notif_stats.failed_cnt = 0

    mock_notif_rcvd_res = MagicMock()
    mock_notif_rcvd_res.one.return_value = mock_notif_stats

    # 6. int_stats: (total, engaged, ignored, pending_int, failed_int)
    mock_int_stats = MagicMock()
    mock_int_stats.total = 0
    mock_int_stats.engaged = 0
    mock_int_stats.ignored = 0
    mock_int_stats.pending_int = 0
    mock_int_stats.failed_int = 0

    mock_int_res = MagicMock()
    mock_int_res.one.return_value = mock_int_stats

    # 7. comments_written scalar: 0
    mock_comm_w_res = MagicMock()
    mock_comm_w_res.scalar.return_value = 0

    # 8. preference query: None
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [
        mock_post_res,
        mock_notif_sent_res,
        mock_notif_dlv_res,
        mock_comm_rcvd_res,
        mock_notif_rcvd_res,
        mock_int_res,
        mock_comm_w_res,
        mock_pref_res,
    ]

    overview = await service.get_agent_overview(mock_db, agent)

    assert overview.agent_id == agent.id
    assert overview.publisher.total_posts_published == 0
    assert overview.publisher.publisher_comment_conversion == 0.0
    assert overview.recipient.total_notifications_received == 0
    assert overview.recipient.recipient_response_rate == 0.0
    assert overview.preferences is None


@pytest.mark.unit
async def test_analytics_overview_active_metrics_and_exact_formulas():
    """
    P8-2: Verifies accurate mathematical computation for publisher comment conversion
    and recipient response rate against populated mock data.
    """
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    # Publisher:
    # 10 published non-deleted posts (7 active, 2 expired, 1 soft-deleted reported under deleted)
    mock_post_stats = MagicMock()
    mock_post_stats.total_all = 11
    mock_post_stats.total_non_deleted = 10
    mock_post_stats.active_count = 7
    mock_post_stats.expired_count = 2
    mock_post_stats.deleted_count = 1

    mock_post_res = MagicMock()
    mock_post_res.one.return_value = mock_post_stats

    # 50 notifications generated for agent's published posts
    mock_notif_sent_res = MagicMock()
    mock_notif_sent_res.scalar.return_value = 50

    # 40 notifications delivered/read for published posts
    mock_notif_dlv_res = MagicMock()
    mock_notif_dlv_res.scalar.return_value = 40

    # 10 comments received from other agents on published posts
    mock_comm_rcvd_res = MagicMock()
    mock_comm_rcvd_res.scalar.return_value = 10

    # Recipient:
    # 20 notifications received (15 delivered, 10 read, 3 pending, 2 failed)
    mock_notif_stats = MagicMock()
    mock_notif_stats.total = 20
    mock_notif_stats.delivered = 15
    mock_notif_stats.read_cnt = 10
    mock_notif_stats.pending_cnt = 3
    mock_notif_stats.failed_cnt = 2

    mock_notif_rcvd_res = MagicMock()
    mock_notif_rcvd_res.one.return_value = mock_notif_stats

    # 8 autonomous interactions evaluated (6 engaged, 2 ignored, 0 pending, 0 failed)
    mock_int_stats = MagicMock()
    mock_int_stats.total = 8
    mock_int_stats.engaged = 6
    mock_int_stats.ignored = 2
    mock_int_stats.pending_int = 0
    mock_int_stats.failed_int = 0

    mock_int_res = MagicMock()
    mock_int_res.one.return_value = mock_int_stats

    # 5 comments written by this agent
    mock_comm_w_res = MagicMock()
    mock_comm_w_res.scalar.return_value = 5

    # Preference attached with known drift
    learned_v = make_unit_vector(2.0)
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=learned_v,
        learning_version=3,
        total_feedback_count=20,
        positive_interactions_count=15,
        negative_interactions_count=5,
        engagement_rate=0.75,
        learned_topics={
            "top_positive": ["fintech", "arbitrage"],
            "top_negative": ["crypto"],
        },
        last_updated_at=datetime.now(timezone.utc),
    )
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = pref

    mock_db.execute.side_effect = [
        mock_post_res,
        mock_notif_sent_res,
        mock_notif_dlv_res,
        mock_comm_rcvd_res,
        mock_notif_rcvd_res,
        mock_int_res,
        mock_comm_w_res,
        mock_pref_res,
    ]

    overview = await service.get_agent_overview(mock_db, agent)

    # Publisher formula verification:
    # publisher_comment_conversion = 10 comments received / 50 notifications sent = 0.2000 (20%)
    # delivered_comment_conversion = 10 comments received / 40 delivered notifications = 0.2500 (25%)
    assert overview.publisher.total_posts_published == 10
    assert overview.publisher.active_posts_count == 7
    assert overview.publisher.expired_posts_count == 2
    assert overview.publisher.deleted_posts_count == 1
    assert overview.publisher.total_notifications_sent == 50
    assert overview.publisher.delivered_notifications_sent == 40
    assert overview.publisher.total_comments_received == 10
    assert math.isclose(overview.publisher.publisher_comment_conversion, 0.2000, rel_tol=1e-4)
    assert math.isclose(overview.publisher.delivered_comment_conversion, 0.2500, rel_tol=1e-4)

    # Recipient formula verification:
    # recipient_response_rate = 6 engaged interactions / 20 notifications received = 0.3000 (30%)
    assert overview.recipient.total_notifications_received == 20
    assert overview.recipient.delivered_notifications_count == 15
    assert overview.recipient.read_notifications_count == 10
    assert overview.recipient.pending_notifications_count == 3
    assert overview.recipient.failed_notifications_count == 2
    assert overview.recipient.total_interactions_evaluated == 8
    assert overview.recipient.interactions_engaged == 6
    assert overview.recipient.interactions_ignored == 2
    assert overview.recipient.comments_written == 5
    assert math.isclose(overview.recipient.recipient_response_rate, 0.3000, rel_tol=1e-4)

    # Preference summary verification (P7)
    assert overview.preferences is not None
    assert overview.preferences.learning_version == 3
    assert overview.preferences.total_feedback_count == 20
    assert overview.preferences.positive_interactions_count == 15
    assert overview.preferences.engagement_rate == 0.75
    assert overview.preferences.top_positive_topics == ["fintech", "arbitrage"]
    assert overview.preferences.top_negative_topics == ["crypto"]
    assert overview.preferences.drift_from_anchor >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Activity Timeline & Continuous Date Series Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_analytics_activity_trend_zero_filled_timeline():
    """
    P8-3: Activity timeline produces continuous zero-filled daily buckets across
    the requested date range, filling in calendar days with zero activity.
    """
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    start_date = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 11, 14, 23, 59, 59, tzinfo=timezone.utc)

    # Simulate activity on 2026-11-11 only:
    # 2 posts published
    mock_posts_res = MagicMock()
    mock_posts_res.all.return_value = [(date(2026, 11, 11), 2)]

    # 5 notifications received on 2026-11-12
    mock_notifs_res = MagicMock()
    mock_notifs_res.all.return_value = [(date(2026, 11, 12), 5)]

    # 1 engaged interaction on 2026-11-12
    mock_ints_res = MagicMock()
    mock_ints_res.all.return_value = [(date(2026, 11, 12), "engaged", 1)]

    # 3 comments written on 2026-11-11
    mock_comm_w_res = MagicMock()
    mock_comm_w_res.all.return_value = [(date(2026, 11, 11), 3)]

    # 1 comment received on 2026-11-13
    mock_comm_r_res = MagicMock()
    mock_comm_r_res.all.return_value = [(date(2026, 11, 13), 1)]

    mock_db.execute.side_effect = [
        mock_posts_res,
        mock_notifs_res,
        mock_ints_res,
        mock_comm_w_res,
        mock_comm_r_res,
    ]

    response = await service.get_agent_activity(mock_db, agent, start_date, end_date)

    assert response.agent_id == agent.id
    assert response.total_days == 5  # Nov 10, 11, 12, 13, 14
    assert len(response.daily_activity) == 5

    buckets_by_date = {b.date: b for b in response.daily_activity}

    # Nov 10: Completely zero-filled
    assert buckets_by_date["2026-11-10"].posts_published == 0
    assert buckets_by_date["2026-11-10"].notifications_received == 0

    # Nov 11: 2 posts, 3 comments written
    assert buckets_by_date["2026-11-11"].posts_published == 2
    assert buckets_by_date["2026-11-11"].comments_written == 3

    # Nov 12: 5 notifications, 1 interaction engaged
    assert buckets_by_date["2026-11-12"].notifications_received == 5
    assert buckets_by_date["2026-11-12"].interactions_engaged == 1
    assert buckets_by_date["2026-11-12"].interactions_ignored == 0

    # Nov 13: 1 comment received
    assert buckets_by_date["2026-11-13"].comments_received == 1

    # Nov 14: Zero-filled
    assert buckets_by_date["2026-11-14"].posts_published == 0


@pytest.mark.unit
async def test_analytics_activity_trend_out_of_bounds_validation():
    """
    P8-4: Invalid date ranges (end before start, or range exceeding 90 days) raise ValueError.
    """
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    # 1. end_date < start_date
    with pytest.raises(ValueError, match="must be >="):
        await service.get_agent_activity(
            mock_db,
            agent,
            start_date=datetime(2026, 11, 15, tzinfo=timezone.utc),
            end_date=datetime(2026, 11, 10, tzinfo=timezone.utc),
        )

    # 2. range > 90 days
    with pytest.raises(ValueError, match="cannot exceed 90 days"):
        await service.get_agent_activity(
            mock_db,
            agent,
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cross-Company Network Intelligence Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_analytics_partners_cross_company_aggregation():
    """
    P8-5: Network intelligence aggregates top partner industries and partner companies
    accurately, detecting cross-industry interactions without hardcoded rules.
    """
    service = AnalyticsService()
    # Agent belongs to fintech & banking
    agent = make_test_agent(industries=["fintech", "banking"])
    mock_db = AsyncMock()

    # Mock interactions:
    # Interaction 1: Partner in 'healthcare' (cross-industry), company 'MedTech AI', engaged
    row1 = MagicMock()
    row1.status = "engaged"
    row1.partner_company = "MedTech AI"
    row1.partner_industries = ["healthcare"]
    row1.target_industries = ["healthcare"]
    row1.post_tags = ["telemedicine", "data-privacy"]

    # Interaction 2: Partner in 'healthcare', company 'MedTech AI', ignored
    row2 = MagicMock()
    row2.status = "ignored"
    row2.partner_company = "MedTech AI"
    row2.partner_industries = ["healthcare"]
    row2.target_industries = ["healthcare"]
    row2.post_tags = ["telemedicine"]

    # Interaction 3: Partner in 'banking' (intra-industry), company 'GlobalBank Corp', engaged
    row3 = MagicMock()
    row3.status = "engaged"
    row3.partner_company = "GlobalBank Corp"
    row3.partner_industries = ["banking"]
    row3.target_industries = ["banking"]
    row3.post_tags = ["liquidity"]

    mock_int_res = MagicMock()
    mock_int_res.all.return_value = [row1, row2, row3]

    # Mock comments received:
    # Comment from 'LogisticsAI' (cross-industry)
    comm_row = MagicMock()
    comm_row.partner_company = "LogisticsAI"
    comm_row.partner_industries = ["supply-chain"]

    mock_comm_res = MagicMock()
    mock_comm_res.all.return_value = [comm_row]

    mock_db.execute.side_effect = [mock_int_res, mock_comm_res]

    insights = await service.get_agent_partners(mock_db, agent, limit=10)

    assert insights.agent_id == agent.id
    assert insights.primary_industries == ["fintech", "banking"]

    # Cross-industry count: row1 and row2 are from 'healthcare' (not in agent's fintech/banking) -> 2
    assert insights.cross_industry_interactions_count == 2
    assert insights.total_partners_count == 3  # MedTech AI, GlobalBank Corp, LogisticsAI

    # Verify top partner industries
    ind_map = {pi.industry: pi for pi in insights.top_partner_industries}
    assert "healthcare" in ind_map
    assert ind_map["healthcare"].interaction_count == 2
    assert ind_map["healthcare"].engaged_count == 1
    assert ind_map["healthcare"].ignored_count == 1
    assert math.isclose(ind_map["healthcare"].engagement_rate, 0.5000, rel_tol=1e-4)

    assert "banking" in ind_map
    assert ind_map["banking"].interaction_count == 1
    assert ind_map["banking"].engaged_count == 1
    assert math.isclose(ind_map["banking"].engagement_rate, 1.0000, rel_tol=1e-4)

    # Verify partner companies
    comp_map = {pc.company: pc for pc in insights.top_partner_companies}
    assert "MedTech AI" in comp_map
    assert comp_map["MedTech AI"].interaction_count == 2
    assert comp_map["MedTech AI"].engaged_count == 1

    assert "LogisticsAI" in comp_map
    assert comp_map["LogisticsAI"].comments_exchanged == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. FastAPI Router Endpoints & Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_get_my_overview_endpoint_success(client: AsyncClient):
    """GET /api/v1/analytics/me/overview successfully returns tenant metrics."""
    agent = make_test_agent()
    overview_mock = AgentAnalyticsOverview(
        agent_id=agent.id,
        agent_name=agent.name,
        company=agent.company,
        publisher=PublisherMetrics(
            total_posts_published=5,
            active_posts_count=4,
            expired_posts_count=1,
            deleted_posts_count=0,
            total_notifications_sent=20,
            total_comments_received=4,
            publisher_comment_conversion=0.2000,
        ),
        recipient=RecipientMetrics(
            total_notifications_received=10,
            delivered_notifications_count=8,
            read_notifications_count=5,
            pending_notifications_count=2,
            failed_notifications_count=0,
            total_interactions_evaluated=4,
            interactions_engaged=2,
            interactions_ignored=2,
            comments_written=2,
            recipient_response_rate=0.2000,
        ),
        preferences=None,
        generated_at=datetime.now(timezone.utc),
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        with patch("app.routers.analytics.get_analytics_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_agent_overview = AsyncMock(return_value=overview_mock)
            mock_get_svc.return_value = mock_svc

            response = await client.get("/api/v1/analytics/me/overview")
            assert response.status_code == 200
            data = response.json()

            assert data["agent_id"] == str(agent.id)
            assert data["publisher"]["total_posts_published"] == 5
            assert data["publisher"]["publisher_comment_conversion"] == 0.2000
            assert data["recipient"]["total_notifications_received"] == 10
            assert data["recipient"]["recipient_response_rate"] == 0.2000
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_my_overview_endpoint_zero_vector_disclosure(client: AsyncClient):
    """
    P8-6: Zero-vector disclosure verification.
    Responses must never expose raw vector floats or embedding fields.
    """
    agent = make_test_agent()
    overview_mock = AgentAnalyticsOverview(
        agent_id=agent.id,
        agent_name=agent.name,
        company=agent.company,
        publisher=PublisherMetrics(),
        recipient=RecipientMetrics(),
        preferences=None,
        generated_at=datetime.now(timezone.utc),
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        with patch("app.routers.analytics.get_analytics_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_agent_overview = AsyncMock(return_value=overview_mock)
            mock_get_svc.return_value = mock_svc

            response = await client.get("/api/v1/analytics/me/overview")
            assert response.status_code == 200
            data = response.json()

            assert "learned_vector" not in data
            assert "interest_embedding" not in data
            assert "content_embedding" not in data
            for k, v in data.items():
                if isinstance(v, list) and v:
                    assert not isinstance(v[0], float), f"Vector leakage in field {k}"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_my_activity_endpoint_success(client: AsyncClient):
    """GET /api/v1/analytics/me/activity returns daily activity buckets."""
    agent = make_test_agent()
    now_utc = datetime.now(timezone.utc)
    activity_mock = AgentActivityResponse(
        agent_id=agent.id,
        period_start=now_utc - timedelta(days=5),
        period_end=now_utc,
        total_days=5,
        daily_activity=[],
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        with patch("app.routers.analytics.get_analytics_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_agent_activity = AsyncMock(return_value=activity_mock)
            mock_get_svc.return_value = mock_svc

            response = await client.get("/api/v1/analytics/me/activity")
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == str(agent.id)
            assert data["total_days"] == 5
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_my_partners_endpoint_success(client: AsyncClient):
    """GET /api/v1/analytics/me/partners returns partnership network insights."""
    agent = make_test_agent()
    partner_mock = AgentPartnershipInsights(
        agent_id=agent.id,
        primary_industries=["fintech"],
        top_partner_industries=[],
        top_partner_companies=[],
        top_partner_categories=[],
        cross_industry_interactions_count=0,
        total_partners_count=0,
        generated_at=datetime.now(timezone.utc),
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        with patch("app.routers.analytics.get_analytics_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_agent_partners = AsyncMock(return_value=partner_mock)
            mock_get_svc.return_value = mock_svc

            response = await client.get("/api/v1/analytics/me/partners?limit=5")
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == str(agent.id)
            assert data["primary_industries"] == ["fintech"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_analytics_endpoints_reject_unauthenticated(client: AsyncClient):
    """P8-7: Unauthenticated calls to analytics endpoints return 401 Unauthorized."""
    # Ensure no overrides are set
    res_overview = await client.get("/api/v1/analytics/me/overview")
    assert res_overview.status_code == 401

    res_activity = await client.get("/api/v1/analytics/me/activity")
    assert res_activity.status_code == 401

    res_partners = await client.get("/api/v1/analytics/me/partners")
    assert res_partners.status_code == 401


@pytest.mark.unit
async def test_analytics_endpoints_reject_inactive_agent(client: AsyncClient):
    """P8-8: Inactive or suspended agents are forbidden with 403."""
    inactive_agent = make_test_agent(is_active=False)

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_agent

    app.dependency_overrides[get_current_agent] = lambda: inactive_agent

    try:
        response = await client.get("/api/v1/analytics/me/overview")
        assert response.status_code == 403
        assert "inactive or has been suspended" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Operational Observability, Liveness & Readiness Probes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_system_liveness_probe(client: AsyncClient):
    """GET /health/live returns 200 OK indicating the API process is alive with correct product branding."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "social-network-for-ai-agents"
    assert "timestamp" in data


@pytest.mark.unit
async def test_system_readiness_probe_success(client: AsyncClient):
    """GET /health/ready returns 200 OK when DB, Redis, and Ollama are reachable."""
    mock_ollama_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_ollama_client.get.return_value = mock_res
    mock_ollama_client.__aenter__.return_value = mock_ollama_client

    with patch("app.database.AsyncSessionLocal") as mock_session_ctx, \
         patch("redis.asyncio.from_url") as mock_redis_cls, \
         patch("httpx.AsyncClient", return_value=mock_ollama_client):

        # 1. DB probe mock
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        # 2. Redis probe mock
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_cls.return_value = mock_redis

        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["redis"]["status"] == "ok"
        assert data["checks"]["ollama"]["status"] == "ok"
        # Confirm no credentials leaked
        assert "postgresql" not in str(data)
        assert "password" not in str(data)


@pytest.mark.unit
async def test_system_readiness_probe_database_unavailable(client: AsyncClient):
    """GET /health/ready returns 503 Service Unavailable when DB is down."""
    mock_ollama_client = AsyncMock()
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_ollama_client.get.return_value = mock_res
    mock_ollama_client.__aenter__.return_value = mock_ollama_client

    with patch("app.database.AsyncSessionLocal") as mock_session_ctx, \
         patch("redis.asyncio.from_url") as mock_redis_cls, \
         patch("httpx.AsyncClient", return_value=mock_ollama_client):

        # DB probe fails
        mock_session_ctx.return_value.__aenter__.side_effect = Exception("DB connection timeout")

        # Redis succeeds
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_cls.return_value = mock_redis

        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unready"
        assert data["checks"]["database"]["status"] == "unavailable"
        assert data["checks"]["redis"]["status"] == "ok"


@pytest.mark.unit
async def test_operational_metrics_ordinary_agent_forbidden(client: AsyncClient):
    """
    P8.1-1: Ordinary enterprise agents are strictly forbidden (HTTP 403) from obtaining
    unrestricted global system and pipeline operational metrics.
    """
    from app.services.auth import create_access_token
    agent = make_test_agent()
    token, _ = create_access_token(agent)

    response = await client.get(
        "/api/v1/analytics/system/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert "ordinary enterprise agents are not authorized" in data["detail"].lower()


@pytest.mark.unit
async def test_operational_metrics_unauthenticated_rejected(client: AsyncClient):
    """
    P8.1-1: Public unauthenticated requests to system metrics are rejected (HTTP 401).
    """
    response = await client.get("/api/v1/analytics/system/metrics")
    assert response.status_code == 401
    assert "Operator authentication required" in response.json()["detail"]


@pytest.mark.unit
async def test_operational_metrics_authorized_operator_token(client: AsyncClient):
    """
    P8.1-1: An authorized operator with a valid X-Operator-Token accesses metrics successfully.
    """
    from app.config import get_settings
    settings = get_settings()

    original_op_token = settings.operator_token
    settings.operator_token = "secure-operator-secret-token"

    try:
        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_redis = AsyncMock()
            mock_redis.xlen.return_value = 0
            mock_redis.xinfo_groups.return_value = []
            mock_redis_cls.return_value = mock_redis

            response = await client.get(
                "/api/v1/analytics/system/metrics",
                headers={"X-Operator-Token": "secure-operator-secret-token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "posts:embed" in data["stream_queues"]
    finally:
        settings.operator_token = original_op_token


@pytest.mark.unit
async def test_operational_metrics_endpoint_low_cardinality(client: AsyncClient):
    """
    P8.1-2: GET /api/v1/analytics/system/metrics accurately measures real streams
    (posts:embed, agents:embed, routing:pending, notifications:pending,
    agent-interactions:pending, agent-feedback:pending), differentiates retained XLEN
    from active group backlog (lag + pending), and maintains strictly low-cardinality keys.
    """
    from app.main import app
    from app.dependencies import verify_operator_or_internal_access

    app.dependency_overrides[verify_operator_or_internal_access] = lambda: None

    try:
        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_redis = AsyncMock()
            # Mock xlen for stream and dlq
            mock_redis.xlen.return_value = 42
            # Mock xinfo_groups returning pending and lag for specific group
            mock_redis.xinfo_groups.return_value = [
                {"name": "interaction-workers", "pending": 3, "lag": 5},
                {"name": "embed-workers", "pending": 2, "lag": 1},
                {"name": "routing-workers", "pending": 1, "lag": 0},
                {"name": "notify-workers", "pending": 4, "lag": 2},
                {"name": "feedback-workers", "pending": 0, "lag": 0},
            ]
            mock_redis_cls.return_value = mock_redis

            response = await client.get("/api/v1/analytics/system/metrics")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "ok"
            assert "agent-interactions:pending" in data["stream_queues"]
            assert "posts:embed" in data["stream_queues"]
            assert "agents:embed" in data["stream_queues"]
            assert "routing:pending" in data["stream_queues"]
            assert "notifications:pending" in data["stream_queues"]
            assert "agent-feedback:pending" in data["stream_queues"]

            # Confirm DLQ naming
            assert "agent-interactions:pending:dlq" in data["dead_letter_queues"]
            assert "posts:embed:dlq" in data["dead_letter_queues"]

            # Confirm breakdown separation
            assert "retained_stream_entries" in data
            assert "pending_worker_entries" in data
            assert "undelivered_lag" in data

            # Confirm no high-cardinality IDs leaked in keys
            all_keys = (
                list(data["stream_queues"].keys())
                + list(data["dead_letter_queues"].keys())
                + list(data["retained_stream_entries"].keys())
                + list(data["pending_worker_entries"].keys())
                + list(data["undelivered_lag"].keys())
            )
            for key in all_keys:
                assert not any(c in key for c in ["uuid", "user", "agent_", "post_"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_operational_metrics_redis_failure_handled_gracefully(client: AsyncClient):
    """When Redis is unavailable, metrics endpoint returns -1 queue depths without crashing."""
    from app.main import app
    from app.dependencies import verify_operator_or_internal_access

    app.dependency_overrides[verify_operator_or_internal_access] = lambda: None

    try:
        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_redis_cls.side_effect = Exception("Redis connection refused")

            response = await client.get("/api/v1/analytics/system/metrics")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["stream_queues"]["posts:embed"] == -1
            assert data["stream_queues"]["agent-interactions:pending"] == -1
            assert data["retained_stream_entries"]["posts:embed"] == -1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_publisher_and_recipient_delivered_metrics_formulas():
    """
    P8.1-3: Verify conversion and response rates under both sent/received and delivered denominators.
    """
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    # 1. Post stats: 10 published posts
    mock_post_stats = MagicMock()
    mock_post_stats.total_all = 10
    mock_post_stats.total_non_deleted = 10
    mock_post_stats.active_count = 8
    mock_post_stats.expired_count = 2
    mock_post_stats.deleted_count = 0
    mock_post_res = MagicMock()
    mock_post_res.one.return_value = mock_post_stats

    # 2. Total notifications sent: 100
    mock_notif_sent_res = MagicMock()
    mock_notif_sent_res.scalar.return_value = 100

    # 3. Delivered notifications sent: 80
    mock_notif_dlv_res = MagicMock()
    mock_notif_dlv_res.scalar.return_value = 80

    # 4. Total comments received: 20
    mock_comm_rcvd_res = MagicMock()
    mock_comm_rcvd_res.scalar.return_value = 20

    # 5. Recipient notifications: total 50, delivered 40, read 30, pending 8, failed 2
    mock_notif_rcvd_stats = MagicMock()
    mock_notif_rcvd_stats.total = 50
    mock_notif_rcvd_stats.delivered = 40
    mock_notif_rcvd_stats.read_cnt = 30
    mock_notif_rcvd_stats.pending_cnt = 8
    mock_notif_rcvd_stats.failed_cnt = 2
    mock_notif_rcvd_res = MagicMock()
    mock_notif_rcvd_res.one.return_value = mock_notif_rcvd_stats

    # 6. Recipient interactions: total 40, engaged 10, ignored 28, pending 1, failed 1
    mock_int_stats = MagicMock()
    mock_int_stats.total = 40
    mock_int_stats.engaged = 10
    mock_int_stats.ignored = 28
    mock_int_stats.pending_int = 1
    mock_int_stats.failed_int = 1
    mock_int_res = MagicMock()
    mock_int_res.one.return_value = mock_int_stats

    # 7. Comments written: 5
    mock_comm_w_res = MagicMock()
    mock_comm_w_res.scalar.return_value = 5

    # 8. Preference: None
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [
        mock_post_res,
        mock_notif_sent_res,
        mock_notif_dlv_res,
        mock_comm_rcvd_res,
        mock_notif_rcvd_res,
        mock_int_res,
        mock_comm_w_res,
        mock_pref_res,
    ]

    overview = await service.get_agent_overview(mock_db, agent)

    # Publisher conversions:
    # 20 comments / 100 sent = 0.20
    assert overview.publisher.total_notifications_sent == 100
    assert overview.publisher.delivered_notifications_sent == 80
    assert overview.publisher.total_comments_received == 20
    assert overview.publisher.publisher_comment_conversion == 0.20
    # 20 comments / 80 delivered = 0.25
    assert overview.publisher.delivered_comment_conversion == 0.25

    # Recipient response rates:
    # 10 engaged / 50 total received = 0.20
    assert overview.recipient.total_notifications_received == 50
    assert overview.recipient.delivered_notifications_count == 40
    assert overview.recipient.interactions_engaged == 10
    assert overview.recipient.interactions_ignored == 28
    assert overview.recipient.interactions_pending == 1
    assert overview.recipient.interactions_failed == 1
    assert overview.recipient.recipient_response_rate == 0.20
    # 10 engaged / 40 delivered = 0.25
    assert overview.recipient.delivered_response_rate == 0.25


@pytest.mark.unit
async def test_health_ready_ollama_disabled_state(client: AsyncClient):
    """
    P8.1-5: When LLM provider is disabled, /health/ready cleanly marks Ollama as disabled
    and reports system readiness as ready.
    """
    from app.config import get_settings
    settings = get_settings()

    original_provider = settings.llm_provider
    settings.llm_provider = "disabled"

    try:
        with patch("app.database.AsyncSessionLocal") as mock_session_ctx, \
             patch("redis.asyncio.from_url") as mock_redis_cls:

            mock_session = AsyncMock()
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis_cls.return_value = mock_redis

            response = await client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["service"] == "social-network-for-ai-agents"
            assert data["checks"]["ollama"]["status"] == "disabled"
            assert data["checks"]["database"]["status"] == "ok"
            assert data["checks"]["redis"]["status"] == "ok"
    finally:
        settings.llm_provider = original_provider


@pytest.mark.unit
async def test_analytics_overview_bad_date_range_rejected(client: AsyncClient):
    """Passing end_date < start_date to overview returns 400 Bad Request."""
    agent = make_test_agent()
    from app.main import app
    from app.dependencies import get_active_agent

    app.dependency_overrides[get_active_agent] = lambda: agent
    try:
        response = await client.get(
            "/api/v1/analytics/me/overview?start_date=2026-11-15T00:00:00Z&end_date=2026-11-10T00:00:00Z"
        )
        assert response.status_code == 400
        assert "end_date must be greater than or equal to start_date" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_analytics_partners_empty_interactions():
    """Agent with no interactions returns empty lists for partner aggregations."""
    service = AnalyticsService()
    agent = make_test_agent()
    mock_db = AsyncMock()

    mock_int_res = MagicMock()
    mock_int_res.all.return_value = []
    mock_comm_res = MagicMock()
    mock_comm_res.all.return_value = []
    mock_db.execute.side_effect = [mock_int_res, mock_comm_res]

    insights = await service.get_agent_partners(mock_db, agent, limit=10)
    assert insights.agent_id == agent.id
    assert insights.top_partner_industries == []
    assert insights.top_partner_companies == []
    assert insights.top_partner_categories == []
    assert insights.cross_industry_interactions_count == 0
    assert insights.total_partners_count == 0
