"""
Notify Worker — consumes 'notifications:pending' stream.
Marks notification as delivered + fires webhooks.
Full HTTP delivery implemented in Phase 7.
"""
from __future__ import annotations

import uuid
import asyncio
import structlog
from datetime import datetime, timezone

from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class NotifyWorker(BaseWorker):
    stream = "notifications:pending"
    group = "notify-workers"
    consumer_name = "notify-worker-1"

    async def handle(self, fields: dict) -> None:
        notification_id = uuid.UUID(fields["notification_id"])
        log = logger.bind(notification_id=str(notification_id))

        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from sqlalchemy import select, update

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notification = result.scalar_one_or_none()

            if not notification:
                log.warning("notification_not_found")
                return

            if notification.status in ("delivered", "read"):
                log.info("notification_already_delivered")
                return

            await db.execute(
                update(Notification)
                .where(Notification.id == notification_id)
                .values(
                    status="delivered",
                    delivered_at=datetime.now(timezone.utc),
                    delivery_attempts=Notification.delivery_attempts + 1,
                )
            )
            await db.commit()
            log.info("notification_delivered")

        # Webhook dispatch will be added in Phase 7:
        # For each active subscription for this agent and event type:
        #   1. Retrieve encrypted_secret from WebhookSubscription
        #   2. In-memory decryption via WebhookSecurityService.decrypt_secret(sub.encrypted_secret)
        #   3. Calculate X-Asama-Signature = WebhookSecurityService.sign_payload(body, secret)
        #   4. Post payload to sub.endpoint_url with timeout and retry handling


async def main():
    worker = NotifyWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
