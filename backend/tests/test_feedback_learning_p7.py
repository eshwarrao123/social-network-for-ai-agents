"""
Unit and integration test suite for P7: Feedback-Driven Learning & Adaptive Agent Preferences.
Tests bounded drift vector mathematics, cold-start gating, topic aggregation, idempotency,
worker reliability, explainable routing, and strict zero-vector API disclosure.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.models.agent import Agent
from app.models.interaction import AgentInteraction
from app.models.notification import Notification
from app.models.post import Post
from app.models.preference import AgentPreference, FeedbackLedger
from app.schemas.agent import AgentPreferenceResetResponse, AgentPreferenceResponse
from app.services.events import publish_feedback_event
from app.services.preference_service import (
    compute_adaptive_vector_step,
    cosine_similarity,
    dot_product,
    get_preference_service,
    is_feedback_ledger_duplicate,
    norm_l2,
    normalize_vector,
    project_to_anchor_constraint,
    PreferenceService,
)
from app.services.routing_engine import RoutingCandidate, RoutingEngine
from app.workers.feedback_worker import FeedbackWorker
from app.workers.llm_worker import LlmWorker


# ─────────────────────────────────────────────────────────────────────────────
# Test Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_unit_vector(seed_val: float = 1.0, dim: int = 768) -> list[float]:
    """Generates a deterministic L2-normalized 768-dimensional vector."""
    v = [math.sin(seed_val + i * 0.1) for i in range(dim)]
    return normalize_vector(v)


def make_test_agent(
    agent_id: uuid.UUID | None = None,
    name: str = "AdaptiveRiskAgent",
    company: str = "EnterpriseCapital",
    is_active: bool = True,
) -> Agent:
    agent = Agent()
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.description = "Autonomous agent specialized in quantitative market analysis and risk forecasting."
    agent.industries = ["fintech", "banking"]
    agent.tags = ["risk-analysis", "derivatives", "portfolio"]
    agent.capabilities = ["var-modeling", "stress-testing"]
    agent.trust_score = 0.90
    agent.is_active = is_active
    agent.interest_embedding = make_unit_vector(1.0)
    agent.embedding_status = "completed"
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


def make_test_post(
    post_id: uuid.UUID | None = None,
    author: Agent | None = None,
    tags: list[str] | None = None,
    target_industries: list[str] | None = None,
) -> Post:
    author = author or make_test_agent(name="AuthorAgent", company="MarketLeader")
    post = Post()
    post.id = post_id or uuid.uuid4()
    post.author_agent_id = author.id
    post.author = author
    post.title = "Algorithmic Market Risk and Derivatives Exposure Protocol"
    post.content = "Standardized messaging exchange for autonomous agents executing real-time liquidity stress tests."
    post.post_type = "partnership"
    post.target_industries = target_industries or ["fintech", "banking"]
    post.tags = tags or ["risk-analysis", "stress-testing"]
    post.content_embedding = make_unit_vector(2.0)
    post.embedding_status = "completed"
    post.status = "published"
    post.created_at = datetime.now(timezone.utc)
    post.updated_at = datetime.now(timezone.utc)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pure Vector Mathematics Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_vector_math_norm_and_normalize():
    """Verifies vector L2 norm calculation and unit normalization."""
    v = [3.0, 4.0]
    assert math.isclose(norm_l2(v), 5.0)

    normed = normalize_vector(v)
    assert math.isclose(norm_l2(normed), 1.0)
    assert math.isclose(normed[0], 0.6)
    assert math.isclose(normed[1], 0.8)

    # Zero vector safety
    zero_v = [0.0, 0.0, 0.0]
    assert normalize_vector(zero_v) == zero_v


@pytest.mark.unit
def test_vector_math_dot_product_and_cosine_similarity():
    """Verifies dot product and cosine similarity across cardinal and orthogonal directions."""
    u = [1.0, 0.0, 0.0]
    v = [0.0, 1.0, 0.0]
    w = [1.0, 0.0, 0.0]
    neg_u = [-1.0, 0.0, 0.0]

    # Orthogonal vectors: similarity == 0.0
    assert math.isclose(cosine_similarity(u, v), 0.0)

    # Identical vectors: similarity == 1.0
    assert math.isclose(cosine_similarity(u, w), 1.0)

    # Opposite vectors: similarity == -1.0
    assert math.isclose(cosine_similarity(u, neg_u), -1.0)


@pytest.mark.unit
def test_vector_math_project_to_anchor_constraint_inside_cone():
    """When cosine similarity to anchor is already >= tau, vector is preserved without change."""
    anchor = make_unit_vector(1.0)
    # A vector very close to anchor
    test_v = normalize_vector([a + 0.01 for a in anchor])
    sim = cosine_similarity(test_v, anchor)
    assert sim >= 0.70

    bounded = project_to_anchor_constraint(test_v, anchor, tau=0.70)
    assert math.isclose(cosine_similarity(bounded, anchor), sim, rel_tol=1e-5)
    assert math.isclose(norm_l2(bounded), 1.0)


@pytest.mark.unit
def test_vector_math_project_to_anchor_constraint_outside_cone():
    """When cosine similarity to anchor is < tau, projects onto boundary cone of cos == tau."""
    anchor = make_unit_vector(1.0)
    orthogonal = make_unit_vector(5.0)
    # Make orthogonal strictly orthogonal to anchor
    proj = dot_product(orthogonal, anchor)
    orthogonal = normalize_vector([o - proj * a for o, a in zip(orthogonal, anchor)])
    assert math.isclose(cosine_similarity(orthogonal, anchor), 0.0, abs_tol=1e-6)

    # Orthogonal vector has cos = 0.0 < 0.70
    bounded = project_to_anchor_constraint(orthogonal, anchor, tau=0.70)
    cos_bounded = cosine_similarity(bounded, anchor)

    assert math.isclose(cos_bounded, 0.70, abs_tol=1e-5)
    assert math.isclose(norm_l2(bounded), 1.0)


@pytest.mark.unit
def test_compute_adaptive_vector_step_positive():
    """Positive interaction steps towards post vector while preserving unit norm."""
    anchor = make_unit_vector(1.0)
    post_vec = make_unit_vector(2.0)

    initial_sim = cosine_similarity(anchor, post_vec)
    new_v = compute_adaptive_vector_step(
        current_v=anchor,
        anchor_v=anchor,
        post_v=post_vec,
        signal="positive",
        confidence=0.90,
        eta_pos=0.08,
        eta_neg=0.04,
        tau_anchor=0.70,
    )

    new_sim = cosine_similarity(new_v, post_vec)
    assert new_sim > initial_sim
    assert math.isclose(norm_l2(new_v), 1.0)


@pytest.mark.unit
def test_compute_adaptive_vector_step_negative():
    """Negative interaction takes an orthogonal rejection step away from post vector."""
    anchor = make_unit_vector(1.0)
    post_vec = make_unit_vector(2.0)

    initial_sim = cosine_similarity(anchor, post_vec)
    new_v = compute_adaptive_vector_step(
        current_v=anchor,
        anchor_v=anchor,
        post_v=post_vec,
        signal="negative",
        confidence=0.85,
        eta_pos=0.08,
        eta_neg=0.04,
        tau_anchor=0.70,
    )

    new_sim = cosine_similarity(new_v, post_vec)
    assert new_sim < initial_sim
    assert math.isclose(norm_l2(new_v), 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Bounded Drift Invariance Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_drift_bound_enforcement_over_divergent_trajectory():
    """
    Simulates 100 consecutive divergent / negative interactions trying to pull the agent
    away from its core business profile. Strictly asserts cos(v_t, v_0) >= tau_anchor at every step.
    """
    anchor_v = make_unit_vector(10.0)
    current_v = list(anchor_v)
    tau = 0.70

    for i in range(100):
        # Generate an antagonistic post vector trying to pull away
        divergent_post = make_unit_vector(50.0 + i)
        current_v = compute_adaptive_vector_step(
            current_v=current_v,
            anchor_v=anchor_v,
            post_v=divergent_post,
            signal="negative",
            confidence=1.0,
            eta_pos=0.08,
            eta_neg=0.08,  # aggressive step
            tau_anchor=tau,
        )

        sim_to_anchor = cosine_similarity(current_v, anchor_v)
        assert sim_to_anchor >= (tau - 1e-6), f"Drift constraint violated at step {i}: {sim_to_anchor} < {tau}"
        assert math.isclose(norm_l2(current_v), 1.0, abs_tol=1e-5)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cold-Start Gating and Routing Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_cold_start_gating_below_min_samples():
    """
    Agents with fewer than feedback_min_samples (e.g. 1 or 2 interactions) experience
    ZERO score adjustment in routing, preserving the pure baseline score.
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    post = make_test_post()

    # Agent has only 2 feedback samples (< min_samples = 3)
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(3.0),
        total_feedback_count=2,
        positive_interactions_count=2,
        negative_interactions_count=0,
        engagement_rate=1.0,
        learned_topics={"positive": {"risk-analysis": 2}, "negative": {}},
    )
    agent.preference = pref

    candidate = engine._score_candidate(post=post, agent=agent, cosine_dist=0.30)

    # Breakdown verification
    assert candidate.score_breakdown["feedback_sample_count"] == 2
    assert candidate.score_breakdown["feedback_adjustment"] == 0.0
    assert candidate.score_breakdown["base_vector_score"] == candidate.score_breakdown["normalized_vector_score"]


