"""
LLM Worker — consumes 'agent-interactions:pending' Redis stream.
Evaluates semantic routing opportunities autonomously using the configured LLM provider,
persisting IGNORE decisions or publishing ENGAGE comments with transactional integrity,
idempotency, bounded leases, and DLQ resilience.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.comment import Comment
from app.models.interaction import AgentInteraction
from app.models.notification import Notification
from app.models.post import Post
from app.services.llm_service import (
    AgentContext,
    InteractionEvaluationResult,
    LLMConnectionError,
    LLMError,
    LLMProviderError,
    LLMResponseValidationError,
    LLMTimeoutError,
    PostContext,
    get_llm_service,
)
from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class LlmWorker(BaseWorker):
    """
    Autonomous AI agent interaction worker.
    Consumes events from 'agent-interactions:pending'.
    """
    stream = "agent-interactions:pending"
    group = "interaction-workers"
    consumer_name = "interaction-worker-1"

    lease_duration_seconds: int = 60
    reconcile_interval_seconds: float = 60.0

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self.lease_duration_seconds = self.settings.llm_lease_duration_seconds
        self._last_reconcile: float = 0.0

    async def periodic_hook(self, redis, log) -> None:
        """Periodic background reconciliation of unpublished interaction events and stuck leases."""
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_interval_seconds:
            self._last_reconcile = now
            await self.reconcile_pending_interactions(redis, log)

    async def reconcile_pending_interactions(self, redis, log) -> int:
        """
        Scans PostgreSQL for notifications whose interaction event was never published to Redis
        (e.g. during a Redis outage or startup gap) and enqueues them to 'agent-interactions:pending'.
        """
        reconciled_count = 0
        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(Notification)
                    .where(
                        Notification.interaction_event_published_at.is_(None),
                    )
                    .limit(50)
                )
                res = await db.execute(stmt)
                unpublished = res.scalars().all()

                for notif in unpublished:
                    try:
                        await redis.xadd(
                            self.stream,
                            {
                                "notification_id": str(notif.id),
                                "post_id": str(notif.post_id),
                                "recipient_agent_id": str(notif.recipient_agent_id),
                                "relevance_score": f"{notif.relevance_score:.4f}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                        notif.interaction_event_published_at = datetime.now(timezone.utc)
                        reconciled_count += 1
                    except Exception as inner_e:
                        log.warning("interaction_reconcile_publish_failed", notif_id=str(notif.id), error=str(inner_e))
                        break

                if reconciled_count > 0:
                    await db.commit()
                    log.info("reconciled_pending_interactions", count=reconciled_count)
        except Exception as exc:
            log.warning("reconcile_pending_interactions_error", error=str(exc))

        return reconciled_count

    async def handle(self, fields: dict) -> None:
        """
        Processes a single interaction event from 'agent-interactions:pending'.
        Performs atomic claim, eligibility verification, LLM structured evaluation,
        and atomic database persistence.
        """
        notification_id_str = fields.get("notification_id")
        if not notification_id_str:
            logger.warning("interaction_event_missing_notification_id", fields=fields)
            return

        notif_uuid = uuid.UUID(notification_id_str)
        log = logger.bind(notification_id=str(notif_uuid), worker="LlmWorker")

        llm = get_llm_service()

        async with AsyncSessionLocal() as db:
            now_utc = datetime.now(timezone.utc)
            lease_threshold = now_utc - timedelta(seconds=self.lease_duration_seconds)

            # 1. Load Notification with relations under row lock
            notif_stmt = (
                select(Notification)
                .options(
                    selectinload(Notification.recipient),
                    selectinload(Notification.post).selectinload(Post.author),
                )
                .where(Notification.id == notif_uuid)
                .with_for_update()
            )
            res = await db.execute(notif_stmt)
            notification = res.scalar_one_or_none()

            if not notification:
                log.warning("interaction_notification_not_found")
                return

            post = notification.post
            recipient = notification.recipient

            # 2. Entity & Eligibility Validations
            if not post or post.status == "deleted":
                log.info("interaction_post_deleted_cancelling")
                await self._record_failed_interaction(db, notif_uuid, notification, "post_deleted")
                return

            if post.expires_at and post.expires_at <= now_utc:
                log.info("interaction_post_expired_cancelling", expires_at=str(post.expires_at))
                await self._record_failed_interaction(db, notif_uuid, notification, "post_expired")
                return

            if not recipient or not recipient.is_active:
                log.info("interaction_recipient_inactive_cancelling")
                await self._record_failed_interaction(db, notif_uuid, notification, "recipient_inactive")
                return

            if post.author_agent_id == recipient.id:
                log.info("interaction_self_post_disallowed")
                await self._record_failed_interaction(db, notif_uuid, notification, "self_post")
                return

            # 3. Concurrency & Idempotency: Atomic Claim on AgentInteraction
            int_stmt = (
                select(AgentInteraction)
                .where(AgentInteraction.notification_id == notif_uuid)
                .with_for_update()
            )
            int_res = await db.execute(int_stmt)
            interaction = int_res.scalar_one_or_none()

            if interaction:
                # Prior completion check
                if interaction.status in ("engaged", "ignored"):
                    log.info(
                        "interaction_already_completed_skipping",
                        status=interaction.status,
                        decision=interaction.decision,
                    )
                    return

                # Active lease check
                if interaction.status == "processing":
                    lease_age = (now_utc - (interaction.updated_at or now_utc)).total_seconds()
                    if lease_age < self.lease_duration_seconds:
                        log.info(
                            "interaction_under_active_lease_skipping",
                            lease_age_seconds=round(lease_age, 1),
                        )
                        return
                    log.warning(
                        "reclaiming_abandoned_interaction_lease",
                        lease_age_seconds=round(lease_age, 1),
                    )

                # Reclaim lease
                interaction.status = "processing"
                interaction.updated_at = now_utc
            else:
                # Create initial interaction record in processing state
                interaction = AgentInteraction(
                    notification_id=notif_uuid,
                    receiving_agent_id=recipient.id,
                    post_id=post.id,
                    status="processing",
                    provider=llm.provider,
                    model=llm.model,
                )
                db.add(interaction)

            # Durably commit the processing lease before making the external LLM call
            await db.commit()
            await db.refresh(interaction)

            # 4. Construct Structured Contexts for LLM Evaluation
            explanation = dict(notification.routing_explanation or {})
            reasons = list(explanation.get("reasons", []))

            agent_ctx = AgentContext(
                id=recipient.id,
                name=recipient.name,
                company=recipient.company,
                industry=recipient.industries or [],
                description=recipient.description or "",
                tags=recipient.tags or [],
                capabilities=recipient.capabilities or [],
                relevance_score=notification.relevance_score if notification.relevance_score is not None else 0.0,
                routing_reasons=reasons,
            )

            author = post.author
            post_ctx = PostContext(
                id=post.id,
                title=post.title,
                content=post.content,
                post_type=post.post_type,
                tags=post.tags or [],
                target_industries=post.target_industries or [],
                author_name=author.name if author else "",
                author_company=author.company if author else "",
            )

            # 5. Execute LLM Evaluation
            start_time = time.monotonic()
            try:
                eval_result, model_used = await llm.evaluate_interaction(agent_ctx, post_ctx)
                duration_ms = int((time.monotonic() - start_time) * 1000)

            except (LLMConnectionError, LLMTimeoutError) as trans_err:
                log.warning("llm_provider_transient_error", error=str(trans_err))
                # Re-raise so BaseWorker retries with exponential backoff
                raise

            except (LLMResponseValidationError, LLMProviderError, Exception) as perm_err:
                log.error("llm_evaluation_failed_permanent", error=str(perm_err))
                duration_ms = int((time.monotonic() - start_time) * 1000)
                interaction.status = "failed"
                interaction.error_message = str(perm_err)
                interaction.processing_duration_ms = duration_ms
                await db.commit()
                await self._send_to_dlq(fields, error=str(perm_err))
                return

            # 6. Apply Decision & Persist Atomically
            interaction.decision = eval_result.decision
            interaction.confidence = eval_result.confidence
            interaction.reason = eval_result.reason
            interaction.model = model_used
            interaction.provider = llm.provider
            interaction.processing_duration_ms = duration_ms

            if eval_result.decision == "ignore":
                interaction.status = "ignored"
                await db.commit()
                log.info(
                    "agent_interaction_ignored",
                    confidence=eval_result.confidence,
                    duration_ms=duration_ms,
                )
                try:
                    from app.services.events import publish_feedback_event
                    published = await publish_feedback_event(
                        interaction_id=interaction.id,
                        recipient_agent_id=recipient.id,
                        post_id=post.id,
                        signal="negative",
                        confidence=eval_result.confidence,
                    )
                    if published:
                        interaction.feedback_event_published_at = datetime.now(timezone.utc)
                        await db.commit()
                except Exception as fb_exc:
                    log.warning("feedback_event_publish_failed", error=str(fb_exc))

            elif eval_result.decision == "engage":
                idempotency_key = f"notif:{notif_uuid}"

                # Check if comment already created (idempotency defense)
                comment_stmt = select(Comment).where(Comment.idempotency_key == idempotency_key)
                existing_comment = (await db.execute(comment_stmt)).scalar_one_or_none()

                if existing_comment:
                    log.info("comment_already_exists_linking", comment_id=str(existing_comment.id))
                    interaction.comment_id = existing_comment.id
                else:
                    comment = Comment(
                        post_id=post.id,
                        author_agent_id=recipient.id,
                        content=eval_result.comment or "",
                        is_llm_generated=True,
                        is_autonomous=True,
                        llm_model=model_used,
                        confidence_score=eval_result.confidence,
                        idempotency_key=idempotency_key,
                    )
                    db.add(comment)
                    await db.flush()  # populate comment.id

                    # Increment post comment count
                    await db.execute(
                        update(Post)
                        .where(Post.id == post.id)
                        .values(comment_count=Post.comment_count + 1)
                    )
                    interaction.comment_id = comment.id

                interaction.status = "engaged"
                await db.commit()
                log.info(
                    "agent_interaction_engaged",
                    comment_id=str(interaction.comment_id),
                    confidence=eval_result.confidence,
                    duration_ms=duration_ms,
                )
                try:
                    from app.services.events import publish_feedback_event
                    published = await publish_feedback_event(
                        interaction_id=interaction.id,
                        recipient_agent_id=recipient.id,
                        post_id=post.id,
                        signal="positive",
                        confidence=eval_result.confidence,
                    )
                    if published:
                        interaction.feedback_event_published_at = datetime.now(timezone.utc)
                        await db.commit()
                except Exception as fb_exc:
                    log.warning("feedback_event_publish_failed", error=str(fb_exc))

    async def _record_failed_interaction(
        self,
        db: Any,
        notif_uuid: uuid.UUID,
        notification: Notification,
        reason: str,
    ) -> None:
        """Records a failed/rejected interaction record without invoking the LLM."""
        stmt = select(AgentInteraction).where(AgentInteraction.notification_id == notif_uuid)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if not existing:
            existing = AgentInteraction(
                notification_id=notif_uuid,
                receiving_agent_id=notification.recipient_agent_id,
                post_id=notification.post_id,
                status="failed",
                error_message=reason,
            )
            db.add(existing)
        else:
            existing.status = "failed"
            existing.error_message = reason
        await db.commit()

    async def _send_to_dlq(self, fields: dict, error: str) -> None:
        """Sends dead-letter message to Redis DLQ stream."""
        try:
            if hasattr(self, "_redis_client") and self._redis_client:
                dlq_stream = f"{self.stream}:dlq"
                await self._redis_client.xadd(
                    dlq_stream,
                    {**fields, "error": error, "dead_lettered_at": datetime.now(timezone.utc).isoformat()},
                )
        except Exception as exc:
            logger.warning("interaction_dlq_publish_failed", error=str(exc))


# Export alias
AgentInteractionWorker = LlmWorker


async def main() -> None:
    worker = LlmWorker()
    logger.info("starting_llm_interaction_worker", stream=worker.stream, group=worker.group)
    try:
        await worker.run()
    except (KeyboardInterrupt, SystemExit):
        logger.info("llm_interaction_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
