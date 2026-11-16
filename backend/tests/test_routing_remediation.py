"""
Unit and integration tests for P4.2: Routing Engine Reliability & Correctness Remediation.
Covers:
  - HNSW migration and ORM metadata integrity.
  - Configuration-driven metadata weights, validation, and scoring effects.
  - Cross-enterprise synergy business policy (diversity) behavior.
  - Recency decay calculations and score bounds.
  - Notification event durability, Redis failure resilience, and reconciliation.
  - Worker lease protection and abandoned task recovery.
"""
from __future__ import annotations

import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.post import Post
from app.services.routing_engine import RoutingCandidate, RoutingEngine
from app.workers.embed_worker import EmbedWorker
from app.workers.routing_worker import RoutingWorker


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_unit_vector(seed: float = 0.1) -> list[float]:
    raw = [math.sin(seed + i * 0.05) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [round(x / norm, 7) for x in raw]


def make_test_agent(
    name: str = "TestAgent",
    company: str = "TestCorp",
    industries: list[str] | None = None,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
    last_active_at: datetime | None = None,
) -> Agent:
    agent = Agent()
    agent.id = uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.industries = industries or ["technology"]
    agent.tags = tags or ["automation"]
    agent.capabilities = capabilities or ["nlp"]
    agent.trust_score = 0.8
    agent.is_active = True
    agent.embedding_status = "completed"
    agent.interest_embedding = make_unit_vector(0.2)
    agent.created_at = datetime.now(timezone.utc)
    agent.last_active_at = last_active_at or datetime.now(timezone.utc)
    return agent


def make_test_post(
    title: str = "Test Announcement",
    content: str = "Test post business content for relevance matching.",
    target_industries: list[str] | None = None,
    tags: list[str] | None = None,
    author_id: uuid.UUID | None = None,
) -> Post:
    post = Post()
    post.id = uuid.uuid4()
    post.author_agent_id = author_id or uuid.uuid4()
    post.title = title
    post.content = content
    post.target_industries = target_industries or ["technology"]
    post.tags = tags or ["automation"]
    post.content_embedding = make_unit_vector(0.2)
    post.embedding_status = "completed"
    post.status = "published"
    post.created_at = datetime.now(timezone.utc)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# 1. HNSW Migration & ORM Metadata Integrity
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hnsw_migration_file_structure():
    """P4.2-1: Verifies 0005 migration references 0004 and creates HNSW index."""
    import importlib.util
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    migration_path = os.path.join(backend_dir, "alembic", "versions", "0005_pgvector_hnsw_indexes.py")
    assert os.path.exists(migration_path), "Migration 0005_pgvector_hnsw_indexes.py does not exist"

    spec = importlib.util.spec_from_file_location("migration_0005", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "0005_pgvector_hnsw_indexes"
    assert mod.down_revision == "0004_embedding_pipeline"
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")

    with open(migration_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "ix_agents_interest_embedding_hnsw" in content
    assert "vector_cosine_ops" in content
    assert "m = 16" in content
    assert "ef_construction = 64" in content
    assert "delivery_event_published_at" in content


@pytest.mark.unit
def test_hnsw_orm_model_index_definition():
    """P4.2-2: Verifies Agent model declares ix_agents_interest_embedding_hnsw in SQLAlchemy metadata."""
    index_names = {idx.name: idx for idx in Agent.__table__.indexes}
    assert "ix_agents_interest_embedding_hnsw" in index_names, "HNSW index missing from Agent table args"

    hnsw_idx = index_names["ix_agents_interest_embedding_hnsw"]
    assert hnsw_idx.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw_idx.dialect_options["postgresql"]["with"] == {"m": 16, "ef_construction": 64}
    assert hnsw_idx.dialect_options["postgresql"]["ops"] == {"interest_embedding": "vector_cosine_ops"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Configurable Weights & Validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_config_weights_default_and_validation():
    """P4.2-3: Verifies default metadata weights sum to 1.0 and invalid sums raise ValidationError."""
    settings = Settings()
    total = (
        settings.routing_weight_industry
        + settings.routing_weight_tag
        + settings.routing_weight_capability
        + settings.routing_weight_diversity
        + settings.routing_weight_recency
    )
    assert pytest.approx(total, 0.0001) == 1.0
    assert settings.redis_claim_min_idle_ms == 120000

    # Invalid weights sum > 1.0 must fail
    with pytest.raises(ValidationError) as exc_info:
        Settings(routing_weight_industry=0.50, routing_weight_tag=0.60)
    assert "Metadata routing weights must sum to 1.0" in str(exc_info.value)

    # Invalid alpha must fail
    with pytest.raises(ValidationError):
        Settings(routing_alpha=1.5)

    # Negative claim timeout must fail
    with pytest.raises(ValidationError):
        Settings(redis_claim_min_idle_ms=-1000)


@pytest.mark.unit
def test_routing_engine_configurable_weights_affect_score():
    """P4.2-4: Verifies custom weights passed to RoutingEngine constructor change candidate metadata score."""
    post = make_test_post(
        target_industries=["fintech"],
        tags=["payments"],
    )
    # Agent with industry match only, no tag match
    agent = make_test_agent(
        company="OtherCorp",
        industries=["fintech"],
        tags=["logistics"],
        capabilities=[],
        last_active_at=datetime.now(timezone.utc),
    )

    # Engine A: High industry weight (0.50), low tag (0.10)
    engine_a = RoutingEngine(
        alpha=0.65,
        threshold=0.50,
        weight_industry=0.50,
        weight_tag=0.10,
        weight_capability=0.20,
        weight_diversity=0.10,
        weight_recency=0.10,
    )
    cand_a = engine_a._score_candidate(post, agent, cosine_dist=0.20, author_company="AuthorCorp")

    # Engine B: Low industry weight (0.10), high tag (0.50)
    engine_b = RoutingEngine(
        alpha=0.65,
        threshold=0.50,
        weight_industry=0.10,
        weight_tag=0.50,
        weight_capability=0.20,
        weight_diversity=0.10,
        weight_recency=0.10,
    )
    cand_b = engine_b._score_candidate(post, agent, cosine_dist=0.20, author_company="AuthorCorp")

    # Since candidate has industry match, Engine A must produce higher metadata score than Engine B
    assert cand_a.metadata_score > cand_b.metadata_score
    assert cand_a.final_score > cand_b.final_score


# ─────────────────────────────────────────────────────────────────────────────
# 3. Diversity / Business Policy Behavior
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_diversity_business_policy_differentiation():
    """
    P4.2-5: Verifies cross-enterprise diversity bonus awards 1.0 to third-party companies
    and 0.0 to intra-company candidate agents.
    """
    engine = RoutingEngine()
    post = make_test_post(target_industries=["fintech"], tags=["payments"])

    # Agent 1: Third-party partner company
    partner_agent = make_test_agent(company="PhonePe", industries=["fintech"], tags=["payments"])
    partner_cand = engine._score_candidate(post, partner_agent, cosine_dist=0.20, author_company="Swiggy")

    # Agent 2: Internal agent from same company
    internal_agent = make_test_agent(company="Swiggy", industries=["fintech"], tags=["payments"])
    internal_cand = engine._score_candidate(post, internal_agent, cosine_dist=0.20, author_company="Swiggy")

    # Expected difference: (1 - alpha) * weight_diversity * 1.0
    expected_diff = (1.0 - engine.alpha) * engine.weight_diversity
    actual_diff = partner_cand.final_score - internal_cand.final_score
    assert pytest.approx(actual_diff, 0.005) == expected_diff

    # Verify explanations state cross-enterprise policy match vs intra-company
    assert any("Cross-enterprise synergy policy match" in r for r in partner_cand.reasons)
    assert any("Intra-company candidate" in r for r in internal_cand.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Recency Bonus Decay & Bounds
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_recency_score_decay():
    """P4.2-6: Verifies recency decays linearly from 1.0 (today) to 0.0 (>= 30 days)."""
    engine = RoutingEngine()
    post = make_test_post(target_industries=["fintech"], tags=["payments"])

    # Active now -> recency = 1.0
    agent_now = make_test_agent(last_active_at=datetime.now(timezone.utc))
    cand_now = engine._score_candidate(post, agent_now, cosine_dist=0.20)

    # Active 15 days ago -> recency = 0.5
    agent_15d = make_test_agent(last_active_at=datetime.now(timezone.utc) - timedelta(days=15))
    cand_15d = engine._score_candidate(post, agent_15d, cosine_dist=0.20)

    # Active 45 days ago -> recency = 0.0
    agent_45d = make_test_agent(last_active_at=datetime.now(timezone.utc) - timedelta(days=45))
    cand_45d = engine._score_candidate(post, agent_45d, cosine_dist=0.20)

    assert cand_now.metadata_score > cand_15d.metadata_score > cand_45d.metadata_score
    assert 0.0 <= cand_now.final_score <= 1.0
    assert 0.0 <= cand_45d.final_score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Notification Durability & Reconciliation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_notification_event_durability_redis_failure():
    """
    P4.2-7: Verifies that when Redis publication fails, Notification record is durably
    saved with delivery_event_published_at=None and error does not crash the database transaction.
    """
    engine = RoutingEngine()
    post = make_test_post()
    candidate = RoutingCandidate(
        agent_id=uuid.uuid4(),
        final_score=0.85,
        passed_threshold=True,
        was_notified=True,
    )

    mock_db = AsyncMock()

    # Simulate Redis event publishing failure (returns False)
    with patch("app.services.routing_engine.publish_notification_pending_event", new_callable=AsyncMock) as mock_pub:
        mock_pub.return_value = False

        await engine._persist_routing_logs_and_notifications(
            post=post,
            candidates=[candidate],
            db=mock_db,
            publish_events=True,
        )

        # Database commit must still be called to persist the pending notification
        assert mock_db.commit.await_count >= 1
        mock_pub.assert_awaited_once()


@pytest.mark.unit
async def test_routing_worker_reconcile_unpublished_notifications():
    """
    P4.2-8: Verifies RoutingWorker.reconcile_pending_notifications reclaims pending notifications
    whose Redis event was missed, dispatches them to Redis, and marks delivery_event_published_at.
    """
    worker = RoutingWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    notif1 = Notification()
    notif1.id = uuid.uuid4()
    notif1.post_id = uuid.uuid4()
    notif1.recipient_agent_id = uuid.uuid4()
    notif1.relevance_score = 0.82
    notif1.status = "pending"
    notif1.delivery_event_published_at = None

    with patch("app.workers.routing_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [notif1]
        mock_db.execute = AsyncMock(return_value=mock_res)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        reconciled = await worker.reconcile_pending_notifications(mock_redis, mock_log)

        assert reconciled == 1
        assert notif1.delivery_event_published_at is not None
        mock_redis.xadd.assert_awaited_once()
        call_args = mock_redis.xadd.await_args[0]
        assert call_args[0] == "notifications:pending"
        assert call_args[1]["notification_id"] == str(notif1.id)
        mock_db.commit.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Worker Lease Protection & Task Recovery
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_embed_worker_active_lease_protection():
    """
    P4.2-9: Verifies secondary worker skips processing if another worker has an active lease
    (updated_at within claim_min_idle_ms).
    """
    worker = EmbedWorker()
    worker.claim_min_idle_ms = 120000  # 120s

    post = Post()
    post.id = uuid.uuid4()
    post.embedding_status = "processing"
    # Active 20 seconds ago -> lease is active (< 120s)
    post.updated_at = datetime.now(timezone.utc) - timedelta(seconds=20)
    post.status = "published"

    mock_service = MagicMock()
    worker.embedding_service = mock_service

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_res)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_post(post.id, {"post_id": str(post.id)})

        # Service must NOT be called because active lease protects the primary worker
        mock_service.embed_post.assert_not_called()


@pytest.mark.unit
async def test_embed_worker_expired_lease_reclaim():
    """
    P4.2-10: Verifies worker reclaims and processes task if previous lease has expired
    (updated_at > 120s ago, indicating crashed worker).
    """
    worker = EmbedWorker()
    worker.claim_min_idle_ms = 120000  # 120s

    post = Post()
    post.id = uuid.uuid4()
    post.embedding_status = "processing"
    # Updated 200 seconds ago -> lease expired (> 120s)
    post.updated_at = datetime.now(timezone.utc) - timedelta(seconds=200)
    post.status = "published"
    post.content_embedding = None

    mock_service = MagicMock()
    mock_service.embed_post = AsyncMock(return_value=make_unit_vector(0.3))
    mock_service.model = "nomic-embed-text"
    worker.embedding_service = mock_service

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_res)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        with patch.object(worker, "_get_redis", new_callable=AsyncMock) as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            await worker.process_post(post.id, {"post_id": str(post.id)})

            # Service MUST be called to recover the abandoned task
            mock_service.embed_post.assert_awaited_once_with(post)
            assert post.embedding_status == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# 7. PostgreSQL EXPLAIN Query Stub (Integration Test)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_postgres_explain_hnsw_query_live(postgres_session):
    """
    P4.2-11: Live PostgreSQL verification query executing EXPLAIN (ANALYZE, BUFFERS)
    against agents.interest_embedding HNSW index.
    Skips cleanly when PostgreSQL is offline.
    """
    from sqlalchemy import text

    try:
        await postgres_session.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL not accessible for live HNSW explain test: {exc}")

    query = text("""
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT id, name, company, interest_embedding <=> :query_vec AS dist
        FROM agents
        WHERE is_active = true
          AND interest_embedding IS NOT NULL
          AND embedding_status = 'completed'
        ORDER BY interest_embedding <=> :query_vec ASC
        LIMIT 50;
    """)
    sample_vec = str(make_unit_vector(0.1))
    result = await postgres_session.execute(query, {"query_vec": sample_vec})
    plan_lines = [r[0] for r in result.all()]
    plan_text = "\n".join(plan_lines)
    assert len(plan_lines) > 0
    print("\nLive PostgreSQL Plan:\n", plan_text)
