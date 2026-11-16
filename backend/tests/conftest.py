"""
Pytest configuration and fixtures for Asama.ai backend.

Architecture:
  - Unit tests:
      Run anywhere in any environment without PostgreSQL, Redis, or Ollama.
      Test business logic, encryption, signatures, scoring formulas, schemas, and routing math.
  - Integration tests (marked with @pytest.mark.integration):
      Require a live PostgreSQL instance with pgvector extension enabled.
      Connection target is defined by DATABASE_TEST_URL environment variable.
      If PostgreSQL is unreachable, integration tests fail/skip with a clear diagnostic message
      rather than pretending database tests passed.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure a deterministic Fernet key and JWT secret exist for all unit tests
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-testing-32-bytes!!")
os.environ.setdefault(
    "WEBHOOK_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8")
)
os.environ.setdefault(
    "DATABASE_TEST_URL",
    "postgresql+asyncpg://asama:asama_pass@localhost:5432/asama_test_db",
)

from app.config import get_settings
from app.database import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def test_fernet_key() -> str:
    """Provides a fresh, isolated 32-byte Fernet key for encryption testing."""
    return Fernet.generate_key().decode("utf-8")


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Standard test client for endpoints that do not require database persistence
    (e.g., system /health, module status checks).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Integration Test Fixtures (@pytest.mark.integration)
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def postgres_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Connects to the real PostgreSQL test database with pgvector.
    Fails or skips explicitly if PostgreSQL is not reachable.
    """
    settings = get_settings()
    test_db_url = os.environ.get("DATABASE_TEST_URL", settings.database_test_url)

    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Health check connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(
            f"PostgreSQL integration test skipped: cannot connect to {test_db_url}. "
            f"Reason: {exc}"
        )

    # Setup schema
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Teardown schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def postgres_session(
    postgres_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated AsyncSession against the live PostgreSQL test database."""
    session_factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def db_client(
    postgres_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX test client with live PostgreSQL session injected into FastAPI get_db."""
    async def override_get_db():
        yield postgres_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()
