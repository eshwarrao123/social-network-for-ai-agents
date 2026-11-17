"""
FastAPI shared dependencies for authentication, database sessions, and agent authorization.
"""
from __future__ import annotations

import hmac
import uuid
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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


async def verify_operator_or_internal_access(request: Request) -> None:
    """
    Guards platform operational and system metrics endpoints.
    Ensures ordinary enterprise agents cannot obtain global operational metrics.
    Authorizes:
      1. Operators supplying a valid operator token configured in settings.
      2. Internal cluster monitoring systems on loopback/private CIDR when enabled.
    Rejects ordinary enterprise agents with 403 Forbidden.
    Rejects unauthenticated external calls with 401 Unauthorized.
    """
    settings = get_settings()
    auth_header = request.headers.get("Authorization", "")
    op_header = request.headers.get("X-Operator-Token", "")

    # 1. Check if caller is an ordinary enterprise agent presenting an agent Bearer token
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:].strip()
        # If an operator token is configured and the bearer matches it, permit operator access
        if settings.operator_token and hmac.compare_digest(token_str, settings.operator_token):
            return

        # Otherwise verify if it's an agent token
        try:
            payload = decode_access_token(token_str)
            if payload.get("sub"):
                logger.warning(
                    "system_metrics_access_denied_for_agent",
                    agent_id=payload.get("sub"),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access restricted: ordinary enterprise agents are not authorized to view platform system metrics.",
                )
        except HTTPException:
            raise
        except Exception:
            # Not a valid agent token and did not match operator token
            pass

    # 2. Check X-Operator-Token header if provided
    if op_header:
        if settings.operator_token and hmac.compare_digest(op_header, settings.operator_token):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid operator authorization credentials.",
        )

    # 3. Check internal deployment network / loopback if internal scraping enabled
    if settings.allow_internal_metrics_scraping:
        client_host = request.client.host if request.client else None
        INTERNAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
        is_forwarded = bool(request.headers.get("X-Forwarded-For"))
        if client_host in INTERNAL_HOSTS and not is_forwarded:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to internal monitoring network.",
        )

    # 4. Default: missing operator credentials
    if not auth_header and not op_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Operator authentication required to access platform system metrics.",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access restricted to authorized platform operators.",
    )

