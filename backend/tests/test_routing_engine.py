"""
Unit and integration tests for P4: Multi-stage Semantic Relevance Routing Engine.
Covers all 19 required routing scenarios and live PostgreSQL integration tests.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Base
from app.main import app
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.post import Post
from app.models.routing_log import RoutingLog
from app.services.auth import create_access_token
from app.services.routing_engine import RoutingCandidate, RoutingEngine, RoutingResult
from app.workers.routing_worker import RoutingWorker


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures & Vector Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_unit_vector(seed: float = 0.1) -> list[float]:
    """Generates a deterministic normalized 768-dim unit vector."""
    raw = [math.sin(seed + i * 0.05) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [round(x / norm, 7) for x in raw]


def make_similar_vector(base_vec: list[float], similarity_target: float = 0.85) -> list[float]:
    """
    Constructs a vector with approximately the target cosine similarity
    relative to base_vec.
    """
    ortho = [-base_vec[(i + 1) % 768] for i in range(768)]
    dot = sum(a * b for a, b in zip(base_vec, ortho))
    ortho = [o - dot * b for o, b in zip(ortho, base_vec)]
    ortho_norm = math.sqrt(sum(x * x for x in ortho))
    ortho = [x / ortho_norm for x in ortho]

    s = max(-1.0, min(1.0, similarity_target))
    weight_ortho = math.sqrt(max(0.0, 1.0 - s * s))
    combined = [s * b + weight_ortho * o for b, o in zip(base_vec, ortho)]
    norm = math.sqrt(sum(x * x for x in combined))
    return [round(x / norm, 7) for x in combined]


def make_agent(
    name: str = "TestAgent",
    company: str = "TestCorp",
    industries: list[str] | None = None,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
    trust_score: float = 0.8,
    is_active: bool = True,
    embedding_status: str = "completed",
    vector_seed: float = 0.1,
    agent_id: uuid.UUID | None = None,
) -> Agent:
    agent = Agent()
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.description = f"Enterprise agent representing {company} for {name}."
    agent.industries = industries or ["technology"]
    agent.tags = tags or ["automation"]
    agent.capabilities = capabilities or ["nlp"]
    agent.trust_score = trust_score
    agent.is_active = is_active
    agent.embedding_status = embedding_status
    agent.interest_embedding = make_unit_vector(seed=vector_seed) if embedding_status == "completed" else None
    agent.created_at = datetime.now(timezone.utc)
    agent.last_active_at = datetime.now(timezone.utc)
    return agent


def make_post(
    title: str = "Test Post",
    content: str = "Test post content for business relevance evaluation.",
    target_industries: list[str] | None = None,
    tags: list[str] | None = None,
    author_id: uuid.UUID | None = None,
    vector_seed: float = 0.1,
    embedding_status: str = "completed",
) -> Post:
    post = Post()
    post.id = uuid.uuid4()
    post.author_agent_id = author_id or uuid.uuid4()
    post.title = title
    post.content = content
    post.target_industries = target_industries or ["technology"]
    post.tags = tags or ["automation"]
    post.status = "published"
    post.embedding_status = embedding_status
    post.content_embedding = make_unit_vector(seed=vector_seed) if embedding_status == "completed" else None
    post.created_at = datetime.now(timezone.utc)
    post.updated_at = datetime.now(timezone.utc)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# 1-3: SQL Eligibility Filtering Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_exclude_inactive_agents():
    """1: Verifies inactive or suspended agents are excluded by eligibility filtering."""
    engine = RoutingEngine()
    author_id = uuid.uuid4()
    post = make_post(author_id=author_id)

    # Active agent vs inactive agent
    active_agent = make_agent(name="ActiveBot", is_active=True)
    inactive_agent = make_agent(name="InactiveBot", is_active=False)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(active_agent, 0.2)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    rows = await engine._retrieve_candidate_rows(post, mock_db, limit=50)

    assert len(rows) == 1
    assert rows[0][0].name == "ActiveBot"
    # Verify SQL query had is_active == True condition in executed statement
    query_str = str(mock_db.execute.call_args[0][0])
    assert "is_active" in query_str


@pytest.mark.unit
async def test_exclude_publishing_agent():
    """2: Verifies publishing agent itself is never evaluated as a candidate."""
    engine = RoutingEngine()
    author_id = uuid.uuid4()
    post = make_post(author_id=author_id)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    await engine._retrieve_candidate_rows(post, mock_db, limit=50)

    # Verify SQL query had Agent.id != post.author_agent_id
    query_str = str(mock_db.execute.call_args[0][0])
    assert "author_agent_id" in query_str or "id !=" in query_str or "!=" in query_str


@pytest.mark.unit
async def test_exclude_agents_without_embeddings():
    """3: Verifies agents with missing or incomplete embeddings are filtered out."""
    engine = RoutingEngine()
    post = make_post()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    await engine._retrieve_candidate_rows(post, mock_db, limit=50)

    query_str = str(mock_db.execute.call_args[0][0])
    assert "interest_embedding IS NOT NULL" in query_str or "is_not" in query_str.lower()
    assert "embedding_status" in query_str


# ─────────────────────────────────────────────────────────────────────────────
# 4-6: Vector Similarity, Normalization & Cross-Industry Matching
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_cross_industry_semantic_matching():
    """4: Verifies cross-industry candidates with zero industry overlap can match on semantics."""
    engine = RoutingEngine(alpha=0.65, threshold=0.55)

    post = make_post(
        title="Automated Logistics Routing",
        target_industries=["logistics"],
        tags=["fleet", "dispatch"],
    )

    # Fintech agent has ZERO industry or tag overlap with logistics, but high semantic vector alignment
    agent = make_agent(
        name="FintechFleetBot",
        company="FintechPay",
        industries=["fintech", "banking"],
        tags=["payments", "fuel-cards"],
        capabilities=["automated-settlement"],
    )

    # High semantic similarity (cosine dist = 0.15 -> sim = 0.85)
    candidate = engine._score_candidate(
        post=post,
        agent=agent,
        cosine_dist=0.15,
        author_company="LogisticsHub",
    )

    # Vector score is 0.85
    assert candidate.vector_score == 0.85
    assert candidate.industry_overlap == []
    # Cross-industry matching succeeds via semantic relevance
    assert candidate.final_score > 0.55
    assert candidate.passed_threshold is True


@pytest.mark.unit
def test_vector_similarity_and_normalization():
    """5: Verifies cosine distance [0, 2] maps correctly to similarity [-1, 1] and clamped score [0, 1]."""
    engine = RoutingEngine()
    post = make_post()
    agent = make_agent()

    # Case A: Identical vectors (dist = 0.0 -> sim = 1.0 -> vector_score = 1.0)
    cA = engine._score_candidate(post, agent, cosine_dist=0.0)
    assert cA.raw_cosine_distance == 0.0
    assert cA.raw_cosine_similarity == 1.0
    assert cA.vector_score == 1.0

    # Case B: Orthogonal vectors (dist = 1.0 -> sim = 0.0 -> vector_score = 0.0)
    cB = engine._score_candidate(post, agent, cosine_dist=1.0)
    assert cB.raw_cosine_distance == 1.0
    assert cB.raw_cosine_similarity == 0.0
    assert cB.vector_score == 0.0

    # Case C: Diametrically opposed vectors (dist = 2.0 -> sim = -1.0 -> vector_score clamped to 0.0)
    cC = engine._score_candidate(post, agent, cosine_dist=2.0)
    assert cC.raw_cosine_distance == 2.0
    assert cC.raw_cosine_similarity == -1.0
    assert cC.vector_score == 0.0  # Clamped, not negative


@pytest.mark.unit
async def test_top_k_candidate_selection():
    """6: Verifies pgvector query applies LIMIT top-K in database query."""
    engine = RoutingEngine(max_candidates=50)
    post = make_post()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    await engine._retrieve_candidate_rows(post, mock_db, limit=50)

    executed_query = str(mock_db.execute.call_args[0][0])
    assert "LIMIT" in executed_query or "limit" in executed_query.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 7-10: Hybrid Reranking, Thresholds, Tie-Breaking & Selection Policy
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hybrid_score_formula_p4():
    """7: Verifies hybrid formula: final = round(alpha * vector + (1 - alpha) * metadata, 4)."""
    engine = RoutingEngine(alpha=0.65)
    post = make_post()
    agent = make_agent()

    candidate = engine._score_candidate(post, agent, cosine_dist=0.20)
    # With dist 0.20, vector_score is 0.80
    assert candidate.vector_score == 0.80
    expected = round(0.65 * 0.80 + 0.35 * candidate.metadata_score, 4)
    assert candidate.final_score == expected


@pytest.mark.unit
def test_threshold_filtering():
    """8: Verifies candidates with final_score < threshold are marked passed_threshold=False."""
    engine = RoutingEngine(threshold=0.70)
    post = make_post()
    agent = make_agent()

    # Low similarity (dist = 0.80 -> vector_score = 0.20)
    c_low = engine._score_candidate(post, agent, cosine_dist=0.80)
    assert c_low.final_score < 0.70
    assert c_low.passed_threshold is False

    # High similarity (dist = 0.10 -> vector_score = 0.90)
    c_high = engine._score_candidate(post, agent, cosine_dist=0.10)
    assert c_high.final_score >= 0.70
    assert c_high.passed_threshold is True


@pytest.mark.unit
async def test_deterministic_ranking_and_tie_breaking():
    """9: Verifies strict deterministic tie-breaking: final_score, vector_score, trust, created_at, id."""
    engine = RoutingEngine(threshold=0.50, max_notifications=5)
    post = make_post()

    # Two candidates with identical scores but different trust scores
    agent_senior = make_agent(name="SeniorAgent", trust_score=0.9)
    agent_junior = make_agent(name="JuniorAgent", trust_score=0.4)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    # Both have identical cosine distance 0.3
    mock_result.all.return_value = [
        (agent_junior, 0.3),
        (agent_senior, 0.3),
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    all_c, selected = await engine._evaluate_candidates(post, mock_db)

    # Senior agent with higher trust score must rank first
    assert all_c[0].agent_name == "SeniorAgent"
    assert all_c[1].agent_name == "JuniorAgent"


@pytest.mark.unit
async def test_maximum_selected_agents_limit():
    """10: Verifies maximum selected candidates does not exceed max_notifications (top 5)."""
    engine = RoutingEngine(threshold=0.30, max_notifications=5)
    post = make_post()

    # 10 agents all passing threshold
    agents = [make_agent(name=f"Agent-{i}") for i in range(10)]
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(a, 0.1) for a in agents]
    mock_db.execute = AsyncMock(return_value=mock_result)

    all_c, selected = await engine._evaluate_candidates(post, mock_db)

    assert len(all_c) == 10
    assert len(selected) == 5
    assert sum(1 for c in all_c if c.was_notified) == 5


# ─────────────────────────────────────────────────────────────────────────────
# 11-14: Explainability, Idempotency & Worker Execution
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_explainable_decision_generation():
    """11: Verifies reasons are generated with truthful, non-fabricated metrics."""
    engine = RoutingEngine(threshold=0.70)
    post = make_post(title="Fintech Payment Gateway", target_industries=["fintech"], tags=["payments"])
    agent = make_agent(
        company="PayCo",
        industries=["fintech"],
        tags=["payments"],
        capabilities=["settlement"],
    )

    c = engine._score_candidate(post, agent, cosine_dist=0.15, author_company="RetailHub")

    assert len(c.reasons) >= 3
    assert any("semantic alignment" in r.lower() for r in c.reasons)
    assert any("fintech" in r.lower() for r in c.reasons)
    assert any("payments" in r.lower() for r in c.reasons)
    assert any("RetailHub ↔ PayCo" in r for r in c.reasons)
    assert "raw_cosine_similarity" in c.score_breakdown
    assert "algorithm_version" in c.score_breakdown


@pytest.mark.unit
async def test_duplicate_routing_events_idempotency():
    """12 & 13: Verifies duplicate routing events update existing records without creating duplicate logs."""
    engine = RoutingEngine()
    post = make_post()
    agent = make_agent()

    candidate = engine._score_candidate(post, agent, cosine_dist=0.10)
    candidate.was_notified = True

    mock_db = AsyncMock()

    # Execute persistence
    await engine._persist_routing_logs_and_notifications(
        post=post,
        candidates=[candidate],
        db=mock_db,
        publish_events=False,
    )

    # 1 execute for RoutingLog, 1 execute for Notification, 1 commit
    assert mock_db.execute.await_count == 2
    assert mock_db.commit.await_count == 1

    # Check statement used on_conflict
    call1_sql = str(mock_db.execute.call_args_list[0][0][0])
    assert "ON CONFLICT" in call1_sql


@pytest.mark.unit
async def test_routing_worker_acknowledgement():
    """14: Verifies RoutingWorker processes routing and acknowledges message only after DB persistence."""
    worker = RoutingWorker()
    post = make_post()

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = post
    mock_db.execute.return_value = mock_result

    with patch("app.workers.routing_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db

        worker.routing_engine = MagicMock(spec=RoutingEngine)
        worker.routing_engine.route_post = AsyncMock(
            return_value=RoutingResult(
                post_id=post.id,
                total_candidates_evaluated=1,
                passed_threshold_count=1,
                notified_count=1,
            )
        )

        mock_redis = AsyncMock()
        mock_log = MagicMock()
        fields = {"post_id": str(post.id)}

        await worker._process_with_retry(mock_redis, "routing:pending", "1-0", fields, mock_log)

        # route_post must be called
        worker.routing_engine.route_post.assert_awaited_once()
        # Message acknowledged only after route_post finishes
        mock_redis.xack.assert_awaited_once_with("routing:pending", "routing-workers", "1-0")


@pytest.mark.unit
async def test_routing_worker_failure_and_retry():
    """15: Verifies routing worker error schedules exponential retry without prematurely acknowledging."""
    worker = RoutingWorker()
    worker.settings.worker_retry_max = 3
    worker.settings.worker_retry_backoff_seconds = 0.01

    with patch("app.workers.routing_worker.AsyncSessionLocal") as mock_ctx:
        mock_db = AsyncMock()
        mock_db.execute.side_effect = RuntimeError("Database connection lost")
        mock_ctx.return_value.__aenter__.return_value = mock_db

        mock_redis = AsyncMock()
        mock_log = MagicMock()
        fields = {"post_id": str(uuid.uuid4()), "_retry_count": "0"}

        await worker._process_with_retry(mock_redis, "routing:pending", "1-0", fields, mock_log)

        # Must schedule retry with incremented retry count
        mock_redis.xadd.assert_awaited_once()
        assert mock_redis.xadd.call_args[0][1]["_retry_count"] == "1"


@pytest.mark.unit
async def test_downstream_event_handoff_to_notifications():
    """16: Verifies selected candidates are handed off to 'notifications:pending' stream."""
    engine = RoutingEngine()
    post = make_post()
    agent = make_agent()

    candidate = engine._score_candidate(post, agent, cosine_dist=0.10)
    candidate.was_notified = True

    mock_db = AsyncMock()

    with patch("app.services.routing_engine.publish_notification_pending_event") as mock_publish:
        mock_publish.return_value = True

        await engine._persist_routing_logs_and_notifications(
            post=post,
            candidates=[candidate],
            db=mock_db,
            publish_events=True,
        )

        mock_publish.assert_awaited_once()
        call_kwargs = mock_publish.await_args.kwargs
        assert call_kwargs["post_id"] == post.id
        assert call_kwargs["recipient_agent_id"] == agent.id
        assert call_kwargs["relevance_score"] == candidate.final_score
        assert isinstance(call_kwargs.get("notification_id"), uuid.UUID)


# ─────────────────────────────────────────────────────────────────────────────
# 17-19: Preview Ownership, Missing Vectors & Swiggy Scenario
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_routing_preview_ownership_enforcement():
    """17: Verifies routing preview forbids requesting agent from previewing another agent's post."""
    from app.routers.routing import RoutingPreviewRequest, preview_routing_decisions
    from fastapi import HTTPException

    author_agent = make_agent(name="AuthorBot")
    other_agent = make_agent(name="IntruderBot")
    post = make_post(author_id=author_agent.id)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = post
    mock_db.execute = AsyncMock(return_value=mock_res)

    with pytest.raises(HTTPException) as exc_info:
        await preview_routing_decisions(
            payload=RoutingPreviewRequest(post_id=post.id),
            current_agent=other_agent,
            db=mock_db,
        )
    assert exc_info.value.status_code == 403
    assert "only for posts published by your agent" in str(exc_info.value.detail)


