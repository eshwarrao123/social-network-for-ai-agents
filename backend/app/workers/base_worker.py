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
    - Consumer group creation (supports single stream or multiple streams)
    - At-least-once message delivery via XREADGROUP + XACK
    - Exponential backoff retry on failure
    - Dead-letter stream after max_retries exceeded
    - Graceful cancellation & shutdown
    """

    stream: str = ""
    streams: list[str] = []
    group: str
    consumer_name: str
    batch_size: int = 10
    block_ms: int = 5000  # Long-poll timeout
    claim_min_idle_ms: int = 120000  # Default 120s idle threshold before reclaiming abandoned messages
    claim_batch_size: int = 10

    def __init__(self):
        from app.config import get_settings
        self.settings = get_settings()
        self.claim_min_idle_ms = getattr(self.settings, "redis_claim_min_idle_ms", 120000)
        self._running = True

    def _get_streams(self) -> list[str]:
        if self.streams:
            return list(self.streams)
        if self.stream:
            return [self.stream]
        raise ValueError(f"Worker {self.__class__.__name__} must specify 'stream' or 'streams'.")

    async def _get_redis(self):
        import redis.asyncio as aioredis
        return aioredis.from_url(self.settings.redis_url, decode_responses=True)

    async def setup(self, redis) -> None:
        """Create consumer group for each configured stream if it doesn't exist."""
        for s in self._get_streams():
            try:
                await redis.xgroup_create(s, self.group, id="0", mkstream=True)
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    pass  # Group already exists — OK
                else:
                    raise

    def stop(self) -> None:
        """Signals the worker loop to terminate."""
        self._running = False

    async def claim_pending_all_streams(self, redis, log) -> int:
        """Reclaims abandoned pending messages across all configured streams."""
        claimed_total = 0
        for s in self._get_streams():
            claimed_total += await self._claim_and_process_pending(redis, s, log)
        return claimed_total

    async def _claim_and_process_pending(self, redis, stream_name: str, log) -> int:
        """
        Reclaims and processes messages abandoned in the consumer group PEL.
        Idle threshold prevents stealing from healthy active workers.
        Returns the number of messages reclaimed and handled.
        """
        claimed_count = 0
        try:
            # 1. Attempt modern XAUTOCLAIM (Redis 6.2+)
            res = await redis.xautoclaim(
                name=stream_name,
                groupname=self.group,
                consumername=self.consumer_name,
                min_idle_time=self.claim_min_idle_ms,
                start_id="0-0",
                count=self.claim_batch_size,
            )
            if res and len(res) >= 2:
                messages = res[1]
                for item in messages:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        msg_id, fields = item
                        if fields:
                            log.info("claimed_pending_message_xautoclaim", stream=stream_name, msg_id=msg_id)
                            await self._process_with_retry(redis, stream_name, msg_id, fields, log)
                            claimed_count += 1
        except Exception as exc:
            # 2. Fallback to XPENDING + XCLAIM for older engines / environments
            try:
                pending_entries = await redis.xpending_range(
                    name=stream_name,
                    groupname=self.group,
                    min="-",
                    max="+",
                    count=self.claim_batch_size,
                )
                if pending_entries:
                    candidate_ids = [
                        p["message_id"]
                        for p in pending_entries
                        if p.get("idle", 0) >= self.claim_min_idle_ms
                    ]
                    if candidate_ids:
                        claimed = await redis.xclaim(
                            name=stream_name,
                            groupname=self.group,
                            consumername=self.consumer_name,
                            min_idle_time=self.claim_min_idle_ms,
                            message_ids=candidate_ids,
                        )
                        for item in claimed:
                            if isinstance(item, (list, tuple)) and len(item) == 2:
                                msg_id, fields = item
                                if fields:
                                    log.info("claimed_pending_message_xclaim", stream=stream_name, msg_id=msg_id)
                                    await self._process_with_retry(redis, stream_name, msg_id, fields, log)
                                    claimed_count += 1
            except Exception as inner_exc:
                log.debug("pending_claim_attempt_skipped", stream=stream_name, error=str(inner_exc))

        return claimed_count

    async def periodic_hook(self, redis, log) -> None:
        """Optional hook called during idle polling or periodic intervals by subclasses."""
        pass

    async def run(self) -> None:
        """Main worker loop. Runs until cancelled or stopped."""
        redis = await self._get_redis()
        try:
            await self.setup(redis)
            log = logger.bind(worker=self.__class__.__name__, streams=self._get_streams())
            log.info("worker_started")

            # Initial sweep for any pending messages abandoned by crashed workers
            await self.claim_pending_all_streams(redis, log)
            await self.periodic_hook(redis, log)

            stream_dict = {s: ">" for s in self._get_streams()}

            while self._running:
                try:
                    messages = await redis.xreadgroup(
                        self.group,
                        self.consumer_name,
                        stream_dict,
                        count=self.batch_size,
                        block=self.block_ms,
                    )
                    if not messages:
                        # Sweep abandoned messages and run periodic tasks during idle polling
                        await self.claim_pending_all_streams(redis, log)
                        await self.periodic_hook(redis, log)
                        continue

                    for stream_name, msg_list in messages:
                        for msg_id, fields in msg_list:
                            await self._process_with_retry(redis, stream_name, msg_id, fields, log)

                except asyncio.CancelledError:
                    log.info("worker_cancelled")
                    break
                except Exception as exc:
                    log.error("worker_loop_error", error=str(exc))
                    await asyncio.sleep(5)
        finally:
            await redis.aclose()

    async def _process_with_retry(self, redis, stream_name: str, msg_id: str, fields: dict, log) -> None:
        retry_count = int(fields.get("_retry_count", 0))
        try:
            await self.handle(fields)
            await redis.xack(stream_name, self.group, msg_id)
            log.debug("message_processed", stream=stream_name, msg_id=msg_id)
        except Exception as exc:
            log.warning("message_failed", stream=stream_name, msg_id=msg_id, error=str(exc), retry=retry_count)
            if retry_count >= self.settings.worker_retry_max:
                # Send to dead-letter stream
                dlq_stream = f"{stream_name}:dlq"
                await redis.xadd(
                    dlq_stream,
                    {**fields, "original_id": msg_id, "error": str(exc)},
                )
                await redis.xack(stream_name, self.group, msg_id)
                log.error("message_dead_lettered", stream=stream_name, msg_id=msg_id, dlq=dlq_stream)
            else:
                # Exponential backoff: re-add with incremented retry count
                backoff = self.settings.worker_retry_backoff_seconds * (2 ** retry_count)
                await asyncio.sleep(backoff)
                await redis.xadd(
                    stream_name,
                    {**fields, "_retry_count": str(retry_count + 1)},
                )
                await redis.xack(stream_name, self.group, msg_id)

    @abc.abstractmethod
    async def handle(self, fields: dict) -> None:
        """Process a single message. Raise on failure (triggers retry)."""
        ...
