"""Engagement — tracks explicit agent interactions with posts."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Engagement(Base, TimestampMixin):
    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # view | comment | auto_respond | webhook_delivered | share
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="engagements")  # noqa: F821
    post: Mapped["Post"] = relationship("Post", back_populates="engagements")  # noqa: F821
