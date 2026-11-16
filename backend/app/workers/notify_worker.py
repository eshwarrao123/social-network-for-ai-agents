"""
Notify Worker — consumes 'notifications:pending' Redis stream.
Reliably delivers notifications to enterprise agents via secure outbound HTTP webhooks
or in-app delivery fallback, with HMAC signing (timestamp-bound), SSRF socket pinning,
per-subscription tracking, atomic lease concurrency control, and DLQ resilience.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import or_, and_, select, update
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.post import Post
from app.models.webhook import WebhookSubscription
from app.services.ssrf_protection import (
    SSRFBlockedError,
    SSRFError,
    create_ssrf_safe_client,
    validate_destination_url,
)
from app.services.webhook_security import (
    WebhookSecurityError,
    get_webhook_security,
)
from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class WebhookDeliveryError(Exception):
    """Base exception for webhook delivery failures."""


class DeliveryPermanentError(WebhookDeliveryError):
    """Permanent delivery failure (e.g. 4xx non-retryable, SSRF violation, invalid endpoint)."""


class DeliveryTransientError(WebhookDeliveryError):
    """Transient delivery failure (e.g. timeout, network reset, 5xx, 429)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def build_notification_payload(
    notification: Notification,
    post: Post,
    recipient: Agent,
    event_id: uuid.UUID,
    timestamp_iso: str,
) -> bytes:
    """
    Constructs a versioned (v1.0), canonical deterministic JSON payload.
    Uses sorted keys and compact separators to ensure reproducible HMAC signing.
    """
    author = post.author if post else None
    author_id_str = str(author.id) if author else (str(post.author_agent_id) if post else None)
    author_name = author.name if author else None
    author_company = author.company if author else None

    recipient_id_str = str(recipient.id) if recipient else str(notification.recipient_agent_id)
    recipient_name = recipient.name if recipient else None
    recipient_company = recipient.company if recipient else None

    published_dt = post.published_at if (post and post.published_at) else (post.created_at if post else None)
    published_iso = published_dt.isoformat() if published_dt else None
    expires_iso = post.expires_at.isoformat() if (post and post.expires_at) else None
    notif_created_iso = (
        notification.created_at.isoformat()
        if notification.created_at
        else timestamp_iso
    )

    payload_dict: dict[str, Any] = {
        "event_id": str(event_id),
        "event_type": "notification.created",
        "event_timestamp": timestamp_iso,
        "notification": {
            "id": str(notification.id),
            "relevance_score": float(notification.relevance_score),
            "routing_explanation": {
                k: v for k, v in (notification.routing_explanation or {}).items()
                if k != "webhook_deliveries"  # Exclude internal delivery state from outbound payload
            },
            "created_at": notif_created_iso,
        },
        "post": {
            "id": str(post.id) if post else str(notification.post_id),
            "title": post.title if post else "",
            "content": post.content if post else "",
            "published_at": published_iso,
            "expires_at": expires_iso,
        },
        "sender": {
            "id": author_id_str,
            "name": author_name,
            "company": author_company,
        },
        "recipient": {
            "id": recipient_id_str,
            "name": recipient_name,
            "company": recipient_company,
        },
    }

    return json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")


