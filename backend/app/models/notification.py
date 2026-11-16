"""Notification model — in-app delivery of routing decisions."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )

    # Routing result
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    routing_explanation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Delivery state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | delivered | read | failed
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    recipient: Mapped["Agent"] = relationship("Agent", back_populates="notifications")  # noqa: F821
    post: Mapped["Post"] = relationship("Post", back_populates="notifications")  # noqa: F821
