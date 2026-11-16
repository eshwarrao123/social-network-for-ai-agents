"""AgentInteraction model — records autonomous evaluation decisions and LLM responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class AgentInteraction(Base, TimestampMixin):
    __tablename__ = "agent_interactions"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", name="uq_agent_interaction_notification"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    receiving_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Decision and evaluation outcome
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # engage | ignore
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Lifecycle state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending | processing | engaged | ignored | failed

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_event_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    notification: Mapped["Notification"] = relationship("Notification", back_populates="interaction")  # noqa: F821
    receiving_agent: Mapped["Agent"] = relationship("Agent")  # noqa: F821
    post: Mapped["Post"] = relationship("Post")  # noqa: F821
    comment: Mapped["Comment | None"] = relationship("Comment")  # noqa: F821
