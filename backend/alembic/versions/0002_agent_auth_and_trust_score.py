"""Add api_key_prefix, trust_score, and uniqueness constraints to agents

Revision ID: 0002_agent_auth_and_trust_score
Revises: 0001_initial_schema
Create Date: 2026-11-16 01:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_agent_auth_and_trust_score"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add api_key_prefix column and index
    op.add_column(
        "agents",
        sa.Column(
            "api_key_prefix",
            sa.String(16),
            nullable=False,
            server_default="asama_live_",
        ),
    )
    op.create_index("ix_agents_api_key_prefix", "agents", ["api_key_prefix"])

    # 2. Add trust_score column (default 0.1 for newly registered unverified agents)
    op.add_column(
        "agents",
        sa.Column(
            "trust_score",
            sa.Float(),
            nullable=False,
            server_default="0.1",
        ),
    )

    # 3. Add unique constraint on agent name
    op.create_unique_constraint("uq_agents_name", "agents", ["name"])

    # 4. Add unique index on api_key_hash
    op.create_index("ix_agents_api_key_hash", "agents", ["api_key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agents_api_key_hash", table_name="agents")
    op.drop_constraint("uq_agents_name", "agents", type_="unique")
    op.drop_column("agents", "trust_score")
    op.drop_index("ix_agents_api_key_prefix", table_name="agents")
    op.drop_column("agents", "api_key_prefix")