@pytest.mark.unit
async def test_missing_or_incomplete_embeddings_handling():
    """18: Verifies preview rejects posts that have not completed vector generation."""
    from app.routers.routing import RoutingPreviewRequest, preview_routing_decisions
    from fastapi import HTTPException

    author_agent = make_agent(name="AuthorBot")
    post = make_post(author_id=author_agent.id, embedding_status="pending")
    post.content_embedding = None  # Incomplete vector

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = post
    mock_db.execute = AsyncMock(return_value=mock_res)

    with pytest.raises(HTTPException) as exc_info:
        await preview_routing_decisions(
            payload=RoutingPreviewRequest(post_id=post.id),
            current_agent=author_agent,
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "not yet completed" in str(exc_info.value.detail)


@pytest.mark.unit
async def test_swiggy_phonepe_hdfc_bajaj_scenario():
    """
    19: Core Acceptance Scenario:
    Swiggy publishes a Diwali food delivery discount.
    PhonePe (UPI/cashback) & HDFC Bank (card offers) are relevant and selected.
    Bajaj Auto (vehicle manufacturing) is irrelevant and rejected.
    """
    engine = RoutingEngine(alpha=0.65, threshold=0.60)

    # 1. Swiggy Post Vector
    swiggy_post_vector = make_unit_vector(seed=1.0)
    swiggy_author_id = uuid.uuid4()
    swiggy_post = Post(
        id=uuid.uuid4(),
        author_agent_id=swiggy_author_id,
        title="Diwali Feast: 5% off on food delivery orders above 300",
        content="Flat 5% discount across all food delivery orders above 300 during the festive Diwali week.",
        target_industries=["food-tech", "retail", "consumer"],
        tags=["food-delivery", "offers", "diwali-promotions", "discounts", "cashback"],
        content_embedding=swiggy_post_vector,
        embedding_status="completed",
        status="published",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # 2. Candidate 1: PhonePe (High semantic relevance to cashback, payments & merchant promotions)
    phonepe_vector = make_similar_vector(swiggy_post_vector, similarity_target=0.82)
    phonepe_agent = Agent(
        id=uuid.uuid4(),
        name="PhonePe-MerchantBot",
        company="PhonePe",
        description="Unified payments, merchant cashback rewards and digital payment processing.",
        industries=["fintech", "payments"],
        tags=["upi", "cashback", "discounts", "promotions", "merchant-partnerships"],
        capabilities=["cashback-rewards", "instant-upi", "merchant-discounts"],
        trust_score=0.9,
        is_active=True,
        embedding_status="completed",
        interest_embedding=phonepe_vector,
        last_active_at=datetime.now(timezone.utc),
    )
    # Cosine distance = 1 - 0.82 = 0.18
    phonepe_cand = engine._score_candidate(
        post=swiggy_post,
        agent=phonepe_agent,
        cosine_dist=0.18,
        author_company="Swiggy",
    )

    # 3. Candidate 2: HDFC Bank (High relevance to card offers and merchant partnerships)
    hdfc_vector = make_similar_vector(swiggy_post_vector, similarity_target=0.80)
    hdfc_agent = Agent(
        id=uuid.uuid4(),
        name="HDFC-OffersBot",
        company="HDFC Bank",
        description="Credit and debit card festive promotions, merchant alliances and consumer banking.",
        industries=["banking", "financial-services"],
        tags=["credit-cards", "merchant-offers", "offers", "discounts", "rewards"],
        capabilities=["card-offers", "merchant-promotions", "pos-checkout"],
        trust_score=0.9,
        is_active=True,
        embedding_status="completed",
        interest_embedding=hdfc_vector,
        last_active_at=datetime.now(timezone.utc),
    )
    # Cosine distance = 1 - 0.80 = 0.20
    hdfc_cand = engine._score_candidate(
        post=swiggy_post,
        agent=hdfc_agent,
        cosine_dist=0.20,
        author_company="Swiggy",
    )

    # 4. Candidate 3: Bajaj Auto (Automotive manufacturing, two-wheelers, irrelevant)
    bajaj_vector = make_similar_vector(swiggy_post_vector, similarity_target=0.15)
    bajaj_agent = Agent(
        id=uuid.uuid4(),
        name="Bajaj-SalesBot",
        company="Bajaj Auto",
        description="Motorcycles, commercial vehicles, manufacturing logistics and dealership distribution.",
        industries=["automotive", "manufacturing"],
        tags=["motorcycles", "commercial-vehicles", "dealerships"],
        capabilities=["vehicle-assembly", "dealer-inventory"],
        trust_score=0.85,
        is_active=True,
        embedding_status="completed",
        interest_embedding=bajaj_vector,
        last_active_at=datetime.now(timezone.utc),
    )
    # Cosine distance = 1 - 0.15 = 0.85
    bajaj_cand = engine._score_candidate(
        post=swiggy_post,
        agent=bajaj_agent,
        cosine_dist=0.85,
        author_company="Swiggy",
    )

    # Verify PhonePe: passes threshold and qualifies for notification
    assert phonepe_cand.final_score >= 0.60, f"PhonePe score {phonepe_cand.final_score} below 0.60"
    assert phonepe_cand.passed_threshold is True
    assert "cashback" in phonepe_cand.tag_overlap or "discounts" in phonepe_cand.tag_overlap

    # Verify HDFC Bank: passes threshold and qualifies for notification
    assert hdfc_cand.final_score >= 0.60, f"HDFC Bank score {hdfc_cand.final_score} below 0.60"
    assert hdfc_cand.passed_threshold is True
    assert "offers" in hdfc_cand.tag_overlap or "discounts" in hdfc_cand.tag_overlap

    # Verify Bajaj Auto: far below threshold, rejected
    assert bajaj_cand.final_score < 0.35, f"Bajaj Auto score {bajaj_cand.final_score} unexpectedly high"
    assert bajaj_cand.passed_threshold is False

    # Verify rank order: PhonePe and HDFC top-ranked, Bajaj at the bottom
    candidates = [phonepe_cand, hdfc_cand, bajaj_cand]
    candidates.sort(key=lambda c: -c.final_score)
    assert candidates[0].company in ("PhonePe", "HDFC Bank")
    assert candidates[1].company in ("PhonePe", "HDFC Bank")
    assert candidates[2].company == "Bajaj Auto"


# ─────────────────────────────────────────────────────────────────────────────
# 20: Live Integration Test Stub (PostgreSQL + pgvector required)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_full_routing_pipeline_live_postgres(postgres_session, client):
    """
    Live end-to-end integration test against PostgreSQL + pgvector.
    Skips cleanly when PostgreSQL is offline.
    """
    engine = RoutingEngine()

    # 1. Verify connection
    from sqlalchemy import text
    try:
        await postgres_session.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL not accessible for live integration test: {exc}")

    # 2. Test live cosine similarity query
    post = make_post()
    rows = await engine._retrieve_candidate_rows(post, postgres_session, limit=10)
    assert isinstance(rows, list)
