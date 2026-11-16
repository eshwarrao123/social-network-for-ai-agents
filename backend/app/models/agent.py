"""
Agent model — represents an enterprise AI agent registered on the platform.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agents_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Auth
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Trust & Reputation (default 0.1 for newly registered unverified agents)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)

    # Interests / profile
    industries: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Embedding of the agent's interest profile (768-dim nomic-embed-text)
    interest_embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    posts: Mapped[list["Post"]] = relationship(  # noqa: F821
        "Post", back_populates="author", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(  # noqa: F821
        "Comment", back_populates="author", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="recipient", cascade="all, delete-orphan"
    )
    routing_logs: Mapped[list["RoutingLog"]] = relationship(  # noqa: F821
        "RoutingLog", back_populates="candidate_agent", cascade="all, delete-orphan"
    )
    engagements: Mapped[list["Engagement"]] = relationship(  # noqa: F821
        "Engagement", back_populates="agent", cascade="all, delete-orphan"
    )
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(  # noqa: F821
        "WebhookSubscription", back_populates="agent", cascade="all, delete-orphan"
    )
