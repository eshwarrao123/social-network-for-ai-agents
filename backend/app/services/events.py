"""
Event publishing service for Redis Streams.
Establishes the integration boundary between API write requests and background workers.
"""
from __future__ import annotations

import uuid
import structlog

logger = structlog.get_logger(__name__)


async def publish_post_created_event(post_id: uuid.UUID, author_agent_id: uuid.UUID) -> None:
    """
    Dispatches a post-created event to the 'posts:embed' Redis stream.
    Gracefully handles Redis connectivity errors so that database persistence
    remains completely decoupled from asynchronous worker delivery.
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
                    "author_agent_id": str(author_agent_id),
                },
            )
            logger.info(
                "post_created_event_published",
                post_id=str(post_id),
                author_agent_id=str(author_agent_id),
                stream="posts:embed",
            )
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(
            "post_created_event_publish_failed",
            post_id=str(post_id),
            error=str(exc),
        )
