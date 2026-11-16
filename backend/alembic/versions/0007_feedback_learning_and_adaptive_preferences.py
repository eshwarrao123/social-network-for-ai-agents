"""Add feedback learning and adaptive preferences tables

Revision ID: 0007_feedback_learning_and_adaptive_preferences
Revises: 0006_agent_interactions_and_comments
Create Date: 2026-11-16 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_feedback_learning_and_adaptive_preferences"
down_revision: Union[str, None] = "0006_agent_interactions_and_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add feedback_event_published_at to agent_interactions table for durable stream tracking
    op.add_column(
        "agent_interactions",
        sa.Column("feedback_event_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_interactions_feedback_event_published_at",
        "agent_interactions",
        ["feedback_event_published_at"],
    )

    # 2. Create agent_preferences table
    op.create_table(
        "agent_preferences",
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("learned_vector", Vector(768), nullable=True),
        sa.Column("positive_interactions_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("negative_interactions_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_feedback_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("engagement_rate", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("learned_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("learning_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. Create feedback_ledger table
    op.create_table(
        "feedback_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "interaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_interactions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
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
        sa.Column("signal", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("topics_applied", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'::varchar[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("interaction_id", name="uq_feedback_ledger_interaction_id"),
    )
    op.create_index("ix_feedback_ledger_interaction_id", "feedback_ledger", ["interaction_id"])
    op.create_index("ix_feedback_ledger_notification_id", "feedback_ledger", ["notification_id"])
    op.create_index("ix_feedback_ledger_agent_id", "feedback_ledger", ["agent_id"])
    op.create_index("ix_feedback_ledger_post_id", "feedback_ledger", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_ledger_post_id", table_name="feedback_ledger")
    op.drop_index("ix_feedback_ledger_agent_id", table_name="feedback_ledger")
    op.drop_index("ix_feedback_ledger_notification_id", table_name="feedback_ledger")
    op.drop_index("ix_feedback_ledger_interaction_id", table_name="feedback_ledger")
    op.drop_table("feedback_ledger")

    op.drop_table("agent_preferences")

    op.drop_index("ix_agent_interactions_feedback_event_published_at", table_name="agent_interactions")
    op.drop_column("agent_interactions", "feedback_event_published_at")
