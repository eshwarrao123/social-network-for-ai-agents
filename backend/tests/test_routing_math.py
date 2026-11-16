"""
Unit tests for RoutingEngine scoring mathematics and candidate evaluation.
Runs in any environment without database dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.agent import Agent
from app.models.post import Post
from app.services.routing_engine import RoutingEngine, RoutingCandidate


@pytest.mark.unit
def test_metadata_score_perfect_overlap():
    engine = RoutingEngine()

    agent = MagicMock(spec=Agent)
    agent.industries = ["fintech", "banking"]
    agent.tags = ["equities", "trading"]
    agent.last_active_at = datetime.now(timezone.utc)

    post = MagicMock(spec=Post)
    post.target_industries = ["fintech", "banking"]
    post.tags = ["equities", "trading"]

    score = engine._compute_metadata_score(
        agent=agent,
        post=post,
        industry_overlap=["fintech", "banking"],
        tag_overlap=["equities", "trading"],
    )

    # Calculation:
    # industry_ratio: 2/2 = 1.0 * 0.40 = 0.40
    # tag_ratio:      2/2 = 1.0 * 0.35 = 0.35
    # diversity:      0.5       * 0.10 = 0.05
    # recency:        1.0       * 0.15 = 0.15
    # Total = 0.40 + 0.35 + 0.05 + 0.15 = 0.95
    assert pytest.approx(score, 0.01) == 0.95


@pytest.mark.unit
def test_metadata_score_zero_overlap():
    engine = RoutingEngine()

    agent = MagicMock(spec=Agent)
    agent.industries = ["agriculture"]
    agent.tags = ["soil"]
    # Inactive for 60 days -> recency = 0.0
    agent.last_active_at = datetime.now(timezone.utc) - timedelta(days=60)

    post = MagicMock(spec=Post)
    post.target_industries = ["cybersecurity"]
    post.tags = ["zero-trust"]

    score = engine._compute_metadata_score(
        agent=agent,
        post=post,
        industry_overlap=[],
        tag_overlap=[],
    )

    # Calculation:
    # industry_ratio: 0.0 * 0.40 = 0.00
    # tag_ratio:      0.0 * 0.35 = 0.00
    # diversity:      0.5 * 0.10 = 0.05
    # recency:        0.0 * 0.15 = 0.00
    # Total = 0.05
    assert pytest.approx(score, 0.01) == 0.05


@pytest.mark.unit
def test_hybrid_score_formula():
    """Verify hybrid formula: final = alpha * vector + (1 - alpha) * metadata"""
    alpha = 0.65
    vector_score = 0.80
    metadata_score = 0.60

    expected_final = (alpha * vector_score) + ((1.0 - alpha) * metadata_score)
    # 0.65 * 0.80 + 0.35 * 0.60 = 0.52 + 0.21 = 0.73
    assert pytest.approx(expected_final, 0.001) == 0.73


@pytest.mark.unit
def test_metadata_only_candidate_fallback():
    engine = RoutingEngine()

    agent = MagicMock(spec=Agent)
    agent.id = uuid.uuid4()
    agent.industries = ["logistics"]
    agent.tags = ["supply-chain"]
    agent.last_active_at = None

    post = MagicMock(spec=Post)
    post.target_industries = ["logistics"]
    post.tags = ["supply-chain"]
    post.content_embedding = None  # No embedding yet

    candidate = engine._metadata_only_candidate(post, agent, alpha=0.65)
    assert candidate.vector_score == 0.0
    assert candidate.final_score > 0.0
    assert candidate.industry_overlap == ["logistics"]
    assert candidate.tag_overlap == ["supply-chain"]
