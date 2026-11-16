"""
Agent Preference and Feedback Ledger models — adaptive learning from interaction feedback.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class AgentPreference(Base):
    """
    Stores an agent's dynamic learned preference vector and interaction statistics.
    The baseline manifesto vector (Agent.interest_embedding) remains immutable as an anchor.
    """
    __tablename__ = "agent_preferences"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 768-dimensional learned preference vector (L2-normalized, bounded by anchor drift)
    learned_vector: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # Cumulative feedback statistics
    positive_interactions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_interactions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_feedback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Topic frequency distributions: {"positive": {"topic": count}, "negative": {"topic": count}}
    learned_topics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    learning_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship back to parent agent
    agent: Mapped["Agent"] = relationship("Agent", back_populates="preference")  # noqa: F821


class FeedbackLedger(Base):
    """
    Append-only audit ledger recording every processed feedback event.
    Guarantees strict idempotency via unique interaction_id constraint.
    """
    __tablename__ = "feedback_ledger"
    __table_args__ = (
        UniqueConstraint("interaction_id", name="uq_feedback_ledger_interaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    interaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_interactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Learning signal details
    signal: Mapped[str] = mapped_column(String(32), nullable=False)  # positive | negative
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    topics_applied: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
