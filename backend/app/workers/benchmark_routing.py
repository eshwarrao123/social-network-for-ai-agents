"""
Routing Engine In-Memory Diagnostic Benchmark Tool — measures execution latencies
for in-memory vector cosine distance computation and hybrid reranking across N candidate objects.

IMPORTANT ARCHITECTURAL DISTINCTION:
  1. This benchmark measures pure CPU in-memory vector math (float dot product) and Python
     hybrid metadata reranking.
  2. It does NOT measure PostgreSQL pgvector ANN index retrieval (HNSW/IVFFlat), database
     transaction latency (SQL INSERT/UPDATE for RoutingLog and Notification), or Redis Streams I/O.
  3. Production routing latency includes database connection, pgvector index scan, network I/O,
     and transaction commits (typically 35ms - 75ms).
"""
from __future__ import annotations

import asyncio
import math
import time
import uuid
from datetime import datetime, timezone

from app.models.agent import Agent
from app.models.post import Post
from app.services.routing_engine import RoutingEngine


def generate_benchmark_vector(seed: float = 0.1) -> list[float]:
    raw = [math.sin(seed + i * 0.05) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


async def run_benchmark(candidate_count: int = 100) -> None:
    print(f"\n================================================================================")
    print(f"  Routing Engine In-Memory Diagnostic Benchmark (N={candidate_count} Candidates)")
    print(f"  Scope: Pure Python CPU computation (vector dot product + hybrid reranking)")
    print(f"  Excludes: PostgreSQL pgvector ANN search, SQL persistence, Redis Stream delivery")
    print(f"================================================================================\n")

    engine = RoutingEngine()

    # 1. Prepare benchmark post
    post = Post(
        id=uuid.uuid4(),
        author_agent_id=uuid.uuid4(),
        title="Diwali Feast: 5% off on food delivery orders above 300",
        content="Flat 5% discount across all food delivery orders above 300 during the festive Diwali week.",
        target_industries=["food-tech", "retail", "consumer"],
        tags=["food-delivery", "offers", "diwali-promotions", "discounts", "cashback"],
        content_embedding=generate_benchmark_vector(seed=0.5),
        embedding_status="completed",
    )

    # 2. Prepare mock candidates
    agents: list[Agent] = []
    for i in range(candidate_count):
        agent = Agent(
            id=uuid.uuid4(),
            name=f"BenchmarkAgent-{i}",
            company="PartnerCorp" if i % 2 == 0 else "Swiggy",
            industries=["fintech", "payments"] if i % 3 == 0 else ["logistics", "automotive"],
            tags=["discounts", "cashback"] if i % 2 == 0 else ["telecom"],
            capabilities=["payment-gateway", "cashback-rewards"] if i % 4 == 0 else [],
            trust_score=0.8,
            is_active=True,
            embedding_status="completed",
            interest_embedding=generate_benchmark_vector(seed=0.1 * i),
            last_active_at=datetime.now(timezone.utc),
        )
        agents.append(agent)

    # Measure Vector Distance calculation
    t0 = time.perf_counter()
    distances = []
    query_vec = post.content_embedding
    for agent in agents:
        # Cosine distance = 1 - dot_product (for unit vectors)
        dot = sum(a * b for a, b in zip(query_vec, agent.interest_embedding))
        dist = max(0.0, min(2.0, 1.0 - dot))
        distances.append((agent, dist))
    t_vector = (time.perf_counter() - t0) * 1000

    # Measure Hybrid Reranking & Explainability
    t1 = time.perf_counter()
    scored = []
    for agent, dist in distances:
        candidate = engine._score_candidate(
            post=post,
            agent=agent,
            cosine_dist=dist,
            author_company="Swiggy",
        )
        scored.append(candidate)

    scored.sort(
        key=lambda c: (
            -c.final_score,
            -c.vector_score,
            -c.agent_trust_score,
            str(c.agent_id),
        )
    )
    t_rerank = (time.perf_counter() - t1) * 1000
    t_total = t_vector + t_rerank

    print(f"Results across {candidate_count} candidates:")
    print(f"  • Vector Cosine Distances: {t_vector:.2f} ms ({t_vector/candidate_count:.3f} ms/candidate)")
    print(f"  • Hybrid Rerank & Reasons: {t_rerank:.2f} ms ({t_rerank/candidate_count:.3f} ms/candidate)")
    print(f"  • Total Scoring Latency:   {t_total:.2f} ms\n")

    passed_count = sum(1 for c in scored if c.passed_threshold)
    print(f"Policy Selection Summary:")
    print(f"  • Threshold: {engine.threshold} (Alpha: {engine.alpha})")
    print(f"  • Passed Threshold: {passed_count}/{candidate_count}")
    print(f"  • Top Selected Candidates (Max 5):")
    for idx, c in enumerate(scored[:5], 1):
        status = "NOTIFIED" if c.passed_threshold else "BELOW_THRESHOLD"
        print(f"    [{idx}] {c.agent_name} ({c.company}): Final={c.final_score:.3f} (Vec={c.vector_score:.3f}, Meta={c.metadata_score:.3f}) -> {status}")
    print("\nBenchmark completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_benchmark(100))
