"""
Preference Service — mathematical formulation and lifecycle management for adaptive agent preferences.
Maintains bounded drift from the agent's baseline manifesto vector and aggregates interaction feedback.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.agent import Agent
from app.models.interaction import AgentInteraction
from app.models.post import Post
from app.models.preference import AgentPreference, FeedbackLedger

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pure Vector Mathematics (Deterministic & Dimension-Agnostic)
# ─────────────────────────────────────────────────────────────────────────────

def norm_l2(v: list[float]) -> float:
    """Calculates the L2 norm of a vector."""
    return math.sqrt(sum(x * x for x in v))


def normalize_vector(v: list[float]) -> list[float]:
    """Returns an L2-normalized unit vector. If norm is 0, returns a copy of v."""
    n = norm_l2(v)
    if n < 1e-12:
        return list(v)
    return [x / n for x in v]


def dot_product(u: list[float], v: list[float]) -> float:
    """Computes the dot product of two vectors of equal dimension."""
    if len(u) != len(v):
        raise ValueError(f"Vector dimensions do not match: {len(u)} != {len(v)}")
    return sum(a * b for a, b in zip(u, v))


def cosine_similarity(u: list[float], v: list[float]) -> float:
    """Computes cosine similarity between two vectors."""
    nu = norm_l2(u)
    nv = norm_l2(v)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0
    sim = dot_product(u, v) / (nu * nv)
    # Clamp to avoid floating point precision escape outside [-1.0, 1.0]
    return max(-1.0, min(1.0, sim))


def project_to_anchor_constraint(
    v_norm: list[float],
    anchor: list[float],
    tau: float = 0.70,
) -> list[float]:
    """
    Ensures that the unit vector v_norm satisfies cos(v_norm, anchor) >= tau.
    If cos(v_norm, anchor) < tau, projects v_norm onto the boundary of the cone
    with aperture arccos(tau) centered at anchor.
    """
    if len(v_norm) != len(anchor):
        raise ValueError("Dimensions must match")

    cos_sim = dot_product(v_norm, anchor)
    if cos_sim >= tau:
        return list(v_norm)

    # Decompose v_norm into parallel and orthogonal components relative to anchor
    # v_norm = cos_sim * anchor + v_perp
    v_perp = [v_i - cos_sim * a_i for v_i, a_i in zip(v_norm, anchor)]
    norm_perp = norm_l2(v_perp)

    if norm_perp < 1e-9:
        # v_norm is collinear or opposite to anchor; return anchor
        return list(anchor)

    # Unit orthogonal direction: u_perp = v_perp / norm_perp
    u_perp = [x / norm_perp for x in v_perp]

    # Reconstruct vector on boundary where cos = tau:
    # v_boundary = tau * anchor + sqrt(1 - tau^2) * u_perp
    sin_tau = math.sqrt(max(0.0, 1.0 - tau * tau))
    bounded = [
        tau * a_i + sin_tau * u_i
        for a_i, u_i in zip(anchor, u_perp)
    ]
    return normalize_vector(bounded)


def is_feedback_ledger_duplicate(exc: IntegrityError) -> bool:
    """
    Classifies database IntegrityError exceptions to differentiate expected
    idempotency collisions on the unique feedback ledger constraint from
    unhandled database integrity errors (such as foreign key or not-null violations).

    Returns True if the exception indicates a duplicate interaction_id on feedback_ledger.
    Returns False otherwise, signaling the error must be propagated.
    """
    orig_msg = str(getattr(exc, "orig", exc)).lower()
    return (
        "uq_feedback_ledger_interaction_id" in orig_msg
        or "feedback_ledger_interaction_id" in orig_msg
        or ("feedback_ledger" in orig_msg and "interaction_id" in orig_msg and "unique" in orig_msg)
    )


def compute_adaptive_vector_step(
    current_v: list[float],
    anchor_v: list[float],
    post_v: list[float],
    signal: str,
    confidence: float,
    eta_pos: float = 0.08,
    eta_neg: float = 0.04,
    tau_anchor: float = 0.70,
) -> list[float]:
    """
    Computes a mathematically bounded adaptive preference update:
    - Positive interaction: step towards post embedding.
    - Negative interaction: step away from post embedding (orthogonal rejection).
    - Anchor drift constraint: cos(v_{t+1}, anchor_v) >= tau_anchor.
    - Result is strictly L2-normalized.
    """
    c_v = normalize_vector(current_v)
    a_v = normalize_vector(anchor_v)
    p_v = normalize_vector(post_v)

    conf = max(0.0, min(1.0, confidence))

    if signal == "positive":
        # Positive update: interpolate towards post vector weighted by confidence
        alpha = eta_pos * max(0.1, conf)
        raw_step = [(1.0 - alpha) * cv + alpha * pv for cv, pv in zip(c_v, p_v)]

    elif signal == "negative":
        # Negative rejection: project post vector orthogonal to current_v
        # p_perp = p_v - (p_v . c_v) * c_v
        proj = dot_product(p_v, c_v)
        p_perp = [pv - proj * cv for pv, cv in zip(p_v, c_v)]
        n_perp = norm_l2(p_perp)
        beta = eta_neg * max(0.1, conf)

        if n_perp < 1e-4:
            # Post vector is near-parallel to current preference (or identical).
            # Rejecting content matching current preference decays the vector back toward baseline anchor.
            raw_step = [(1.0 - beta) * cv + beta * av for cv, av in zip(c_v, a_v)]
        else:
            u_perp = [x / n_perp for x in p_perp]
            raw_step = [cv - beta * uv for cv, uv in zip(c_v, u_perp)]
    else:
        raise ValueError(f"Unknown feedback signal '{signal}'")

    # Normalize raw step
    normed_step = normalize_vector(raw_step)

    # Project onto anchor cone boundary to strictly satisfy drift constraint
    final_v = project_to_anchor_constraint(normed_step, a_v, tau=tau_anchor)
    return final_v


# ─────────────────────────────────────────────────────────────────────────────
# Preference Lifecycle Service
# ─────────────────────────────────────────────────────────────────────────────

class PreferenceService:
    """
    Manages persistence, atomic updates, and query operations for AgentPreference.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def process_feedback_event(
        self,
        db: AsyncSession,
        interaction_id: uuid.UUID,
    ) -> AgentPreference | None:
        """
        Processes a single interaction feedback event idempotently and atomically:
        1. Checks unique interaction_id in FeedbackLedger (skips if already recorded).
        2. Inspects AgentInteraction outcome ('engaged' -> positive, 'ignored' -> negative).
        3. Filters low-confidence negative signals below feedback_min_confidence.
        4. Computes updated adaptive vector under row lock.
        5. Updates topic frequency distribution and ledger.
        """
        log = logger.bind(interaction_id=str(interaction_id))

        # 1. Idempotency Check in Ledger
        ledger_stmt = select(FeedbackLedger).where(FeedbackLedger.interaction_id == interaction_id)
        existing_ledger = (await db.execute(ledger_stmt)).scalar_one_or_none()
        if existing_ledger:
            log.info("feedback_event_already_processed_in_ledger", signal=existing_ledger.signal)
            return None

        # 2. Load AgentInteraction with relations
        int_stmt = (
            select(AgentInteraction)
            .options(
                selectinload(AgentInteraction.receiving_agent),
                selectinload(AgentInteraction.post),
            )
            .where(AgentInteraction.id == interaction_id)
        )
        interaction = (await db.execute(int_stmt)).scalar_one_or_none()
        if not interaction:
            log.warning("feedback_interaction_not_found")
            return None

        # Determine signal
        if interaction.status == "engaged":
            signal = "positive"
        elif interaction.status == "ignored":
            signal = "negative"
        else:
            log.info("feedback_interaction_neutral_skipping", status=interaction.status)
            return None

        confidence = interaction.confidence if interaction.confidence is not None else 0.5
        agent = interaction.receiving_agent
        post = interaction.post

        if not agent or not post:
            log.warning("feedback_missing_agent_or_post")
            return None

        if not agent.interest_embedding:
            log.info("feedback_agent_missing_anchor_embedding", agent_id=str(agent.id))
            return None

        if not post.content_embedding:
            log.info("feedback_post_missing_content_embedding", post_id=str(post.id))
            return None

        # 3. Low-confidence negative filter
        if signal == "negative" and confidence < self.settings.feedback_min_confidence:
            log.info(
                "feedback_negative_below_min_confidence_gated",
                confidence=confidence,
                min_confidence=self.settings.feedback_min_confidence,
            )
            # Record in ledger as filtered to guarantee idempotency without altering vector
            ledger_entry = FeedbackLedger(
                interaction_id=interaction.id,
                notification_id=interaction.notification_id,
                agent_id=agent.id,
                post_id=post.id,
                signal="negative_filtered",
                confidence=confidence,
                topics_applied=[],
            )
            db.add(ledger_entry)
            try:
                await db.commit()
            except IntegrityError as exc:
                await db.rollback()
                if is_feedback_ledger_duplicate(exc):
                    log.info("concurrent_filtered_feedback_event_already_recorded", interaction_id=str(interaction.id))
                    return None
                log.error("unhandled_database_integrity_error_during_filtered_feedback", error=str(exc))
                raise exc
            return None

        # 4. Atomic Row-Level Lock on parent Agent to serialize preference row initialization and updates
        agent_lock_stmt = (
            select(Agent.id)
            .where(Agent.id == agent.id)
            .with_for_update()
        )
        await db.execute(agent_lock_stmt)

        # Atomic Row-Level Lock on AgentPreference
        pref_stmt = (
            select(AgentPreference)
            .where(AgentPreference.agent_id == agent.id)
            .with_for_update()
        )
        pref = (await db.execute(pref_stmt)).scalar_one_or_none()

        if not pref:
            pref = AgentPreference(
                agent_id=agent.id,
                learned_vector=list(agent.interest_embedding),
                positive_interactions_count=0,
                negative_interactions_count=0,
                total_feedback_count=0,
                engagement_rate=0.0,
                learned_topics={"positive": {}, "negative": {}, "top_positive": [], "top_negative": []},
                learning_version=1,
            )
            db.add(pref)
            await db.flush()

        anchor_v = list(agent.interest_embedding)
        current_v = list(pref.learned_vector) if pref.learned_vector is not None else anchor_v
        post_v = list(post.content_embedding)

        # 5. Compute Adaptive Vector
        new_vector = compute_adaptive_vector_step(
            current_v=current_v,
            anchor_v=anchor_v,
            post_v=post_v,
            signal=signal,
            confidence=confidence,
            eta_pos=self.settings.feedback_learning_rate_pos,
            eta_neg=self.settings.feedback_learning_rate_neg,
            tau_anchor=self.settings.feedback_anchor_cosine_min,
        )
        pref.learned_vector = new_vector

        # 6. Update counts
        pos_cnt = pref.positive_interactions_count if pref.positive_interactions_count is not None else 0
        neg_cnt = pref.negative_interactions_count if pref.negative_interactions_count is not None else 0
        if signal == "positive":
            pos_cnt += 1
        else:
            neg_cnt += 1
        pref.positive_interactions_count = pos_cnt
        pref.negative_interactions_count = neg_cnt
        pref.total_feedback_count = pos_cnt + neg_cnt
        pref.engagement_rate = round(pos_cnt / pref.total_feedback_count, 4) if pref.total_feedback_count > 0 else 0.0

        # 7. Update Learned Topics
        post_topics = sorted(
            list(
                set(
                    [t.strip().lower() for t in (post.tags or []) if t.strip()]
                    + [i.strip().lower() for i in (post.target_industries or []) if i.strip()]
                )
            )
        )

        current_topics = dict(pref.learned_topics or {})
        pos_map = dict(current_topics.get("positive", {}))
        neg_map = dict(current_topics.get("negative", {}))

        target_map = pos_map if signal == "positive" else neg_map
        for topic in post_topics:
            target_map[topic] = target_map.get(topic, 0) + 1

        current_topics["positive"] = pos_map
        current_topics["negative"] = neg_map
        current_topics["top_positive"] = [
            k for k, _ in sorted(pos_map.items(), key=lambda item: item[1], reverse=True)[:10]
        ]
        current_topics["top_negative"] = [
            k for k, _ in sorted(neg_map.items(), key=lambda item: item[1], reverse=True)[:10]
        ]
        pref.learned_topics = current_topics
        pref.last_updated_at = datetime.now(timezone.utc)

        # 8. Record in FeedbackLedger
        ledger = FeedbackLedger(
            interaction_id=interaction.id,
            notification_id=interaction.notification_id,
            agent_id=agent.id,
            post_id=post.id,
            signal=signal,
            confidence=confidence,
            topics_applied=post_topics,
        )
        db.add(ledger)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            if is_feedback_ledger_duplicate(exc):
                log.info("concurrent_feedback_event_already_recorded", interaction_id=str(interaction.id))
                return None
            log.error("unhandled_database_integrity_error_during_feedback", error=str(exc))
            raise exc

        log.info(
            "feedback_applied_successfully",
            agent_id=str(agent.id),
            signal=signal,
            total_feedback=pref.total_feedback_count,
            engagement_rate=pref.engagement_rate,
        )
        return pref

    async def reanchor_to_new_embedding(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        new_embedding: list[float],
        prior_embedding: list[float] | None = None,
    ) -> AgentPreference | None:
        """
        Re-anchors an agent's preferences when the base manifesto/profile changes.

        Idempotency:
        - If prior_embedding is provided and cosine_similarity(prior_embedding, new_embedding) >= 0.9999,
          the embedding has not materially changed (e.g. worker retry or identical manifesto).
          Learned preference counters, topics, and learning_version are strictly preserved.
        - If prior_embedding is materially different (cos < 0.9999) or None,
          the learned vector is reset to the new embedding, counters and topics are cleared,
          and learning_version is incremented.
        """
        # Lock parent Agent row first to serialize preference initialization/re-anchoring
        agent_lock_stmt = (
            select(Agent.id)
            .where(Agent.id == agent_id)
            .with_for_update()
        )
        await db.execute(agent_lock_stmt)

        pref_stmt = (
            select(AgentPreference)
            .where(AgentPreference.agent_id == agent_id)
            .with_for_update()
        )
        pref = (await db.execute(pref_stmt)).scalar_one_or_none()
        if not pref:
            return None

        # Check if embedding materially changed
        if prior_embedding is not None:
            sim = cosine_similarity(prior_embedding, new_embedding)
            if sim >= 0.9999:
                logger.info(
                    "agent_preferences_reanchor_skipped_identical_embedding",
                    agent_id=str(agent_id),
                    cosine_similarity=round(sim, 6),
                )
                if pref.learned_vector is not None:
                    pref.learned_vector = project_to_anchor_constraint(
                        pref.learned_vector,
                        new_embedding,
                        tau=self.settings.feedback_anchor_cosine_min,
                    )
                pref.last_updated_at = datetime.now(timezone.utc)
                return pref

        # Material profile change: reset learned vector and accumulated counters
        pref.learned_vector = list(new_embedding)
        pref.positive_interactions_count = 0
        pref.negative_interactions_count = 0
        pref.total_feedback_count = 0
        pref.engagement_rate = 0.0
        pref.learned_topics = {"positive": {}, "negative": {}, "top_positive": [], "top_negative": []}
        pref.learning_version = (pref.learning_version or 1) + 1
        pref.last_updated_at = datetime.now(timezone.utc)
        logger.info(
            "agent_preferences_reanchored_to_new_profile",
            agent_id=str(agent_id),
            new_version=pref.learning_version,
        )
        return pref

    async def reset_preferences(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
    ) -> AgentPreference:
        """
        Resets an agent's learned preference vector back to the baseline manifesto anchor.
        Clears topic counters and increments learning_version.
        """
        agent_stmt = select(Agent).where(Agent.id == agent_id).with_for_update()
        agent = (await db.execute(agent_stmt)).scalar_one_or_none()
        if not agent:
            raise ValueError(f"Agent '{agent_id}' not found")

        pref_stmt = (
            select(AgentPreference)
            .where(AgentPreference.agent_id == agent_id)
            .with_for_update()
        )
        pref = (await db.execute(pref_stmt)).scalar_one_or_none()

        anchor_vec = list(agent.interest_embedding) if agent.interest_embedding else None

        if not pref:
            pref = AgentPreference(
                agent_id=agent_id,
                learned_vector=anchor_vec,
                positive_interactions_count=0,
                negative_interactions_count=0,
                total_feedback_count=0,
                engagement_rate=0.0,
                learned_topics={"positive": {}, "negative": {}, "top_positive": [], "top_negative": []},
                learning_version=1,
            )
            db.add(pref)
        else:
            pref.learned_vector = anchor_vec
            pref.positive_interactions_count = 0
            pref.negative_interactions_count = 0
            pref.total_feedback_count = 0
            pref.engagement_rate = 0.0
            pref.learned_topics = {"positive": {}, "negative": {}, "top_positive": [], "top_negative": []}
            pref.learning_version = (pref.learning_version or 1) + 1
            pref.last_updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(pref)
        logger.info("agent_preferences_reset", agent_id=str(agent_id), version=pref.learning_version)
        return pref


_preference_service: PreferenceService | None = None


def get_preference_service() -> PreferenceService:
    global _preference_service
    if _preference_service is None:
        _preference_service = PreferenceService()
    return _preference_service
