"""Add agent interactions table and comment enhancements for autonomous AI interaction

Revision ID: 0006_agent_interactions_and_comments
Revises: 0005_pgvector_hnsw_indexes
Create Date: 2026-11-16 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_agent_interactions_and_comments"
down_revision: Union[str, None] = "0005_pgvector_hnsw_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add interaction_event_published_at to notifications table for durable Redis Streams dispatch tracking
    op.add_column(
        "notifications",
        sa.Column("interaction_event_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_interaction_event_published_at",
        "notifications",
        ["interaction_event_published_at"],
    )

    # 2. Add is_autonomous and idempotency_key to comments table
    op.add_column(
        "comments",
        sa.Column("is_autonomous", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "comments",
        sa.Column("idempotency_key", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_comments_idempotency_key",
        "comments",
        ["idempotency_key"],
    )

    # 3. Create agent_interactions table
    op.create_table(
        "agent_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "receiving_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("notification_id", name="uq_agent_interaction_notification"),
    )
    op.create_index("ix_agent_interactions_notification_id", "agent_interactions", ["notification_id"])
    op.create_index("ix_agent_interactions_receiving_agent_id", "agent_interactions", ["receiving_agent_id"])
    op.create_index("ix_agent_interactions_post_id", "agent_interactions", ["post_id"])
    op.create_index("ix_agent_interactions_comment_id", "agent_interactions", ["comment_id"])
    op.create_index("ix_agent_interactions_status", "agent_interactions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_interactions_status", table_name="agent_interactions")
    op.drop_index("ix_agent_interactions_comment_id", table_name="agent_interactions")
    op.drop_index("ix_agent_interactions_post_id", table_name="agent_interactions")
    op.drop_index("ix_agent_interactions_receiving_agent_id", table_name="agent_interactions")
    op.drop_index("ix_agent_interactions_notification_id", table_name="agent_interactions")
    op.drop_table("agent_interactions")

    op.drop_index("ix_comments_idempotency_key", table_name="comments")
    op.drop_column("comments", "idempotency_key")
    op.drop_column("comments", "is_autonomous")

    op.drop_index("ix_notifications_interaction_event_published_at", table_name="notifications")
    op.drop_column("notifications", "interaction_event_published_at")
