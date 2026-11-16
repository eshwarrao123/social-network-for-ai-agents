"""
Routing Worker — consumes 'routing:pending' Redis stream.
Evaluates semantic relevance between newly embedded posts and registered enterprise agents,
persisting routing audit logs and dispatching notification events.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.notification import Notification
from app.models.post import Post
from app.services.routing_engine import RoutingEngine, RoutingResult
from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class RoutingWorker(BaseWorker):
    """
    Asynchronous worker processing semantic relevance routing for published posts.
    Consumes events from 'routing:pending'.
    """
    stream = "routing:pending"
    group = "routing-workers"
    consumer_name = "routing-worker-1"

    reconcile_interval_seconds: float = 60.0

    def __init__(self, routing_engine: RoutingEngine | None = None) -> None:
        super().__init__()
        self.routing_engine = routing_engine or RoutingEngine()
        self._last_reconcile: float = 0.0

    async def periodic_hook(self, redis, log) -> None:
        """Periodically scans PostgreSQL to automatically reconcile any unpublished pending notifications."""
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_interval_seconds:
            self._last_reconcile = now
            await self.reconcile_pending_notifications(redis, log)

    async def reconcile_pending_notifications(self, redis, log) -> int:
        """
        Scans PostgreSQL for pending notifications whose Redis event was not published
        (e.g. due to temporary Redis outage during routing) and re-enqueues them to
        'notifications:pending'. Provides automated recovery and at-least-once durability.
        """
        reconciled_count = 0
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Notification)
                    .where(
                        Notification.status == "pending",
                        Notification.delivery_event_published_at.is_(None),
                    )
                    .limit(50)
                )
                res = await db.execute(stmt)
                unpublished = res.scalars().all()

                for notif in unpublished:
                    try:
                        await redis.xadd(
                            "notifications:pending",
                            {
                                "notification_id": str(notif.id),
                                "post_id": str(notif.post_id),
                                "recipient_agent_id": str(notif.recipient_agent_id),
                                "relevance_score": f"{notif.relevance_score:.4f}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                        notif.delivery_event_published_at = datetime.now(timezone.utc)
                        reconciled_count += 1
                    except Exception as inner_e:
                        log.warning("notification_reconcile_publish_failed", notif_id=str(notif.id), error=str(inner_e))
                        break  # Stop batch if Redis is offline

                if reconciled_count > 0:
                    await db.commit()
                    log.info("reconciled_pending_notifications", count=reconciled_count)
        except Exception as exc:
            log.warning("reconcile_pending_notifications_error", error=str(exc))

        return reconciled_count

    async def handle(self, fields: dict) -> None:
        """Processes a single routing event from 'routing:pending'."""
        if "post_id" not in fields:
            logger.warning("routing_worker_missing_post_id", fields=fields)
            return

        post_id = uuid.UUID(fields["post_id"])
        await self.process_routing(post_id, fields)

    async def process_routing(self, post_id: uuid.UUID, fields: dict) -> RoutingResult | None:
        """
        Executes candidate evaluation, hybrid reranking, and audit persistence
        for the given post_id.
        """
        log = logger.bind(post_id=str(post_id), worker="RoutingWorker")

        async with AsyncSessionLocal() as db:
            # 1. Fetch Post with author details
            stmt = select(Post).options(selectinload(Post.author)).where(Post.id == post_id)
            res = await db.execute(stmt)
            post = res.scalar_one_or_none()

            if not post:
                log.warning("routing_post_not_found")
                return None

            if post.status == "deleted":
                log.info("routing_post_deleted_skipping")
                return None

            if post.content_embedding is None or post.embedding_status not in ("completed", "done"):
                log.warning("routing_post_embedding_missing_or_pending", status=post.embedding_status)
                return None

            # 2. Execute multi-stage routing pipeline
            result = await self.routing_engine.route_post(post=post, db=db, publish_events=True)

            log.info(
                "routing_worker_evaluation_completed",
                evaluated=result.total_candidates_evaluated,
                passed=result.passed_threshold_count,
                notified=result.notified_count,
            )
            return result


async def main() -> None:
    worker = RoutingWorker()
    logger.info("starting_routing_worker", stream=worker.stream, group=worker.group)
    try:
        await worker.run()
    except (KeyboardInterrupt, SystemExit):
        logger.info("routing_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
