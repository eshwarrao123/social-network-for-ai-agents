"""
Comprehensive unit and integration tests for P3: Semantic Embedding Pipeline & Vector Generation.

Tests cover:
  Embedding Service:
    1. Correct Ollama request construction
    2. Correct model selection
    3. Response parsing
    4. 768-dimensional validation
    5. Invalid dimensions rejection
    6. Invalid numeric values rejection (NaN, Inf, all zeros)
    7. Timeout handling
    8. Ollama unavailable handling

  Text Construction:
    9. Deterministic post embedding text
    10. Deterministic agent interest text
    11. Correct document and query prefixes (search_query: for posts, search_document: for agents)

  Pipeline:
    12. Post embedding persistence
    13. Agent embedding persistence
    14. Re-embedding after post updates
    15. Re-embedding after agent profile updates
    16. Duplicate event handling (idempotency)
    17. Stale event protection
    18. Retry behaviour with exponential backoff
    19. Dead-letter handling after retry exhaustion
    20. Successful acknowledgement after persistence
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.agent import Agent
from app.models.post import Post
from app.services.embedding import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    NOMIC_DOC_PREFIX,
    NOMIC_QUERY_PREFIX,
    EmbeddingConnectionError,
    EmbeddingDimensionError,
    EmbeddingResponseError,
    EmbeddingService,
    EmbeddingValueError,
    OllamaEmbeddingProvider,
    build_agent_text,
    build_post_text,
)
from app.workers.embed_worker import EmbedWorker


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_valid_vector(dim: int = DEFAULT_EMBEDDING_DIMENSIONS, seed: float = 0.05) -> list[float]:
    """Generates a synthetic non-zero vector of valid floats."""
    return [seed * (i % 10 + 1) for i in range(dim)]


def make_mock_agent(
    agent_id: uuid.UUID | None = None,
    name: str = "FinanceBot-Alpha",
    company: str = "Meridian Capital",
    description: str = "Monitors financial markets, regulatory changes, and liquidity risk.",
    industries: list[str] | None = None,
    capabilities: list[str] | None = None,
    tags: list[str] | None = None,
    is_active: bool = True,
) -> Agent:
    agent = MagicMock(spec=Agent)
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.description = description
    agent.industries = industries or ["fintech", "banking"]
    agent.capabilities = capabilities or ["market-analysis", "risk-scoring"]
    agent.tags = tags or ["equities", "basel-iii"]
    agent.is_active = is_active
    agent.interest_embedding = None
    agent.embedding_status = "pending"
    agent.embedding_model = None
    agent.updated_at = datetime.now(timezone.utc)
    return agent


def make_mock_post(
    post_id: uuid.UUID | None = None,
    title: str = "Basel IV Capital Adequacy Advisory",
    content: str = "Regulatory changes will impact Tier 1 capital reserve requirements across European counterparties.",
    tags: list[str] | None = None,
    target_industries: list[str] | None = None,
    status: str = "published",
) -> Post:
    post = MagicMock(spec=Post)
    post.id = post_id or uuid.uuid4()
    post.author_agent_id = uuid.uuid4()
    post.title = title
    post.content = content
    post.tags = tags or ["basel-iv", "capital-adequacy"]
    post.target_industries = target_industries or ["banking", "fintech"]
    post.status = status
    post.content_embedding = None
    post.embedding_status = "pending"
    post.embedding_model = None
    post.updated_at = datetime.now(timezone.utc)
    return post


# ─────────────────────────────────────────────────────────────────────────────
# 1-8: Embedding Service Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_ollama_request_construction_and_endpoint():
    """1 & 2: Verifies Ollama POST /api/embed request payload and model selection."""
    valid_vec = make_valid_vector()
    mock_response = httpx.Response(
        status_code=200,
        json={"model": "nomic-embed-text", "embeddings": [valid_vec]},
        request=httpx.Request("POST", "http://localhost:11434/api/embed"),
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_response

    provider = OllamaEmbeddingProvider(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        client=mock_client,
    )

    result = await provider.embed("search_query: Sample post content")

    mock_client.post.assert_awaited_once_with(
        "/api/embed",
        json={"model": "nomic-embed-text", "input": "search_query: Sample post content"},
    )
    assert len(result) == 768
    assert result == valid_vec


@pytest.mark.unit
async def test_ollama_response_parsing_fallback():
    """3: Verifies parsing from /api/embed ('embeddings' array) and legacy ('embedding' array)."""
    valid_vec = make_valid_vector()

    # Legacy format: {"embedding": [...]}
    mock_response_legacy = httpx.Response(
        status_code=200,
        json={"embedding": valid_vec},
        request=httpx.Request("POST", "http://localhost:11434/api/embeddings"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_response_legacy

    provider = OllamaEmbeddingProvider(client=mock_client)
    res = await provider.embed("test text")
    assert res == valid_vec


@pytest.mark.unit
async def test_embedding_768_dimensional_validation():
    """4: Verifies exactly 768 dimensions pass validation."""
    valid_vec = make_valid_vector(dim=768)
    provider = OllamaEmbeddingProvider(client=AsyncMock())
    # Directly test validator
    provider._validate_vector(valid_vec)


@pytest.mark.unit
async def test_embedding_invalid_dimensions_rejected():
    """5: Verifies vector with incorrect dimension raises EmbeddingDimensionError."""
    provider = OllamaEmbeddingProvider(dimensions=768, client=AsyncMock())

    with pytest.raises(EmbeddingDimensionError) as exc_info:
        provider._validate_vector([0.1] * 512)
    assert "expected 768, got 512" in str(exc_info.value)

    with pytest.raises(EmbeddingDimensionError) as exc_info:
        provider._validate_vector([0.1] * 1024)
    assert "expected 768, got 1024" in str(exc_info.value)


@pytest.mark.unit
async def test_embedding_invalid_numeric_values_rejected():
    """6: Verifies NaN, Inf, non-numeric, and all-zero degenerate vectors raise EmbeddingValueError."""
    provider = OllamaEmbeddingProvider(dimensions=768, client=AsyncMock())

    # NaN test
    nan_vec = make_valid_vector()
    nan_vec[10] = float("nan")
    with pytest.raises(EmbeddingValueError) as exc:
        provider._validate_vector(nan_vec)
    assert "NaN or Inf" in str(exc.value)

    # Infinity test
    inf_vec = make_valid_vector()
    inf_vec[20] = float("inf")
    with pytest.raises(EmbeddingValueError) as exc:
        provider._validate_vector(inf_vec)
    assert "NaN or Inf" in str(exc.value)

    # All-zero degenerate vector test
    zero_vec = [0.0] * 768
    with pytest.raises(EmbeddingValueError) as exc:
        provider._validate_vector(zero_vec)
    assert "all dimensions are zero" in str(exc.value).lower()


@pytest.mark.unit
async def test_embedding_timeout_handling():
    """7: Verifies httpx.TimeoutException raises EmbeddingConnectionError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ReadTimeout("Ollama read timed out after 30s")

    provider = OllamaEmbeddingProvider(client=mock_client)
    with pytest.raises(EmbeddingConnectionError) as exc_info:
        await provider.embed("test text")
    assert "unavailable" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()


