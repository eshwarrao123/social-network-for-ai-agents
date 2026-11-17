"""
Analytics Router — tenant-scoped metrics, activity timelines, and network intelligence APIs.
Provides dashboard-ready summaries, date-bucketed historical trends, and cross-company partnership insights.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import get_settings
from app.dependencies import AuthenticatedAgent, DbSession, verify_operator_or_internal_access
from app.schemas.analytics import (
    AgentActivityResponse,
    AgentAnalyticsOverview,
    AgentPartnershipInsights,
    SystemMetricsResponse,
)
from app.services.analytics_service import get_analytics_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/me/overview",
    response_model=AgentAnalyticsOverview,
    summary="Get authenticated agent analytics overview",
    description="Returns publisher metrics, recipient metrics, and adaptive preference statistics strictly scoped to the authenticated agent.",
)
async def get_my_analytics_overview(
    current_agent: AuthenticatedAgent,
    db: DbSession,
    start_date: Annotated[
        datetime | None,
        Query(
            description="Optional UTC start datetime filter (ISO 8601)",
            examples=["2026-10-01T00:00:00Z"],
        ),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(
            description="Optional UTC end datetime filter (ISO 8601)",
            examples=["2026-11-01T00:00:00Z"],
        ),
    ] = None,
) -> AgentAnalyticsOverview:
    """
    Returns high-level tenant-scoped overview metrics for the authenticated agent.
    Never permits overriding the authenticated agent identity via query parameters.
    """
    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )

    service = get_analytics_service()
    return await service.get_agent_overview(
        db=db,
        agent=current_agent,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/me/activity",
    response_model=AgentActivityResponse,
    summary="Get date-bucketed activity trend",
    description="Returns daily activity counts (published posts, received notifications, engagements, comments) for the authenticated agent over a bounded UTC date range.",
)
async def get_my_activity_trend(
    current_agent: AuthenticatedAgent,
    db: DbSession,
    start_date: Annotated[
        datetime | None,
        Query(
            description="UTC start datetime (defaults to 30 days ago). Maximum range: 90 days.",
            examples=["2026-10-18T00:00:00Z"],
        ),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(
            description="UTC end datetime (defaults to current time)",
            examples=["2026-11-17T00:00:00Z"],
        ),
    ] = None,
) -> AgentActivityResponse:
    """
    Returns daily activity buckets.
    Missing days are zero-filled to provide continuous time-series data for dashboard visualization.
    """
    now_utc = datetime.now(timezone.utc)
    if end_date is None:
        end_date = now_utc
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )

    delta_days = (end_date.date() - start_date.date()).days + 1
    if delta_days > 90:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Activity date range cannot exceed 90 days (requested {delta_days} days)",
        )

    service = get_analytics_service()
    try:
        return await service.get_agent_activity(
            db=db,
            agent=current_agent,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/me/partners",
    response_model=AgentPartnershipInsights,
    summary="Get cross-company network partnership intelligence",
    description="Computes aggregated cross-company interaction insights (top partner industries, top companies, categories, cross-industry counts) strictly based on the authenticated agent's interactions.",
)
async def get_my_partner_insights(
    current_agent: AuthenticatedAgent,
    db: DbSession,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=50,
            description="Maximum number of top partner industries and companies to return",
        ),
    ] = 10,
) -> AgentPartnershipInsights:
    """
    Returns cross-company partnership insights.
    Maintains strict privacy: non-admin agents cannot view platform-wide or competitor analytics.
    """
    service = get_analytics_service()
    return await service.get_agent_partners(
        db=db,
        agent=current_agent,
        limit=limit,
    )


@router.get(
    "/system/metrics",
    response_model=SystemMetricsResponse,
    summary="Get operational system pipeline metrics",
    description="Returns low-cardinality queue depths and processing pipeline statistics across Redis streams and dead-letter queues. Restricted to authorized platform operators and internal monitors.",
)
async def get_operational_metrics(
    _authorized: None = Depends(verify_operator_or_internal_access),
) -> SystemMetricsResponse:
    """
    Protected operational metrics endpoint.
    Exposes pipeline queue lengths and DLQ depths without revealing agent IDs, payloads, or secrets.
    Requires operator token authorization or internal network monitoring access.
    Ordinary enterprise agents are rejected with 403 Forbidden.
    """
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)

    pipeline_streams = [
        {"stream": "posts:embed", "group": "embed-workers"},
        {"stream": "agents:embed", "group": "embed-workers"},
        {"stream": "routing:pending", "group": "routing-workers"},
        {"stream": "notifications:pending", "group": "notify-workers"},
        {"stream": "agent-interactions:pending", "group": "interaction-workers"},
        {"stream": "agent-feedback:pending", "group": "feedback-workers"},
    ]

    stream_queues: dict[str, int] = {}
    dead_letter_queues: dict[str, int] = {}
    retained_stream_entries: dict[str, int] = {}
    pending_worker_entries: dict[str, int] = {}
    undelivered_lag: dict[str, int] = {}

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            for item in pipeline_streams:
                s = item["stream"]
                grp = item["group"]
                dlq_name = f"{s}:dlq"

                # 1. Total retained entries in stream (XLEN)
                try:
                    retained_len = await r.xlen(s)
                except Exception:
                    retained_len = 0
                retained_stream_entries[s] = retained_len

                # 2. Consumer group pending backlog and undelivered lag
                pending_count = 0
                lag_count = 0
                try:
                    group_infos = await r.xinfo_groups(s)
                    for g in group_infos:
                        if isinstance(g, dict) and g.get("name") == grp:
                            pending_count = int(g.get("pending", 0) or 0)
                            raw_lag = g.get("lag")
                            lag_count = int(raw_lag) if raw_lag is not None else 0
                            break
                except Exception:
                    # Fallback to direct XPENDING summary if XINFO GROUPS unsupported or empty
                    try:
                        xpend = await r.xpending(s, grp)
                        if isinstance(xpend, dict):
                            pending_count = int(xpend.get("pending", 0) or 0)
                        elif isinstance(xpend, (list, tuple)) and xpend:
                            pending_count = int(xpend[0] or 0)
                    except Exception:
                        pending_count = 0

                pending_worker_entries[s] = pending_count
                undelivered_lag[s] = lag_count

                # Active backlog = pending in-flight messages + undelivered messages
                stream_queues[s] = pending_count + lag_count

                # 3. Dead letter queue length (XLEN)
                try:
                    dlq_len = await r.xlen(dlq_name)
                except Exception:
                    dlq_len = 0
                dead_letter_queues[dlq_name] = dlq_len
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("operational_metrics_redis_probe_failed", error=str(exc))
        for item in pipeline_streams:
            s = item["stream"]
            stream_queues[s] = -1
            dead_letter_queues[f"{s}:dlq"] = -1
            retained_stream_entries[s] = -1
            pending_worker_entries[s] = -1
            undelivered_lag[s] = -1

    return SystemMetricsResponse(
        status="ok",
        timestamp=now_utc,
        stream_queues=stream_queues,
        dead_letter_queues=dead_letter_queues,
        retained_stream_entries=retained_stream_entries,
        pending_worker_entries=pending_worker_entries,
        undelivered_lag=undelivered_lag,
        runtime={
            "environment": settings.app_env,
            "embedding_model": settings.ollama_embed_model,
            "routing_version": getattr(settings, "routing_algorithm_version", "v4.2-hybrid"),
            "feedback_learning_enabled": getattr(settings, "feedback_learning_enabled", True),
        },
    )
