"""
P10.2 Full End-to-End Autonomous Agent Pipeline Orchestrator & Verifier
Runs the real multi-agent scenario through all 5 workers in controlled stages.
Zero mocks. Real PostgreSQL, Redis 5, FastAPI, Ollama, and Next.js.
"""
import asyncio
import os
import sys
import uuid
import time
import json
import httpx
import psycopg2
import structlog

# Add backend to sys.path and load environment variables
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
env_file = os.path.join(BACKEND_DIR, ".env")
if os.path.exists(env_file):
    load_dotenv(env_file, override=True)

from app.workers.base_worker import BaseWorker
from app.workers.embed_worker import EmbedWorker
from app.workers.routing_worker import RoutingWorker
from app.workers.notify_worker import NotifyWorker
from app.workers.llm_worker import LlmWorker
from app.workers.feedback_worker import FeedbackWorker
import redis.asyncio as aioredis

logger = structlog.get_logger("p10_2_scenario")
API_BASE = "http://127.0.0.1:8000/api/v1"
BFF_BASE = "http://127.0.0.1:3000"


async def drain_worker(worker: BaseWorker, max_empty_polls: int = 3) -> int:
    """Runs a worker instance in controlled bounded mode until its streams are drained."""
    redis = await worker._get_redis()
    await worker.setup(redis)
    log = logger.bind(worker=worker.__class__.__name__)
    await worker.claim_pending_all_streams(redis, log)

    stream_dict = {s: ">" for s in worker._get_streams()}
    empty_count = 0
    processed_count = 0

    while empty_count < max_empty_polls:
        messages = await redis.xreadgroup(
            worker.group,
            worker.consumer_name,
            stream_dict,
            count=worker.batch_size,
            block=1000,
        )
        if not messages:
            empty_count += 1
            continue

        has_msg = False
        for stream_name, msg_list in messages:
            for msg_id, fields in msg_list:
                has_msg = True
                await worker._process_with_retry(redis, stream_name, msg_id, fields, log)
                processed_count += 1

        if not has_msg:
            empty_count += 1
        else:
            empty_count = 0

    await redis.aclose()
    return processed_count


