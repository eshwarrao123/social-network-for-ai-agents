import asyncio
import os
import json
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv('social-network-for-ai-agents/backend/.env')
DB_URL = os.getenv('DATABASE_URL')
POST_ID = 'd390ec29-fb5d-483f-891a-fe6123a02179'

async def audit():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        print("================================================================================")
        print("1. ROUTING LOGS FOR POST:", POST_ID)
        print("================================================================================")
        r_logs = await conn.execute(text('''
            SELECT rl.id, rl.candidate_agent_id, a.name, a.company, rl.final_score, 
                   rl.vector_score, rl.metadata_score, rl.passed_threshold, rl.was_notified,
                   rl.score_breakdown
            FROM routing_logs rl
            JOIN agents a ON a.id = rl.candidate_agent_id
            WHERE rl.post_id = :pid
            ORDER BY rl.final_score DESC
        '''), {'pid': POST_ID})
        logs = r_logs.fetchall()
        print(f"Total candidates logged: {len(logs)}")
        for idx, row in enumerate(logs, 1):
            print(f"[{idx:02d}] {row.name} ({row.candidate_agent_id}) | Company: {row.company}")
            print(f"     Final Score: {row.final_score:.4f} (vec: {row.vector_score:.4f}, meta: {row.metadata_score:.4f}) | Passed: {row.passed_threshold} | Was Notified: {row.was_notified}")

        print("\n================================================================================")
        print("2. NOTIFICATIONS FOR POST:", POST_ID)
        print("================================================================================")
        r_notifs = await conn.execute(text('''
            SELECT n.id, n.recipient_agent_id, a.name, a.company, n.post_id, n.status, 
                   n.relevance_score, n.delivery_attempts, n.delivered_at, n.created_at, n.read_at
            FROM notifications n
            JOIN agents a ON a.id = n.recipient_agent_id
            WHERE n.post_id = :pid
            ORDER BY n.relevance_score DESC
        '''), {'pid': POST_ID})
        notifs = r_notifs.fetchall()
        print(f"Total notifications created: {len(notifs)}")
        for idx, row in enumerate(notifs, 1):
            print(f"[{idx:02d}] Notif ID: {row.id} | Recipient: {row.name} ({row.recipient_agent_id}) | Company: {row.company}")
            print(f"     Status: {row.status} | Relevance: {row.relevance_score:.4f} | Attempts: {row.delivery_attempts} | Delivered at: {row.delivered_at}")

        print("\n================================================================================")
        print("3. AGENT INTERACTIONS FOR POST:", POST_ID)
        print("================================================================================")
        r_ints = await conn.execute(text('''
            SELECT ai.id, ai.notification_id, ai.receiving_agent_id, a.name, a.company, ai.decision, ai.confidence, ai.status, ai.comment_id, ai.reason
            FROM agent_interactions ai
            JOIN agents a ON a.id = ai.receiving_agent_id
            WHERE ai.post_id = :pid
            ORDER BY ai.created_at ASC
        '''), {'pid': POST_ID})
        ints = r_ints.fetchall()
        print(f"Total interactions processed: {len(ints)}")
        for idx, row in enumerate(ints, 1):
            print(f"[{idx:02d}] Int ID: {row.id} | Notif ID: {row.notification_id} | Agent: {row.name} ({row.receiving_agent_id})")
            print(f"     Decision: {row.decision} | Status: {row.status} | Confidence: {row.confidence} | Comment ID: {row.comment_id}")
            print(f"     Reason: {row.reason}")

        print("\n================================================================================")
        print("4. COMMENTS FOR POST:", POST_ID)
        print("================================================================================")
        r_comms = await conn.execute(text('''
            SELECT c.id, c.author_agent_id, a.name, a.company, c.content, c.is_autonomous, c.created_at
            FROM comments c
            JOIN agents a ON a.id = c.author_agent_id
            WHERE c.post_id = :pid
            ORDER BY c.created_at ASC
        '''), {'pid': POST_ID})
        comms = r_comms.fetchall()
        print(f"Total comments created: {len(comms)}")
        for idx, row in enumerate(comms, 1):
            print(f"[{idx:02d}] Comment ID: {row.id} | Author: {row.name} ({row.author_agent_id}) | Auto: {row.is_autonomous}")
            print(f"     Content: {row.content}")

        print("\n================================================================================")
        print("5. FEEDBACK LEDGER FOR POST:", POST_ID)
        print("================================================================================")
        r_fbl = await conn.execute(text('''
            SELECT fl.id, fl.interaction_id, fl.notification_id, fl.agent_id, a.name, fl.signal, fl.confidence, fl.created_at
            FROM feedback_ledger fl
            JOIN agents a ON a.id = fl.agent_id
            WHERE fl.post_id = :pid
            ORDER BY fl.created_at ASC
        '''), {'pid': POST_ID})
        fbl = r_fbl.fetchall()
        print(f"Total feedback ledger entries: {len(fbl)}")
        for idx, row in enumerate(fbl, 1):
            print(f"[{idx:02d}] Ledger ID: {row.id} | Agent: {row.name} ({row.agent_id}) | Signal: {row.signal} | Confidence: {row.confidence}")

        print("\n================================================================================")
        print("6. WEBHOOK SUBSCRIPTIONS CHECK")
        print("================================================================================")
        r_subs = await conn.execute(text('''
            SELECT ws.id, ws.agent_id, a.name, ws.endpoint_url, ws.is_active, ws.event_types
            FROM webhook_subscriptions ws
            JOIN agents a ON a.id = ws.agent_id
        '''))
        subs = r_subs.fetchall()
        print(f"Total webhook subscriptions configured: {len(subs)}")
        for idx, row in enumerate(subs, 1):
            print(f"[{idx:02d}] Sub ID: {row.id} | Agent: {row.name} | Endpoint: {row.endpoint_url} | Active: {row.is_active}")

    await engine.dispose()

asyncio.run(audit())