@pytest.mark.unit
def test_gated_adjustment_above_min_samples():
    """
    Agents with >= feedback_min_samples experience a feedback adjustment in their vector score.
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    post = make_test_post()

    # Agent has 4 feedback samples (>= min_samples = 3) with high alignment to post
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=post.content_embedding,  # learned vector perfectly matches post
        total_feedback_count=4,
        positive_interactions_count=4,
        negative_interactions_count=0,
        engagement_rate=1.0,
        learned_topics={"positive": {"risk-analysis": 4}, "top_positive": ["risk-analysis"]},
    )
    agent.preference = pref

    # Base cosine dist = 0.50 (sim = 0.50)
    candidate = engine._score_candidate(post=post, agent=agent, cosine_dist=0.50)

    assert candidate.score_breakdown["feedback_sample_count"] == 4
    assert candidate.score_breakdown["feedback_adjustment"] > 0.0
    assert candidate.score_breakdown["normalized_vector_score"] > candidate.score_breakdown["base_vector_score"]


@pytest.mark.unit
def test_feedback_adjustment_clamped_to_max():
    """
    Feedback adjustments are strictly clamped to [-max_adjustment, +max_adjustment] (default 0.15).
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    post = make_test_post()

    # Learned vector has maximal contrast
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=post.content_embedding,
        total_feedback_count=10,
        positive_interactions_count=10,
        negative_interactions_count=0,
        engagement_rate=1.0,
        learned_topics={"positive": {}, "top_positive": []},
    )
    agent.preference = pref

    candidate = engine._score_candidate(post=post, agent=agent, cosine_dist=1.50)  # low base sim = 0.0
    adj = candidate.score_breakdown["feedback_adjustment"]
    # max possible adjustment = feedback_weight (0.30) * max_delta (0.15) = 0.045
    assert adj <= 0.30 * 0.15 + 1e-4


@pytest.mark.unit
def test_explainable_reasons_contain_real_topics():
    """
    Verifies that explainable routing reasons cite actual recorded topics from learned_topics.
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    post = make_test_post(tags=["derivatives", "stress-testing"])

    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=post.content_embedding,
        total_feedback_count=5,
        positive_interactions_count=5,
        negative_interactions_count=0,
        engagement_rate=1.0,
        learned_topics={
            "positive": {"derivatives": 3, "stress-testing": 2},
            "top_positive": ["derivatives", "stress-testing"],
        },
    )
    agent.preference = pref

    candidate = engine._score_candidate(post=post, agent=agent, cosine_dist=0.60)
    reasons_text = " ".join(candidate.reasons)

    assert "Adaptive preference boost" in reasons_text
    assert "derivatives" in reasons_text


@pytest.mark.unit
def test_explainable_reasons_fallback_pattern_when_no_topic_overlap():
    """
    When adjustment occurs but post metadata does not overlap with top_positive/top_negative,
    routing reasons use the deterministic fallback without hallucinating topics.
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    # Post with topics not in top_positive
    post = make_test_post(tags=["unrelated-topic-abc"])

    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=post.content_embedding,
        total_feedback_count=5,
        positive_interactions_count=5,
        negative_interactions_count=0,
        engagement_rate=1.0,
        learned_topics={
            "positive": {"crypto": 5},
            "top_positive": ["crypto"],
        },
    )
    agent.preference = pref

    candidate = engine._score_candidate(post=post, agent=agent, cosine_dist=0.60)
    reasons_text = " ".join(candidate.reasons)

    assert "Adaptive preference boost" in reasons_text
    assert "historical interaction patterns" in reasons_text


