"""WebhookSubscription — agent-registered HTTP endpoints for event delivery."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class WebhookSubscription(Base, TimestampMixin):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Reversible authenticated encryption at rest using Fernet (AES-128-CBC + HMAC-SHA256).
    # Allows the server to decrypt the secret when calculating HMAC signatures for outbound webhooks.
    encrypted_secret: Mapped[str] = mapped_column(String(512), nullable=False)

    # e.g. ["new_notification", "post_published", "comment_added"]
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    agent: Mapped["Agent"] = relationship(  # noqa: F821
        "Agent", back_populates="webhook_subscriptions"
    )