@pytest.mark.unit
async def test_embedding_ollama_unavailable_handling():
    """8: Verifies httpx.ConnectError raises EmbeddingConnectionError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Connection refused to 127.0.0.1:11434")

    provider = OllamaEmbeddingProvider(client=mock_client)
    with pytest.raises(EmbeddingConnectionError) as exc_info:
        await provider.embed("test text")
    assert "unavailable" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 9-11: Text Construction & Prefix Unit Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_deterministic_post_embedding_text():
    """9 & 11: Verifies post embedding text construction starts with 'search_query:' and is deterministic."""
    text1 = build_post_text(
        title="Cross-border FX Settlement Protocol",
        content="Automated multi-currency netting protocol using distributed agents.",
        tags=["fx", "settlement", "netting"],
        target_industries=["banking", "fintech"],
    )
    # Different order of tags in input should produce identical deterministic output
    text2 = build_post_text(
        title="Cross-border FX Settlement Protocol",
        content="Automated multi-currency netting protocol using distributed agents.",
        tags=["netting", "fx", "settlement"],
        target_industries=["fintech", "banking"],
    )

    assert text1.startswith(NOMIC_QUERY_PREFIX)
    assert text1 == text2
    assert "Title: Cross-border FX Settlement Protocol" in text1
    assert "Content: Automated multi-currency netting protocol" in text1
    assert "Tags: fx, netting, settlement" in text1
    assert "Target Industries: banking, fintech" in text1


@pytest.mark.unit
def test_deterministic_agent_interest_text():
    """10 & 11: Verifies agent interest text construction starts with 'search_document:' and uses 6 model fields."""
    text1 = build_agent_text(
        name="GovBot-1",
        company="RegTech Global",
        description="Continuous compliance verification for inter-agent settlement agreements.",
        industries=["compliance", "legal", "fintech"],
        tags=["gdpr", "basel-iii"],
        capabilities=["contract-nlp", "audit-scoring"],
    )
    text2 = build_agent_text(
        name="GovBot-1",
        company="RegTech Global",
        description="Continuous compliance verification for inter-agent settlement agreements.",
        industries=["legal", "fintech", "compliance"],
        tags=["basel-iii", "gdpr"],
        capabilities=["audit-scoring", "contract-nlp"],
    )

    assert text1.startswith(NOMIC_DOC_PREFIX)
    assert text1 == text2
    assert "Agent: GovBot-1" in text1
    assert "Company: RegTech Global" in text1
    assert "Manifesto: Continuous compliance verification" in text1
    assert "Industries: compliance, fintech, legal" in text1
    assert "Capabilities: audit-scoring, contract-nlp" in text1
    assert "Tags: basel-iii, gdpr" in text1


# ─────────────────────────────────────────────────────────────────────────────
# 12-20: Pipeline, Worker, and Event Processing Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_post_embedding_persistence():
    """12: Verifies EmbedWorker persists post vector, completed status, and model."""
    post = make_mock_post()
    valid_vec = make_valid_vector()

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.model = "nomic-embed-text"
    mock_service.embed_post = AsyncMock(return_value=valid_vec)

    worker = EmbedWorker(embedding_service=mock_service)
    worker._get_redis = AsyncMock(return_value=AsyncMock())

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_post(post.id, {"post_id": str(post.id)})

        assert post.content_embedding == valid_vec
        assert post.embedding_status == "completed"
        assert post.embedding_model == "nomic-embed-text"
        assert mock_db.commit.await_count >= 2


@pytest.mark.unit
async def test_agent_embedding_persistence():
    """13: Verifies EmbedWorker persists agent vector, completed status, and model."""
    agent = make_mock_agent()
    valid_vec = make_valid_vector()

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.model = "nomic-embed-text"
    mock_service.embed_agent_profile = AsyncMock(return_value=valid_vec)

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_agent(agent.id, {"agent_id": str(agent.id)})

        assert agent.interest_embedding == valid_vec
        assert agent.embedding_status == "completed"
        assert agent.embedding_model == "nomic-embed-text"
        assert mock_db.commit.await_count >= 2


@pytest.mark.unit
async def test_re_embedding_after_post_updates():
    """14: Verifies updated post with pending status is re-embedded and completed."""
    post = make_mock_post()
    post.content_embedding = make_valid_vector(seed=0.01)
    post.embedding_status = "pending"  # Invalidation triggered by update

    new_vec = make_valid_vector(seed=0.09)
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.model = "nomic-embed-text"
    mock_service.embed_post = AsyncMock(return_value=new_vec)

    worker = EmbedWorker(embedding_service=mock_service)
    worker._get_redis = AsyncMock(return_value=AsyncMock())

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_post(post.id, {"post_id": str(post.id)})

        assert post.content_embedding == new_vec
        assert post.embedding_status == "completed"


@pytest.mark.unit
async def test_re_embedding_after_agent_updates():
    """15: Verifies updated agent with pending status is re-embedded and completed."""
    agent = make_mock_agent()
    agent.interest_embedding = make_valid_vector(seed=0.01)
    agent.embedding_status = "pending"  # Invalidation triggered by profile update

    new_vec = make_valid_vector(seed=0.08)
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.model = "nomic-embed-text"
    mock_service.embed_agent_profile = AsyncMock(return_value=new_vec)

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_agent(agent.id, {"agent_id": str(agent.id)})

        assert agent.interest_embedding == new_vec
        assert agent.embedding_status == "completed"


@pytest.mark.unit
async def test_duplicate_event_handling_idempotency():
    """16: Verifies duplicate event for already completed entity is skipped without re-calling Ollama."""
    post = make_mock_post()
    post.content_embedding = make_valid_vector()
    post.embedding_status = "completed"

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.embed_post = AsyncMock()

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_post(post.id, {"post_id": str(post.id)})

        # embed_post should NOT have been called
        mock_service.embed_post.assert_not_awaited()


@pytest.mark.unit
async def test_stale_event_protection():
    """17: Verifies older event timestamp does not overwrite newer entity."""
    post = make_mock_post()
    post.content_embedding = make_valid_vector()
    post.embedding_status = "completed"
    post.updated_at = datetime.now(timezone.utc)

    # Event generated 1 hour prior to latest entity update
    stale_ts = (post.updated_at - timedelta(hours=1)).isoformat()

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.embed_post = AsyncMock()

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_post(post.id, {"post_id": str(post.id), "timestamp": stale_ts})

        mock_service.embed_post.assert_not_awaited()


@pytest.mark.unit
async def test_worker_retry_behaviour():
    """18: Verifies transient failure raises error and schedules backoff retry."""
    from app.workers.base_worker import BaseWorker

    class FailingWorker(BaseWorker):
        stream = "test:stream"
        group = "test-group"
        consumer_name = "test-c1"

        def __init__(self):
            super().__init__()
            self.settings.worker_retry_max = 3
            self.settings.worker_retry_backoff_seconds = 0.01  # Fast for tests

        async def handle(self, fields: dict) -> None:
            raise EmbeddingConnectionError("Simulated Ollama down")

    worker = FailingWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    fields = {"post_id": str(uuid.uuid4()), "_retry_count": "0"}
    await worker._process_with_retry(mock_redis, "test:stream", "1-0", fields, mock_log)

    # Must re-add with _retry_count = 1 and ACK old message
    mock_redis.xadd.assert_awaited_once_with(
        "test:stream",
        {**fields, "_retry_count": "1"},
    )
    mock_redis.xack.assert_awaited_once_with("test:stream", "test-group", "1-0")


@pytest.mark.unit
async def test_worker_dead_letter_handling():
    """19: Verifies exhausted retries (retry_count >= worker_retry_max) routes to DLQ."""
    from app.workers.base_worker import BaseWorker

    class FailingWorker(BaseWorker):
        stream = "test:stream"
        group = "test-group"
        consumer_name = "test-c1"

        def __init__(self):
            super().__init__()
            self.settings.worker_retry_max = 3

        async def handle(self, fields: dict) -> None:
            raise EmbeddingValueError("Corrupt vector payload")

    worker = FailingWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    fields = {"post_id": str(uuid.uuid4()), "_retry_count": "3"}
    await worker._process_with_retry(mock_redis, "test:stream", "10-0", fields, mock_log)

    # Must add to test:stream:dlq and ACK original
    mock_redis.xadd.assert_awaited_once()
    args, kwargs = mock_redis.xadd.call_args
    assert args[0] == "test:stream:dlq"
    assert args[1]["original_id"] == "10-0"
    assert "Corrupt vector" in args[1]["error"]
    mock_redis.xack.assert_awaited_once_with("test:stream", "test-group", "10-0")


@pytest.mark.unit
async def test_worker_acknowledgement_after_persistence():
    """20: Verifies XACK is invoked only after handle() succeeds."""
    from app.workers.base_worker import BaseWorker

    order_of_execution = []

    class TrackedWorker(BaseWorker):
        stream = "test:stream"
        group = "test-group"
        consumer_name = "test-c1"

        async def handle(self, fields: dict) -> None:
            order_of_execution.append("handle_persisted")

    worker = TrackedWorker()
    mock_redis = AsyncMock()

    async def mock_xack(stream, group, msg_id):
        order_of_execution.append("xack_called")

    mock_redis.xack.side_effect = mock_xack

    await worker._process_with_retry(mock_redis, "test:stream", "1-0", {"id": "test"}, MagicMock())

    assert order_of_execution == ["handle_persisted", "xack_called"]


# ─────────────────────────────────────────────────────────────────────────────
# P3.1: Specific Review Tests (Tags, Pending Recovery, Stale, Chain Consistency)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_agent_tags_included_in_embedding_input():
    """P3.1-1: Verifies agent tags are properly included, sanitized, sorted, and formatted."""
    text = build_agent_text(
        name="AlphaBot",
        company="AlphaCorp",
        description="Autonomous procurement and supplier negotiations.",
        industries=["Procurement", "Supply-Chain"],
        tags=["ERP", "SAP-Integration", "erp", "  "],
        capabilities=["price-arbitrage", "rfp-analysis"],
    )

    assert text.startswith(NOMIC_DOC_PREFIX)
    assert "Agent: AlphaBot" in text
    assert "Company: AlphaCorp" in text
    assert "Manifesto: Autonomous procurement and supplier negotiations." in text
    assert "Industries: procurement, supply-chain" in text
    assert "Tags: erp, sap-integration" in text
    assert "Capabilities: price-arbitrage, rfp-analysis" in text
    # Verify deduplication
    assert text.count("erp") == 1


@pytest.mark.unit
async def test_pending_message_recovery_xautoclaim():
    """P3.1-2a: Verifies abandoned pending messages (idle >= 60s) are reclaimed via XAUTOCLAIM."""
    from app.workers.base_worker import BaseWorker

    reclaimed_ids = []

    class MockWorker(BaseWorker):
        stream = "posts:embed"
        group = "embed-workers"
        consumer_name = "test-worker-recovery"

        async def handle(self, fields: dict) -> None:
            reclaimed_ids.append(fields.get("post_id"))

    worker = MockWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    # Redis returns [start_id, [(msg_id, fields)]]
    mock_redis.xautoclaim.return_value = [
        "0-0",
        [("100-0", {"post_id": "abc-123", "_retry_count": "0"})],
    ]

    claimed = await worker._claim_and_process_pending(mock_redis, "posts:embed", mock_log)

    assert claimed == 1
    assert reclaimed_ids == ["abc-123"]
    mock_redis.xautoclaim.assert_awaited_once_with(
        name="posts:embed",
        groupname="embed-workers",
        consumername="test-worker-recovery",
        min_idle_time=worker.claim_min_idle_ms,
        start_id="0-0",
        count=10,
    )
    mock_redis.xack.assert_awaited_once_with("posts:embed", "embed-workers", "100-0")


@pytest.mark.unit
async def test_pending_message_recovery_fallback_xclaim():
    """P3.1-2b: Verifies fallback to XPENDING + XCLAIM only reclaims messages idle >= 60000ms."""
    from app.workers.base_worker import BaseWorker

    processed_ids = []

    class MockWorker(BaseWorker):
        stream = "posts:embed"
        group = "embed-workers"
        consumer_name = "test-worker-fallback"

        async def handle(self, fields: dict) -> None:
            processed_ids.append(fields.get("post_id"))

    worker = MockWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    # Simulate xautoclaim failing (e.g. older redis engine)
    mock_redis.xautoclaim.side_effect = Exception("Unknown command 'XAUTOCLAIM'")

    # Mock xpending_range returning one idle (130s) and one active (5s) message
    mock_redis.xpending_range.return_value = [
        {"message_id": "idle-msg-1", "consumer": "c-crashed", "idle": 130000},
        {"message_id": "active-msg-2", "consumer": "c-healthy", "idle": 5000},
    ]

    # Mock xclaim returning only the idle claimed message
    mock_redis.xclaim.return_value = [
        ("idle-msg-1", {"post_id": "recovered-post", "_retry_count": "0"})
    ]

    claimed = await worker._claim_and_process_pending(mock_redis, "posts:embed", mock_log)

    assert claimed == 1
    assert processed_ids == ["recovered-post"]
    # Verify active message was NOT claimed
    mock_redis.xclaim.assert_awaited_once_with(
        name="posts:embed",
        groupname="embed-workers",
        consumername="test-worker-fallback",
        min_idle_time=worker.claim_min_idle_ms,
        message_ids=["idle-msg-1"],
    )
    mock_redis.xack.assert_awaited_once_with("posts:embed", "embed-workers", "idle-msg-1")


@pytest.mark.unit
async def test_agent_duplicate_event_handling_idempotency():
    """P3.1-3: Verifies duplicate event for already completed Agent is skipped idempotently."""
    agent = make_mock_agent()
    agent.interest_embedding = make_valid_vector()
    agent.embedding_status = "completed"

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.embed_agent_profile = AsyncMock()

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_agent(agent.id, {"agent_id": str(agent.id)})

        # embed_agent_profile should NOT have been called
        mock_service.embed_agent_profile.assert_not_awaited()


@pytest.mark.unit
async def test_agent_stale_event_protection():
    """P3.1-4: Verifies older event timestamp does not overwrite newer agent profile."""
    agent = make_mock_agent()
    agent.interest_embedding = make_valid_vector()
    agent.embedding_status = "completed"
    agent.updated_at = datetime.now(timezone.utc)

    # Event generated 30 minutes prior to latest profile update
    stale_ts = (agent.updated_at - timedelta(minutes=30)).isoformat()

    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.embed_agent_profile = AsyncMock()

    worker = EmbedWorker(embedding_service=mock_service)

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = agent
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await worker.process_agent(agent.id, {"agent_id": str(agent.id), "timestamp": stale_ts})

        mock_service.embed_agent_profile.assert_not_awaited()


@pytest.mark.unit
async def test_worker_automated_pending_reconciliation():
    """P3.1-5: Verifies automated reconciliation finds pending/failed DB records and enqueues to Redis."""
    worker = EmbedWorker()
    mock_redis = AsyncMock()
    mock_log = MagicMock()

    post = make_mock_post()
    post.embedding_status = "pending"
    agent = make_mock_agent()
    agent.embedding_status = "pending"

    with patch("app.workers.embed_worker.AsyncSessionLocal") as mock_session_ctx:
        mock_db = AsyncMock()
        # Mock first query (posts), then second query (agents)
        mock_posts_result = MagicMock()
        mock_posts_result.all.return_value = [(post.id, post.updated_at)]
        mock_agents_result = MagicMock()
        mock_agents_result.all.return_value = [(agent.id, agent.updated_at)]

        mock_db.execute.side_effect = [mock_posts_result, mock_agents_result]
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        count = await worker.reconcile_pending_embeddings(mock_redis, mock_log)

        assert count == 2
        assert mock_redis.xadd.await_count == 2
        calls = [c.args for c in mock_redis.xadd.await_args_list]
        assert calls[0][0] == "posts:embed"
        assert calls[0][1]["post_id"] == str(post.id)
        assert calls[1][0] == "agents:embed"
        assert calls[1][1]["agent_id"] == str(agent.id)


@pytest.mark.unit
def test_alembic_migration_chain_consistency():
    """P3.1-6: Programmatically verifies linear unbroken Alembic migration chain from 0001 to 0004."""
    import os
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")

    config = Config(alembic_ini)
    config.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

    script = ScriptDirectory.from_config(config)

    # 1. Check exactly 1 head
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 migration head, got: {heads}"
    assert heads[0] == "0007_feedback_learning_and_adaptive_preferences"

    # 2. Check linear chain
    revisions = list(script.walk_revisions())
    rev_ids = [r.revision for r in revisions]

    expected_chain = [
        "0007_feedback_learning_and_adaptive_preferences",
        "0006_agent_interactions_and_comments",
        "0005_pgvector_hnsw_indexes",
        "0004_embedding_pipeline",
        "0003_post_expires_at_and_feed_index",
        "0002_agent_auth_and_trust_score",
        "0001_initial_schema",
    ]
    assert rev_ids == expected_chain, f"Migration chain mismatch. Got: {rev_ids}"

    # 3. Check down_revisions
    rev_map = {r.revision: r.down_revision for r in revisions}
    assert rev_map["0007_feedback_learning_and_adaptive_preferences"] == "0006_agent_interactions_and_comments"
    assert rev_map["0006_agent_interactions_and_comments"] == "0005_pgvector_hnsw_indexes"
    assert rev_map["0005_pgvector_hnsw_indexes"] == "0004_embedding_pipeline"
    assert rev_map["0004_embedding_pipeline"] == "0003_post_expires_at_and_feed_index"
    assert rev_map["0003_post_expires_at_and_feed_index"] == "0002_agent_auth_and_trust_score"
    assert rev_map["0002_agent_auth_and_trust_score"] == "0001_initial_schema"
    assert rev_map["0001_initial_schema"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration Test Stubs (PostgreSQL + pgvector + Redis + Ollama required)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_full_embedding_pipeline_live(postgres_session, client):
    """
    End-to-end integration test against live PostgreSQL + pgvector and Ollama.
    Skips cleanly if PostgreSQL, Redis, or Ollama is offline.
    """
    # 1. Register agent
    reg_res = await client.post(
        "/api/v1/agents/register",
        json={
            "name": f"LiveEmbedAgent-{uuid.uuid4().hex[:6]}",
            "company": "Live Enterprise",
            "industries": ["fintech", "ai"],
            "description": "Live embedding test agent for pgvector verification.",
        },
    )
    assert reg_res.status_code == 201
    key = reg_res.json()["api_key"]

    tok_res = await client.post("/api/v1/auth/token", json={"api_key": key})
    assert tok_res.status_code == 200
    token = tok_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Publish post
    post_res = await client.post(
        "/api/v1/posts",
        headers=headers,
        json={
            "title": "Live Vector Generation Test Post",
            "content": "Verifying asynchronous 768-dimensional embedding generation with nomic-embed-text.",
            "tags": ["pgvector", "ollama"],
        },
    )
    assert post_res.status_code == 201
    post_id = uuid.UUID(post_res.json()["id"])

    # 3. Process with worker
    service = EmbeddingService()
    try:
        # Check if Ollama is accessible
        await service.embed("test connection")
    except Exception as exc:
        pytest.skip(f"Ollama server not reachable for live integration test: {exc}")

    worker = EmbedWorker(embedding_service=service)
    await worker.process_post(post_id, {"post_id": str(post_id)})

    # 4. Verify post embedding stored
    from app.models.post import Post
    result = await postgres_session.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    assert post is not None
    assert post.embedding_status == "completed"
    assert post.content_embedding is not None
    assert len(post.content_embedding) == 768
