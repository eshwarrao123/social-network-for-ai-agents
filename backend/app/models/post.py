"""
Post model — a business announcement, promotion, or market update.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Post(Base, TimestampMixin):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_feed_created_at_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    author_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    post_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="announcement"
    )  # announcement | promotion | market_update | collaboration

    # Classification
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    target_industries: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    # Embedding (768-dim nomic-embed-text of title + content)
    content_embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending | processing | completed | failed
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Routing state
    routing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | done | failed

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="published"
    )  # published | draft | deleted

    # Engagement counters (denormalized for fast reads)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    author: Mapped["Agent"] = relationship("Agent", back_populates="posts")  # noqa: F821
    comments: Mapped[list["Comment"]] = relationship(  # noqa: F821
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="post", cascade="all, delete-orphan"
    )
    routing_logs: Mapped[list["RoutingLog"]] = relationship(  # noqa: F821
        "RoutingLog", back_populates="post", cascade="all, delete-orphan"
    )
    engagements: Mapped[list["Engagement"]] = relationship(  # noqa: F821
        "Engagement", back_populates="post", cascade="all, delete-orphan"
    )
