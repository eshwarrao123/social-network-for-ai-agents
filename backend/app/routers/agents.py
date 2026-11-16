"""
Agents router — registration, authentication, profile management.
Full implementation: Phase 1.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/health")
async def agents_health():
    return {"module": "agents", "status": "ready"}
