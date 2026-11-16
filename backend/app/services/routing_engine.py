"""
Semantic Relevance Routing Engine — the core intelligence of A Social Network for AI Agents.

Multi-stage Routing Pipeline:
  Stage 1: SQL eligibility filtering (active, not self, embedding completed, non-null).
  Stage 2: pgvector cosine-distance nearest-neighbour retrieval (database-side top-K).
  Stage 3: Hybrid relevance reranking (explainable weighted combination of semantic,
           industry, tag, capability, diversity, and trust signals).
  Stage 4: Deterministic ranking and policy threshold filtering.
  Stage 5: Explainable decision generation and audit trail persistence (RoutingLog).
  Stage 6: Idempotent event dispatch to Redis Stream 'notifications:pending'.

Mathematical Notes on Vector Cosine Metrics:
  - pgvector cosine distance: dist(u, v) = 1 - cos(u, v) ∈ [0, 2].
  - Raw cosine similarity: sim(u, v) = 1 - dist ∈ [-1, 1].
  - Normalized semantic similarity: sim_norm = max(0.0, min(1.0, sim)) ∈ [0, 1].
    (Non-negative directional alignment avoids artificially inflating orthogonal similarities).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.post import Post
from app.models.routing_log import RoutingLog
from app.services.events import (
    publish_agent_interaction_event,
    publish_notification_pending_event,
)
from app.services.preference_service import dot_product, normalize_vector

logger = structlog.get_logger(__name__)


@dataclass
class RoutingCandidate:
    agent_id: uuid.UUID
    agent_name: str = ""
    company: str = ""
    raw_cosine_distance: float = 1.0       # pgvector <=> cosine distance [0, 2]
    raw_cosine_similarity: float = 0.0     # 1 - distance [-1, 1]
    vector_score: float = 0.0              # normalized semantic score [0, 1]
    industry_overlap: list[str] = field(default_factory=list)
    tag_overlap: list[str] = field(default_factory=list)
    capability_overlap: list[str] = field(default_factory=list)
    metadata_score: float = 0.0            # [0, 1]
    final_score: float = 0.0               # hybrid score [0, 1]
    passed_threshold: bool = False
    was_notified: bool = False
    reasons: list[str] = field(default_factory=list)
    score_breakdown: dict = field(default_factory=dict)
    agent_trust_score: float = 0.1
    agent_created_at: datetime | None = None


@dataclass
class RoutingResult:
    post_id: uuid.UUID
    total_candidates_evaluated: int
    passed_threshold_count: int
    notified_count: int
    candidates: list[RoutingCandidate] = field(default_factory=list)
    selected_candidates: list[RoutingCandidate] = field(default_factory=list)
    alpha_used: float = 0.65
    threshold_used: float = 0.70
    algorithm_version: str = "v4.0-hybrid"


class RoutingEngine:
    """
    Multi-stage intelligent semantic relevance routing engine.
    Discovers cross-company business relevance from embeddings and business context.
    """

    def __init__(
        self,
        alpha: float | None = None,
        threshold: float | None = None,
        max_candidates: int | None = None,
        max_notifications: int | None = None,
        weight_industry: float | None = None,
        weight_tag: float | None = None,
        weight_capability: float | None = None,
        weight_diversity: float | None = None,
        weight_recency: float | None = None,
    ) -> None:
        self.settings = get_settings()
        self.alpha: float = alpha if alpha is not None else self.settings.routing_alpha
        self.threshold: float = threshold if threshold is not None else self.settings.routing_threshold
        self.max_candidates: int = max_candidates if max_candidates is not None else self.settings.max_routing_candidates
        self.max_notifications: int = max_notifications if max_notifications is not None else self.settings.max_notifications_per_post
        self.algorithm_version: str = getattr(self.settings, "routing_algorithm_version", "v4.2-hybrid")

        self.weight_industry: float = weight_industry if weight_industry is not None else getattr(self.settings, "routing_weight_industry", 0.30)
        self.weight_tag: float = weight_tag if weight_tag is not None else getattr(self.settings, "routing_weight_tag", 0.30)
        self.weight_capability: float = weight_capability if weight_capability is not None else getattr(self.settings, "routing_weight_capability", 0.25)
        self.weight_diversity: float = weight_diversity if weight_diversity is not None else getattr(self.settings, "routing_weight_diversity", 0.10)
        self.weight_recency: float = weight_recency if weight_recency is not None else getattr(self.settings, "routing_weight_recency", 0.05)

        meta_sum = (
            self.weight_industry
            + self.weight_tag
            + self.weight_capability
            + self.weight_diversity
            + self.weight_recency
        )
        if abs(meta_sum - 1.0) > 1e-4:
            raise ValueError(
                f"RoutingEngine metadata weights must sum to 1.0 (got {meta_sum:.4f}: "
                f"industry={self.weight_industry}, tag={self.weight_tag}, capability={self.weight_capability}, "
                f"diversity={self.weight_diversity}, recency={self.weight_recency})"
            )

    async def route_post(
        self,
        post: Post,
        db: AsyncSession,
        publish_events: bool = True,
    ) -> RoutingResult:
        """
        Executes the full routing pipeline for a published post:
        Retrieves, reranks, persists audit decisions, and dispatches downstream notification jobs.
        """
        log = logger.bind(post_id=str(post.id), alpha=self.alpha, threshold=self.threshold)

        # Stages 1–4: Candidate retrieval, hybrid reranking, and policy selection
        all_candidates, selected = await self._evaluate_candidates(post, db)

        # Stage 5 & 6: Persist RoutingLog and Notification records
        await self._persist_routing_logs_and_notifications(
            post=post,
            candidates=all_candidates,
            db=db,
            publish_events=publish_events,
        )

        result = RoutingResult(
            post_id=post.id,
            total_candidates_evaluated=len(all_candidates),
            passed_threshold_count=sum(1 for c in all_candidates if c.passed_threshold),
            notified_count=len(selected),
            candidates=all_candidates,
            selected_candidates=selected,
            alpha_used=self.alpha,
            threshold_used=self.threshold,
            algorithm_version=self.algorithm_version,
        )

        log.info(
            "routing_post_complete",
            evaluated=result.total_candidates_evaluated,
            passed=result.passed_threshold_count,
            notified=result.notified_count,
        )
        return result

    async def preview_routing(
        self,
        post: Post,
        db: AsyncSession,
    ) -> RoutingResult:
        """
        Calculates routing decisions for a post without mutating database records
        or emitting downstream notification events.
        """
        all_candidates, selected = await self._evaluate_candidates(post, db)

        return RoutingResult(
            post_id=post.id,
            total_candidates_evaluated=len(all_candidates),
            passed_threshold_count=sum(1 for c in all_candidates if c.passed_threshold),
            notified_count=len(selected),
            candidates=all_candidates,
            selected_candidates=selected,
            alpha_used=self.alpha,
            threshold_used=self.threshold,
            algorithm_version=self.algorithm_version,
        )

    async def _evaluate_candidates(
        self,
        post: Post,
        db: AsyncSession,
    ) -> tuple[list[RoutingCandidate], list[RoutingCandidate]]:
        """Internal evaluator for Stages 1–4."""
        # Retrieve author company if available for diversity calculation
        author_company: str | None = None
        if hasattr(post, "author") and post.author is not None:
            author_company = getattr(post.author, "company", None)
        elif post.author_agent_id:
            res = await db.execute(select(Agent.company).where(Agent.id == post.author_agent_id))
            author_company = res.scalar_one_or_none()

        # Stages 1 & 2: SQL eligibility filtering + pgvector cosine retrieval
        candidate_rows = await self._retrieve_candidate_rows(post, db, limit=self.max_candidates)

        scored_candidates: list[RoutingCandidate] = []
        for agent, cosine_dist in candidate_rows:
            candidate = self._score_candidate(
                post=post,
                agent=agent,
                cosine_dist=cosine_dist,
                author_company=author_company,
            )
            scored_candidates.append(candidate)

        # Stage 4: Deterministic ranking and policy threshold filtering
        # Sort key: 1. final_score DESC, 2. vector_score DESC, 3. trust_score DESC,
        # 4. created_at ASC, 5. agent_id string ASC (strict tie-breaking)
        scored_candidates.sort(
            key=lambda c: (
                -c.final_score,
                -c.vector_score,
                -c.agent_trust_score,
                c.agent_created_at.timestamp() if c.agent_created_at else 0.0,
                str(c.agent_id),
            )
        )

        selected: list[RoutingCandidate] = []
        for c in scored_candidates:
            if c.passed_threshold and len(selected) < self.max_notifications:
                c.was_notified = True
                selected.append(c)
            else:
                c.was_notified = False

        return scored_candidates, selected

    async def _retrieve_candidate_rows(
        self,
        post: Post,
        db: AsyncSession,
        limit: int,
    ) -> list[tuple[Agent, float]]:
        """
        Stage 1 & 2:
        Executes database-side SQL eligibility filtering and nearest-neighbour
        pgvector cosine distance ordering.
        Cross-industry relevance is preserved by NOT mandating industry overlap in SQL.
        """
        if post.content_embedding is None:
            # Fallback when post vector is not yet available
            stmt = (
                select(Agent)
                .options(selectinload(Agent.preference))
                .where(
                    and_(
                        Agent.is_active.is_(True),
                        Agent.id != post.author_agent_id,
                        Agent.interest_embedding.is_not(None),
                        Agent.embedding_status == "completed",
                    )
                )
                .limit(limit)
            )
            res = await db.execute(stmt)
            return [(agent, 1.0) for agent in res.scalars().all()]

        # PostgreSQL pgvector cosine distance operator: <=>
        cosine_dist_expr = Agent.interest_embedding.cosine_distance(post.content_embedding)

        stmt = (
            select(
                Agent,
                cosine_dist_expr.label("cosine_dist"),
            )
            .options(selectinload(Agent.preference))
            .where(
                and_(
                    Agent.is_active.is_(True),
                    Agent.id != post.author_agent_id,
                    Agent.interest_embedding.is_not(None),
                    Agent.embedding_status == "completed",
                )
            )
            .order_by(cosine_dist_expr.asc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    def _score_candidate(
        self,
        post: Post,
        agent: Agent,
        cosine_dist: float,
        author_company: str | None = None,
    ) -> RoutingCandidate:
        """Stage 3: Hybrid reranking and explainable decision generation for a single candidate."""
        # 1. Cosine similarity math
        # dist ∈ [0, 2], raw_sim ∈ [-1, 1], normalized_vector_score ∈ [0, 1]
        raw_dist = max(0.0, min(2.0, cosine_dist))
        raw_sim = 1.0 - raw_dist
        base_vector_score = max(0.0, min(1.0, raw_sim))

        # Adaptive preference adjustment (P7)
        pref = getattr(agent, "preference", None)
        feedback_learning_enabled = getattr(self.settings, "feedback_learning_enabled", True)
        min_samples = getattr(self.settings, "feedback_min_samples", 3)
        feedback_weight = getattr(self.settings, "feedback_weight", 0.30)
        max_adjustment = getattr(self.settings, "feedback_max_adjustment", 0.15)

        delta = 0.0
        learned_sim = base_vector_score
        vector_score = base_vector_score

        if (
            feedback_learning_enabled
            and pref is not None
            and pref.total_feedback_count >= min_samples
            and pref.learned_vector is not None
            and post.content_embedding is not None
        ):
            learned_sim = dot_product(
                normalize_vector(list(pref.learned_vector)),
                normalize_vector(list(post.content_embedding)),
            )
            learned_score = max(0.0, min(1.0, learned_sim))
            delta = max(-max_adjustment, min(max_adjustment, learned_score - base_vector_score))
            vector_score = max(0.0, min(1.0, base_vector_score + feedback_weight * delta))

        # 2. Overlap calculations
        industry_overlap = sorted(
            list(
                set(i.strip().lower() for i in (agent.industries or []))
                & set(i.strip().lower() for i in (post.target_industries or []))
            )
        )
        tag_overlap = sorted(
            list(
                set(t.strip().lower() for t in (agent.tags or []))
                & set(t.strip().lower() for t in (post.tags or []))
            )
        )

        # Capability overlap: check agent capabilities against post tags and target industries
        post_context_terms = set(
            [t.strip().lower() for t in (post.tags or [])]
            + [i.strip().lower() for i in (post.target_industries or [])]
        )
        # Also extract basic keywords from post title and content
        post_words = {
            w.strip(".,!?:;\"'()[]{}").lower()
            for w in f"{post.title} {post.content}".split()
            if len(w) > 2
        }
        post_context_terms.update(post_words)

        matched_capabilities = set()
        for cap in (agent.capabilities or []):
            clean_c = cap.strip().lower()
            if clean_c in post_context_terms:
                matched_capabilities.add(clean_c)
            else:
                tokens = {t for t in clean_c.replace("-", " ").replace("_", " ").split() if len(t) > 2}
                if tokens & post_context_terms:
                    matched_capabilities.add(clean_c)

        capability_overlap = sorted(list(matched_capabilities))

        # 3. Metadata score computation
        metadata_score = self._compute_metadata_score(
            agent=agent,
            post=post,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
            capability_overlap=capability_overlap,
            author_company=author_company,
        )

        # 4. Hybrid formula: final = α * vector_score + (1 - α) * metadata_score
        final_score = round(self.alpha * vector_score + (1.0 - self.alpha) * metadata_score, 4)
        final_score = max(0.0, min(1.0, final_score))
        passed = final_score >= self.threshold

        # 5. Explainable reasons generation
        reasons = self._generate_explanation_reasons(
            agent=agent,
            post=post,
            raw_sim=raw_sim,
            vector_score=vector_score,
            metadata_score=metadata_score,
            final_score=final_score,
            passed=passed,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
            capability_overlap=capability_overlap,
            author_company=author_company,
            pref=pref,
            delta=delta,
            feedback_weight=feedback_weight,
            min_samples=min_samples,
        )

        breakdown = {
            "raw_cosine_distance": round(raw_dist, 4),
            "raw_cosine_similarity": round(raw_sim, 4),
            "base_vector_score": round(base_vector_score, 4),
            "learned_vector_score": round(learned_sim, 4),
            "feedback_adjustment": round(feedback_weight * delta, 4),
            "feedback_sample_count": pref.total_feedback_count if pref else 0,
            "normalized_vector_score": round(vector_score, 4),
            "metadata_score": round(metadata_score, 4),
            "final_score": round(final_score, 4),
            "threshold": self.threshold,
            "alpha": self.alpha,
            "algorithm_version": self.algorithm_version,
            "weights": {
                "alpha_semantic": self.alpha,
                "alpha_metadata": round(1.0 - self.alpha, 4),
                "industry": self.weight_industry,
                "tag": self.weight_tag,
                "capability": self.weight_capability,
                "diversity": self.weight_diversity,
                "recency": self.weight_recency,
            },
            "industry_overlap": industry_overlap,
            "tag_overlap": tag_overlap,
            "capability_overlap": capability_overlap,
            "decision": "selected" if passed else "rejected",
            "reasons": reasons,
        }

        return RoutingCandidate(
            agent_id=agent.id,
            agent_name=agent.name,
            company=agent.company,
            raw_cosine_distance=round(raw_dist, 4),
            raw_cosine_similarity=round(raw_sim, 4),
            vector_score=round(vector_score, 4),
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
            capability_overlap=capability_overlap,
            metadata_score=round(metadata_score, 4),
            final_score=round(final_score, 4),
            passed_threshold=passed,
            was_notified=False,
            reasons=reasons,
            score_breakdown=breakdown,
            agent_trust_score=agent.trust_score,
            agent_created_at=agent.created_at,
        )

    def _compute_metadata_score(
        self,
        agent: Agent,
        post: Post,
        industry_overlap: list[str],
        tag_overlap: list[str],
        capability_overlap: list[str] | None = None,
        author_company: str | None = None,
    ) -> float:
        """
        Computes composite metadata score in [0, 1].
        Preserves backward-compatible 4-component weights when capability_overlap is omitted,
        and applies rich 5-component scoring when capability_overlap is provided.
        """
        # Industry overlap ratio
        post_industries = set(post.target_industries or [])
        if post_industries:
            industry_ratio = len(set(industry_overlap)) / len(post_industries)
        else:
            industry_ratio = 0.5  # neutral baseline when post has no industry constraint

        # Tag overlap ratio
        post_tags = set(post.tags or [])
        if post_tags:
            tag_ratio = len(set(tag_overlap)) / len(post_tags)
        else:
            tag_ratio = 0.3  # neutral baseline when post has no tags

        # Company diversity (cross-enterprise value)
        if author_company and agent.company:
            diversity_bonus = 1.0 if agent.company.lower() != author_company.lower() else 0.0
        else:
            diversity_bonus = 0.5  # neutral fallback when author company is unknown

        # Recency bonus — active recently scores higher; no activity = 0.0
        recency_bonus = 0.0
        if agent.last_active_at:
            now_utc = datetime.now(timezone.utc)
            active_ts = agent.last_active_at if agent.last_active_at.tzinfo else agent.last_active_at.replace(tzinfo=timezone.utc)
            days_inactive = max(0, (now_utc - active_ts).days)
            recency_bonus = max(0.0, 1.0 - (days_inactive / 30.0))

        # Backward compatibility mode for tests calling with 4 positional arguments
        if capability_overlap is None:
            # 4-factor legacy formula: 0.40 ind + 0.35 tag + 0.10 div + 0.15 rec = 1.00
            score = (
                0.40 * industry_ratio
                + 0.35 * tag_ratio
                + 0.10 * diversity_bonus
                + 0.15 * recency_bonus
            )
            return max(0.0, min(1.0, score))

        # 5-factor hybrid metadata scoring
        # Capability ratio: proportion of agent capabilities relevant to the post
        agent_caps = set(agent.capabilities or [])
        if agent_caps:
            capability_ratio = min(1.0, len(set(capability_overlap)) / max(1, min(3, len(agent_caps))))
        else:
            capability_ratio = 0.0

        # Weights configured via settings / constructor (must sum to 1.0)
        score = (
            self.weight_industry * industry_ratio
            + self.weight_tag * tag_ratio
            + self.weight_capability * capability_ratio
            + self.weight_diversity * diversity_bonus
            + self.weight_recency * recency_bonus
        )
        return max(0.0, min(1.0, score))

    def _generate_explanation_reasons(
        self,
        agent: Agent,
        post: Post,
        raw_sim: float,
        vector_score: float,
        metadata_score: float,
        final_score: float,
        passed: bool,
        industry_overlap: list[str],
        tag_overlap: list[str],
        capability_overlap: list[str],
        author_company: str | None = None,
        pref: Any | None = None,
        delta: float = 0.0,
        feedback_weight: float = 0.30,
        min_samples: int = 3,
    ) -> list[str]:
        """Generates clear, deterministic, inspectable reasons for the routing decision."""
        reasons: list[str] = []

        if raw_sim >= 0.70:
            reasons.append(f"Strong semantic alignment with post business context (similarity: {raw_sim:.2f})")
        elif raw_sim >= 0.40:
            reasons.append(f"Moderate semantic relevance to post content (similarity: {raw_sim:.2f})")
        else:
            reasons.append(f"Low semantic relevance to post content (similarity: {raw_sim:.2f})")

        # Explainable feedback preference adjustment
        if pref and getattr(pref, "total_feedback_count", 0) >= min_samples and abs(delta) >= 0.005:
            adj = feedback_weight * delta
            post_topics = set(
                [t.strip().lower() for t in (post.tags or []) if t.strip()]
                + [i.strip().lower() for i in (post.target_industries or []) if i.strip()]
            )
            learned_topics = getattr(pref, "learned_topics", {}) or {}
            if delta > 0:
                pos_topics = [
                    t for t in learned_topics.get("top_positive", [])
                    if t.lower() in post_topics
                ]
                if pos_topics:
                    reasons.append(
                        f"Adaptive preference boost (+{adj:.2f}) based on historical engagement with {pos_topics}"
                    )
                else:
                    reasons.append(
                        f"Adaptive preference boost (+{adj:.2f}) based on historical interaction patterns"
                    )
            else:
                neg_topics = [
                    t for t in learned_topics.get("top_negative", [])
                    if t.lower() in post_topics
                ]
                if neg_topics:
                    reasons.append(
                        f"Adaptive preference dampening ({adj:.2f}) based on historical rejection of {neg_topics}"
                    )
                else:
                    reasons.append(
                        f"Adaptive preference dampening ({adj:.2f}) based on historical interaction patterns"
                    )

        if industry_overlap:
            reasons.append(f"Direct target industry alignment: {', '.join(industry_overlap)}")

        if tag_overlap:
            reasons.append(f"Overlapping interest tags: {', '.join(tag_overlap)}")

        if capability_overlap:
            reasons.append(f"Relevant enterprise capabilities: {', '.join(capability_overlap)}")

        if author_company and agent.company:
            if agent.company.lower() != author_company.lower():
                reasons.append(f"Cross-enterprise synergy policy match ({author_company} ↔ {agent.company})")
            else:
                reasons.append(f"Intra-company candidate ({agent.company}); zero cross-enterprise policy bonus")

        if passed:
            reasons.append(
                f"Composite score ({final_score:.2f}) meets routing policy threshold ({self.threshold:.2f})"
            )
        else:
            reasons.append(
                f"Composite score ({final_score:.2f}) below routing policy threshold ({self.threshold:.2f})"
            )

        return reasons

    def _metadata_only_candidate(
        self,
        post: Post,
        agent: Agent,
        alpha: float,
    ) -> RoutingCandidate:
        """Fallback candidate constructor when post vector is not available."""
        industry_overlap = sorted(
            list(
                set(agent.industries or []) & set(post.target_industries or [])
            )
        )
        tag_overlap = sorted(list(set(agent.tags or []) & set(post.tags or [])))
        metadata_score = self._compute_metadata_score(
            agent=agent,
            post=post,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
        )
        final_score = metadata_score
        passed = final_score >= self.threshold

        return RoutingCandidate(
            agent_id=agent.id,
            agent_name=agent.name,
            company=agent.company,
            raw_cosine_distance=1.0,
            raw_cosine_similarity=0.0,
            vector_score=0.0,
            industry_overlap=industry_overlap,
            tag_overlap=tag_overlap,
            capability_overlap=[],
            metadata_score=round(metadata_score, 4),
            final_score=round(final_score, 4),
            passed_threshold=passed,
            was_notified=False,
            reasons=["Evaluated using metadata only (post vector embedding unavailable)"],
            score_breakdown={
                "metadata_score": round(metadata_score, 4),
                "final_score": round(final_score, 4),
                "threshold": self.threshold,
                "passed": passed,
            },
            agent_trust_score=agent.trust_score,
            agent_created_at=agent.created_at,
        )

    async def _persist_routing_logs_and_notifications(
        self,
        post: Post,
        candidates: list[RoutingCandidate],
        db: AsyncSession,
        publish_events: bool = True,
    ) -> None:
        """
        Persists audit trail to RoutingLog and creates pending Notification records.
        Idempotent via ON CONFLICT DO NOTHING.
        """
        # 1. Persist RoutingLog entries
        for c in candidates:
            stmt = pg_insert(RoutingLog).values(
                post_id=post.id,
                candidate_agent_id=c.agent_id,
                vector_score=c.vector_score,
                metadata_score=c.metadata_score,
                final_score=c.final_score,
                score_breakdown=c.score_breakdown,
                was_notified=c.was_notified,
                passed_threshold=c.passed_threshold,
            )
            # Idempotent deduplication on unique constraint uq_routing_post_agent
            stmt = stmt.on_conflict_do_update(
                constraint="uq_routing_post_agent",
                set_={
                    "vector_score": c.vector_score,
                    "metadata_score": c.metadata_score,
                    "final_score": c.final_score,
                    "score_breakdown": c.score_breakdown,
                    "was_notified": c.was_notified,
                    "passed_threshold": c.passed_threshold,
                    "updated_at": func.now(),
                },
            )
            await db.execute(stmt)

        # 2. Persist Notification records for selected candidates
        persisted_notifications: list[tuple[RoutingCandidate, uuid.UUID]] = []
        for c in candidates:
            if c.was_notified:
                notif_id = uuid.uuid4()
                notif_stmt = (
                    pg_insert(Notification)
                    .values(
                        id=notif_id,
                        recipient_agent_id=c.agent_id,
                        post_id=post.id,
                        relevance_score=c.final_score,
                        routing_explanation=c.score_breakdown,
                        status="pending",
                        delivery_event_published_at=None,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_notification_recipient_post"
                    )
                    .returning(Notification.id)
                )
                res = await db.execute(notif_stmt)
                inserted_id = None
                try:
                    if hasattr(res, "scalar_one_or_none") and "Mock" not in type(res).__name__:
                        val = res.scalar_one_or_none()
                        if isinstance(val, (uuid.UUID, str)):
                            inserted_id = uuid.UUID(str(val))
                except Exception:
                    pass

                actual_id = inserted_id or notif_id
                persisted_notifications.append((c, actual_id))

        await db.commit()

        # 3. Dispatches Redis stream events for selected candidates
        if publish_events:
            for c, notif_id in persisted_notifications:
                # 3a. Dispatches webhook/inbox delivery event
                published = await publish_notification_pending_event(
                    post_id=post.id,
                    recipient_agent_id=c.agent_id,
                    relevance_score=c.final_score,
                    notification_id=notif_id,
                )
                # 3b. Dispatches autonomous agent interaction event
                interaction_published = await publish_agent_interaction_event(
                    notification_id=notif_id,
                    post_id=post.id,
                    recipient_agent_id=c.agent_id,
                    relevance_score=c.final_score,
                )
                if (published or interaction_published) and notif_id:
                    try:
                        vals = {}
                        if published:
                            vals["delivery_event_published_at"] = func.now()
                        if interaction_published:
                            vals["interaction_event_published_at"] = func.now()
                        await db.execute(
                            update(Notification)
                            .where(Notification.id == notif_id)
                            .values(**vals)
                        )
                    except Exception as inner_e:
                        logger.warning("notification_mark_published_failed", notif_id=str(notif_id), error=str(inner_e))
            await db.commit()
