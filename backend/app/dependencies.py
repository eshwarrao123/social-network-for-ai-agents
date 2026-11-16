"""
FastAPI shared dependencies for authentication, database sessions, and agent authorization.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.services.auth import (
    AuthError,
    InvalidTokenError,
    TokenExpiredError,
    decode_access_token,
)

logger = structlog.get_logger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> Agent:
    """
    Extracts and verifies the Bearer JWT access token from request headers.
    Loads the Agent ORM object from the database.
    Raises 401 on missing, expired, or malformed credentials.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"token_expired\""},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or malformed authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    agent_id_str = payload.get("sub")
    if not agent_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        agent_id = uuid.UUID(agent_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed agent UUID in token subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(Agent).where(Agent.id == agent_id)
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated agent does not exist or has been deleted.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return agent


async def get_active_agent(
    current_agent: Annotated[Agent, Depends(get_current_agent)],
) -> Agent:
    """
    Ensures the authenticated agent is active and not suspended or disabled.
    Raises 403 Forbidden if is_active is False.
    """
    if not current_agent.is_active:
        logger.warning("inactive_agent_access_denied", agent_id=str(current_agent.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent account is inactive or has been suspended by governance.",
        )
    return current_agent


# Convenient dependency aliases for endpoints
CurrentAgent = Annotated[Agent, Depends(get_current_agent)]
AuthenticatedAgent = Annotated[Agent, Depends(get_active_agent)]
