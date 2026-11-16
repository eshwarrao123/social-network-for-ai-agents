"""
Feedback Worker — consumes 'agent-feedback:pending' Redis stream.
Processes autonomous agent interaction feedback to incrementally adapt preference vectors
under strict drift boundaries without fine-tuning underlying models.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.interaction import AgentInteraction
from app.services.preference_service import PreferenceService, get_preference_service
from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class FeedbackWorker(BaseWorker):
    """
    Asynchronous worker processing feedback events from 'agent-feedback:pending'.
    Maintains adaptive agent preferences, enforces drift constraints, and updates topic statistics.
    """
    stream = "agent-feedback:pending"
    group = "feedback-workers"
    consumer_name = "feedback-worker-1"

    reconcile_interval_seconds: float = 60.0

    def __init__(self, preference_service: PreferenceService | None = None) -> None:
        super().__init__()
        self.preference_service = preference_service or get_preference_service()
        self._last_reconcile: float = 0.0

    async def periodic_hook(self, redis, log) -> None:
        """Periodically scans PostgreSQL to automatically reconcile any unpublished pending feedback."""
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_interval_seconds:
            self._last_reconcile = now
            await self.reconcile_unprocessed_interactions(redis, log)

    async def reconcile_unprocessed_interactions(self, redis, log) -> int:
        """
        Scans PostgreSQL for completed agent interactions whose feedback event was not published
        (e.g., due to temporary Redis outage during LLM completion) and re-enqueues them to
        'agent-feedback:pending'. Guarantees at-least-once learning durability.
        """
        reconciled_count = 0
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(AgentInteraction)
                    .where(
                        AgentInteraction.status.in_(["engaged", "ignored"]),
                        AgentInteraction.feedback_event_published_at.is_(None),
                    )
                    .limit(50)
                )
                res = await db.execute(stmt)
                unprocessed = res.scalars().all()

                for inter in unprocessed:
                    try:
                        signal = "positive" if inter.status == "engaged" else "negative"
                        conf = inter.confidence if inter.confidence is not None else 0.5
                        payload = {
                            "interaction_id": str(inter.id),
                            "recipient_agent_id": str(inter.receiving_agent_id),
                            "post_id": str(inter.post_id),
                            "signal": signal,
                            "confidence": f"{conf:.4f}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        await redis.xadd(self.stream, payload)

                        # Update publication timestamp in DB
                        await db.execute(
                            update(AgentInteraction)
                            .where(AgentInteraction.id == inter.id)
                            .values(feedback_event_published_at=datetime.now(timezone.utc))
                        )
                        await db.commit()
                        reconciled_count += 1
                        log.info(
                            "reconciled_unprocessed_feedback_event",
                            interaction_id=str(inter.id),
                            signal=signal,
                        )
                    except Exception as inner_exc:
                        log.warning(
                            "reconcile_feedback_interaction_failed",
                            interaction_id=str(inter.id),
                            error=str(inner_exc),
                        )
        except Exception as exc:
            log.warning("reconcile_unprocessed_interactions_error", error=str(exc))

        return reconciled_count

    async def handle(self, fields: dict) -> None:
        """Processes a single feedback message from 'agent-feedback:pending'."""
        if "interaction_id" not in fields:
            logger.warning("feedback_worker_missing_interaction_id", fields=fields)
            return

        try:
            interaction_id = uuid.UUID(fields["interaction_id"])
        except (ValueError, TypeError) as val_err:
            logger.error("feedback_worker_invalid_uuid", error=str(val_err), fields=fields)
            raise

        async with AsyncSessionLocal() as db:
            await self.preference_service.process_feedback_event(db, interaction_id)


async def main() -> None:
    worker = FeedbackWorker()
    logger.info("starting_feedback_worker", stream=worker.stream, group=worker.group)
    try:
        await worker.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("feedback_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
