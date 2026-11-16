"""
Base worker — shared Redis Streams consumer pattern.
Subclass this for embed_worker, notify_worker, llm_worker.
"""
from __future__ import annotations

import abc
import asyncio
import structlog

logger = structlog.get_logger(__name__)


class BaseWorker(abc.ABC):
    """
    Redis Streams consumer base class.
    
    Provides:
    - Consumer group creation
    - At-least-once message delivery via XREADGROUP + XACK
    - Exponential backoff retry on failure
    - Dead-letter stream after max_retries exceeded
    """

    stream: str
    group: str
    consumer_name: str
    batch_size: int = 10
    block_ms: int = 5000  # Long-poll timeout

    def __init__(self):
        from app.config import get_settings
        self.settings = get_settings()

    async def _get_redis(self):
        import redis.asyncio as aioredis
        return aioredis.from_url(self.settings.redis_url, decode_responses=True)

    async def setup(self, redis) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            await redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" in str(e):
                pass  # Group already exists — OK
            else:
                raise

    async def run(self) -> None:
        """Main worker loop. Runs indefinitely."""
        redis = await self._get_redis()
        await self.setup(redis)
        log = logger.bind(worker=self.__class__.__name__, stream=self.stream)
        log.info("worker_started")

        while True:
            try:
                messages = await redis.xreadgroup(
                    self.group,
                    self.consumer_name,
                    {self.stream: ">"},
                    count=self.batch_size,
                    block=self.block_ms,
                )
                if not messages:
                    continue

                for stream_name, msg_list in messages:
                    for msg_id, fields in msg_list:
                        await self._process_with_retry(redis, msg_id, fields, log)

            except asyncio.CancelledError:
                log.info("worker_cancelled")
                break
            except Exception as exc:
                log.error("worker_loop_error", error=str(exc))
                await asyncio.sleep(5)

    async def _process_with_retry(self, redis, msg_id: str, fields: dict, log) -> None:
        retry_count = int(fields.get("_retry_count", 0))
        try:
            await self.handle(fields)
            await redis.xack(self.stream, self.group, msg_id)
            log.debug("message_processed", msg_id=msg_id)
        except Exception as exc:
            log.warning("message_failed", msg_id=msg_id, error=str(exc), retry=retry_count)
            if retry_count >= self.settings.worker_retry_max:
                # Send to dead-letter stream
                await redis.xadd(
                    f"{self.stream}:dlq",
                    {"original_id": msg_id, "error": str(exc), **fields},
                )
                await redis.xack(self.stream, self.group, msg_id)
                log.error("message_dead_lettered", msg_id=msg_id)
            else:
                # Exponential backoff: re-add with incremented retry count
                backoff = self.settings.worker_retry_backoff_seconds * (2 ** retry_count)
                await asyncio.sleep(backoff)
                await redis.xadd(
                    self.stream,
                    {"_retry_count": str(retry_count + 1), **fields},
                )
                await redis.xack(self.stream, self.group, msg_id)

    @abc.abstractmethod
    async def handle(self, fields: dict) -> None:
        """Process a single message. Raise on failure (triggers retry)."""
        ...
