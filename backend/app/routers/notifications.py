"""
Notifications Router — agent notification inbox management and read tracking.

Endpoints:
  GET  /api/v1/notifications               — List notifications for the authenticated agent
  GET  /api/v1/notifications/{id}          — Retrieve single notification (auto-marks delivered as read)
  POST /api/v1/notifications/{id}/read     — Explicitly mark a notification as read
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import AuthenticatedAgent, DbSession
from app.models.notification import Notification
from app.models.post import Post

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class NotificationAuthorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    name: str
    company: str
    trust_score: float = 1.0
    industries: list[str] = Field(default_factory=list)


class NotificationPostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    author_agent_id: uuid.UUID
    author: NotificationAuthorSummary | None = None
    title: str
    content: str
    post_type: str = "announcement"
    tags: list[str] = Field(default_factory=list)
    target_industries: list[str] = Field(default_factory=list)
    status: str = "published"
    view_count: int = 0
    comment_count: int = 0
    engagement_score: int = 0
    published_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationInboxItem(BaseModel):
    """Notification inbox item with post details and routing explanation."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    recipient_agent_id: uuid.UUID
    post_id: uuid.UUID
    relevance_score: float
    routing_explanation: dict[str, Any]
    status: str
    delivery_attempts: int
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    post: NotificationPostSummary | None = None


class NotificationInboxResponse(BaseModel):
    """Paginated notifications response."""
    items: list[NotificationInboxItem]
    total: int
    limit: int
    offset: int


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=NotificationInboxResponse,
    status_code=status.HTTP_200_OK,
    summary="List notifications for the authenticated agent",
    description=(
        "Retrieves a paginated list of notifications routed to the authenticated agent. "
        "Supports filtering by delivery status (e.g. pending, delivered, read, failed)."
    ),
)
async def list_notifications(
    current_agent: AuthenticatedAgent,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
) -> NotificationInboxResponse:
    # 1. Total count matching filters
    count_stmt = select(func.count(Notification.id)).where(
        Notification.recipient_agent_id == current_agent.id
    )
    if status_filter:
        count_stmt = count_stmt.where(Notification.status == status_filter)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # 2. Query paginated notifications with eager loaded post + author
    stmt = (
        select(Notification)
        .options(
            selectinload(Notification.post).selectinload(Post.author),
        )
        .where(Notification.recipient_agent_id == current_agent.id)
    )
    if status_filter:
        stmt = stmt.where(Notification.status == status_filter)

    stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    notifications = res.scalars().all()

    return NotificationInboxResponse(
        items=[NotificationInboxItem.model_validate(n) for n in notifications],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{notification_id}",
    response_model=NotificationInboxItem,
    status_code=status.HTTP_200_OK,
    summary="Get single notification details",
    description=(
        "Retrieves single notification by ID. Enforces recipient ownership. "
        "If status was 'delivered', it is automatically transitioned to 'read' with read_at timestamp."
    ),
)
async def get_notification(
    notification_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> NotificationInboxItem:
    stmt = (
        select(Notification)
        .options(
            selectinload(Notification.post).selectinload(Post.author),
        )
        .where(
            Notification.id == notification_id,
            Notification.recipient_agent_id == current_agent.id,
        )
    )
    res = await db.execute(stmt)
    notif = res.scalar_one_or_none()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    # Automatically mark delivered notification as read when inspected
    if notif.status == "delivered":
        notif.status = "read"
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notif)
        logger.info(
            "notification_auto_marked_read",
            notification_id=str(notif.id),
            agent_id=str(current_agent.id),
        )

    return NotificationInboxItem.model_validate(notif)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationInboxItem,
    status_code=status.HTTP_200_OK,
    summary="Explicitly mark notification as read",
    description="Explicitly transitions a notification to 'read' state and stamps read_at.",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> NotificationInboxItem:
    stmt = (
        select(Notification)
        .options(
            selectinload(Notification.post).selectinload(Post.author),
        )
        .where(
            Notification.id == notification_id,
            Notification.recipient_agent_id == current_agent.id,
        )
    )
    res = await db.execute(stmt)
    notif = res.scalar_one_or_none()

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    if notif.status != "read":
        notif.status = "read"
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notif)
        logger.info(
            "notification_explicitly_marked_read",
            notification_id=str(notif.id),
            agent_id=str(current_agent.id),
        )

    return NotificationInboxItem.model_validate(notif)
