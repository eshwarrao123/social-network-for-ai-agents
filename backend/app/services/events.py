"""
Event publishing service for Redis Streams.
Establishes the integration boundary between API write requests and background workers.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


async def publish_post_embed_event(post_id: uuid.UUID, author_agent_id: uuid.UUID | None = None) -> bool:
    """
    Dispatches a post-embedding event to the 'posts:embed' Redis stream.
    Returns True if successfully queued to Redis, False if Redis was unavailable.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.xadd(
                "posts:embed",
                {
                    "post_id": str(post_id),
                    "author_agent_id": str(author_agent_id or ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                "post_embed_event_published",
                post_id=str(post_id),
                author_agent_id=str(author_agent_id or ""),
                stream="posts:embed",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "post_embed_event_publish_failed_redis_offline",
            post_id=str(post_id),
            error=str(exc),
        )
        return False


async def publish_post_created_event(post_id: uuid.UUID, author_agent_id: uuid.UUID) -> None:
    """Backward-compatible wrapper for post publication events."""
    await publish_post_embed_event(post_id=post_id, author_agent_id=author_agent_id)


async def publish_agent_embed_event(agent_id: uuid.UUID) -> bool:
    """
    Dispatches an agent-embedding event to the 'agents:embed' Redis stream.
    Returns True if successfully queued to Redis, False if Redis was unavailable.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.xadd(
                "agents:embed",
                {
                    "agent_id": str(agent_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                "agent_embed_event_published",
                agent_id=str(agent_id),
                stream="agents:embed",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "agent_embed_event_publish_failed_redis_offline",
            agent_id=str(agent_id),
            error=str(exc),
        )
        return False


async def publish_routing_pending_event(post_id: uuid.UUID) -> bool:
    """
    Dispatches a routing event to the 'routing:pending' Redis stream
    after a post embedding has been persisted.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.xadd(
                "routing:pending",
                {
                    "post_id": str(post_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                "routing_pending_event_published",
                post_id=str(post_id),
                stream="routing:pending",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "routing_pending_event_publish_failed_redis_offline",
            post_id=str(post_id),
            error=str(exc),
        )
        return False


async def publish_notification_pending_event(
    post_id: uuid.UUID,
    recipient_agent_id: uuid.UUID,
    relevance_score: float,
    notification_id: uuid.UUID | None = None,
) -> bool:
    """
    Dispatches a notification event to the 'notifications:pending' Redis stream
    for an agent selected by the routing engine.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            payload = {
                "post_id": str(post_id),
                "recipient_agent_id": str(recipient_agent_id),
                "relevance_score": f"{relevance_score:.4f}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if notification_id:
                payload["notification_id"] = str(notification_id)

            await client.xadd(
                "notifications:pending",
                payload,
            )
            logger.info(
                "notification_pending_event_published",
                post_id=str(post_id),
                recipient_agent_id=str(recipient_agent_id),
                notification_id=str(notification_id or ""),
                relevance_score=relevance_score,
                stream="notifications:pending",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "notification_pending_event_publish_failed_redis_offline",
            post_id=str(post_id),
            recipient_agent_id=str(recipient_agent_id),
            error=str(exc),
        )
        return False


async def publish_agent_interaction_event(
    notification_id: uuid.UUID,
    post_id: uuid.UUID,
    recipient_agent_id: uuid.UUID,
    relevance_score: float,
) -> bool:
    """
    Dispatches an autonomous interaction event to the 'agent-interactions:pending' Redis stream.
    Returns True if successfully queued to Redis, False if Redis was unavailable.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            payload = {
                "notification_id": str(notification_id),
                "post_id": str(post_id),
                "recipient_agent_id": str(recipient_agent_id),
                "relevance_score": f"{relevance_score:.4f}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await client.xadd(
                "agent-interactions:pending",
                payload,
            )
            logger.info(
                "agent_interaction_pending_event_published",
                notification_id=str(notification_id),
                post_id=str(post_id),
                recipient_agent_id=str(recipient_agent_id),
                relevance_score=relevance_score,
                stream="agent-interactions:pending",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "agent_interaction_pending_event_publish_failed_redis_offline",
            notification_id=str(notification_id),
            post_id=str(post_id),
            recipient_agent_id=str(recipient_agent_id),
            error=str(exc),
        )
        return False


async def publish_feedback_event(
    interaction_id: uuid.UUID,
    recipient_agent_id: uuid.UUID,
    post_id: uuid.UUID,
    signal: str,
    confidence: float,
) -> bool:
    """
    Dispatches a feedback learning event to the 'agent-feedback:pending' Redis stream.
    Returns True if successfully queued to Redis, False if Redis was unavailable.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            payload = {
                "interaction_id": str(interaction_id),
                "recipient_agent_id": str(recipient_agent_id),
                "post_id": str(post_id),
                "signal": signal,
                "confidence": f"{confidence:.4f}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await client.xadd(
                "agent-feedback:pending",
                payload,
            )
            logger.info(
                "feedback_event_published",
                interaction_id=str(interaction_id),
                recipient_agent_id=str(recipient_agent_id),
                signal=signal,
                confidence=confidence,
                stream="agent-feedback:pending",
            )
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "feedback_event_publish_failed_redis_offline",
            interaction_id=str(interaction_id),
            error=str(exc),
        )
        return False
