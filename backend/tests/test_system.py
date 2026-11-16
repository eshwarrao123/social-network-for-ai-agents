"""
Unit tests for system health, configuration, and API factory.
Runs in any environment without database dependencies.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.models import (
    Agent,
    Post,
    Comment,
    Notification,
    Engagement,
    RoutingLog,
    WebhookSubscription,
    AgentInteraction,
    AgentPreference,
    FeedbackLedger,
)


@pytest.mark.unit
async def test_system_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "asama-api"


@pytest.mark.unit
def test_settings_cors_parsing():
    settings = get_settings()
    assert isinstance(settings.cors_origins_list, list)
    assert len(settings.cors_origins_list) >= 1
    assert any("localhost" in origin for origin in settings.cors_origins_list)


@pytest.mark.unit
def test_all_orm_models_registered():
    models = [
        Agent,
        Post,
        Comment,
        Notification,
        Engagement,
        RoutingLog,
        WebhookSubscription,
        AgentInteraction,
        AgentPreference,
        FeedbackLedger,
    ]
    table_names = {m.__tablename__ for m in models}
    expected = {
        "agents",
        "posts",
        "comments",
        "notifications",
        "engagements",
        "routing_logs",
        "webhook_subscriptions",
        "agent_interactions",
        "agent_preferences",
        "feedback_ledger",
    }
    assert table_names == expected
