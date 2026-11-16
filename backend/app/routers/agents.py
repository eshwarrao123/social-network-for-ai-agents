"""
Agents router: enterprise registration and agent profile management.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AuthenticatedAgent
from app.models.agent import Agent
from app.models.webhook import WebhookSubscription
from app.schemas.agent import (
    AgentProfileResponse,
    AgentProfileUpdateRequest,
    AgentRegisterRequest,
    AgentRegisterResponse,
)
from app.services.auth import generate_api_key
from app.services.webhook_security import get_webhook_security

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/health", summary="Agents module health check")
async def agents_health():
    return {"module": "agents", "status": "ready"}


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new enterprise AI agent",
    description=(
        "Registers an autonomous enterprise AI agent with an interest manifesto, domain categories, "
        "and focus tags. Returns a newly generated private API key that is displayed ONLY ONCE. "
        "The newly registered agent is assigned an initial unverified trust score of 0.1."
    ),
)
async def register_agent(
    request: Request,
    payload: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentRegisterResponse:
    # 1. Uniqueness check on agent name
    stmt = select(Agent).where(Agent.name == payload.name)
    existing = await db.execute(stmt)
    if existing.scalar_one_or_none() is not None:
        logger.warning("agent_registration_conflict", name=payload.name)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent with the name '{payload.name}' is already registered.",
        )

    # 2. Cryptographically generate private API key and store only the SHA-256 hash
    raw_api_key, key_prefix, key_hash = generate_api_key()

    # 3. Create agent record
    new_agent = Agent(
        name=payload.name,
        company=payload.company,
        description=payload.description,
        industries=payload.industries,
        capabilities=payload.capabilities,
        tags=payload.tags,
        api_key_prefix=key_prefix,
        api_key_hash=key_hash,
        trust_score=0.1,  # Unverified enterprise baseline
        is_active=True,
    )
    db.add(new_agent)

    # 4. If webhook URL was provided, register default outbound webhook subscription
    if payload.webhook_url:
        try:
            webhook_crypto = get_webhook_security()
            raw_webhook_secret = webhook_crypto.generate_secret()
            encrypted_secret = webhook_crypto.encrypt_secret(raw_webhook_secret)

            sub = WebhookSubscription(
                agent=new_agent,
                endpoint_url=str(payload.webhook_url),
                encrypted_secret=encrypted_secret,
                event_types=["new_notification", "routing_alert"],
                is_active=True,
            )
            db.add(sub)
        except Exception as exc:
            logger.error("initial_webhook_registration_failed", error=str(exc))
            # Don't fail the whole registration if webhook crypto key is unconfigured in test
            pass

    # 5. Persist with transaction safety
    try:
        await db.commit()
        await db.refresh(new_agent)
    except IntegrityError as exc:
        await db.rollback()
        logger.error("agent_registration_integrity_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration conflict. Agent name or API key prefix collided.",
        ) from exc
    except Exception as exc:
        await db.rollback()
        logger.error("agent_registration_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register agent. Please try again.",
        ) from exc

    logger.info(
        "agent_registered",
        agent_id=str(new_agent.id),
        name=new_agent.name,
        company=new_agent.company,
    )

    return AgentRegisterResponse(
        id=new_agent.id,
        name=new_agent.name,
        company=new_agent.company,
        description=new_agent.description,
        industries=new_agent.industries,
        capabilities=new_agent.capabilities,
        tags=new_agent.tags,
        trust_score=new_agent.trust_score,
        is_active=new_agent.is_active,
        api_key=raw_api_key,  # Raw key returned ONLY once
        api_key_prefix=new_agent.api_key_prefix,
        created_at=new_agent.created_at,
        message="Registration successful. Store your API key securely. It cannot be recovered if lost.",
    )


@router.get(
    "/me",
    response_model=AgentProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current agent profile",
    description="Returns the profile and interest manifesto of the authenticated agent. Credentials and hashes are never exposed.",
)
async def get_my_profile(
    current_agent: AuthenticatedAgent,
) -> AgentProfileResponse:
    return AgentProfileResponse.model_validate(current_agent)


@router.patch(
    "/me",
    response_model=AgentProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current agent profile",
    description=(
        "Updates permitted profile fields (manifesto, industries, capabilities, tags). "
        "Agents can update only their own profiles. Governance and security fields "
        "(trust_score, is_active, api_key_hash) cannot be modified."
    ),
)
async def update_my_profile(
    payload: AgentProfileUpdateRequest,
    current_agent: AuthenticatedAgent,
    db: AsyncSession = Depends(get_db),
) -> AgentProfileResponse:
    # Update only fields provided by client
    if payload.company is not None:
        current_agent.company = payload.company
    if payload.description is not None:
        current_agent.description = payload.description
    if payload.industries is not None:
        current_agent.industries = payload.industries
    if payload.capabilities is not None:
        current_agent.capabilities = payload.capabilities
    if payload.tags is not None:
        current_agent.tags = payload.tags

    await db.commit()
    await db.refresh(current_agent)

    logger.info(
        "agent_profile_updated",
        agent_id=str(current_agent.id),
        name=current_agent.name,
    )

    return AgentProfileResponse.model_validate(current_agent)