async def run_scenario():
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agents": {},
        "post": {},
        "embedding_stage": {},
        "routing_stage": {},
        "notification_stage": {},
        "interaction_stage": {},
        "feedback_stage": {},
        "frontend_verification": {},
    }

    client = httpx.AsyncClient(timeout=30.0)

    try:
        print("\n==================================================")
        print("STAGE 1: Registering Real Scenario Agents")
        print("==================================================")

        agents_data = [
            {
                "key": "swiggy",
                "name": f"Swiggy-Commerce-Ops-{uuid.uuid4().hex[:6]}",
                "company": "Bundl Technologies Pvt Ltd (Swiggy)",
                "description": "Hyperlocal food delivery, quick-commerce logistics, and merchant ecosystem operations across India.",
                "industries": ["food-delivery", "quick-commerce", "logistics", "e-commerce"],
                "capabilities": ["merchant-settlement", "partner-payouts", "order-fulfillment", "delivery-dispatch"],
                "tags": ["upi", "settlement", "merchants", "payments", "logistics"],
            },
            {
                "key": "phonepe",
                "name": f"PhonePe-Payments-Core-{uuid.uuid4().hex[:6]}",
                "company": "PhonePe Private Limited",
                "description": "Enterprise digital payment infrastructure, high-throughput UPI processing, merchant payment gateway, and instant bank reconciliation.",
                "industries": ["fintech", "payments", "banking", "e-commerce"],
                "capabilities": ["upi-infrastructure", "payment-processing", "merchant-payments", "digital-payment-reliability", "payment-reconciliation"],
                "tags": ["upi", "payments", "reconciliation", "settlement", "merchant-gateway"],
            },
            {
                "key": "hdfc",
                "name": f"HDFC-Treasury-Settlements-{uuid.uuid4().hex[:6]}",
                "company": "HDFC Bank Ltd",
                "description": "Institutional banking infrastructure, corporate treasury management, nodal accounts, bulk merchant settlement speed, and payment reconciliation.",
                "industries": ["banking", "fintech", "financial-services"],
                "capabilities": ["banking-infrastructure", "merchant-settlements", "payment-reconciliation", "enterprise-financial-services", "merchant-banking"],
                "tags": ["nodal-accounts", "merchant-settlements", "treasury", "reconciliation", "banking"],
            },
            {
                "key": "bajaj",
                "name": f"BajajAuto-Manufacturing-Ops-{uuid.uuid4().hex[:6]}",
                "company": "Bajaj Auto Ltd",
                "description": "Automotive manufacturing, two-wheeler vehicle engineering, assembly line robotics, and mobility supply chain operations.",
                "industries": ["automotive", "manufacturing", "heavy-engineering"],
                "capabilities": ["automotive-manufacturing", "vehicle-engineering", "mobility-operations", "supply-chain-assembly"],
                "tags": ["two-wheelers", "assembly-line", "robotics", "automotive", "engine-design"],
            },
        ]

        for a in agents_data:
            res = await client.post(f"{API_BASE}/agents/register", json={
                "name": a["name"],
                "company": a["company"],
                "description": a["description"],
                "industries": a["industries"],
                "capabilities": a["capabilities"],
                "tags": a["tags"],
            })
            assert res.status_code == 201, f"Failed to register {a['name']}: {res.text}"
            data = res.json()
            results["agents"][a["key"]] = {
                "id": data["id"],
                "name": data["name"],
                "company": data["company"],
                "api_key": data["api_key"],
                "trust_score": data["trust_score"],
            }
            print(f"[+] Registered {a['key'].upper()}: {data['name']} (ID: {data['id']})")

        swiggy_info = results["agents"]["swiggy"]

        # Authenticate Swiggy to get Bearer JWT
        token_res = await client.post(f"{API_BASE}/auth/token", json={"api_key": swiggy_info["api_key"]})
        assert token_res.status_code == 200, f"Swiggy token failed: {token_res.text}"
        swiggy_jwt = token_res.json()["access_token"]
        print("[+] Swiggy Bearer JWT successfully acquired")

        print("\n==================================================")
        print("STAGE 2: Publishing Swiggy Opportunity")
        print("==================================================")

        post_payload = {
            "title": "Enterprise Payment Infrastructure & Merchant Settlement Partnership",
            "content": (
                "Swiggy is exploring enterprise payment infrastructure partnerships to improve "
                "UPI payment reliability, merchant settlement speed, payout reconciliation, and "
                "payment operations across its restaurant and delivery partner ecosystem. We are "
                "looking for partners with proven merchant payments, financial infrastructure, "
                "and reconciliation capabilities."
            ),
            "post_type": "collaboration",
            "tags": ["upi", "settlement", "reconciliation", "merchant-payments", "financial-infrastructure"],
            "target_industries": ["fintech", "payments", "banking", "e-commerce"],
        }

        post_res = await client.post(
            f"{API_BASE}/posts",
            headers={"Authorization": f"Bearer {swiggy_jwt}"},
            json=post_payload,
        )
        assert post_res.status_code == 201, f"Failed to publish post: {post_res.text}"
        post_data = post_res.json()
        post_id = post_data["id"]
        results["post"] = {
            "id": post_id,
            "title": post_data["title"],
            "author_agent_id": post_data["author_agent_id"],
            "embedding_status": post_data.get("embedding_status", "pending"),
            "created_at": post_data["created_at"],
        }
        print(f"[+] Published Post ID: {post_id} - '{post_data['title']}'")

        print("\n==================================================")
        print("STAGE 3: Executing EmbedWorker (Ollama nomic-embed-text 768d)")
        print("==================================================")
        embed_worker = EmbedWorker()
        embed_processed = await drain_worker(embed_worker)
        print(f"[+] EmbedWorker processed {embed_processed} stream message(s)")
        results["embedding_stage"]["messages_processed"] = embed_processed

        # Verify embeddings in PostgreSQL
        conn = psycopg2.connect("postgresql://asama:asama_pass@127.0.0.1:5432/asama_db")
        cur = conn.cursor()
        cur.execute("SELECT id, name, embedding_status, array_length(string_to_array(trim(both '[]' from interest_embedding::text), ','), 1) FROM agents WHERE id IN (%s, %s, %s, %s);",
                    (results["agents"]["swiggy"]["id"], results["agents"]["phonepe"]["id"], results["agents"]["hdfc"]["id"], results["agents"]["bajaj"]["id"]))
        agent_embeds = cur.fetchall()
        for a_id, a_name, a_status, a_dim in agent_embeds:
            print(f"[+] Agent Embedding: {a_name} | status: {a_status} | dimensions: {a_dim}")
            assert a_status == "completed", f"Agent {a_name} embedding not completed"
            assert a_dim == 768, f"Agent {a_name} embedding dimension {a_dim} != 768"

        cur.execute("SELECT id, title, embedding_status, array_length(string_to_array(trim(both '[]' from content_embedding::text), ','), 1) FROM posts WHERE id = %s;", (post_id,))
        p_id, p_title, p_status, p_dim = cur.fetchone()
        print(f"[+] Post Embedding: '{p_title}' | status: {p_status} | dimensions: {p_dim}")
        assert p_status == "completed", "Post embedding not completed"
        assert p_dim == 768, f"Post embedding dimension {p_dim} != 768"
        results["embedding_stage"]["post_embedding_verified"] = {"dimensions": p_dim, "status": p_status}

        print("\n==================================================")
        print("STAGE 4: Executing RoutingWorker (Hybrid Semantic & Metadata)")
        print("==================================================")
        routing_worker = RoutingWorker()
        routing_processed = await drain_worker(routing_worker)
        print(f"[+] RoutingWorker processed {routing_processed} stream message(s)")
        results["routing_stage"]["messages_processed"] = routing_processed

        # Inspect routing logs from database
        cur.execute("""
            SELECT rl.candidate_agent_id, a.name, rl.passed_threshold, rl.final_score, rl.vector_score,
                   rl.metadata_score, rl.score_breakdown
            FROM routing_logs rl
            JOIN agents a ON a.id = rl.candidate_agent_id
            WHERE rl.post_id = %s
            ORDER BY rl.final_score DESC;
        """, (post_id,))
        routing_rows = cur.fetchall()
        print(f"[+] Total Routing Decisions Evaluated: {len(routing_rows)}")
        routing_audit = {}
        for r_id, a_name, passed_thresh, final_s, vec_s, meta_s, breakdown in routing_rows:
            dec = breakdown.get("decision", "selected" if passed_thresh else "rejected")
            thresh = breakdown.get("threshold", 0.5)
            routing_audit[a_name] = {
                "decision": dec,
                "passed_threshold": passed_thresh,
                "final_score": float(final_s),
                "semantic_score": float(vec_s),
                "metadata_score": float(meta_s),
                "threshold": float(thresh),
                "score_breakdown": breakdown,
            }
            print(f"    - {a_name:35} | Decision: {dec:8} | Final: {final_s:.4f} | Semantic: {vec_s:.4f} | Meta: {meta_s:.4f} | Thresh: {thresh:.4f}")

        results["routing_stage"]["decisions"] = routing_audit

        # Confirm PhonePe and HDFC were selected, and Bajaj was not selected
        phonepe_name = results["agents"]["phonepe"]["name"]
        hdfc_name = results["agents"]["hdfc"]["name"]
        bajaj_name = results["agents"]["bajaj"]["name"]

        phonepe_dec = routing_audit.get(phonepe_name, {}).get("decision")
        hdfc_dec = routing_audit.get(hdfc_name, {}).get("decision")
        bajaj_dec = routing_audit.get(bajaj_name, {}).get("decision")

        print(f"[+] PhonePe decision: {phonepe_dec} (expected 'selected')")
        print(f"[+] HDFC Bank decision: {hdfc_dec} (expected 'selected')")
        print(f"[+] Bajaj Auto decision: {bajaj_dec} (expected 'rejected' or 'below_threshold')")

        assert phonepe_dec == "selected", f"PhonePe expected 'selected', got {phonepe_dec}"
        assert hdfc_dec == "selected", f"HDFC Bank expected 'selected', got {hdfc_dec}"
        assert bajaj_dec in ("rejected", "below_threshold", "filtered", None), f"Bajaj Auto expected not selected, got {bajaj_dec}"

        print("\n==================================================")
        print("STAGE 5: Executing NotifyWorker (Notification Processing)")
        print("==================================================")
        notify_worker = NotifyWorker()
        notify_processed = await drain_worker(notify_worker)
        print(f"[+] NotifyWorker processed {notify_processed} stream message(s)")
        results["notification_stage"]["messages_processed"] = notify_processed

        cur.execute("""
            SELECT n.id, a.name, n.status, n.relevance_score, n.created_at
            FROM notifications n
            JOIN agents a ON a.id = n.recipient_agent_id
            WHERE n.post_id = %s;
        """, (post_id,))
        notifs = cur.fetchall()
        notifs_summary = []
        for n_id, a_name, n_status, r_score, c_at in notifs:
            notifs_summary.append({
                "notification_id": str(n_id),
                "recipient_agent": a_name,
                "status": n_status,
                "relevance_score": float(r_score),
            })
            print(f"[+] Notification created: {a_name} | status: {n_status} | relevance: {r_score:.4f}")
        results["notification_stage"]["notifications"] = notifs_summary

        print("\n==================================================")
        print("STAGE 6: Executing LlmWorker (Ollama qwen2.5-coder:1.5b)")
        print("==================================================")
        llm_worker = LlmWorker()
        t_llm_start = time.perf_counter()
        llm_processed = await drain_worker(llm_worker)
        llm_duration_sec = round(time.perf_counter() - t_llm_start, 2)
        print(f"[+] LlmWorker processed {llm_processed} message(s) in {llm_duration_sec}s")
        results["interaction_stage"]["messages_processed"] = llm_processed
        results["interaction_stage"]["duration_seconds"] = llm_duration_sec

        # Query generated comments and interactions
        cur.execute("""
            SELECT c.id, a.name, c.content, c.is_autonomous, c.confidence_score, c.created_at
            FROM comments c
            JOIN agents a ON a.id = c.author_agent_id
            WHERE c.post_id = %s;
        """, (post_id,))
        comments_rows = cur.fetchall()
        print(f"[+] Total Autonomous Comments Generated: {len(comments_rows)}")
        comments_data = []
        for c_id, a_name, c_content, is_auton, conf, c_time in comments_rows:
            comments_data.append({
                "comment_id": str(c_id),
                "author": a_name,
                "content": c_content,
                "is_autonomous": is_auton,
                "confidence": float(conf) if conf else None,
            })
            print(f"\n--- Autonomous Comment by {a_name} (Confidence: {conf}) ---")
            print(c_content)
            print("-----------------------------------------------------------------")
        results["interaction_stage"]["comments"] = comments_data

        cur.execute("""
            SELECT i.id, a.name, i.decision, i.status, i.confidence, i.reason
            FROM agent_interactions i
            JOIN agents a ON a.id = i.receiving_agent_id
            WHERE i.post_id = %s;
        """, (post_id,))
        interactions_rows = cur.fetchall()
        interactions_data = []
        for i_id, a_name, dec, stat, conf, reason in interactions_rows:
            interactions_data.append({
                "interaction_id": str(i_id),
                "agent": a_name,
                "decision": dec,
                "status": stat,
                "confidence": float(conf) if conf else None,
                "reasoning": reason,
            })
            print(f"[+] Interaction Record: {a_name} | decision: {dec} | status: {stat} | conf: {conf}")
        results["interaction_stage"]["interactions"] = interactions_data

        print("\n==================================================")
        print("STAGE 7: Executing FeedbackWorker (Adaptive Preferences)")
        print("==================================================")
        feedback_worker = FeedbackWorker()
        feedback_processed = await drain_worker(feedback_worker)
        print(f"[+] FeedbackWorker processed {feedback_processed} message(s)")
        results["feedback_stage"]["messages_processed"] = feedback_processed

        cur.execute("""
            SELECT fl.id, a.name, fl.signal, fl.confidence, fl.created_at
            FROM feedback_ledger fl
            JOIN agents a ON a.id = fl.agent_id
            WHERE fl.post_id = %s;
        """, (post_id,))
        feedback_rows = cur.fetchall()
        print(f"[+] Feedback Ledger entries recorded: {len(feedback_rows)}")
        results["feedback_stage"]["ledger_entries"] = [
            {"id": str(r[0]), "agent": r[1], "signal": r[2], "confidence": float(r[3]) if r[3] else None}
            for r in feedback_rows
        ]

        # Check adaptive preferences table
        cur.execute("SELECT agent_id, total_feedback_count, positive_interactions_count, negative_interactions_count, engagement_rate FROM agent_preferences;")
        pref_rows = cur.fetchall()
        results["feedback_stage"]["preferences"] = [
            {
                "agent_id": str(p[0]),
                "total_samples": p[1],
                "positive": p[2],
                "negative": p[3],
                "engagement_rate": float(p[4]),
                "adaptation_active": (p[1] >= 3),
            }
            for p in pref_rows
        ]

        print("\n==================================================")
        print("STAGE 8: Frontend BFF Workspace Verification")
        print("==================================================")
        # Authenticate via Next.js BFF using Swiggy's API key
        bff_conn_res = await client.post(
            f"{BFF_BASE}/api/auth/connect",
            json={"api_key": swiggy_info["api_key"]},
            headers={"Origin": BFF_BASE, "Referer": f"{BFF_BASE}/connect"},
        )
        assert bff_conn_res.status_code == 200, f"BFF connect failed: {bff_conn_res.text}"
        session_cookie = bff_conn_res.cookies.get("agent_session")
        print("[+] BFF agent_session cookie acquired successfully")

        bff_headers = {
            "Cookie": f"agent_session={session_cookie}",
            "Accept": "application/json",
            "Origin": BFF_BASE,
            "Referer": f"{BFF_BASE}/dashboard",
        }

        # 1. /api/auth/session
        sess_res = await client.get(f"{BFF_BASE}/api/auth/session", headers=bff_headers)
        assert sess_res.status_code == 200
        sess_data = sess_res.json()
        print(f"[+] BFF /api/auth/session: authenticated={sess_data.get('authenticated')}, agent={sess_data.get('agent', {}).get('name')}")

        # 2. /api/v1/posts
        feed_res = await client.get(f"{BFF_BASE}/api/v1/posts?limit=5", headers=bff_headers)
        assert feed_res.status_code == 200
        feed_data = feed_res.json()
        post_in_feed = any(p["id"] == str(post_id) for p in feed_data.get("items", []))
        print(f"[+] BFF Feed check: new Swiggy opportunity visible in feed: {post_in_feed}")

        # 3. /api/v1/posts/:id/comments
        comments_res = await client.get(f"{BFF_BASE}/api/v1/posts/{post_id}/comments", headers=bff_headers)
        assert comments_res.status_code == 200
        comments_json = comments_res.json()
        comment_items = comments_json.get("items", [])
        print(f"[+] BFF Comments check: {len(comment_items)} comment(s) visible on post")

        # 4. /api/v1/routing/posts/:id
        routing_audit_res = await client.get(f"{BFF_BASE}/api/v1/routing/posts/{post_id}", headers=bff_headers)
        assert routing_audit_res.status_code == 200
        routing_audit_json = routing_audit_res.json()
        total_eval = len(routing_audit_json) if isinstance(routing_audit_json, list) else routing_audit_json.get("total_candidates_evaluated", 0)
        print(f"[+] BFF Routing Explain check: evaluated_count={total_eval}")

        # 5. /api/v1/notifications
        notif_res = await client.get(f"{BFF_BASE}/api/v1/notifications", headers=bff_headers)
        assert notif_res.status_code == 200
        notif_json = notif_res.json()
        print(f"[+] BFF Notifications check: HTTP {notif_res.status_code}")

        # 6. /api/v1/analytics/me/overview
        analytics_res = await client.get(f"{BFF_BASE}/api/v1/analytics/me/overview", headers=bff_headers)
        print(f"[+] BFF Analytics check: HTTP {analytics_res.status_code}")

        results["frontend_verification"] = {
            "session_authenticated": sess_data.get("authenticated"),
            "agent_name": sess_data.get("agent", {}).get("name"),
            "post_visible_in_feed": post_in_feed,
            "comments_count": len(comment_items),
            "routing_audit_total_evaluated": total_eval,
            "notifications_http_status": notif_res.status_code,
            "analytics_http_status": analytics_res.status_code,
        }

        cur.close()
        conn.close()

        print("\n==================================================")
        print("[SUCCESS] P10.2 FULL SCENARIO INTEGRATION COMPLETED!")
        print("==================================================")
        return results

    finally:
        await client.aclose()


if __name__ == "__main__":
    res = asyncio.run(run_scenario())
    with open("p10_2_scenario_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print("\nWrote results to p10_2_scenario_results.json")
