"""
Auth service stub — full implementation in Phase 1.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def verify_token(token: str, db: AsyncSession):
    """Verify JWT and return Agent, or None. Implemented in Phase 1."""
    return None