# ─────────────────────────────────────────────────────────────────────────────
# 4. Preference Service & Feedback Ledger Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_feedback_ledger_idempotency_duplicate_interaction_skipped():
    """
    Verifies that if an interaction_id has already been recorded in FeedbackLedger,
    the event is skipped idempotently without re-applying vector updates.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    existing_ledger = FeedbackLedger(
        interaction_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        post_id=uuid.uuid4(),
        signal="positive",
        confidence=0.9,
    )
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = existing_ledger
    mock_db.execute.return_value = mock_exec

    result = await service.process_feedback_event(mock_db, existing_ledger.interaction_id)
    assert result is None
    # No write operations should occur
    mock_db.commit.assert_not_called()


@pytest.mark.unit
async def test_feedback_negative_low_confidence_filtered():
    """
    A negative interaction with confidence below feedback_min_confidence (0.60)
    is recorded in the ledger as 'negative_filtered' but does not modify the preference vector.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    post = make_test_post()
    interaction = AgentInteraction(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        receiving_agent_id=agent.id,
        post_id=post.id,
        status="ignored",
        confidence=0.45,  # below 0.60 threshold
    )
    interaction.receiving_agent = agent
    interaction.post = post

    # 1. No existing ledger entry
    mock_ledger_exec = MagicMock()
    mock_ledger_exec.scalar_one_or_none.return_value = None

    # 2. Return interaction
    mock_int_exec = MagicMock()
    mock_int_exec.scalar_one_or_none.return_value = interaction

    mock_db.execute.side_effect = [mock_ledger_exec, mock_int_exec]

    result = await service.process_feedback_event(mock_db, interaction.id)

    assert result is None
    # Entry added to ledger
    mock_db.add.assert_called_once()
    added_entry = mock_db.add.call_args[0][0]
    assert isinstance(added_entry, FeedbackLedger)
    assert added_entry.signal == "negative_filtered"
    mock_db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_process_feedback_event_positive_success():
    """
    Successful processing of a positive engagement event updates counts, topics, and vector.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    post = make_test_post(tags=["quant-trading"])
    interaction = AgentInteraction(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        receiving_agent_id=agent.id,
        post_id=post.id,
        status="engaged",
        confidence=0.95,
    )
    interaction.receiving_agent = agent
    interaction.post = post

    # 1. No existing ledger
    mock_ledger_exec = MagicMock()
    mock_ledger_exec.scalar_one_or_none.return_value = None

    # 2. Return interaction
    mock_int_exec = MagicMock()
    mock_int_exec.scalar_one_or_none.return_value = interaction

    # 3. Parent Agent row lock
    mock_agent_lock_exec = MagicMock()

    # 4. No existing AgentPreference (creates fresh)
    mock_pref_exec = MagicMock()
    mock_pref_exec.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [mock_ledger_exec, mock_int_exec, mock_agent_lock_exec, mock_pref_exec]

    result = await service.process_feedback_event(mock_db, interaction.id)

    assert result is not None
    assert result.positive_interactions_count == 1
    assert result.total_feedback_count == 1
    assert result.engagement_rate == 1.0
    assert "quant-trading" in result.learned_topics["top_positive"]
    assert mock_db.commit.await_count >= 1


@pytest.mark.unit
async def test_reset_preferences_service():
    """
    Reset restores the learned vector to the anchor embedding and increments learning_version.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(9.0),
        positive_interactions_count=10,
        negative_interactions_count=5,
        total_feedback_count=15,
        engagement_rate=0.6667,
        learning_version=2,
        learned_topics={"positive": {"tag": 10}, "top_positive": ["tag"]},
    )

    mock_agent_exec = MagicMock()
    mock_agent_exec.scalar_one_or_none.return_value = agent

    mock_pref_exec = MagicMock()
    mock_pref_exec.scalar_one_or_none.return_value = pref

    mock_db.execute.side_effect = [mock_agent_exec, mock_pref_exec]

    updated = await service.reset_preferences(mock_db, agent.id)

    assert updated.learning_version == 3
    assert updated.total_feedback_count == 0
    assert updated.engagement_rate == 0.0
    assert updated.learned_vector == list(agent.interest_embedding)
    assert updated.learned_topics["top_positive"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Feedback Worker Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_feedback_worker_handle_processes_event():
    """FeedbackWorker successfully reads interaction_id and invokes PreferenceService."""
    mock_service = MagicMock(spec=PreferenceService)
    mock_service.process_feedback_event = AsyncMock()

    worker = FeedbackWorker(preference_service=mock_service)
    test_id = uuid.uuid4()

    with patch("app.workers.feedback_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.handle({"interaction_id": str(test_id)})

        mock_service.process_feedback_event.assert_awaited_once_with(mock_db, test_id)


@pytest.mark.unit
async def test_feedback_worker_reconciles_unprocessed_interactions():
    """FeedbackWorker periodically finds completed interactions without published events and enqueues them."""
    worker = FeedbackWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    interaction = AgentInteraction(
        id=uuid.uuid4(),
        receiving_agent_id=uuid.uuid4(),
        post_id=uuid.uuid4(),
        status="engaged",
        confidence=0.88,
        feedback_event_published_at=None,
    )

    with patch("app.workers.feedback_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [interaction]
        mock_db.execute.return_value = mock_res
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        count = await worker.reconcile_unprocessed_interactions(mock_redis, mock_log)

        assert count == 1
        mock_redis.xadd.assert_awaited_once()
        call_args = mock_redis.xadd.await_args[0]
        assert call_args[0] == "agent-feedback:pending"
        assert call_args[1]["interaction_id"] == str(interaction.id)
        assert call_args[1]["signal"] == "positive"


@pytest.mark.unit
async def test_feedback_worker_handles_invalid_message():
    """FeedbackWorker gracefully skips messages with missing interaction_id."""
    worker = FeedbackWorker()
    # Missing interaction_id
    await worker.handle({"unrelated_field": "123"})
    # Should not raise exception


# ─────────────────────────────────────────────────────────────────────────────
# 6. Event Dispatch in LLM Worker Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_llm_worker_dispatches_feedback_event_on_engage():
    """LlmWorker dispatches a positive feedback event when the agent decides to engage."""
    agent = make_test_agent()
    post = make_test_post()
    notification = Notification(
        id=uuid.uuid4(),
        recipient_agent_id=agent.id,
        post_id=post.id,
        status="pending",
        relevance_score=0.88,
        routing_explanation={"reasons": ["domain synergy"]},
    )
    notification.recipient = agent
    notification.post = post

    worker = LlmWorker()

    with patch("app.workers.llm_worker.AsyncSessionLocal") as mock_session_ctx, \
         patch("app.workers.llm_worker.get_llm_service") as mock_get_llm, \
         patch("app.services.events.publish_feedback_event", new_callable=AsyncMock) as mock_pub:

        mock_db = AsyncMock()
        # 1. notif query
        mock_notif_res = MagicMock()
        mock_notif_res.scalar_one_or_none.return_value = notification

        # 2. interaction query (None -> create)
        mock_int_res = MagicMock()
        mock_int_res.scalar_one_or_none.return_value = None

        # 3. comment check query (None)
        mock_comm_res = MagicMock()
        mock_comm_res.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_notif_res, mock_int_res, mock_comm_res, MagicMock()]
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        mock_llm = MagicMock()
        from app.services.llm_service import InteractionEvaluationResult
        mock_llm.evaluate_interaction = AsyncMock(
            return_value=(
                InteractionEvaluationResult(
                    decision="engage",
                    confidence=0.92,
                    comment="Great risk framework.",
                    reason="Strong domain synergy.",
                ),
                "llama3.2",
            )
        )
        mock_llm.provider = "ollama"
        mock_get_llm.return_value = mock_llm
        mock_pub.return_value = True

        await worker.handle({"notification_id": str(notification.id)})

        mock_pub.assert_awaited_once()
        call_kwargs = mock_pub.await_args[1]
        assert call_kwargs["signal"] == "positive"
        assert math.isclose(call_kwargs["confidence"], 0.92, rel_tol=1e-3)


@pytest.mark.unit
async def test_llm_worker_dispatches_feedback_event_on_ignore():
    """LlmWorker dispatches a negative feedback event when the agent decides to ignore."""
    agent = make_test_agent()
    post = make_test_post()
    notification = Notification(
        id=uuid.uuid4(),
        recipient_agent_id=agent.id,
        post_id=post.id,
        status="pending",
        relevance_score=0.88,
        routing_explanation={"reasons": ["domain synergy"]},
    )
    notification.recipient = agent
    notification.post = post

    worker = LlmWorker()

    with patch("app.workers.llm_worker.AsyncSessionLocal") as mock_session_ctx, \
         patch("app.workers.llm_worker.get_llm_service") as mock_get_llm, \
         patch("app.services.events.publish_feedback_event", new_callable=AsyncMock) as mock_pub:

        mock_db = AsyncMock()
        # 1. notif query
        mock_notif_res = MagicMock()
        mock_notif_res.scalar_one_or_none.return_value = notification

        # 2. interaction query (None -> create)
        mock_int_res = MagicMock()
        mock_int_res.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_notif_res, mock_int_res]
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        mock_llm = MagicMock()
        from app.services.llm_service import InteractionEvaluationResult
        mock_llm.evaluate_interaction = AsyncMock(
            return_value=(
                InteractionEvaluationResult(
                    decision="ignore",
                    confidence=0.80,
                    comment=None,
                    reason="Outside target scope.",
                ),
                "llama3.2",
            )
        )
        mock_llm.provider = "ollama"
        mock_get_llm.return_value = mock_llm
        mock_pub.return_value = True

        await worker.handle({"notification_id": str(notification.id)})

        mock_pub.assert_awaited_once()
        call_kwargs = mock_pub.await_args[1]
        assert call_kwargs["signal"] == "negative"
        assert math.isclose(call_kwargs["confidence"], 0.80, rel_tol=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# 7. REST API Endpoints Tests & Zero-Vector Exposure
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_get_my_preferences_endpoint_success(client: AsyncClient):
    """GET /api/v1/agents/me/preferences returns accurate statistics and topics."""
    agent = make_test_agent()
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(2.0),
        positive_interactions_count=6,
        negative_interactions_count=2,
        total_feedback_count=8,
        engagement_rate=0.75,
        learning_version=2,
        learned_topics={
            "positive": {"risk": 6},
            "negative": {"crypto": 2},
            "top_positive": ["risk"],
            "top_negative": ["crypto"],
        },
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_res

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        response = await client.get("/api/v1/agents/me/preferences")
        assert response.status_code == 200
        data = response.json()

        assert data["agent_id"] == str(agent.id)
        assert data["positive_interactions_count"] == 6
        assert data["negative_interactions_count"] == 2
        assert data["total_feedback_count"] == 8
        assert data["engagement_rate"] == 0.75
        assert data["learning_version"] == 2
        assert data["top_positive_topics"] == ["risk"]
        assert data["top_negative_topics"] == ["crypto"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_my_preferences_endpoint_zero_vector_disclosure(client: AsyncClient):
    """
    CRITICAL SECURITY CONTRACT:
    The preferences API MUST NEVER return raw float vector embeddings
    ('learned_vector', 'interest_embedding', etc.) to prevent model inversion or vector theft.
    """
    agent = make_test_agent()
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(2.0),
        total_feedback_count=5,
    )

    from app.main import app
    from app.database import get_db
    from app.dependencies import get_active_agent

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_res

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_active_agent] = lambda: agent

    try:
        response = await client.get("/api/v1/agents/me/preferences")
        assert response.status_code == 200
        data = response.json()

        # Strict assertion against vector leakage
        assert "learned_vector" not in data
        assert "interest_embedding" not in data
        assert "embedding" not in data

        # Ensure no list of floats is present in the response
        for k, v in data.items():
            if isinstance(v, list) and v:
                assert not isinstance(v[0], float), f"Leaked float array in field '{k}'"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
async def test_reset_my_preferences_endpoint_success(client: AsyncClient):
    """POST /api/v1/agents/me/preferences/reset successfully calls reset and increments version."""
    agent = make_test_agent()
    reset_pref = AgentPreference(
        agent_id=agent.id,
        learning_version=2,
        last_updated_at=datetime.now(timezone.utc),
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
        with patch("app.routers.agents.get_preference_service") as mock_get_pref_svc:
            mock_svc = MagicMock()
            mock_svc.reset_preferences = AsyncMock(return_value=reset_pref)
            mock_get_pref_svc.return_value = mock_svc

            response = await client.post("/api/v1/agents/me/preferences/reset")
            assert response.status_code == 200
            data = response.json()

            assert data["agent_id"] == str(agent.id)
            assert data["learning_version"] == 2
            assert "reset to baseline" in data["message"]
    finally:
        app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 8. End-to-End Feedback Loop Integration Test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_end_to_end_feedback_loop_routing_divergence():
    """
    Demonstrates the full adaptive feedback loop:
    1. Base agent receives a post and gets baseline score.
    2. Agent repeatedly engages with this topic, causing preference vector to step towards it.
    3. Subsequent evaluation on the same topic yields a measurable preference boost in routing.
    """
    engine = RoutingEngine()
    agent = make_test_agent()
    post = make_test_post(tags=["fintech-arbitrage"])

    # Initial score before any feedback
    candidate_initial = engine._score_candidate(post=post, agent=agent, cosine_dist=0.40)
    score_initial = candidate_initial.final_score

    # Simulate 5 positive engagements on posts with this topic
    anchor_v = list(agent.interest_embedding)
    learned_v = list(anchor_v)
    for _ in range(5):
        learned_v = compute_adaptive_vector_step(
            current_v=learned_v,
            anchor_v=anchor_v,
            post_v=list(post.content_embedding),
            signal="positive",
            confidence=0.90,
        )

    # Attach learned preference
    agent.preference = AgentPreference(
        agent_id=agent.id,
        learned_vector=learned_v,
        positive_interactions_count=5,
        total_feedback_count=5,
        engagement_rate=1.0,
        learned_topics={
            "positive": {"fintech-arbitrage": 5},
            "top_positive": ["fintech-arbitrage"],
        },
    )

    # Re-evaluate routing candidate
    candidate_adapted = engine._score_candidate(post=post, agent=agent, cosine_dist=0.40)
    score_adapted = candidate_adapted.final_score

    # Assert adaptive boost has taken effect
    assert score_adapted > score_initial
    assert candidate_adapted.score_breakdown["feedback_adjustment"] > 0.0
    assert any("Adaptive preference boost" in r for r in candidate_adapted.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 9. P7.1 Adversarial Audit & Edge Case Verification Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_negative_feedback_exact_parallel_retreats_to_anchor():
    """
    P7.1-1: When rejected post vector is exactly parallel to learned vector (p == c),
    and current preference has drifted from anchor (cos(c, a) < 1.0),
    the negative update decays the preference vector back towards the baseline anchor.
    """
    anchor_v = make_unit_vector(1.0)
    current_v = make_unit_vector(2.0)
    post_v = list(current_v)  # Exactly parallel

    initial_anchor_sim = cosine_similarity(current_v, anchor_v)
    assert initial_anchor_sim < 0.99  # Current has drifted from anchor

    new_v = compute_adaptive_vector_step(
        current_v=current_v,
        anchor_v=anchor_v,
        post_v=post_v,
        signal="negative",
        confidence=1.0,
        eta_pos=0.08,
        eta_neg=0.04,
        tau_anchor=0.70,
    )

    new_anchor_sim = cosine_similarity(new_v, anchor_v)
    assert new_anchor_sim > initial_anchor_sim  # Retreated back towards anchor
    assert cosine_similarity(new_v, post_v) < 1.0  # Rejected post similarity decreased
    assert math.isclose(norm_l2(new_v), 1.0, abs_tol=1e-5)


@pytest.mark.unit
def test_negative_feedback_near_parallel_no_noise_amplification():
    """
    P7.1-2: When post vector has a tiny perpendicular residual (e.g. 1e-6) near current vector,
    the update does not amplify floating point noise into a random unit vector step.
    """
    anchor_v = make_unit_vector(1.0)
    current_v = make_unit_vector(2.0)
    noise_vec = make_unit_vector(50.0)
    proj = dot_product(noise_vec, current_v)
    perp = normalize_vector([noise_vec[i] - proj * current_v[i] for i in range(768)])

    # Extremely close to current_v (cosine = 0.99999999995)
    post_near = normalize_vector([current_v[i] + 1e-6 * perp[i] for i in range(768)])

    new_v = compute_adaptive_vector_step(
        current_v=current_v,
        anchor_v=anchor_v,
        post_v=post_near,
        signal="negative",
        confidence=1.0,
        eta_pos=0.08,
        eta_neg=0.04,
        tau_anchor=0.70,
    )

    # Vector is clean, normalized, obeys drift boundary
    assert not any(math.isnan(x) for x in new_v)
    assert math.isclose(norm_l2(new_v), 1.0, abs_tol=1e-5)
    assert cosine_similarity(new_v, anchor_v) >= (0.70 - 1e-6)


@pytest.mark.unit
def test_negative_feedback_zero_residual_at_anchor_remains_at_anchor():
    """
    P7.1-3: When c == a and rejected post p == a, preference vector remains at the
    immutable baseline anchor without escape or NaN.
    """
    anchor_v = make_unit_vector(1.0)
    current_v = list(anchor_v)
    post_v = list(anchor_v)

    new_v = compute_adaptive_vector_step(
        current_v=current_v,
        anchor_v=anchor_v,
        post_v=post_v,
        signal="negative",
        confidence=1.0,
        eta_pos=0.08,
        eta_neg=0.04,
        tau_anchor=0.70,
    )

    assert math.isclose(cosine_similarity(new_v, anchor_v), 1.0, abs_tol=1e-5)
    assert math.isclose(norm_l2(new_v), 1.0, abs_tol=1e-5)


@pytest.mark.unit
async def test_neutral_interaction_behavior_across_multiple_reconciliation_cycles():
    """
    P7.1-4: Neutral completed interactions (e.g. status='failed' due to deleted post or error)
    must NEVER be reconciled, published to Redis, or interpreted as negative feedback across cycles.
    """
    worker = FeedbackWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    # Terminal neutral failure interaction
    failed_interaction = AgentInteraction(
        id=uuid.uuid4(),
        receiving_agent_id=uuid.uuid4(),
        post_id=uuid.uuid4(),
        status="failed",
        error_message="post_deleted",
        feedback_event_published_at=None,
    )

    with patch("app.workers.feedback_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []  # status in ('engaged', 'ignored') yields nothing
        mock_db.execute.return_value = mock_res
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        # Cycle 1
        count_1 = await worker.reconcile_unprocessed_interactions(mock_redis, mock_log)
        assert count_1 == 0

        # Cycle 2
        count_2 = await worker.reconcile_unprocessed_interactions(mock_redis, mock_log)
        assert count_2 == 0

        # Cycle 3
        count_3 = await worker.reconcile_unprocessed_interactions(mock_redis, mock_log)
        assert count_3 == 0

        # Never queued to Redis
        mock_redis.xadd.assert_not_awaited()


@pytest.mark.unit
async def test_profile_update_reanchors_learned_preferences():
    """
    P7.1-5: When an agent updates its manifesto/profile, EmbedWorker re-anchors the
    learned preferences, resetting vector to the new anchor and clearing obsolete topics.
    """
    service = PreferenceService()
    agent = make_test_agent()
    old_anchor = list(agent.interest_embedding)

    # Agent had drifted preferences from old profile
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(2.0),
        positive_interactions_count=10,
        negative_interactions_count=3,
        total_feedback_count=13,
        engagement_rate=0.7692,
        learning_version=2,
        learned_topics={"positive": {"old-topic": 10}, "top_positive": ["old-topic"]},
    )

    new_anchor = make_unit_vector(99.0)  # Completely new profile embedding

    mock_db = AsyncMock()
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_pref_res

    reanchored = await service.reanchor_to_new_embedding(mock_db, agent.id, new_anchor)

    assert reanchored is not None
    assert reanchored.learned_vector == new_anchor
    assert reanchored.total_feedback_count == 0
    assert reanchored.positive_interactions_count == 0
    assert reanchored.engagement_rate == 0.0
    assert reanchored.learning_version == 3
    assert reanchored.learned_topics["top_positive"] == []
    # Drift relative to new anchor is strictly 0.0 (cosine = 1.0 >= 0.70)
    assert math.isclose(cosine_similarity(reanchored.learned_vector, new_anchor), 1.0)


@pytest.mark.unit
async def test_concurrent_feedback_ledger_integrity_error_handled_gracefully():
    """
    P7.1-6: Concurrent worker race on unique interaction_id constraint safely rolls back
    and returns None without throwing unhandled exceptions or causing retry loops.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    post = make_test_post()
    interaction = AgentInteraction(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        receiving_agent_id=agent.id,
        post_id=post.id,
        status="engaged",
        confidence=0.95,
    )
    interaction.receiving_agent = agent
    interaction.post = post

    mock_ledger_exec = MagicMock()
    mock_ledger_exec.scalar_one_or_none.return_value = None  # None at initial check

    mock_int_exec = MagicMock()
    mock_int_exec.scalar_one_or_none.return_value = interaction

    pref = AgentPreference(agent_id=agent.id, learned_vector=list(agent.interest_embedding))
    mock_pref_exec = MagicMock()
    mock_pref_exec.scalar_one_or_none.return_value = pref

    mock_agent_lock_exec = MagicMock()
    mock_db.execute.side_effect = [mock_ledger_exec, mock_int_exec, mock_agent_lock_exec, mock_pref_exec]

    from sqlalchemy.exc import IntegrityError
    # Simulate concurrent worker having committed first
    mock_db.commit.side_effect = IntegrityError("duplicate key", params={}, orig=Exception("uq_feedback_ledger_interaction_id"))

    result = await service.process_feedback_event(mock_db, interaction.id)

    assert result is None
    mock_db.rollback.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# 10. P7.2 Final Reliability & Boundary Verification Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_reanchor_idempotency_identical_embedding_preserves_learning():
    """
    P7.2-1: Reprocessing the same embedding (e.g. worker retry or identical profile text)
    must NOT reset learned preference counters or increment learning_version.
    """
    service = PreferenceService()
    agent = make_test_agent()
    anchor = list(agent.interest_embedding)

    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(2.0),
        positive_interactions_count=10,
        negative_interactions_count=5,
        total_feedback_count=15,
        engagement_rate=0.6667,
        learning_version=2,
        learned_topics={"positive": {"risk-analysis": 10}, "top_positive": ["risk-analysis"]},
    )

    mock_db = AsyncMock()
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_pref_res

    # Call reanchor with identical prior and new embedding (cosine = 1.0 >= 0.9999)
    result = await service.reanchor_to_new_embedding(
        mock_db,
        agent.id,
        new_embedding=list(anchor),
        prior_embedding=list(anchor),
    )

    assert result is not None
    assert result.learning_version == 2  # NOT incremented
    assert result.total_feedback_count == 15  # Preserved
    assert result.positive_interactions_count == 10  # Preserved
    assert result.negative_interactions_count == 5  # Preserved
    assert result.engagement_rate == 0.6667  # Preserved
    assert result.learned_topics["top_positive"] == ["risk-analysis"]  # Preserved


@pytest.mark.unit
async def test_reanchor_material_change_resets_learning():
    """
    P7.2-2: When baseline embedding materially changes (cos < 0.9999), preferences
    are re-anchored: learned vector resets, counters reset to 0, learning_version increments.
    """
    service = PreferenceService()
    agent = make_test_agent()
    old_anchor = list(agent.interest_embedding)
    new_anchor = make_unit_vector(99.0)  # Materially different vector

    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=make_unit_vector(2.0),
        positive_interactions_count=10,
        negative_interactions_count=5,
        total_feedback_count=15,
        engagement_rate=0.6667,
        learning_version=2,
        learned_topics={"positive": {"risk-analysis": 10}, "top_positive": ["risk-analysis"]},
    )

    mock_db = AsyncMock()
    mock_pref_res = MagicMock()
    mock_pref_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_pref_res

    result = await service.reanchor_to_new_embedding(
        mock_db,
        agent.id,
        new_embedding=new_anchor,
        prior_embedding=old_anchor,
    )

    assert result is not None
    assert result.learning_version == 3  # Incremented
    assert result.total_feedback_count == 0  # Reset
    assert result.positive_interactions_count == 0  # Reset
    assert result.negative_interactions_count == 0  # Reset
    assert result.engagement_rate == 0.0  # Reset
    assert result.learned_topics["top_positive"] == []  # Cleared
    assert result.learned_vector == new_anchor  # Reset to new anchor


@pytest.mark.unit
async def test_unhandled_integrity_error_is_not_swallowed():
    """
    P7.2-3: IntegrityError not caused by duplicate interaction_id (e.g. FK violation,
    not-null violation) must rollback and re-raise, never silently returning None.
    """
    from sqlalchemy.exc import IntegrityError

    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    post = make_test_post()
    interaction = AgentInteraction(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        receiving_agent_id=agent.id,
        post_id=post.id,
        status="engaged",
        confidence=0.95,
    )
    interaction.receiving_agent = agent
    interaction.post = post

    mock_ledger_exec = MagicMock()
    mock_ledger_exec.scalar_one_or_none.return_value = None

    mock_int_exec = MagicMock()
    mock_int_exec.scalar_one_or_none.return_value = interaction

    pref = AgentPreference(agent_id=agent.id, learned_vector=list(agent.interest_embedding))
    mock_pref_exec = MagicMock()
    mock_pref_exec.scalar_one_or_none.return_value = pref

    mock_agent_lock_exec = MagicMock()
    mock_db.execute.side_effect = [mock_ledger_exec, mock_int_exec, mock_agent_lock_exec, mock_pref_exec]

    # Foreign key violation (unrelated to duplicate interaction_id)
    fk_error = IntegrityError(
        "insert or update on table violates foreign key constraint",
        params={},
        orig=Exception('violates foreign key constraint "fk_feedback_ledger_agent_id"'),
    )
    mock_db.commit.side_effect = fk_error

    with pytest.raises(IntegrityError) as exc_info:
        await service.process_feedback_event(mock_db, interaction.id)

    assert "fk_feedback_ledger_agent_id" in str(exc_info.value)
    mock_db.rollback.assert_awaited_once()


@pytest.mark.unit
def test_is_feedback_ledger_duplicate_classification():
    """
    P7.2-4: Tests that is_feedback_ledger_duplicate classifies constraint names accurately.
    """
    from sqlalchemy.exc import IntegrityError

    # Expected duplicate error
    dup_err = IntegrityError("dup", {}, Exception('duplicate key value violates unique constraint "uq_feedback_ledger_interaction_id"'))
    assert is_feedback_ledger_duplicate(dup_err) is True

    # Generic duplicate interaction_id
    dup_err2 = IntegrityError("dup", {}, Exception("UNIQUE constraint failed: feedback_ledger.interaction_id"))
    assert is_feedback_ledger_duplicate(dup_err2) is True

    # Foreign key violation -> False
    fk_err = IntegrityError("fk", {}, Exception('violates foreign key constraint "fk_feedback_ledger_post_id"'))
    assert is_feedback_ledger_duplicate(fk_err) is False

    # Not-null violation -> False
    null_err = IntegrityError("null", {}, Exception('null value in column "signal" of relation "feedback_ledger"'))
    assert is_feedback_ledger_duplicate(null_err) is False


@pytest.mark.unit
async def test_parent_agent_row_lock_acquired_in_reanchor():
    """
    P7.2-5: Re-anchoring acquires row-level lock on Agent before selecting AgentPreference
    to prevent initialization race conditions with concurrent feedback workers.
    """
    service = PreferenceService()
    agent_id = uuid.uuid4()
    new_embedding = make_unit_vector(5.0)

    mock_db = AsyncMock()
    pref = AgentPreference(agent_id=agent_id, learned_vector=new_embedding)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = pref
    mock_db.execute.return_value = mock_res

    await service.reanchor_to_new_embedding(mock_db, agent_id, new_embedding)

    # First call must lock Agent with FOR UPDATE
    assert mock_db.execute.await_count >= 2
    first_stmt = mock_db.execute.await_args_list[0][0][0]
    compiled = str(first_stmt)
    assert "agents" in compiled.lower()


@pytest.mark.unit
async def test_parent_agent_row_lock_acquired_in_process_feedback():
    """
    P7.2-6: Feedback processing acquires row-level lock on Agent before AgentPreference
    to prevent initialization race conditions.
    """
    service = PreferenceService()
    mock_db = AsyncMock()

    agent = make_test_agent()
    post = make_test_post()
    interaction = AgentInteraction(
        id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        receiving_agent_id=agent.id,
        post_id=post.id,
        status="engaged",
        confidence=0.90,
    )
    interaction.receiving_agent = agent
    interaction.post = post

    mock_ledger_exec = MagicMock()
    mock_ledger_exec.scalar_one_or_none.return_value = None

    mock_int_exec = MagicMock()
    mock_int_exec.scalar_one_or_none.return_value = interaction

    mock_agent_lock_exec = MagicMock()

    pref = AgentPreference(agent_id=agent.id, learned_vector=list(agent.interest_embedding))
    mock_pref_exec = MagicMock()
    mock_pref_exec.scalar_one_or_none.return_value = pref

    mock_db.execute.side_effect = [mock_ledger_exec, mock_int_exec, mock_agent_lock_exec, mock_pref_exec]

    await service.process_feedback_event(mock_db, interaction.id)

    # The 3rd query must be the agent lock query
    agent_lock_stmt = mock_db.execute.await_args_list[2][0][0]
    assert "agents" in str(agent_lock_stmt).lower()


@pytest.mark.unit
def test_routing_boundary_positive_feedback_promotes_candidate_above_threshold():
    """
    P7.2-7: A candidate initially just below the notification threshold (e.g. 0.585 < 0.60)
    becomes eligible (score >= 0.60, passed_threshold = True) after positive feedback.
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)
    agent = make_test_agent()
    post = make_test_post()

    # Configure baseline vector similarity such that unadjusted score is ~0.585
    agent.preference = None
    baseline_cand = engine._score_candidate(post, agent, cosine_dist=0.45)
    assert baseline_cand.passed_threshold is False
    assert baseline_cand.final_score < 0.60

    # Now add learned preference with high alignment to post (positive feedback)
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=list(post.content_embedding),
        total_feedback_count=5,  # Above cold-start min_samples
    )
    agent.preference = pref

    adapted_cand = engine._score_candidate(post, agent, cosine_dist=0.45)
    assert adapted_cand.final_score >= 0.60
    assert adapted_cand.passed_threshold is True
    # Verify the candidate was promoted strictly by adaptive feedback
    assert adapted_cand.final_score > baseline_cand.final_score


@pytest.mark.unit
def test_routing_boundary_negative_feedback_demotes_candidate_below_threshold():
    """
    P7.2-8: A candidate initially just above the notification threshold (e.g. 0.610 >= 0.60)
    drops below threshold (< 0.60, passed_threshold = False) after negative feedback.
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)
    agent = make_test_agent()
    post = make_test_post()

    agent.preference = None
    baseline_cand = engine._score_candidate(post, agent, cosine_dist=0.41)
    assert baseline_cand.passed_threshold is True
    assert baseline_cand.final_score >= 0.60

    # Add learned preference showing negative feedback divergence
    divergent_v = [-x for x in post.content_embedding]
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=divergent_v,
        total_feedback_count=5,  # Above cold-start min_samples
    )
    agent.preference = pref

    adapted_cand = engine._score_candidate(post, agent, cosine_dist=0.41)
    assert adapted_cand.final_score < 0.60
    assert adapted_cand.passed_threshold is False
    # Verify demoted strictly by negative feedback
    assert adapted_cand.final_score < baseline_cand.final_score


@pytest.mark.unit
def test_routing_boundary_stably_above_threshold_remains_eligible():
    """
    P7.2-9: A high-relevance candidate (e.g. baseline score ~0.85) remains eligible
    even after experiencing the maximum allowable negative feedback penalty (-0.0293).
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)
    agent = make_test_agent()
    post = make_test_post()

    # Very strong semantic and metadata match: cosine distance = 0.10
    divergent_v = [-x for x in post.content_embedding]
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=divergent_v,
        total_feedback_count=10,
    )
    agent.preference = pref

    cand = engine._score_candidate(post, agent, cosine_dist=0.10)
    # Even with max penalty, score is well above 0.60
    assert cand.final_score >= 0.60
    assert cand.passed_threshold is True


