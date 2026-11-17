"""
Social Network for AI Agents FastAPI application factory.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("api_starting", env=settings.app_env)
    yield
    from app.database import engine
    await engine.dispose()
    logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Social Network for AI Agents API",
        description="Enterprise Social Network for AI Agents",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # --- Rate limiter ---
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers (registered in dependency order) ---
    from app.routers import (
        agents,
        analytics,
        auth,
        comments,
        notifications,
        posts,
        routing,
        webhooks,
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")
    app.include_router(posts.router, prefix="/api/v1")
    app.include_router(comments.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(routing.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")

    @app.get("/health", tags=["System"])
    @app.get("/health/live", tags=["System"])
    async def liveness_check():
        from datetime import datetime, timezone
        return {
            "status": "ok",
            "service": "social-network-for-ai-agents",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/health/ready", tags=["System"])
    async def readiness_check():
        import time
        from datetime import datetime, timezone
        from fastapi.responses import JSONResponse

        checks = {}
        all_ok = True

        # 1. Database probe
        t0 = time.perf_counter()
        try:
            from app.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            db_latency = round((time.perf_counter() - t0) * 1000, 2)
            checks["database"] = {"status": "ok", "latency_ms": db_latency}
        except Exception:
            db_latency = round((time.perf_counter() - t0) * 1000, 2)
            checks["database"] = {
                "status": "unavailable",
                "latency_ms": db_latency,
                "error": "Database connection failed",
            }
            all_ok = False

        # 2. Redis probe
        t0 = time.perf_counter()
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                await r.ping()
                redis_latency = round((time.perf_counter() - t0) * 1000, 2)
                checks["redis"] = {"status": "ok", "latency_ms": redis_latency}
            finally:
                await r.aclose()
        except Exception:
            redis_latency = round((time.perf_counter() - t0) * 1000, 2)
            checks["redis"] = {
                "status": "unavailable",
                "latency_ms": redis_latency,
                "error": "Redis connection failed",
            }
            all_ok = False

        # 3. Ollama provider probe
        if settings.llm_provider == "disabled":
            checks["ollama"] = {
                "status": "disabled",
                "latency_ms": 0.0,
                "message": "Ollama LLM provider is disabled in configuration",
            }
        else:
            t0 = time.perf_counter()
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as client:
                    res = await client.get(f"{settings.ollama_base_url}/api/tags")
                    ollama_latency = round((time.perf_counter() - t0) * 1000, 2)
                    if res.status_code == 200:
                        checks["ollama"] = {"status": "ok", "latency_ms": ollama_latency}
                    else:
                        checks["ollama"] = {
                            "status": "degraded",
                            "latency_ms": ollama_latency,
                            "error": f"Ollama returned HTTP {res.status_code}",
                        }
            except Exception:
                ollama_latency = round((time.perf_counter() - t0) * 1000, 2)
                # If Ollama is the required LLM provider in production, mark unavailable and impact readiness
                # Otherwise, treat as degraded without failing overall readiness
                is_strictly_required = settings.llm_provider == "ollama" and settings.is_production
                checks["ollama"] = {
                    "status": "unavailable" if is_strictly_required else "degraded",
                    "latency_ms": ollama_latency,
                    "error": "Ollama service unreachable",
                }
                if is_strictly_required:
                    all_ok = False

        status_str = "ready" if all_ok else "unready"
        status_code = 200 if all_ok else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": status_str,
                "service": "social-network-for-ai-agents",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": checks,
            },
        )

    return app


app = create_app()
