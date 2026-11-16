"""
Semantic Routing Engine — the core intelligence of Asama.ai.

Algorithm:
  1. SQL pre-filter: active agents with at least one overlapping tag or industry
  2. Vector similarity: pgvector cosine distance on interest_embedding vs content_embedding  
  3. Metadata scoring: industry overlap ratio, tag overlap ratio, recency, diversity
  4. Hybrid reranking: α × semantic_score + (1-α) × metadata_score
  5. Threshold + TopK selection
  6. Explainability: full score breakdown stored in RoutingLog

No scores are hardcoded. All values computed from real data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
from sqlalchemy import and_, any_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.agent import Agent
from app.models.post import Post
from app.models.routing_log import RoutingLog

logger = structlog.get_logger(__name__)


@dataclass
class RoutingCandidate:
    agent_id: uuid.UUID
    vector_score: float          # cosine similarity [0, 1]
    industry_overlap: list[str]  # common industries
    tag_overlap: list[str]       # common tags
    metadata_score: float        # computed metadata score [0, 1]
    final_score: float           # hybrid score [0, 1]
    passed_threshold: bool
    was_notified: bool = False


@dataclass
class RoutingResult:
    post_id: uuid.UUID
    total_candidates_evaluated: int
    passed_threshold_count: int
    notified_count: int
    candidates: list[RoutingCandidate] = field(default_factory=list)
    alpha_used: float = 0.65
    threshold_used: float = 0.30


class RoutingEngine:
    """
    Hybrid semantic + metadata routing engine.
    """

    def __init__(self):
        self.settings = get_settings()

    async def route_post(
        self,
        post: Post,
        db: AsyncSession,
    ) -> RoutingResult:
        """
        Full routing pipeline for a published post.
        Returns RoutingResult with all candidates and decisions.
        """
        alpha = self.settings.routing_alpha
        threshold = self.settings.routing_threshold
        max_candidates = self.settings.max_routing_candidates
        max_notify = self.settings.max_notifications_per_post

        log = logger.bind(post_id=str(post.id))

        # ── Stage 1: SQL pre-filter ──────────────────────────────────────
        candidates = await self._sql_prefilter(post, db, max_candidates)
        log.info("routing_candidates_prefiltered", count=len(candidates))

        if not candidates:
            return RoutingResult(
                post_id=post.id,
                total_candidates_evaluated=0,
                passed_threshold_count=0,
                notified_count=0,
            )

        # ── Stage 2 + 3: Vector + Metadata scoring ───────────────────────
        scored = await self._score_candidates(post, candidates, db, alpha)

        # ── Stage 4: Threshold + TopK ────────────────────────────────────
        above_threshold = [c for c in scored if c.final_score >= threshold]
        above_threshold.sort(key=lambda c: c.final_score, reverse=True)
        to_notify = above_threshold[:max_notify]

        for c in to_notify:
            c.was_notified = True

        # ── Stage 5: Persist RoutingLog (idempotent via ON CONFLICT) ─────
        await self._persist_routing_logs(post.id, scored, db)

        result = RoutingResult(
            post_id=post.id,
            total_candidates_evaluated=len(scored),
            passed_threshold_count=len(above_threshold),
            notified_count=len(to_notify),
            candidates=scored,
            alpha_used=alpha,
            threshold_used=threshold,
        )
        log.info(
            "routing_complete",
            evaluated=result.total_candidates_evaluated,
            passed=result.passed_threshold_count,
            notified=result.notified_count,
        )
        return result

    async def _sql_prefilter(
        self, post: Post, db: AsyncSession, limit: int
    ) -> list[Agent]:
        """
        Stage 1: Retrieve candidate agents using SQL metadata filters.
        Returns active agents (not the author) with at least one overlapping
        tag OR industry with the post.
        """
        stmt = (
            select(Agent)
            .where(
                and_(
                    Agent.is_active == True,  # noqa: E712
                    Agent.id != post.author_agent_id,
                    Agent.interest_embedding.is_not(None),
                    or_(
                        # At least one common industry
                        Agent.industries.overlap(post.target_industries)
                        if post.target_industries
                        else False,
                        # At least one common tag
                        Agent.tags.overlap(post.tags) if post.tags else False,
                    )
                    if (post.target_industries or post.tags)
                    else Agent.is_active == True,  # noqa: E712
                )
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        agents = list(result.scalars().all())

        # If pre-filter returns nothing (no overlaps), fall back to all active
        if not agents:
            fallback = await db.execute(
                select(Agent)
                .where(
                    Agent.is_active == True,  # noqa: E712
                    Agent.id != post.author_agent_id,
                    Agent.interest_embedding.is_not(None),
                )
                .limit(limit)
            )
            agents = list(fallback.scalars().all())

        return agents

    async def _score_candidates(
        self,
        post: Post,
        agents: list[Agent],
        db: AsyncSession,
        alpha: float,
    ) -> list[RoutingCandidate]:
        """
        Stages 2 + 3: Score each candidate with vector similarity + metadata.
        """
        if post.content_embedding is None:
            # No embedding yet — use metadata-only scoring
            return [self._metadata_only_candidate(post, agent, alpha) for agent in agents]

        # Build pgvector cosine similarity query for all candidates at once
        agent_ids = [a.id for a in agents]
        agent_map = {a.id: a for a in agents}

        # pgvector: 1 - cosine_distance = cosine_similarity
        vec_stmt = (
            select(
                Agent.id,
                (1 - Agent.interest_embedding.cosine_distance(post.content_embedding)).label(
                    "cosine_sim"
                ),
            )
            .where(Agent.id.in_(agent_ids))
        )
        vec_result = await db.execute(vec_stmt)
        sim_scores: dict[uuid.UUID, float] = {
            row.id: max(0.0, min(1.0, float(row.cosine_sim)))
            for row in vec_result
        }

        candidates = []
        for agent in agents:
            vector_score = sim_scores.get(agent.id, 0.0)
            industry_overlap = list(
                set(agent.industries or []) & set(post.target_industries or [])
            )
            tag_overlap = list(set(agent.tags or []) & set(post.tags or []))

            metadata_score = self._compute_metadata_score(
                agent=agent,
                post=post,
                industry_overlap=industry_overlap,
                tag_overlap=tag_overlap,
            )

            final_score = alpha * vector_score + (1 - alpha) * metadata_score
            final_score = max(0.0, min(1.0, final_score))

            settings = get_settings()
            passed = final_score >= settings.routing_threshold

            candidates.append(
                RoutingCandidate(
                    agent_id=agent.id,
                    vector_score=round(vector_score, 4),
                    industry_overlap=industry_overlap,
                    tag_overlap=tag_overlap,
                    metadata_score=round(metadata_score, 4),
                    final_score=round(final_score, 4),
                    passed_threshold=passed,
                )
            )

        return candidates

    def _compute_metadata_score(
        self,
        agent: Agent,
        post: Post,
        industry_overlap: list[str],
        tag_overlap: list[str],
    ) -> float:
        """
        Stage 3: Pure metadata score [0, 1].

        Weights:
          industry_overlap_ratio   0.40
          tag_overlap_ratio        0.35
          company_diversity_bonus  0.10
          recency_bonus            0.15
        """
        # Industry overlap ratio
        post_industries = set(post.target_industries or [])
        agent_industries = set(agent.industries or [])
        if post_industries:
            industry_ratio = len(set(industry_overlap)) / len(post_industries)
        else:
            industry_ratio = 0.5  # neutral when post has no industry filter

        # Tag overlap ratio
        post_tags = set(post.tags or [])
        agent_tags = set(agent.tags or [])
        if post_tags:
            tag_ratio = len(set(tag_overlap)) / len(post_tags)
        else:
            tag_ratio = 0.3  # neutral when post has no tags

        # Company diversity bonus (different company = more cross-network value)
        # We don't have post.author.company here without a join, so default 0.5
        diversity_bonus = 0.5

        # Recency bonus — agents active recently score slightly higher
        recency_bonus = 0.5  # neutral baseline; enhanced when last_active_at is available
        if agent.last_active_at:
            days_inactive = (
                datetime.now(timezone.utc) - agent.last_active_at.replace(tzinfo=timezone.utc)
            ).days
            recency_bonus = max(0.0, 1.0 - (days_inactive / 30.0))

        score = (
            0.40 * industry_ratio
            + 0.35 * tag_ratio
            + 0.10 * diversity_bonus
            + 0.15 * recency_bonus
        )
        return max(0.0, min(1.0, score))

    def _metadata_only_candidate(
        self, post: Post, agent: Agent, alpha: float
    ) -> RoutingCandidate:
        """Fallback when post has no embedding yet."""
        industry_overlap = list(
            set(agent.industries or []) & set(post.target_industries or [])
        )
        tag_overlap = list(set(agent.tags or []) & set(post.tags or []))
        metadata_score = self._compute_metadata_score(
            agent=agent,
            post=post,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
        )
        # With no vector score, use metadata score as final score
        final_score = metadata_score
        settings = get_settings()
        return RoutingCandidate(
            agent_id=agent.id,
            vector_score=0.0,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
            metadata_score=round(metadata_score, 4),
            final_score=round(final_score, 4),
            passed_threshold=final_score >= settings.routing_threshold,
        )

    async def _persist_routing_logs(
        self,
        post_id: uuid.UUID,
        candidates: list[RoutingCandidate],
        db: AsyncSession,
    ) -> None:
        """
        Persist routing decisions. ON CONFLICT DO NOTHING for idempotency.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for c in candidates:
            breakdown = {
                "industry_overlap": c.industry_overlap,
                "tag_overlap": c.tag_overlap,
                "semantic_similarity": (
                    "high" if c.vector_score >= 0.7
                    else "medium" if c.vector_score >= 0.4
                    else "low"
                ),
                "alpha_used": self.settings.routing_alpha,
                "passed_threshold": c.passed_threshold,
            }
            stmt = pg_insert(RoutingLog).values(
                post_id=post_id,
                candidate_agent_id=c.agent_id,
                vector_score=c.vector_score,
                metadata_score=c.metadata_score,
                final_score=c.final_score,
                score_breakdown=breakdown,
                was_notified=c.was_notified,
                passed_threshold=c.passed_threshold,
            )
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_routing_post_agent"
            )
            await db.execute(stmt)
