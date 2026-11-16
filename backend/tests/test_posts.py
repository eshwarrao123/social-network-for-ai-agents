"""
Comprehensive unit and integration tests for P2 Post Publishing, Management & Agent Feed.

Tests cover:
  1. Successful post creation.
  2. Missing required fields.
  3. Invalid title and content (empty, whitespace-only, too long).
  4. Author identity derived from JWT.
  5. Rejection of inactive agents.
  6. Individual post retrieval.
  7. Nonexistent post handling.
  8. Feed pagination.
  9. Stable ordering.
  10. Updating own posts.
  11. Preventing updates to another agent's posts.
  12. Deleting own posts.
  13. Preventing deletion of another agent's posts.
  14. Expired post handling.
  15. Database persistence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import get_active_agent
from app.models.agent import Agent
from app.models.post import Post
from app.routers.posts import (
    create_post,
    delete_post,
    get_post_by_id,
    list_posts_feed,
    update_post,
)
from app.schemas.post import (
    AuthorSummaryResponse,
    PostCreateRequest,
    PostDeleteResponse,
    PostListResponse,
    PostResponse,
    PostUpdateRequest,
    decode_feed_cursor,
    encode_feed_cursor,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_mock_agent(
    agent_id: uuid.UUID | None = None,
    name: str = "TestAgent-1",
    company: str = "TestCorp",
    is_active: bool = True,
) -> Agent:
    """Creates a mock Agent model instance."""
    agent = MagicMock(spec=Agent)
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.trust_score = 0.5
    agent.industries = ["fintech", "compliance"]
    agent.is_active = is_active
    return agent


def make_mock_post(
    post_id: uuid.UUID | None = None,
    author: Agent | None = None,
    title: str = "Quarterly Risk Protocol Update",
    content: str = "Detailed evaluation of cross-agent compliance guarantees.",
    post_type: str = "announcement",
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
    status: str = "published",
) -> Post:
    """Creates a mock Post model instance."""
    post = MagicMock(spec=Post)
    post.id = post_id or uuid.uuid4()
    author_agent = author or make_mock_agent()
    post.author_agent_id = author_agent.id
    post.author = author_agent
    post.title = title
    post.content = content
    post.post_type = post_type
    post.tags = ["compliance", "risk"]
    post.target_industries = ["fintech"]
    post.status = status
    post.view_count = 0
    post.comment_count = 0
    post.engagement_score = 0
    now = datetime.now(timezone.utc)
    post.published_at = now
    post.expires_at = expires_at
    post.created_at = created_at or now
    post.updated_at = now
    return post


# ─────────────────────────────────────────────────────────────────────────────
# 1, 2, 3: Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_post_create_valid_payload():
    payload = {
        "title": "Autonomous Settlement Protocol Release",
        "content": "Production release of the settlement protocol for cross-enterprise agents.",
        "post_type": "announcement",
        "tags": ["settlement", "finance"],
        "target_industries": ["banking"],
    }
    req = PostCreateRequest.model_validate(payload)
    assert req.title == "Autonomous Settlement Protocol Release"
    assert req.content.startswith("Production release")
    assert req.post_type == "announcement"
    assert len(req.tags) == 2
    assert req.expires_at is None


@pytest.mark.unit
def test_post_create_missing_required_fields():
    # Missing content
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({"title": "Headline Only"})
    assert "content" in str(exc_info.value)

    # Missing title
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({"content": "Body text only"})
    assert "title" in str(exc_info.value)


@pytest.mark.unit
def test_post_create_empty_or_whitespace_title():
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({
            "title": "    ",
            "content": "Valid content text.",
        })
    assert "whitespace only" in str(exc_info.value).lower()


@pytest.mark.unit
def test_post_create_empty_or_whitespace_content():
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({
            "title": "Valid Title",
            "content": " \t \n ",
        })
    assert "whitespace only" in str(exc_info.value).lower()


@pytest.mark.unit
def test_post_create_title_too_long():
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({
            "title": "x" * 501,
            "content": "Valid content text.",
        })
    assert "title" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4: Author Identity Isolation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_post_create_forbids_client_author_identity_injection():
    # Attempting to supply author_agent_id in request body must be rejected
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({
            "title": "Spoofed Post",
            "content": "Attempting to claim authorship as another agent.",
            "author_agent_id": str(uuid.uuid4()),
        })
    assert "extra_forbidden" in str(exc_info.value) or "extra fields" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 5: Inactive Agent Rejection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_post_action_rejects_inactive_agent():
    inactive_agent = make_mock_agent(is_active=False)
    with pytest.raises(HTTPException) as exc_info:
        await get_active_agent(inactive_agent)
    assert exc_info.value.status_code == 403
    assert "inactive" in str(exc_info.value.detail).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 6: Individual Post Retrieval Excludes Internal Vectors
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_post_response_serialization_excludes_vectors():
    agent_id = uuid.uuid4()
    post_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    mock_agent = make_mock_agent(agent_id=agent_id)
    mock_post = make_mock_post(post_id=post_id, author=mock_agent)

    # Validate PostResponse
    res = PostResponse.model_validate(mock_post)
    assert res.id == post_id
    assert res.author_agent_id == agent_id
    assert res.author.name == mock_agent.name
    assert res.author.company == mock_agent.company
    assert not hasattr(res, "content_embedding")
    assert not hasattr(res, "embedding_status")
    assert not hasattr(res, "routing_status")


# ─────────────────────────────────────────────────────────────────────────────
# 7 & 14: Nonexistent and Expired Post Handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_get_individual_post_not_found():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    current_agent = make_mock_agent()
    nonexistent_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await get_post_by_id(nonexistent_id, current_agent, db)

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.unit
async def test_get_individual_post_expired():
    db = AsyncMock()
    expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_post = make_mock_post(expires_at=expired_time)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_post
    db.execute.return_value = mock_result

    current_agent = make_mock_agent()

    with pytest.raises(HTTPException) as exc_info:
        await get_post_by_id(mock_post.id, current_agent, db)

    assert exc_info.value.status_code == 404
    assert "expired" in str(exc_info.value.detail).lower()


@pytest.mark.unit
def test_post_create_rejects_past_expiration():
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    with pytest.raises(ValidationError) as exc_info:
        PostCreateRequest.model_validate({
            "title": "Expired Notice",
            "content": "This notice should already have expired.",
            "expires_at": past_time,
        })
    assert "future" in str(exc_info.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# 8 & 9: Cursor Pagination and Stable Ordering
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_cursor_encoding_and_decoding_roundtrip():
    test_dt = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
    test_id = uuid.uuid4()

    cursor_str = encode_feed_cursor(test_dt, test_id)
    assert isinstance(cursor_str, str)

    decoded_dt, decoded_id = decode_feed_cursor(cursor_str)
    assert decoded_dt == test_dt
    assert decoded_id == test_id


@pytest.mark.unit
def test_cursor_decoding_malformed():
    with pytest.raises(ValueError) as exc_info:
        decode_feed_cursor("invalid-base64-not-a-cursor!@#")
    assert "Malformed" in str(exc_info.value)


@pytest.mark.unit
async def test_feed_pagination_keyset_ordering():
    db = AsyncMock()
    current_agent = make_mock_agent()

    now = datetime.now(timezone.utc)
    p1 = make_mock_post(created_at=now, title="Post 1")
    p2 = make_mock_post(created_at=now - timedelta(minutes=1), title="Post 2")
    p3 = make_mock_post(created_at=now - timedelta(minutes=2), title="Post 3")

    # If limit is 2, returning 3 rows indicates has_more = True
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [p1, p2, p3]
    db.execute.return_value = mock_result

    res = await list_posts_feed(
        current_agent=current_agent,
        db=db,
        limit=2,
        cursor=None,
    )

    assert res.total_returned == 2
    assert res.has_more is True
    assert res.next_cursor is not None
    assert res.items[0].title == "Post 1"
    assert res.items[1].title == "Post 2"

    # Verify next cursor points to the last item on the page
    cursor_dt, cursor_id = decode_feed_cursor(res.next_cursor)
    assert cursor_id == p2.id


# ─────────────────────────────────────────────────────────────────────────────
# 10 & 11: Update Post and Ownership Protection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_update_own_post_success():
    db = AsyncMock()
    author_agent = make_mock_agent()
    existing_post = make_mock_post(author=author_agent, title="Original Title", content="Original Content")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_post
    db.execute.return_value = mock_result

    payload = PostUpdateRequest(
        title="Updated Title",
        content="Updated body content.",
        tags=["new-tag"],
    )

    res = await update_post(
        post_id=existing_post.id,
        payload=payload,
        current_agent=author_agent,
        db=db,
    )

    assert res.title == "Updated Title"
    assert res.content == "Updated body content."
    assert existing_post.embedding_status == "pending"  # Content changed, must re-embed
    assert existing_post.routing_status == "pending"
    db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_update_other_agent_post_returns_404():
    db = AsyncMock()
    author_agent = make_mock_agent(name="AuthorBot")
    other_agent = make_mock_agent(name="AttackerBot")

    target_post = make_mock_post(author=author_agent)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = target_post
    db.execute.return_value = mock_result

    payload = PostUpdateRequest(title="Malicious Modification")

    # Must return 404 Not Found to prevent resource enumeration
    with pytest.raises(HTTPException) as exc_info:
        await update_post(
            post_id=target_post.id,
            payload=payload,
            current_agent=other_agent,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail).lower()
    db.commit.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# 12 & 13: Delete Post and Ownership Protection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_delete_own_post_success():
    db = AsyncMock()
    author_agent = make_mock_agent()
    post = make_mock_post(author=author_agent)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = post
    db.execute.return_value = mock_result

    res = await delete_post(
        post_id=post.id,
        current_agent=author_agent,
        db=db,
    )

    assert res.status == "deleted"
    assert res.id == post.id
    assert post.status == "deleted"
    db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_delete_other_agent_post_returns_404():
    db = AsyncMock()
    author_agent = make_mock_agent(name="AuthorBot")
    other_agent = make_mock_agent(name="AttackerBot")

    target_post = make_mock_post(author=author_agent)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = target_post
    db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await delete_post(
            post_id=target_post.id,
            current_agent=other_agent,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert target_post.status != "deleted"
    db.commit.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# 15: Full Lifecycle Integration Test (PostgreSQL + pgvector required)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_full_post_lifecycle_postgres(postgres_session, client):
    """
    End-to-end integration test:
      1. Registers Agent A and Agent B.
      2. Obtains JWT access tokens for both agents.
      3. Agent A creates 3 posts.
      4. Agent B reads Agent A's posts via GET /api/v1/posts/{post_id}.
      5. Agent B paginates the feed with limit=2 and cursor.
      6. Agent A updates its own post.
      7. Agent B attempts to update Agent A's post (rejected 404).
      8. Agent A deletes its post.
      9. Agent B attempts to delete Agent A's post (rejected 404).
      10. Deleted post is excluded from subsequent feed.
    """
    # 1. Register Agent A
    res_a = await client.post(
        "/api/v1/agents/register",
        json={
            "name": f"AuthorAgent-{uuid.uuid4().hex[:6]}",
            "company": "Enterprise Alpha",
            "industries": ["cloud", "fintech"],
            "description": "Primary authoring agent for automated post lifecycle validation.",
        },
    )
    assert res_a.status_code == 201
    key_a = res_a.json()["api_key"]

    # Register Agent B
    res_b = await client.post(
        "/api/v1/agents/register",
        json={
            "name": f"ConsumerAgent-{uuid.uuid4().hex[:6]}",
            "company": "Enterprise Beta",
            "industries": ["analytics"],
            "description": "Secondary reader agent testing access isolation and feed retrieval.",
        },
    )
    assert res_b.status_code == 201
    key_b = res_b.json()["api_key"]

    # 2. Issue tokens
    tok_a = (await client.post("/api/v1/auth/token", json={"api_key": key_a})).json()["access_token"]
    tok_b = (await client.post("/api/v1/auth/token", json={"api_key": key_b})).json()["access_token"]

    headers_a = {"Authorization": f"Bearer {tok_a}"}
    headers_b = {"Authorization": f"Bearer {tok_b}"}

    # 3. Agent A publishes 3 posts
    post_ids = []
    for i in range(3):
        create_res = await client.post(
            "/api/v1/posts",
            headers=headers_a,
            json={
                "title": f"Enterprise Update {i + 1}",
                "content": f"Quarterly operational announcement number {i + 1} with compliance benchmarks.",
                "tags": ["benchmarking", f"tier-{i}"],
                "target_industries": ["cloud"],
            },
        )
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["title"] == f"Enterprise Update {i + 1}"
        assert data["author"]["company"] == "Enterprise Alpha"
        post_ids.append(data["id"])

    # 4. Agent B reads post by ID
    get_res = await client.get(f"/api/v1/posts/{post_ids[0]}", headers=headers_b)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == post_ids[0]

    # 5. Agent B paginates feed
    feed_page1 = await client.get("/api/v1/posts?limit=2", headers=headers_b)
    assert feed_page1.status_code == 200
    p1_data = feed_page1.json()
    assert len(p1_data["items"]) == 2
    assert p1_data["has_more"] is True
    assert p1_data["next_cursor"] is not None

    feed_page2 = await client.get(f"/api/v1/posts?limit=2&cursor={p1_data['next_cursor']}", headers=headers_b)
    assert feed_page2.status_code == 200
    p2_data = feed_page2.json()
    assert len(p2_data["items"]) >= 1

    # 6. Agent A updates its own post
    patch_res = await client.patch(
        f"/api/v1/posts/{post_ids[0]}",
        headers=headers_a,
        json={"title": "Updated Enterprise Benchmark Title"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Enterprise Benchmark Title"

    # 7. Agent B attempts to update Agent A's post (rejected with 404)
    cross_patch = await client.patch(
        f"/api/v1/posts/{post_ids[0]}",
        headers=headers_b,
        json={"title": "Unauthorized Modification"},
    )
    assert cross_patch.status_code == 404

    # 8. Agent B attempts to delete Agent A's post (rejected with 404)
    cross_delete = await client.delete(f"/api/v1/posts/{post_ids[0]}", headers=headers_b)
    assert cross_delete.status_code == 404

    # 9. Agent A deletes its own post
    delete_res = await client.delete(f"/api/v1/posts/{post_ids[0]}", headers=headers_a)
    assert delete_res.status_code == 200
    assert delete_res.json()["status"] == "deleted"

    # 10. Deleted post is 404 on subsequent get
    post_get_after = await client.get(f"/api/v1/posts/{post_ids[0]}", headers=headers_b)
    assert post_get_after.status_code == 404
