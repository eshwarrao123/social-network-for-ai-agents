"""
Authentication router: machine-to-machine token issuance.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.auth import TokenRequest, TokenResponse
from app.services.auth import authenticate_agent_by_api_key, create_access_token

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange agent API key for short-lived Bearer JWT",
    description=(
        "Authenticates a registered enterprise AI agent using its private API key. "
        "Returns a short-lived signed JWT access token for subsequent authorized API calls."
    ),
)
async def issue_access_token(
    request: Request,
    payload: TokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # 1. Authenticate agent against hashed API key in DB
    agent = await authenticate_agent_by_api_key(payload.api_key, db)
    if agent is None:
        logger.warning(
            "agent_authentication_failed",
            api_key_prefix=payload.api_key[:12] if len(payload.api_key) >= 12 else "short",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unverified API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Check if agent is active
    if not agent.is_active:
        logger.warning("inactive_agent_login_blocked", agent_id=str(agent.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent account is inactive or has been suspended.",
        )

    # 3. Update last active timestamp
    agent.last_active_at = datetime.now(timezone.utc)
    await db.commit()

    # 4. Generate JWT
    token_str, expires_in = create_access_token(agent)

    logger.info(
        "agent_token_issued",
        agent_id=str(agent.id),
        name=agent.name,
        company=agent.company,
    )

    return TokenResponse(
        access_token=token_str,
        token_type="bearer",
        expires_in=expires_in,
        agent_id=agent.id,
        agent_name=agent.name,
        company=agent.company,
    )
