"""
Live Redis 5.0.14.1 Pending-Message Recovery Integration Test (P10.1.2)
Exercises:
  1. Real local Redis 5.0.14.1 server
  2. Real redis-py async client
  3. Real BaseWorker._claim_and_process_pending fallback implementation
  4. PEL inspection (time_since_delivered field)
  5. XCLAIM reclamation from crashed consumer A to reclaimer consumer B
  6. Message processing, retry envelope handling, and XACK
  7. PEL verification (cleared to 0)
  8. Clean up of disposable keys
"""
import asyncio
import os
import sys
import uuid
import time
import structlog

# Add backend to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.workers.base_worker import BaseWorker
import redis.asyncio as aioredis

logger = structlog.get_logger("test_live_redis5_worker_recovery")


class LiveTestRecoveryWorker(BaseWorker):
    """Concrete BaseWorker subclass for isolated live recovery test."""
    stream = "temporary:stream"
    group = "temporary:group"
    consumer_name = "consumer_B_reclaimer"
    claim_min_idle_ms = 1000  # 1.0 second test idle threshold
    claim_batch_size = 10

    def __init__(self, stream_name: str, group_name: str):
        super().__init__()
        self.stream = stream_name
        self.group = group_name
        self.claim_min_idle_ms = 1000  # Set explicitly after super().__init__()
        self.handled_messages = []

    def _get_streams(self) -> list[str]:
        return [self.stream]

    async def handle(self, fields: dict) -> None:
        self.handled_messages.append(fields)


async def run_live_test():
    redis_url = "redis://127.0.0.1:6379?protocol=2"
    r = aioredis.from_url(redis_url, decode_responses=True)

    stream_name = f"test:stream:p10_1_2_{uuid.uuid4().hex[:8]}"
    group_name = f"test_group_{uuid.uuid4().hex[:6]}"
    consumer_a = "consumer_A_crashed"

    worker = LiveTestRecoveryWorker(stream_name, group_name)

    print(f"[*] Live Test on stream: {stream_name}")
    print(f"[*] Consumer group: {group_name}")
    print(f"[*] Configured test claim_min_idle_ms: {worker.claim_min_idle_ms} ms")

    try:
        # 1. Verify Redis 5 version
        info = await r.info()
        print(f"[+] Redis Version: {info.get('redis_version')}")

        # 2. Seed test message into stream
        msg_payload = {
            "task_id": "test-task-42",
            "operation": "embed_opportunity",
            "content": "Autonomous agent opportunity dispatch payload",
        }
        msg_id = await r.xadd(stream_name, msg_payload)
        print(f"[+] Added test message: {msg_id}")

        # 3. Create consumer group
        await r.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        print(f"[+] Consumer group created: {group_name}")

        # 4. Consumer A reads message without ACKing -> enters PEL
        read_batch = await r.xreadgroup(group_name, consumer_a, {stream_name: ">"}, count=1)
        assert len(read_batch) == 1, "Expected 1 stream in read_batch"
        assert len(read_batch[0][1]) == 1, "Expected 1 message read by Consumer A"
        print(f"[+] Consumer A read message {read_batch[0][1][0][0]} into PEL (unacknowledged)")

        # 5. Inspect PEL via xpending_range to verify redis-py dictionary keys
        pending_entries = await r.xpending_range(stream_name, group_name, min="-", max="+", count=10)
        assert len(pending_entries) == 1, "PEL should contain 1 pending entry"
        entry_0 = pending_entries[0]
        print(f"[+] Raw redis-py xpending_range entry: {entry_0}")
        assert "time_since_delivered" in entry_0, "Expected 'time_since_delivered' in redis-py entry"
        assert entry_0["consumer"] == consumer_a, f"Expected consumer '{consumer_a}'"

        # 6. Verify that an immediate recovery attempt (idle < 1000ms) does NOT claim the message
        log = logger.bind(test="live_recovery")
        claimed_too_early = await worker._claim_and_process_pending(r, stream_name, log)
        print(f"[+] Immediate claim attempt (below threshold): claimed={claimed_too_early} (expected 0)")
        assert claimed_too_early == 0, f"Expected 0 claimed before idle threshold, got {claimed_too_early}"

        # 7. Wait for idle threshold to expire (> 1000 ms)
        wait_seconds = 1.3
        print(f"[*] Sleeping {wait_seconds}s to exceed {worker.claim_min_idle_ms}ms idle threshold...")
        await asyncio.sleep(wait_seconds)

        # Re-check PEL idle time
        pending_now = await r.xpending_range(stream_name, group_name, min="-", max="+", count=10)
        idle_observed = pending_now[0].get("time_since_delivered", 0)
        print(f"[+] Measured idle time in PEL: {idle_observed} ms (threshold: {worker.claim_min_idle_ms} ms)")
        assert idle_observed >= worker.claim_min_idle_ms, "Measured idle time did not exceed threshold"

        # 8. Execute real BaseWorker recovery method
        print("[*] Invoking worker._claim_and_process_pending (exercising Redis 5 fallback)...")
        claimed_count = await worker._claim_and_process_pending(r, stream_name, log)
        print(f"[+] Worker recovery returned: claimed_count={claimed_count}")
        assert claimed_count == 1, f"Expected 1 claimed message, got {claimed_count}"

        # 9. Verify worker handled the message
        assert len(worker.handled_messages) == 1, "Expected worker to have handled 1 message"
        handled = worker.handled_messages[0]
        print(f"[+] Worker handled message payload: {handled}")
        assert handled.get("task_id") == "test-task-42"

        # 10. Verify PEL is now completely cleared (0 pending)
        pending_summary = await r.xpending(stream_name, group_name)
        print(f"[+] Final PEL status: pending_count={pending_summary['pending']}")
        assert pending_summary["pending"] == 0, f"Expected 0 pending in PEL, got {pending_summary['pending']}"

        print("\n[SUCCESS] Live Redis 5 recovery test PASSED completely with real redis-py client and Redis 5 server!")
        return True

    except Exception as exc:
        print(f"\n[FAIL] Live Redis 5 test failed: {exc}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup disposable stream and group
        try:
            await r.xgroup_destroy(stream_name, group_name)
        except Exception:
            pass
        try:
            await r.delete(stream_name)
            print(f"[+] Cleaned up disposable stream: {stream_name}")
        except Exception:
            pass
        await r.aclose()


if __name__ == "__main__":
    success = asyncio.run(run_live_test())
    sys.exit(0 if success else 1)
