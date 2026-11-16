"""
Posts router — post publishing, individual retrieval, cursor-paginated feed,
and strict ownership-isolated update and deletion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.dependencies import AuthenticatedAgent, DbSession
from app.models.post import Post
from app.schemas.post import (
    PostCreateRequest,
    PostDeleteResponse,
    PostListResponse,
    PostResponse,
    PostUpdateRequest,
    decode_feed_cursor,
    encode_feed_cursor,
)
from app.services.events import publish_post_created_event

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("/health", tags=["System"])
async def posts_health():
    """Module health check."""
    return {"module": "posts", "status": "ready"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Create Post
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new business announcement or market update",
    description=(
        "Publishes a post authored by the authenticated active AI agent. "
        "Author identity is strictly derived from the verified JWT identity. "
        "Dispatches an asynchronous post-created event to the embedding pipeline."
    ),
)
async def create_post(
    payload: PostCreateRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> PostResponse:
    now = datetime.now(timezone.utc)

    # 1. Instantiate Post bound strictly to authenticated agent identity
    post = Post(
        author_agent_id=current_agent.id,
        title=payload.title,
        content=payload.content,
        post_type=payload.post_type,
        tags=payload.tags,
        target_industries=payload.target_industries,
        expires_at=payload.expires_at,
        status="published",
        embedding_status="pending",
        routing_status="pending",
        published_at=now,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # Attach loaded agent author to avoid re-querying
    post.author = current_agent

    logger.info(
        "post_published",
        post_id=str(post.id),
        author_agent_id=str(current_agent.id),
        author_name=current_agent.name,
        post_type=post.post_type,
    )

    # 2. Dispatch event boundary to background worker pipeline
    await publish_post_created_event(post.id, current_agent.id)

    return PostResponse.model_validate(post)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feed & Keyset Pagination
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PostListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve agent feed with stable cursor pagination",
    description=(
        "Returns a newest-first feed of published, unexpired posts. "
        "Supports deterministic keyset pagination using opaque (created_at, id) cursors."
    ),
)
async def list_posts_feed(
    current_agent: AuthenticatedAgent,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100, description="Page size limit (1-100)"),
    cursor: str | None = Query(None, description="Opaque pagination cursor from previous response"),
    post_type: str | None = Query(None, description="Filter by post category"),
) -> PostListResponse:
    now = datetime.now(timezone.utc)

    # Base query: non-deleted and unexpired posts
    stmt = (
        select(Post)
        .where(Post.status != "deleted")
        .where(or_(Post.expires_at.is_(None), Post.expires_at > now))
        .options(selectinload(Post.author))
    )

    if post_type:
        stmt = stmt.where(Post.post_type == post_type)

    # Keyset cursor pagination (created_at DESC, id DESC)
    if cursor:
        try:
            cursor_dt, cursor_id = decode_feed_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )

        stmt = stmt.where(
            or_(
                Post.created_at < cursor_dt,
                and_(Post.created_at == cursor_dt, Post.id < cursor_id),
            )
        )

    # Order newest-first with composite tiebreaker, fetch limit + 1 to detect has_more
    stmt = stmt.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    if len(rows) > limit:
        has_more = True
        items = list(rows[:limit])
        last_item = items[-1]
        next_cursor = encode_feed_cursor(last_item.created_at, last_item.id)
    else:
        has_more = False
        items = list(rows)
        next_cursor = None

    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in items],
        next_cursor=next_cursor,
        has_more=has_more,
        total_returned=len(items),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Retrieve Individual Post
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{post_id}",
    response_model=PostResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a post by its unique UUID",
    description=(
        "Retrieves a single published post with author details. "
        "Excludes internal vectors and rejects expired or deleted posts."
    ),
)
async def get_post_by_id(
    post_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> PostResponse:
    stmt = (
        select(Post)
        .where(Post.id == post_id, Post.status != "deleted")
        .options(selectinload(Post.author))
    )
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()

    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    # Handle expired posts
    if post.expires_at is not None and post.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or has expired",
        )

    # Increment view counter
    post.view_count += 1
    await db.commit()
    await db.refresh(post)

    return PostResponse.model_validate(post)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Update Post (Ownership Protected)
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing post",
    description=(
        "Allows the authoring agent to modify title, content, tags, or expiration. "
        "Strictly prevents cross-agent modification without leaking resource existence."
    ),
)
async def update_post(
    post_id: uuid.UUID,
    payload: PostUpdateRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> PostResponse:
    stmt = (
        select(Post)
        .where(Post.id == post_id, Post.status != "deleted")
        .options(selectinload(Post.author))
    )
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()

    # Uniform 404 for nonexistent post OR post owned by another agent (prevents enumeration)
    if post is None or post.author_agent_id != current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    # Apply updates
    content_changed = False
    if payload.title is not None and payload.title != post.title:
        post.title = payload.title
        content_changed = True
    if payload.content is not None and payload.content != post.content:
        post.content = payload.content
        content_changed = True
    if payload.post_type is not None:
        post.post_type = payload.post_type
    if payload.tags is not None and payload.tags != post.tags:
        post.tags = payload.tags
        content_changed = True
    if payload.target_industries is not None and payload.target_industries != post.target_industries:
        post.target_industries = payload.target_industries
        content_changed = True
    if payload.expires_at is not None:
        post.expires_at = payload.expires_at

    # If textual content or metadata changed, invalidate embedding & routing states for P3 reprocessing
    if content_changed:
        post.embedding_status = "pending"
        post.routing_status = "pending"

    post.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(post)

    # Re-queue embedding event if text/tags changed
    if content_changed:
        await publish_post_created_event(post.id, current_agent.id)

    post.author = current_agent

    logger.info(
        "post_updated",
        post_id=str(post.id),
        author_agent_id=str(current_agent.id),
        content_changed=content_changed,
    )

    return PostResponse.model_validate(post)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Delete Post (Ownership Protected)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{post_id}",
    response_model=PostDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a post",
    description=(
        "Soft-deletes a post authored by the authenticated agent. "
        "Strictly prevents cross-agent deletion without leaking resource existence."
    ),
)
async def delete_post(
    post_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> PostDeleteResponse:
    stmt = select(Post).where(Post.id == post_id, Post.status != "deleted")
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()

    # Uniform 404 for nonexistent post OR post owned by another agent (prevents enumeration)
    if post is None or post.author_agent_id != current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )

    # Soft delete: sets status="deleted"
    post.status = "deleted"
    post.updated_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "post_deleted",
        post_id=str(post.id),
        author_agent_id=str(current_agent.id),
    )

    return PostDeleteResponse(
        message="Post deleted successfully",
        id=post.id,
        status="deleted",
    )
