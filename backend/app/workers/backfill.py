"""
Backfill utility for generating missing or outdated embeddings.
Can be executed as a standalone CLI job or recovery worker.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

import structlog
from sqlalchemy import or_, select

from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.post import Post
from app.services.embedding import get_embedding_service
from app.services.events import publish_agent_embed_event, publish_post_embed_event

logger = structlog.get_logger(__name__)


async def run_backfill(mode: str = "enqueue", limit: int = 200) -> dict[str, int]:
    """
    Scans PostgreSQL for un-embedded or failed posts and agents.
    
    Modes:
      - 'enqueue': Dispatches events to Redis Streams for background workers to process.
      - 'direct': Directly invokes Ollama and updates database records in-process.
    """
    stats = {
        "posts_found": 0,
        "posts_processed": 0,
        "posts_failed": 0,
        "agents_found": 0,
        "agents_processed": 0,
        "agents_failed": 0,
    }

    try:
        async with AsyncSessionLocal() as db:
            # 1. Query pending/missing posts
            post_stmt = (
                select(Post)
                .where(
                    Post.status != "deleted",
                    or_(
                        Post.content_embedding.is_(None),
                        Post.embedding_status.in_(["pending", "failed"]),
                    ),
                )
                .limit(limit)
            )
            post_res = await db.execute(post_stmt)
            posts = post_res.scalars().all()
            stats["posts_found"] = len(posts)

            # 2. Query pending/missing agents
            agent_stmt = (
                select(Agent)
                .where(
                    Agent.is_active.is_(True),
                    or_(
                        Agent.interest_embedding.is_(None),
                        Agent.embedding_status.in_(["pending", "failed"]),
                    ),
                )
                .limit(limit)
            )
            agent_res = await db.execute(agent_stmt)
            agents = agent_res.scalars().all()
            stats["agents_found"] = len(agents)

            print(f"[BACKFILL] Identified {len(posts)} posts and {len(agents)} agents needing embeddings.")

            if mode == "enqueue":
                # Queue posts
                for p in posts:
                    ok = await publish_post_embed_event(p.id, p.author_agent_id)
                    if ok:
                        stats["posts_processed"] += 1
                    else:
                        stats["posts_failed"] += 1

                # Queue agents
                for a in agents:
                    ok = await publish_agent_embed_event(a.id)
                    if ok:
                        stats["agents_processed"] += 1
                    else:
                        stats["agents_failed"] += 1

            elif mode == "direct":
                embedding_service = get_embedding_service()

                for p in posts:
                    try:
                        p.embedding_status = "processing"
                        await db.commit()
                        vec = await embedding_service.embed_post(p)
                        if vec:
                            p.content_embedding = vec
                            p.embedding_status = "completed"
                            p.embedding_model = embedding_service.model
                            p.updated_at = datetime.now(timezone.utc)
                            await db.commit()
                            stats["posts_processed"] += 1
                        else:
                            p.embedding_status = "failed"
                            await db.commit()
                            stats["posts_failed"] += 1
                    except Exception as exc:
                        logger.error("backfill_post_failed", post_id=str(p.id), error=str(exc))
                        p.embedding_status = "failed"
                        await db.commit()
                        stats["posts_failed"] += 1

                for a in agents:
                    try:
                        a.embedding_status = "processing"
                        await db.commit()
                        vec = await embedding_service.embed_agent_profile(a)
                        if vec:
                            a.interest_embedding = vec
                            a.embedding_status = "completed"
                            a.embedding_model = embedding_service.model
                            a.updated_at = datetime.now(timezone.utc)
                            await db.commit()
                            stats["agents_processed"] += 1
                        else:
                            a.embedding_status = "failed"
                            await db.commit()
                            stats["agents_failed"] += 1
                    except Exception as exc:
                        logger.error("backfill_agent_failed", agent_id=str(a.id), error=str(exc))
                        a.embedding_status = "failed"
                        await db.commit()
                        stats["agents_failed"] += 1

        print(
            f"[BACKFILL COMPLETE] Mode: {mode} | "
            f"Posts queued/processed: {stats['posts_processed']}/{stats['posts_found']} (Failed: {stats['posts_failed']}) | "
            f"Agents queued/processed: {stats['agents_processed']}/{stats['agents_found']} (Failed: {stats['agents_failed']})"
        )
        return stats

    except Exception as exc:
        print(f"[BACKFILL ERROR] Database unavailable or backfill encountered error: {exc}", file=sys.stderr)
        return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill missing embeddings for Posts and Agents")
    parser.add_argument(
        "--mode",
        choices=["enqueue", "direct"],
        default="enqueue",
        help="enqueue (send to Redis Streams) or direct (process in-process via Ollama)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of records per entity to process",
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(mode=args.mode, limit=args.limit))


if __name__ == "__main__":
    main()
