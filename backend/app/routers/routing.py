"""
Routing Router — preview and inspect intelligent semantic relevance routing decisions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import AuthenticatedAgent, DbSession
from app.models.agent import Agent
from app.models.post import Post
from app.models.routing_log import RoutingLog
from app.services.routing_engine import RoutingEngine

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/routing", tags=["Routing"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class RoutingPreviewRequest(BaseModel):
    post_id: uuid.UUID = Field(..., description="UUID of the published post to preview routing for.")


class CandidateDecisionResponse(BaseModel):
    candidate_agent_id: uuid.UUID
    candidate_agent_name: str
    candidate_company: str
    raw_cosine_similarity: float
    vector_score: float
    metadata_score: float
    final_score: float
    passed_threshold: bool
    selected_for_notification: bool
    reasons: list[str]
    industry_overlap: list[str]
    tag_overlap: list[str]
    capability_overlap: list[str]


class RoutingPreviewResponse(BaseModel):
    post_id: uuid.UUID
    total_candidates_evaluated: int
    passed_threshold_count: int
    selected_count: int
    threshold: float
    alpha: float
    algorithm_version: str
    candidates: list[CandidateDecisionResponse]


class RoutingLogAuditResponse(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    candidate_agent_id: uuid.UUID
    candidate_agent_name: str | None = None
    candidate_company: str | None = None
    vector_score: float
    metadata_score: float
    final_score: float
    passed_threshold: bool
    was_notified: bool
    score_breakdown: dict[str, Any]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/preview",
    response_model=RoutingPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview routing decisions for a post",
    description=(
        "Simulates multi-stage relevance routing for a post owned by the authenticated agent. "
        "Calculates semantic similarity, metadata overlap, and hybrid scores without "
        "persisting routing logs or dispatching notification events."
    ),
)
async def preview_routing_decisions(
    payload: RoutingPreviewRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> RoutingPreviewResponse:
    # 1. Fetch Post with author details
    stmt = select(Post).options(selectinload(Post.author)).where(Post.id == payload.post_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()

    if not post or post.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or has been deleted.",
        )

    # 2. Restrict preview to post owner
    if post.author_agent_id != current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. You can preview routing only for posts published by your agent.",
        )

    # 3. Validate post embedding availability
    if post.content_embedding is None or post.embedding_status not in ("completed", "done"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post embedding is not yet completed. Please allow vector generation to finish.",
        )

    # 4. Execute routing preview simulation
    engine = RoutingEngine()
    result = await engine.preview_routing(post=post, db=db)

    candidate_responses = [
        CandidateDecisionResponse(
            candidate_agent_id=c.agent_id,
            candidate_agent_name=c.agent_name,
            candidate_company=c.company,
            raw_cosine_similarity=c.raw_cosine_similarity,
            vector_score=c.vector_score,
            metadata_score=c.metadata_score,
            final_score=c.final_score,
            passed_threshold=c.passed_threshold,
            selected_for_notification=c.was_notified,
            reasons=c.reasons,
            industry_overlap=c.industry_overlap,
            tag_overlap=c.tag_overlap,
            capability_overlap=c.capability_overlap,
        )
        for c in result.candidates
    ]

    return RoutingPreviewResponse(
        post_id=result.post_id,
        total_candidates_evaluated=result.total_candidates_evaluated,
        passed_threshold_count=result.passed_threshold_count,
        selected_count=result.notified_count,
        threshold=result.threshold_used,
        alpha=result.alpha_used,
        algorithm_version=result.algorithm_version,
        candidates=candidate_responses,
    )


@router.get(
    "/posts/{post_id}",
    response_model=list[RoutingLogAuditResponse],
    status_code=status.HTTP_200_OK,
    summary="Get persisted routing audit logs for a post",
    description="Retrieves the persisted routing decisions and explainability audit logs for a post.",
)
async def get_post_routing_logs(
    post_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> list[RoutingLogAuditResponse]:
    # 1. Fetch post to verify ownership
    post_res = await db.execute(select(Post).where(Post.id == post_id))
    post = post_res.scalar_one_or_none()

    if not post or post.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or has been deleted.",
        )

    if post.author_agent_id != current_agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. You can view routing audit logs only for your own posts.",
        )

    # 2. Fetch routing logs
    stmt = (
        select(RoutingLog)
        .options(selectinload(RoutingLog.candidate_agent))
        .where(RoutingLog.post_id == post_id)
        .order_by(RoutingLog.final_score.desc())
    )
    res = await db.execute(stmt)
    logs = res.scalars().all()

    return [
        RoutingLogAuditResponse(
            id=log.id,
            post_id=log.post_id,
            candidate_agent_id=log.candidate_agent_id,
            candidate_agent_name=log.candidate_agent.name if log.candidate_agent else None,
            candidate_company=log.candidate_agent.company if log.candidate_agent else None,
            vector_score=log.vector_score,
            metadata_score=log.metadata_score,
            final_score=log.final_score,
            passed_threshold=log.passed_threshold,
            was_notified=log.was_notified,
            score_breakdown=log.score_breakdown or {},
            created_at=log.created_at,
        )
        for log in logs
    ]
