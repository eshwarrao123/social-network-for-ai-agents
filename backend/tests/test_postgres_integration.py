"""
PostgreSQL integration test stub.
Marked with @pytest.mark.integration.
Requires live PostgreSQL with pgvector extension enabled.
If PostgreSQL is unreachable, it skips with a clear diagnostic explanation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_postgres_pgvector_connection(postgres_session: AsyncSession):
    """
    Verifies connection to real PostgreSQL and checks that pgvector extension is functional.
    Automatically skipped if PostgreSQL is not available at DATABASE_TEST_URL.
    """
    result = await postgres_session.execute(
        text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
    )
    row = result.fetchone()
    assert row is not None, "pgvector extension is not installed in the database"
    assert row[0] == "vector"
