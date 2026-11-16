"""
Asama.ai FastAPI application factory.
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
    logger.info("asama_api_starting", env=settings.app_env)
    yield
    from app.database import engine
    await engine.dispose()
    logger.info("asama_api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Asama.ai API",
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
    async def health_check():
        return {"status": "ok", "service": "asama-api"}

    return app


app = create_app()
