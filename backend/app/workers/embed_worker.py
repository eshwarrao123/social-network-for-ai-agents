"""
Embed Worker — consumes 'posts:embed' and 'agents:embed' streams.
Generates 768-dimensional semantic vectors via Ollama nomic-embed-text
and persists them into PostgreSQL with pgvector.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import or_, select, update

from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.post import Post
from app.services.embedding import (
    EmbeddingDimensionError,
    EmbeddingError,
    EmbeddingValueError,
    get_embedding_service,
)
from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class EmbedWorker(BaseWorker):
    """
    Asynchronous worker processing semantic embeddings for Posts and Agents.
    Listens to both 'posts:embed' and 'agents:embed' Redis streams.
    """
    stream = "posts:embed"
    streams = ["posts:embed", "agents:embed"]
    group = "embed-workers"
    consumer_name = "embed-worker-1"
    reconcile_interval_seconds: float = 60.0

    def __init__(self, embedding_service=None):
        super().__init__()
        self.embedding_service = embedding_service or get_embedding_service()
        self._last_reconcile: float = 0.0

    async def periodic_hook(self, redis, log) -> None:
        """Periodically scans PostgreSQL to automatically reconcile any pending or failed embeddings."""
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_interval_seconds:
            self._last_reconcile = now
            await self.reconcile_pending_embeddings(redis, log)

    async def reconcile_pending_embeddings(self, redis, log) -> int:
        """
        Scans PostgreSQL for pending or failed records and re-enqueues them
        to Redis Streams. Provides automated recovery after Redis or network outages
        without requiring manual operator intervention.
        """
        reconciled_count = 0
        try:
            async with AsyncSessionLocal() as db:
                # 1. Reconcile pending posts (exclude permanently failed to prevent endless loops)
                pending_posts = await db.execute(
                    select(Post.id, Post.updated_at)
                    .where(
                        Post.status != "deleted",
                        Post.embedding_status == "pending",
                        Post.content_embedding.is_(None),
                    )
                    .limit(50)
                )
                for post_id, updated_at in pending_posts.all():
                    ts = updated_at.isoformat() if updated_at else datetime.now(timezone.utc).isoformat()
                    await redis.xadd("posts:embed", {"post_id": str(post_id), "timestamp": ts})
                    reconciled_count += 1

                # 2. Reconcile pending agents (exclude permanently failed to prevent endless loops)
                pending_agents = await db.execute(
                    select(Agent.id, Agent.updated_at)
                    .where(
                        Agent.is_active.is_(True),
                        Agent.embedding_status == "pending",
                        Agent.interest_embedding.is_(None),
                    )
                    .limit(50)
                )
                for agent_id, updated_at in pending_agents.all():
                    ts = updated_at.isoformat() if updated_at else datetime.now(timezone.utc).isoformat()
                    await redis.xadd("agents:embed", {"agent_id": str(agent_id), "timestamp": ts})
                    reconciled_count += 1

            if reconciled_count > 0:
                log.info("reconciled_pending_embeddings", count=reconciled_count)
        except Exception as exc:
            log.warning("reconcile_pending_failed", error=str(exc))

        return reconciled_count

    async def handle(self, fields: dict) -> None:
        """Dispatches event to appropriate post or agent handler."""
        if "post_id" in fields:
            post_id = uuid.UUID(fields["post_id"])
            await self.process_post(post_id, fields)
        elif "agent_id" in fields:
            agent_id = uuid.UUID(fields["agent_id"])
            await self.process_agent(agent_id, fields)
        else:
            logger.warning("embed_worker_unknown_event_format", fields=fields)

    async def process_post(self, post_id: uuid.UUID, fields: dict) -> None:
        """Processes an embedding request for a published or updated Post."""
        log = logger.bind(post_id=str(post_id), worker="EmbedWorker")

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()

            if not post:
                log.warning("embed_post_not_found")
                return

            # Skip deleted posts
            if post.status == "deleted":
                log.info("embed_post_deleted_skipping")
                return

            # Stale event protection: if post was updated after this event was generated
            event_ts = fields.get("timestamp")
            if event_ts and post.embedding_status in ("completed", "done") and post.content_embedding is not None:
                try:
                    dt = datetime.fromisoformat(event_ts)
                    if post.updated_at and post.updated_at > dt + timedelta(seconds=1):
                        log.info("embed_post_stale_event_skipped")
                        return
                except Exception:
                    pass

            # Idempotency check: if already completed and not pending re-embed
            if post.embedding_status in ("completed", "done") and post.content_embedding is not None:
                log.info("embed_post_already_completed")
                return

            # Active worker lease protection: if another worker is actively processing within lease window, skip
            if post.embedding_status == "processing" and post.updated_at:
                now_utc = datetime.now(timezone.utc)
                up_ts = post.updated_at if post.updated_at.tzinfo else post.updated_at.replace(tzinfo=timezone.utc)
                idle_sec = (self.claim_min_idle_ms / 1000.0)
                if (now_utc - up_ts).total_seconds() < idle_sec:
                    log.info("embed_post_active_lease_skipped_another_worker_active", updated_at=up_ts.isoformat())
                    return

            # Mark state as processing and update lease timestamp
            post.embedding_status = "processing"
            post.updated_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                embedding = await self.embedding_service.embed_post(post)
            except Exception as exc:
                log.error("embed_post_failed", error=str(exc))
                post.embedding_status = "failed"
                await db.commit()
                raise exc

            if embedding is None:
                post.embedding_status = "failed"
                await db.commit()
                raise EmbeddingError(f"Embedding generation returned empty vector for post {post_id}")

            # Persist vector
            post.content_embedding = embedding
            post.embedding_status = "completed"
            post.embedding_model = self.embedding_service.model
            post.updated_at = datetime.now(timezone.utc)
            await db.commit()
            log.info("embed_post_persisted", dimensions=len(embedding), model=self.embedding_service.model)

        # Trigger routing queue for newly embedded post
        try:
            redis = await self._get_redis()
            await redis.xadd("routing:pending", {"post_id": str(post_id)})
            await redis.aclose()
            log.info("routing_job_enqueued")
        except Exception as exc:
            log.warning("routing_enqueue_warning_redis_unavailable", error=str(exc))

    async def process_agent(self, agent_id: uuid.UUID, fields: dict) -> None:
        """Processes an embedding request for an enterprise Agent interest manifesto."""
        log = logger.bind(agent_id=str(agent_id), worker="EmbedWorker")

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()

            if not agent:
                log.warning("embed_agent_not_found")
                return

            # Skip inactive agents
            if not agent.is_active:
                log.info("embed_agent_inactive_skipping")
                return

            # Stale event protection
            event_ts = fields.get("timestamp")
            if event_ts and agent.embedding_status == "completed" and agent.interest_embedding is not None:
                try:
                    dt = datetime.fromisoformat(event_ts)
                    if agent.updated_at and agent.updated_at > dt + timedelta(seconds=1):
                        log.info("embed_agent_stale_event_skipped")
                        return
                except Exception:
                    pass

            # Idempotency check
            if agent.embedding_status == "completed" and agent.interest_embedding is not None:
                log.info("embed_agent_already_completed")
                return

            # Active worker lease protection: if another worker is actively processing within lease window, skip
            if agent.embedding_status == "processing" and agent.updated_at:
                now_utc = datetime.now(timezone.utc)
                up_ts = agent.updated_at if agent.updated_at.tzinfo else agent.updated_at.replace(tzinfo=timezone.utc)
                idle_sec = (self.claim_min_idle_ms / 1000.0)
                if (now_utc - up_ts).total_seconds() < idle_sec:
                    log.info("embed_agent_active_lease_skipped_another_worker_active", updated_at=up_ts.isoformat())
                    return

            # Mark state as processing and update lease timestamp
            agent.embedding_status = "processing"
            agent.updated_at = datetime.now(timezone.utc)
            await db.commit()

            try:
                embedding = await self.embedding_service.embed_agent_profile(agent)
            except Exception as exc:
                log.error("embed_agent_failed", error=str(exc))
                agent.embedding_status = "failed"
                await db.commit()
                raise exc

            if embedding is None:
                agent.embedding_status = "failed"
                await db.commit()
                raise EmbeddingError(f"Embedding generation returned empty vector for agent {agent_id}")

            # Capture prior embedding for idempotent re-anchoring detection
            prior_embedding = list(agent.interest_embedding) if agent.interest_embedding is not None else None

            # Persist vector
            agent.interest_embedding = embedding
            agent.embedding_status = "completed"
            agent.embedding_model = self.embedding_service.model
            agent.updated_at = datetime.now(timezone.utc)

            # Re-anchor adaptive preferences if they exist
            try:
                from app.services.preference_service import get_preference_service
                pref_svc = get_preference_service()
                await pref_svc.reanchor_to_new_embedding(
                    db,
                    agent.id,
                    embedding,
                    prior_embedding=prior_embedding,
                )
            except Exception as reanchor_exc:
                log.warning("preference_reanchor_on_profile_update_failed", error=str(reanchor_exc))

            await db.commit()
            log.info("embed_agent_persisted", dimensions=len(embedding), model=self.embedding_service.model)


async def main():
    worker = EmbedWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
