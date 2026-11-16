"""
Posts router — publish, retrieve, feed.
Full implementation: Phase 2.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("/health")
async def posts_health():
    return {"module": "posts", "status": "ready"}
