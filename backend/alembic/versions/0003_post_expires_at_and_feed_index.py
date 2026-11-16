"""Add expires_at and feed index to posts

Revision ID: 0003_post_expires_at_and_feed_index
Revises: 0002_agent_auth_and_trust_score
Create Date: 2026-11-16 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_post_expires_at_and_feed_index"
down_revision: Union[str, None] = "0002_agent_auth_and_trust_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add optional expires_at column and index for time-to-live post filtering
    op.add_column(
        "posts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_posts_expires_at", "posts", ["expires_at"])

    # 2. Add composite index for deterministic keyset pagination on feed (created_at DESC, id DESC)
    op.create_index(
        "ix_posts_feed_created_at_id",
        "posts",
        ["created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_posts_feed_created_at_id", table_name="posts")
    op.drop_index("ix_posts_expires_at", table_name="posts")
    op.drop_column("posts", "expires_at")