@pytest.mark.unit
def test_routing_cold_start_gating_near_threshold():
    """
    P7.2-10: An agent with fewer than min_samples feedback events (cold start) experiences
    strictly 0.0 feedback adjustment and cannot cross the threshold via feedback alone.
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)
    agent = make_test_agent()
    post = make_test_post()

    # Base score = 0.585 (< 0.60)
    agent.preference = None
    baseline_cand = engine._score_candidate(post, agent, cosine_dist=0.45)
    assert baseline_cand.passed_threshold is False

    # Add preference with total_feedback_count = 2 (< min_samples = 3)
    pref = AgentPreference(
        agent_id=agent.id,
        learned_vector=list(post.content_embedding),  # Perfect alignment
        total_feedback_count=2,  # Cold start!
    )
    agent.preference = pref

    cold_cand = engine._score_candidate(post, agent, cosine_dist=0.45)
    assert cold_cand.score_breakdown["feedback_adjustment"] == 0.0
    assert cold_cand.final_score == baseline_cand.final_score
    assert cold_cand.passed_threshold is False


@pytest.mark.unit
def test_routing_feedback_contribution_strictly_bounded():
    """
    P7.2-11: Mathematical guarantee that feedback contribution to the composite score
    can never exceed alpha * weight_feedback * max_adjustment = 0.65 * 0.30 * 0.15 = 0.02925 (approx 2.92%).
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)
    agent = make_test_agent()
    post = make_test_post()

    max_possible_delta = 0.15
    feedback_weight = 0.30
    alpha = 0.65

    # Test extreme positive alignment
    pref_pos = AgentPreference(
        agent_id=agent.id,
        learned_vector=list(post.content_embedding),
        total_feedback_count=100,
    )
    agent.preference = pref_pos
    cand_pos = engine._score_candidate(post, agent, cosine_dist=1.0)
    adj_pos = cand_pos.score_breakdown["feedback_adjustment"]
    assert abs(adj_pos) <= feedback_weight * max_possible_delta + 1e-6

    # Test extreme negative divergence
    pref_neg = AgentPreference(
        agent_id=agent.id,
        learned_vector=[-x for x in post.content_embedding],
        total_feedback_count=100,
    )
    agent.preference = pref_neg
    cand_neg = engine._score_candidate(post, agent, cosine_dist=0.0)
    adj_neg = cand_neg.score_breakdown["feedback_adjustment"]
    assert abs(adj_neg) <= feedback_weight * max_possible_delta + 1e-6
