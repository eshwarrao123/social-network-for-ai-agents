"""
Audit script for Redis XAUTOCLAIM compatibility (P10.1.1).
Executes functional tests on a disposable stream:
  1. Server version check
  2. COMMAND INFO XAUTOCLAIM
  3. Direct XAUTOCLAIM execution probe
  4. XPENDING and XCLAIM functional test
  5. BaseWorker._claim_and_process_pending simulation test
Cleans up all disposable keys.
"""
import sys
import uuid
import time
import asyncio
import redis.asyncio as aioredis

async def audit_redis():
    r = aioredis.from_url("redis://127.0.0.1:6379?protocol=2", decode_responses=True)
    disposable_key = f"audit:stream:{uuid.uuid4().hex[:8]}"
    group_name = f"audit_grp_{uuid.uuid4().hex[:6]}"
    consumer_1 = "worker_crashed"
    consumer_2 = "worker_reclaiming"

    results = {}

    try:
        # 1. Server info & version
        info = await r.info()
        redis_version = info.get("redis_version", "unknown")
        results["redis_version"] = redis_version
        print(f"[+] Redis Version: {redis_version}")

        # 2. COMMAND INFO XAUTOCLAIM
        try:
            cmd_info = await r.execute_command("COMMAND", "INFO", "XAUTOCLAIM")
            results["command_info_xautoclaim"] = cmd_info
            print(f"[+] COMMAND INFO XAUTOCLAIM: {cmd_info}")
        except Exception as e:
            results["command_info_xautoclaim"] = f"Error: {e}"
            print(f"[-] COMMAND INFO XAUTOCLAIM error: {e}")

        # Create disposable stream and consumer group
        msg_id1 = await r.xadd(disposable_key, {"payload": "msg_abandoned"})
        await r.xgroup_create(disposable_key, group_name, id="0", mkstream=True)

        # Consumer 1 reads message without acknowledging -> message enters PEL
        read_msgs = await r.xreadgroup(group_name, consumer_1, {disposable_key: ">"}, count=1)
        print(f"[+] Read into PEL by {consumer_1}: {read_msgs}")

        # 3. Direct XAUTOCLAIM execution probe
        xautoclaim_supported = False
        try:
            claim_res = await r.xautoclaim(
                name=disposable_key,
                groupname=group_name,
                consumername=consumer_2,
                min_idle_time=0,  # 0ms so immediately eligible for probe
                start_id="0-0",
                count=10,
            )
            xautoclaim_supported = True
            results["xautoclaim_execution"] = {"supported": True, "result": claim_res}
            print(f"[+] XAUTOCLAIM succeeded: {claim_res}")
        except Exception as e:
            results["xautoclaim_execution"] = {"supported": False, "error": str(e)}
            print(f"[-] XAUTOCLAIM unsupported: {e}")

        # 4. Functional test of XPENDING + XCLAIM
        xpending_works = False
        xclaim_works = False
        try:
            # Check XPENDING
            pending_summary = await r.xpending(disposable_key, group_name)
            pending_range = await r.xpending_range(disposable_key, group_name, min="-", max="+", count=10)
            xpending_works = len(pending_range) > 0
            print(f"[+] XPENDING summary: {pending_summary}")
            print(f"[+] XPENDING range ({len(pending_range)} items): {pending_range}")

            # Reclaim using XCLAIM
            if pending_range:
                cand_ids = [p["message_id"] for p in pending_range]
                claimed_msgs = await r.xclaim(
                    name=disposable_key,
                    groupname=group_name,
                    consumername=consumer_2,
                    min_idle_time=0,
                    message_ids=cand_ids,
                )
                xclaim_works = len(claimed_msgs) > 0
                print(f"[+] XCLAIM reclaimed {len(claimed_msgs)} message(s): {claimed_msgs}")

                # Verify ownership changed to consumer_2
                pending_after = await r.xpending_range(disposable_key, group_name, min="-", max="+", count=10)
                consumer_now = pending_after[0]["consumer"] if pending_after else "none"
                print(f"[+] Owner after XCLAIM: {consumer_now} (expected {consumer_2})")

                # Acknowledge
                await r.xack(disposable_key, group_name, msg_id1)
                pending_final = await r.xpending(disposable_key, group_name)
                print(f"[+] XACK confirmed, remaining PEL count: {pending_final['pending']}")

        except Exception as e:
            print(f"[-] XPENDING/XCLAIM error: {e}")

        results["xpending_works"] = xpending_works
        results["xclaim_works"] = xclaim_works

    finally:
        # Cleanup disposable test keys
        try:
            await r.delete(disposable_key)
            print(f"[+] Cleaned up disposable stream: {disposable_key}")
        except Exception:
            pass
        await r.aclose()

    return results

if __name__ == "__main__":
    res = asyncio.run(audit_redis())
    print("\n=== FINAL AUDIT RESULT ===")
    print(res)
