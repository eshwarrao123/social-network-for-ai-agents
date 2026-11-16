"""
Webhooks Router — agent subscription management for outbound event notifications.

Endpoints:
  POST   /api/v1/webhooks                 — Create webhook subscription (reveals secret ONCE)
  GET    /api/v1/webhooks                 — List authenticated agent's subscriptions
  GET    /api/v1/webhooks/{id}            — Get single subscription details
  PATCH  /api/v1/webhooks/{id}            — Update endpoint URL, event types, or active status
  POST   /api/v1/webhooks/{id}/rotate-secret — Rotate HMAC signing secret (reveals new secret ONCE)
  DELETE /api/v1/webhooks/{id}            — Delete subscription
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import AuthenticatedAgent, DbSession
from app.models.agent import Agent
from app.models.webhook import WebhookSubscription
from app.services.ssrf_protection import SSRFError, validate_destination_url
from app.services.webhook_security import get_webhook_security

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CreateWebhookRequest(BaseModel):
    endpoint_url: str = Field(..., description="HTTPS endpoint URL to receive webhook event dispatches.")
    event_types: list[str] = Field(
        default=["new_notification"],
        description="Event types to subscribe to (e.g. ['new_notification']).",
    )
    is_active: bool = Field(default=True, description="Whether the webhook subscription is immediately active.")

    @field_validator("endpoint_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("endpoint_url cannot be empty.")
        settings = get_settings()
        try:
            validate_destination_url(
                v,
                allow_http=settings.webhook_allow_http,
                allowed_ports=set(settings.webhook_allowed_ports),
            )
        except SSRFError as exc:
            raise ValueError(f"Invalid or prohibited webhook endpoint URL: {exc}") from exc
        return v


class UpdateWebhookRequest(BaseModel):
    endpoint_url: str | None = Field(default=None, description="Updated HTTPS endpoint URL.")
    event_types: list[str] | None = Field(default=None, description="Updated subscribed event types.")
    is_active: bool | None = Field(default=None, description="Enable or disable subscription.")

    @field_validator("endpoint_url")
    @classmethod
    def validate_optional_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("endpoint_url cannot be empty.")
        settings = get_settings()
        try:
            validate_destination_url(
                v,
                allow_http=settings.webhook_allow_http,
                allowed_ports=set(settings.webhook_allowed_ports),
            )
        except SSRFError as exc:
            raise ValueError(f"Invalid or prohibited webhook endpoint URL: {exc}") from exc
        return v


class WebhookSubscriptionResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    endpoint_url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreatedResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    endpoint_url: str
    event_types: list[str]
    is_active: bool
    secret: str = Field(
        ...,
        description="Plaintext HMAC signing secret. Store securely immediately. Revealed ONLY ONCE.",
    )
    created_at: datetime


class WebhookSecretRotatedResponse(BaseModel):
    id: uuid.UUID
    secret: str = Field(
        ...,
        description="New plaintext HMAC signing secret. Store securely immediately. Revealed ONLY ONCE.",
    )
    rotated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=WebhookSubscriptionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook subscription",
    description=(
        "Registers a new HTTPS endpoint for the authenticated agent. Generates a secure "
        "HMAC-SHA256 signing secret which is revealed exactly once."
    ),
)
async def create_webhook_subscription(
    payload: CreateWebhookRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> WebhookSubscriptionCreatedResponse:
    webhook_sec = get_webhook_security()

    # Generate cryptographically secure 32-byte signing secret
    plaintext_secret = webhook_sec.generate_secret()
    encrypted_secret = webhook_sec.encrypt_secret(plaintext_secret)

    subscription = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=current_agent.id,
        endpoint_url=payload.endpoint_url,
        encrypted_secret=encrypted_secret,
        event_types=payload.event_types,
        is_active=payload.is_active,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    logger.info(
        "webhook_subscription_created",
        agent_id=str(current_agent.id),
        subscription_id=str(subscription.id),
        endpoint_url=subscription.endpoint_url,
    )

    now_utc = datetime.now(timezone.utc)
    return WebhookSubscriptionCreatedResponse(
        id=subscription.id,
        agent_id=subscription.agent_id,
        endpoint_url=subscription.endpoint_url,
        event_types=subscription.event_types,
        is_active=subscription.is_active,
        secret=plaintext_secret,
        created_at=subscription.created_at or now_utc,
    )


@router.get(
    "",
    response_model=list[WebhookSubscriptionResponse],
    status_code=status.HTTP_200_OK,
    summary="List authenticated agent's webhook subscriptions",
    description="Returns all registered webhook subscriptions for the authenticated agent. Never exposes secrets.",
)
async def list_webhook_subscriptions(
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> list[WebhookSubscriptionResponse]:
    stmt = (
        select(WebhookSubscription)
        .where(WebhookSubscription.agent_id == current_agent.id)
        .order_by(WebhookSubscription.created_at.desc())
    )
    res = await db.execute(stmt)
    subscriptions = res.scalars().all()

    return [
        WebhookSubscriptionResponse(
            id=sub.id,
            agent_id=sub.agent_id,
            endpoint_url=sub.endpoint_url,
            event_types=sub.event_types,
            is_active=sub.is_active,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )
        for sub in subscriptions
    ]


@router.get(
    "/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single webhook subscription details",
)
async def get_webhook_subscription(
    subscription_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> WebhookSubscriptionResponse:
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id,
        WebhookSubscription.agent_id == current_agent.id,
    )
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found.",
        )

    return WebhookSubscriptionResponse(
        id=sub.id,
        agent_id=sub.agent_id,
        endpoint_url=sub.endpoint_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


@router.patch(
    "/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update webhook subscription",
)
async def update_webhook_subscription(
    subscription_id: uuid.UUID,
    payload: UpdateWebhookRequest,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> WebhookSubscriptionResponse:
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id,
        WebhookSubscription.agent_id == current_agent.id,
    )
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found.",
        )

    if payload.endpoint_url is not None:
        sub.endpoint_url = payload.endpoint_url
    if payload.event_types is not None:
        sub.event_types = payload.event_types
    if payload.is_active is not None:
        sub.is_active = payload.is_active

    sub.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sub)

    logger.info(
        "webhook_subscription_updated",
        agent_id=str(current_agent.id),
        subscription_id=str(sub.id),
        is_active=sub.is_active,
    )

    return WebhookSubscriptionResponse(
        id=sub.id,
        agent_id=sub.agent_id,
        endpoint_url=sub.endpoint_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


@router.post(
    "/{subscription_id}/rotate-secret",
    response_model=WebhookSecretRotatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate webhook signing secret",
    description="Generates a new HMAC signing secret for the subscription and invalidates the previous secret.",
)
async def rotate_webhook_secret(
    subscription_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> WebhookSecretRotatedResponse:
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id,
        WebhookSubscription.agent_id == current_agent.id,
    )
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found.",
        )

    webhook_sec = get_webhook_security()
    new_plaintext_secret = webhook_sec.generate_secret()
    sub.encrypted_secret = webhook_sec.encrypt_secret(new_plaintext_secret)
    sub.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "webhook_secret_rotated",
        agent_id=str(current_agent.id),
        subscription_id=str(sub.id),
    )

    return WebhookSecretRotatedResponse(
        id=sub.id,
        secret=new_plaintext_secret,
        rotated_at=sub.updated_at,
    )


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete webhook subscription",
)
async def delete_webhook_subscription(
    subscription_id: uuid.UUID,
    current_agent: AuthenticatedAgent,
    db: DbSession,
) -> None:
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == subscription_id,
        WebhookSubscription.agent_id == current_agent.id,
    )
    res = await db.execute(stmt)
    sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found.",
        )

    await db.delete(sub)
    await db.commit()

    logger.info(
        "webhook_subscription_deleted",
        agent_id=str(current_agent.id),
        subscription_id=str(subscription_id),
    )
