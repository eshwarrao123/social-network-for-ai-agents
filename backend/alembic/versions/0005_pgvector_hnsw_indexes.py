"""Add pgvector HNSW index for agents and notification delivery tracking

Revision ID: 0005_pgvector_hnsw_indexes
Revises: 0004_embedding_pipeline
Create Date: 2026-11-16 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_pgvector_hnsw_indexes"
down_revision: Union[str, None] = "0004_embedding_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create HNSW index on agents.interest_embedding for cosine distance search
    # m = 16 (bi-directional links per node), ef_construction = 64 (size of dynamic candidate list)
    # Uses vector_cosine_ops to support the pgvector <=> cosine distance operator.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agents_interest_embedding_hnsw "
        "ON agents USING hnsw (interest_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # 2. Add delivery_event_published_at to notifications table for durable Redis Streams dispatch tracking
    op.add_column(
        "notifications",
        sa.Column("delivery_event_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_delivery_event_published_at",
        "notifications",
        ["delivery_event_published_at"],
    )


def downgrade() -> None:
    # 1. Drop notification dispatch tracking column and index
    op.drop_index("ix_notifications_delivery_event_published_at", table_name="notifications")
    op.drop_column("notifications", "delivery_event_published_at")

    # 2. Drop HNSW index from agents table
    op.execute("DROP INDEX IF EXISTS ix_agents_interest_embedding_hnsw;")