class NotifyWorker(BaseWorker):
    """
    Asynchronous worker processing notification delivery events.
    Consumes events from 'notifications:pending'.
    """

    stream = "notifications:pending"
    group = "notify-workers"
    consumer_name = "notify-worker-1"

    reconcile_interval_seconds: float = 60.0
    lease_duration_seconds: float = 60.0

    def __init__(self):
        super().__init__()
        self._last_reconcile: float = 0.0
        self._redis_client = None

    async def periodic_hook(self, redis, log) -> None:
        """Periodically scans PostgreSQL to reconcile pending/retrying notifications."""
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_interval_seconds:
            self._last_reconcile = now
            await self.reconcile_pending_notifications(redis, log)

    async def reconcile_pending_notifications(self, redis, log) -> int:
        """
        Scans PostgreSQL for stuck notifications:
          1. New 'pending' notifications whose delivery event was never published to Redis.
          2. 'retrying' notifications whose retry was not enqueued or was lost during Redis downtime.
          3. 'delivering' notifications whose lease has expired (>120s) due to worker crash.
        """
        reconciled_count = 0
        now_utc = datetime.now(timezone.utc)
        retry_threshold = now_utc - timedelta(seconds=60)
        crashed_lease_threshold = now_utc - timedelta(seconds=120)

        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Notification)
                    .where(
                        or_(
                            # 1. Unpublished pending records
                            and_(
                                Notification.status == "pending",
                                Notification.delivery_event_published_at.is_(None),
                            ),
                            # 2. Stuck retries (e.g. Redis was down when retry was attempted)
                            and_(
                                Notification.status == "retrying",
                                Notification.delivery_attempts < self.settings.webhook_max_delivery_attempts,
                                Notification.updated_at < retry_threshold,
                            ),
                            # 3. Abandoned deliveries from crashed workers
                            and_(
                                Notification.status == "delivering",
                                Notification.updated_at < crashed_lease_threshold,
                            ),
                        )
                    )
                    .limit(50)
                )
                res = await db.execute(stmt)
                stuck = res.scalars().all()

                for notif in stuck:
                    try:
                        await redis.xadd(
                            self.stream,
                            {
                                "notification_id": str(notif.id),
                                "post_id": str(notif.post_id),
                                "recipient_agent_id": str(notif.recipient_agent_id),
                                "relevance_score": f"{notif.relevance_score:.4f}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "_reconciled": "true",
                            },
                        )
                        notif.delivery_event_published_at = datetime.now(timezone.utc)
                        reconciled_count += 1
                    except Exception as err:
                        log.warning("notification_reconcile_publish_failed", notif_id=str(notif.id), error=str(err))
                        break

                if reconciled_count > 0:
                    await db.commit()
                    log.info("reconciled_pending_notifications", count=reconciled_count)
        except Exception as exc:
            log.warning("reconcile_pending_notifications_error", error=str(exc))

        return reconciled_count

    async def handle(self, fields: dict) -> None:
        """
        Process a single notification event with atomic concurrency control,
        per-subscription tracking, and crash-resilient leases.
        """
        notification_id_str = fields.get("notification_id")
        if not notification_id_str:
            post_id_str = fields.get("post_id")
            recipient_id_str = fields.get("recipient_agent_id")
            if not post_id_str or not recipient_id_str:
                logger.warning("notify_worker_missing_identifying_fields", fields=fields)
                return
            post_uuid = uuid.UUID(post_id_str)
            recipient_uuid = uuid.UUID(recipient_id_str)
        else:
            post_uuid = None
            recipient_uuid = None

        log = logger.bind(
            notification_id=notification_id_str or "",
            post_id=fields.get("post_id", ""),
            recipient_id=fields.get("recipient_agent_id", ""),
            worker="NotifyWorker",
        )

        async with AsyncSessionLocal() as db:
            # 1. Fetch Notification with row-level lock (FOR UPDATE concurrency control)
            if notification_id_str:
                notif_uuid = uuid.UUID(notification_id_str)
                stmt = (
                    select(Notification)
                    .options(
                        selectinload(Notification.recipient),
                        selectinload(Notification.post).selectinload(Post.author),
                    )
                    .where(Notification.id == notif_uuid)
                    .with_for_update()
                )
            else:
                stmt = (
                    select(Notification)
                    .options(
                        selectinload(Notification.recipient),
                        selectinload(Notification.post).selectinload(Post.author),
                    )
                    .where(
                        Notification.post_id == post_uuid,
                        Notification.recipient_agent_id == recipient_uuid,
                    )
                    .with_for_update()
                )

            res = await db.execute(stmt)
            notification = res.scalar_one_or_none()

            if not notification:
                log.warning("notification_record_not_found")
                return

            # 2. Concurrency Control: Check Prior Completion & Active Leases
            now_utc = datetime.now(timezone.utc)

            if notification.status in ("delivered", "read"):
                log.info(
                    "notification_already_completed_skipping",
                    current_status=notification.status,
                    delivered_at=str(notification.delivered_at),
                )
                return

            if notification.status == "delivering":
                # Check whether another concurrent worker is actively processing
                lease_age = (now_utc - (notification.updated_at or now_utc)).total_seconds()
                if lease_age < self.lease_duration_seconds:
                    log.info(
                        "notification_under_active_lease_skipping",
                        lease_age_seconds=round(lease_age, 1),
                    )
                    return
                # Lease expired (>60s): previous worker likely crashed; reclaim lease
                log.warning(
                    "reclaiming_abandoned_delivery_lease",
                    lease_age_seconds=round(lease_age, 1),
                )

            post = notification.post
            recipient = notification.recipient

            # 3. Post Validity: check deleted or expired
            if not post or post.status == "deleted":
                log.info("notification_post_deleted_cancelling_delivery")
                notification.status = "failed"
                notification.routing_explanation = {
                    **dict(notification.routing_explanation or {}),
                    "failure_reason": "post_deleted",
                }
                await db.commit()
                return

            if post.expires_at and post.expires_at <= now_utc:
                log.info("notification_post_expired_cancelling_delivery", expires_at=str(post.expires_at))
                notification.status = "failed"
                notification.routing_explanation = {
                    **dict(notification.routing_explanation or {}),
                    "failure_reason": "post_expired",
                }
                await db.commit()
                return

            # 4. Recipient Validity: check active
            if not recipient or not recipient.is_active:
                log.info("notification_recipient_inactive_cancelling_delivery")
                notification.status = "failed"
                notification.routing_explanation = {
                    **dict(notification.routing_explanation or {}),
                    "failure_reason": "recipient_inactive",
                }
                await db.commit()
                return

            # 5. Query Active Webhook Subscriptions for recipient
            sub_stmt = select(WebhookSubscription).where(
                WebhookSubscription.agent_id == notification.recipient_agent_id,
                WebhookSubscription.is_active.is_(True),
            )
            sub_res = await db.execute(sub_stmt)
            subscriptions = sub_res.scalars().all()

            matching_subs = [
                s for s in subscriptions
                if not s.event_types or any(
                    e in ("new_notification", "notification.created") for e in s.event_types
                )
            ]

            # 6. In-App Delivery Fallback (when no active webhooks exist)
            if not matching_subs:
                log.info("no_active_webhook_subscription_delivering_in_app")
                notification.status = "delivered"
                notification.delivered_at = now_utc
                notification.delivery_attempts = notification.delivery_attempts + 1
                await db.commit()
                log.info(
                    "notification_in_app_delivery_completed",
                    notification_id=str(notification.id),
                    recipient_id=str(notification.recipient_agent_id),
                )
                return

            # 7. Atomically Acquire Delivery Lease (durably committed before outbound HTTP network calls)
            notification.status = "delivering"
            notification.updated_at = now_utc
            notification.delivery_attempts = notification.delivery_attempts + 1
            await db.commit()
            await db.refresh(notification)

            event_id = uuid.uuid4()
            delivery_id = uuid.uuid4()
            timestamp_iso = now_utc.isoformat()

            # Canonical deterministic JSON payload
            payload_bytes = build_notification_payload(
                notification=notification,
                post=post,
                recipient=recipient,
                event_id=event_id,
                timestamp_iso=timestamp_iso,
            )

            webhook_sec = get_webhook_security()

            # 8. Multi-Endpoint Independent Delivery Execution
            explanation = dict(notification.routing_explanation or {})
            webhook_deliveries = dict(explanation.get("webhook_deliveries", {}))

            max_retry_after: float | None = None

            for sub in matching_subs:
                sub_id_str = str(sub.id)
                sub_state = dict(webhook_deliveries.get(sub_id_str, {
                    "endpoint_url": sub.endpoint_url,
                    "status": "pending",
                    "delivery_attempts": 0,
                    "delivered_at": None,
                    "last_error": None,
                }))

                # Idempotency per endpoint: do not re-dispatch to already delivered endpoint
                if sub_state.get("status") == "delivered":
                    log.info("subscription_endpoint_already_delivered", sub_id=sub_id_str)
                    continue

                sub_state["delivery_attempts"] = int(sub_state.get("delivery_attempts", 0)) + 1
                try:
                    await self._dispatch_to_subscription(
                        sub=sub,
                        notification=notification,
                        payload_bytes=payload_bytes,
                        event_id=event_id,
                        delivery_id=delivery_id,
                        timestamp_iso=timestamp_iso,
                        webhook_sec=webhook_sec,
                        log=log,
                    )
                    sub_state["status"] = "delivered"
                    sub_state["delivered_at"] = datetime.now(timezone.utc).isoformat()
                    sub_state["last_error"] = None
                    log.info("subscription_endpoint_delivered", sub_id=sub_id_str)

                except DeliveryPermanentError as perm_err:
                    sub_state["status"] = "failed"
                    sub_state["last_error"] = str(perm_err)
                    sub_state["permanent"] = True
                    log.error("subscription_endpoint_permanent_failure", sub_id=sub_id_str, error=str(perm_err))
                    await self._send_to_dlq(
                        fields,
                        error=str(perm_err),
                        failure_type="permanent",
                        subscription_id=sub_id_str,
                    )

                except DeliveryTransientError as trans_err:
                    if sub_state["delivery_attempts"] >= self.settings.webhook_max_delivery_attempts:
                        sub_state["status"] = "failed"
                        sub_state["last_error"] = str(trans_err)
                        sub_state["retries_exhausted"] = True
                        log.error("subscription_endpoint_retries_exhausted", sub_id=sub_id_str, error=str(trans_err))
                        await self._send_to_dlq(
                            fields,
                            error=str(trans_err),
                            failure_type="retries_exhausted",
                            subscription_id=sub_id_str,
                        )
                    else:
                        sub_state["status"] = "retrying"
                        sub_state["last_error"] = str(trans_err)
                        sub_state["retry_after"] = trans_err.retry_after
                        if trans_err.retry_after is not None:
                            max_retry_after = max(max_retry_after or 0.0, trans_err.retry_after)
                        log.warning("subscription_endpoint_transient_failure", sub_id=sub_id_str, error=str(trans_err))

                webhook_deliveries[sub_id_str] = sub_state

            # 9. Aggregate Status Across All Subscriptions
            statuses = [webhook_deliveries.get(str(s.id), {}).get("status", "pending") for s in matching_subs]
            all_delivered = all(st == "delivered" for st in statuses)
            any_retrying = any(st == "retrying" for st in statuses)
            all_failed = all(st == "failed" for st in statuses)

            explanation["webhook_deliveries"] = webhook_deliveries
            notification.routing_explanation = explanation

            if all_delivered:
                notification.status = "delivered"
                notification.delivered_at = datetime.now(timezone.utc)
                await db.commit()
                log.info("all_subscription_endpoints_delivered", notif_id=str(notification.id))

            elif any_retrying:
                notification.status = "retrying"
                await db.commit()

                # Schedule retry backoff with jitter and respect Retry-After
                base_backoff = self.settings.webhook_retry_backoff_seconds * (2 ** (notification.delivery_attempts - 1))
                jitter = random.uniform(0.1, 0.5)
                delay = base_backoff + jitter
                if max_retry_after is not None:
                    delay = max(delay, max_retry_after)

                log.info("scheduling_retry_for_pending_subscriptions", delay_seconds=round(delay, 2))
                await self._re_enqueue_with_delay(fields, delay=delay, retry_count=notification.delivery_attempts)

            elif all_failed:
                notification.status = "failed"
                await db.commit()
                log.error("all_subscription_endpoints_failed", notif_id=str(notification.id))

            else:
                # Partial success (at least one delivered, others failed permanently)
                notification.status = "delivered"
                notification.delivered_at = datetime.now(timezone.utc)
                await db.commit()
                log.info("partial_subscription_delivery_completed", notif_id=str(notification.id))

    async def _dispatch_to_subscription(
        self,
        sub: WebhookSubscription,
        notification: Notification,
        payload_bytes: bytes,
        event_id: uuid.UUID,
        delivery_id: uuid.UUID,
        timestamp_iso: str,
        webhook_sec: Any,
        log: Any,
    ) -> None:
        """Dispatches an HTTP POST payload to a single webhook subscription under SSRF protections."""
        # 1. Decrypt signing secret in-memory
        try:
            secret = webhook_sec.decrypt_secret(sub.encrypted_secret)
        except WebhookSecurityError as sec_err:
            raise DeliveryPermanentError(f"Webhook secret decryption failed: {sec_err}") from sec_err

        # 2. Compute HMAC-SHA256 signature cryptographically bound to timestamp
        signature = webhook_sec.sign_payload(payload_bytes, secret, timestamp=timestamp_iso)

        # 3. Validate destination URL against SSRF policy and resolve DNS
        try:
            hostname, port, resolved_ips = validate_destination_url(
                sub.endpoint_url,
                allow_http=self.settings.webhook_allow_http,
                allowed_ports=set(self.settings.webhook_allowed_ports),
            )
        except SSRFError as ssrf_err:
            raise DeliveryPermanentError(f"SSRF policy blocked destination URL: {ssrf_err}") from ssrf_err

        # 4. Pin socket to first validated IP address (defeats DNS rebinding / TOCTOU attacks)
        pinned_ip = resolved_ips[0]

        headers = {
            "X-Agent-Network-Event": "notification.created",
            "X-Agent-Network-Delivery": str(delivery_id),
            "X-Agent-Network-Timestamp": timestamp_iso,
            "X-Agent-Network-Signature": signature,
            "Idempotency-Key": str(notification.id),
            "Content-Type": "application/json",
            "User-Agent": "Agent-Network/1.0",
        }

        # 5. Dispatch HTTP request with pinned socket and strict timeouts
        client = create_ssrf_safe_client(
            pinned_ip=pinned_ip,
            connect_timeout=self.settings.webhook_connect_timeout,
            read_timeout=self.settings.webhook_read_timeout,
        )

        async with client:
            try:
                response = await client.post(
                    sub.endpoint_url,
                    content=payload_bytes,
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                raise DeliveryTransientError(f"Network transport error: {net_err}") from net_err
            except Exception as unk_err:
                raise DeliveryTransientError(f"Outbound dispatch error: {unk_err}") from unk_err

        # 6. Evaluate HTTP status code
        if 200 <= response.status_code < 300:
            log.info(
                "webhook_http_response_success",
                endpoint_url=sub.endpoint_url,
                status_code=response.status_code,
            )
            return

        # Check for transient retryable HTTP codes: 408, 425, 429, 5xx
        if response.status_code in (408, 425, 429) or response.status_code >= 500:
            retry_after_val: float | None = None
            retry_header = response.headers.get("Retry-After")
            if retry_header:
                try:
                    retry_after_val = float(retry_header)
                except ValueError:
                    pass
            raise DeliveryTransientError(
                f"HTTP {response.status_code} transient error from endpoint",
                retry_after=retry_after_val,
            )

        # Permanent HTTP failure (4xx except 408/425/429)
        raise DeliveryPermanentError(
            f"HTTP {response.status_code} permanent error from endpoint"
        )

    async def _send_to_dlq(
        self,
        fields: dict,
        error: str,
        failure_type: str,
        subscription_id: str | None = None,
    ) -> None:
        """Sends permanently failed or exhausted notification messages to the DLQ stream."""
        dlq_stream = f"{self.stream}:dlq"
        try:
            redis = self._redis_client or await self._get_redis()
            try:
                dlq_payload = {
                    **fields,
                    "error": error,
                    "failure_type": failure_type,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
                if subscription_id:
                    dlq_payload["subscription_id"] = subscription_id

                await redis.xadd(dlq_stream, dlq_payload)
                logger.info(
                    "notification_sent_to_dlq",
                    dlq_stream=dlq_stream,
                    failure_type=failure_type,
                    subscription_id=subscription_id or "",
                )
            finally:
                if self._redis_client is None:
                    await redis.aclose()
        except Exception as exc:
            logger.warning("failed_to_publish_notification_dlq", dlq_stream=dlq_stream, error=str(exc))

    async def _re_enqueue_with_delay(self, fields: dict, delay: float, retry_count: int) -> None:
        """Waits backoff delay and re-enqueues notification to Redis stream with incremented retry count."""
        try:
            redis = self._redis_client or await self._get_redis()
            try:
                if delay > 0:
                    await asyncio.sleep(min(delay, 5.0))
                await redis.xadd(
                    self.stream,
                    {
                        **fields,
                        "_retry_count": str(retry_count),
                    },
                )
                logger.info(
                    "notification_re_enqueued_for_retry",
                    stream=self.stream,
                    retry_count=retry_count,
                    delay_seconds=f"{delay:.2f}",
                )
            finally:
                if self._redis_client is None:
                    await redis.aclose()
        except Exception as exc:
            logger.warning("failed_to_re_enqueue_notification_retry", stream=self.stream, error=str(exc))


async def main() -> None:
    worker = NotifyWorker()
    logger.info("starting_notify_worker", stream=worker.stream, group=worker.group)
    try:
        await worker.run()
    except (KeyboardInterrupt, SystemExit):
        logger.info("notify_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
