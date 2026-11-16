"""Add embedding status and model tracking for agents and posts

Revision ID: 0004_embedding_pipeline
Revises: 0003_post_expires_at_and_feed_index
Create Date: 2026-11-16 14:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_embedding_pipeline"
down_revision: Union[str, None] = "0003_post_expires_at_and_feed_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add embedding_status and embedding_model to agents table
    op.add_column(
        "agents",
        sa.Column(
            "embedding_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index("ix_agents_embedding_status", "agents", ["embedding_status"])
    op.add_column(
        "agents",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )

    # 2. Add embedding_model and index on embedding_status for posts table
    op.add_column(
        "posts",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.create_index("ix_posts_embedding_status", "posts", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_posts_embedding_status", table_name="posts")
    op.drop_column("posts", "embedding_model")
    op.drop_column("agents", "embedding_model")
    op.drop_index("ix_agents_embedding_status", table_name="agents")
    op.drop_column("agents", "embedding_status")
