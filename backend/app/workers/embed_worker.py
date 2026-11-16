"""
Embed Worker — consumes 'posts:embed' stream.
Fetches post from DB → calls Ollama → stores 768-dim embedding.
"""
from __future__ import annotations

import uuid
import asyncio
import structlog

from app.workers.base_worker import BaseWorker

logger = structlog.get_logger(__name__)


class EmbedWorker(BaseWorker):
    stream = "posts:embed"
    group = "embed-workers"
    consumer_name = "embed-worker-1"

    async def handle(self, fields: dict) -> None:
        post_id = uuid.UUID(fields["post_id"])
        log = logger.bind(post_id=str(post_id))

        from app.database import AsyncSessionLocal
        from app.models.post import Post
        from app.services.embedding import get_embedding_service
        from sqlalchemy import select, update

        embedding_service = get_embedding_service()

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()

            if not post:
                log.warning("embed_post_not_found")
                return

            if post.embedding_status == "done":
                log.info("embed_already_done")
                return  # Idempotent

            await db.execute(
                update(Post).where(Post.id == post_id).values(embedding_status="processing")
            )
            await db.commit()

            embedding = await embedding_service.embed_post(post)

            if embedding:
                await db.execute(
                    update(Post)
                    .where(Post.id == post_id)
                    .values(content_embedding=embedding, embedding_status="done")
                )
                log.info("embed_stored")
            else:
                await db.execute(
                    update(Post).where(Post.id == post_id).values(embedding_status="failed")
                )
                log.warning("embed_failed_no_embedding")

            await db.commit()

        # After embedding, trigger routing
        redis = await self._get_redis()
        await redis.xadd("routing:pending", {"post_id": str(post_id)})
        log.info("routing_job_enqueued")


async def main():
    worker = EmbedWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
