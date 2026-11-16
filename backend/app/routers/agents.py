"""
Agents router: enterprise registration and agent profile management.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import AuthenticatedAgent
from app.models.agent import Agent
from app.models.preference import AgentPreference
from app.models.webhook import WebhookSubscription
from app.schemas.agent import (
    AgentPreferenceResetResponse,
    AgentPreferenceResponse,
    AgentProfileResponse,
    AgentProfileUpdateRequest,
    AgentRegisterRequest,
    AgentRegisterResponse,
)
from app.services.auth import generate_api_key
from app.services.events import publish_agent_embed_event
from app.services.preference_service import cosine_similarity, get_preference_service
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

    # 6. Dispatch interest embedding event to background worker pipeline
    await publish_agent_embed_event(new_agent.id)

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
    profile_changed = False
    # Update only fields provided by client
    if payload.company is not None and payload.company != current_agent.company:
        current_agent.company = payload.company
        profile_changed = True
    if payload.description is not None and payload.description != current_agent.description:
        current_agent.description = payload.description
        profile_changed = True
    if payload.industries is not None and payload.industries != current_agent.industries:
        current_agent.industries = payload.industries
        profile_changed = True
    if payload.capabilities is not None and payload.capabilities != current_agent.capabilities:
        current_agent.capabilities = payload.capabilities
        profile_changed = True
    if payload.tags is not None and payload.tags != current_agent.tags:
        current_agent.tags = payload.tags
        profile_changed = True

    if profile_changed:
        current_agent.embedding_status = "pending"

    await db.commit()
    await db.refresh(current_agent)

    if profile_changed:
        await publish_agent_embed_event(current_agent.id)

    logger.info(
        "agent_profile_updated",
        agent_id=str(current_agent.id),
        name=current_agent.name,
        profile_changed=profile_changed,
    )

    return AgentProfileResponse.model_validate(current_agent)


@router.get(
    "/me/preferences",
    response_model=AgentPreferenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current agent adaptive preference statistics",
    description=(
        "Returns adaptive feedback statistics, engagement rates, and top learned topics. "
        "Raw vector embeddings are STRICTLY omitted to prevent vector theft and model inversion."
    ),
)
async def get_my_preferences(
    current_agent: AuthenticatedAgent,
    db: AsyncSession = Depends(get_db),
) -> AgentPreferenceResponse:
    settings = get_settings()
    stmt = select(AgentPreference).where(AgentPreference.agent_id == current_agent.id)
    res = await db.execute(stmt)
    pref = res.scalar_one_or_none()

    drift = 0.0
    if (
        pref
        and pref.learned_vector is not None
        and current_agent.interest_embedding is not None
    ):
        cos_sim = cosine_similarity(list(pref.learned_vector), list(current_agent.interest_embedding))
        # Drift = cosine distance = 1 - cos_sim
        drift = round(max(0.0, 1.0 - cos_sim), 4)

    learned_topics = pref.learned_topics if pref else {}
    top_pos = learned_topics.get("top_positive", []) if isinstance(learned_topics, dict) else []
    top_neg = learned_topics.get("top_negative", []) if isinstance(learned_topics, dict) else []

    return AgentPreferenceResponse(
        agent_id=current_agent.id,
        learning_enabled=getattr(settings, "feedback_learning_enabled", True),
        total_feedback_count=pref.total_feedback_count if (pref and pref.total_feedback_count is not None) else 0,
        positive_interactions_count=pref.positive_interactions_count if (pref and pref.positive_interactions_count is not None) else 0,
        negative_interactions_count=pref.negative_interactions_count if (pref and pref.negative_interactions_count is not None) else 0,
        engagement_rate=pref.engagement_rate if (pref and pref.engagement_rate is not None) else 0.0,
        learning_version=pref.learning_version if (pref and pref.learning_version is not None) else 1,
        drift_from_anchor=drift,
        top_positive_topics=top_pos,
        top_negative_topics=top_neg,
        last_updated_at=pref.last_updated_at if pref else None,
    )


@router.post(
    "/me/preferences/reset",
    response_model=AgentPreferenceResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset adaptive preferences to baseline manifesto anchor",
    description="Resets the learned preference vector back to the baseline manifesto embedding and clears learned topic counters.",
)
async def reset_my_preferences(
    current_agent: AuthenticatedAgent,
    db: AsyncSession = Depends(get_db),
) -> AgentPreferenceResetResponse:
    pref_service = get_preference_service()
    updated_pref = await pref_service.reset_preferences(db, current_agent.id)

    return AgentPreferenceResetResponse(
        agent_id=current_agent.id,
        message="Adaptive preferences successfully reset to baseline manifesto embedding.",
        learning_version=updated_pref.learning_version,
        reset_at=updated_pref.last_updated_at,
    )
