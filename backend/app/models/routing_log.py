"""RoutingLog — full audit trail of every routing decision."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class RoutingLog(Base, TimestampMixin):
    __tablename__ = "routing_logs"
    __table_args__ = (
        UniqueConstraint("post_id", "candidate_agent_id", name="uq_routing_post_agent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )

    # Scores
    vector_score: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Explainability
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Decision
    was_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passed_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="routing_logs")  # noqa: F821
    candidate_agent: Mapped["Agent"] = relationship("Agent", back_populates="routing_logs")  # noqa: F821
