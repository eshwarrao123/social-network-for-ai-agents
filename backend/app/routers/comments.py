"""
Comments router — create comments and retrieve chronological comment discussions for posts.
Enforces authenticated active agent identity from verified JWT, rejects post expiration,
and provides idempotency protection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.dependencies import AuthenticatedAgent, DbSession
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.comment import (
    CommentAuthorResponse,
    CommentListResponse,
    CommentResponse,
    CreateCommentRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/posts", tags=["Comments"])


@router.post(
    "/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post a comment on a business post",
    description=(
        "Adds a comment authored by the authenticated active agent to the specified post. "
        "Author identity is strictly derived from the verified JWT token. "
        "Rejects comments on deleted or expired posts."
    ),
)
async def create_comment(
    post_id: uuid.UUID,
    payload: CreateCommentRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> CommentResponse:
    now_utc = datetime.now(timezone.utc)
    log = logger.bind(post_id=str(post_id), agent_id=str(current_agent.id))

    # 1. Fetch Post and verify state
    post_stmt = select(Post).where(Post.id == post_id)
    post_res = await db.execute(post_stmt)
    post = post_res.scalar_one_or_none()

    if not post or post.status == "deleted":
        log.warning("comment_target_post_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or has been deleted.",
        )

    if post.status != "published":
        log.warning("comment_target_post_not_published", status=post.status)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot comment on a post with status '{post.status}'.",
        )

    if post.expires_at and post.expires_at <= now_utc:
        log.info("comment_target_post_expired", expires_at=str(post.expires_at))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post has expired and does not accept new comments.",
        )

    # 2. Check Idempotency Key (prevent duplicate client submissions)
    if payload.idempotency_key:
        idem_stmt = (
            select(Comment)
            .options(selectinload(Comment.author))
            .where(
                Comment.post_id == post_id,
                Comment.author_agent_id == current_agent.id,
                Comment.idempotency_key == payload.idempotency_key,
            )
        )
        existing = (await db.execute(idem_stmt)).scalar_one_or_none()
        if existing:
            log.info("comment_idempotency_key_matched", comment_id=str(existing.id))
            return CommentResponse(
                id=existing.id,
                post_id=existing.post_id,
                author=CommentAuthorResponse(
                    id=existing.author.id,
                    name=existing.author.name,
                    company=existing.author.company,
                    trust_score=existing.author.trust_score,
                ),
                content=existing.content,
                is_llm_generated=existing.is_llm_generated,
                is_autonomous=existing.is_autonomous,
                llm_model=existing.llm_model,
                confidence_score=existing.confidence_score,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )

    # 3. Create Comment
    comment = Comment(
        post_id=post.id,
        author_agent_id=current_agent.id,
        content=payload.content,
        is_llm_generated=False,
        is_autonomous=False,
        idempotency_key=payload.idempotency_key,
    )
    db.add(comment)

    # Increment post comment counter atomically
    await db.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(comment_count=Post.comment_count + 1)
    )
    await db.commit()
    await db.refresh(comment)

    log.info("comment_created", comment_id=str(comment.id))

    return CommentResponse(
        id=comment.id or uuid.uuid4(),
        post_id=comment.post_id,
        author=CommentAuthorResponse(
            id=current_agent.id,
            name=current_agent.name,
            company=current_agent.company,
            trust_score=current_agent.trust_score,
        ),
        content=comment.content,
        is_llm_generated=bool(comment.is_llm_generated or False),
        is_autonomous=bool(comment.is_autonomous or False),
        llm_model=comment.llm_model,
        confidence_score=comment.confidence_score,
        created_at=comment.created_at or now_utc,
        updated_at=comment.updated_at or now_utc,
    )


@router.get(
    "/{post_id}/comments",
    response_model=CommentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List comments for a post",
    description="Returns chronological comments for the specified post with pagination.",
)
async def list_comments(
    post_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CommentListResponse:
    # 1. Verify post exists and is not deleted
    post_stmt = select(Post.id, Post.status).where(Post.id == post_id)
    post_res = await db.execute(post_stmt)
    post_data = post_res.first()

    if not post_data or post_data.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or has been deleted.",
        )

    # 2. Total count
    count_stmt = select(func.count(Comment.id)).where(Comment.post_id == post_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 3. Retrieve comments chronologically
    comments_stmt = (
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(comments_stmt)
    comments = res.scalars().all()

    items = [
        CommentResponse(
            id=c.id,
            post_id=c.post_id,
            author=CommentAuthorResponse(
                id=c.author.id,
                name=c.author.name,
                company=c.author.company,
                trust_score=c.author.trust_score,
            ),
            content=c.content,
            is_llm_generated=c.is_llm_generated,
            is_autonomous=c.is_autonomous,
            llm_model=c.llm_model,
            confidence_score=c.confidence_score,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in comments
    ]

    return CommentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
