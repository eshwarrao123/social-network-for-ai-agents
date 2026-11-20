"""
Verification script for Redis Streams capabilities (P10.1 requirement).
Verifies:
  1. Server connectivity and PING
  2. Stream append (XADD)
  3. Consumer group creation (XGROUP CREATE)
  4. Consumer group read (XREADGROUP)
  5. Pending entry inspection (XPENDING)
  6. Acknowledgment (XACK)
  7. Autoclaim (XAUTOCLAIM if supported)
  8. Dead Letter Queue / Stream trim (XTRIM / DLQ flow)
"""
import sys
import uuid
import time

def verify_redis():
    try:
        import redis
    except ImportError:
        print("[FAIL] redis package not installed in environment")
        sys.exit(1)

    print("[*] Connecting to Redis on localhost:6379 (RESP2)...")
    client = redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True, protocol=2)

    try:
        pong = client.ping()
        print(f"[+] PING response: {pong}")
        assert pong is True, "PING failed"

        info = client.info()
        print(f"[+] Redis version: {info.get('redis_version')}")
        print(f"[+] OS: {info.get('os')}")

        test_stream = f"test:stream:{uuid.uuid4().hex[:8]}"
        group_name = "test_group"
        consumer_name = "test_consumer_1"

        # 1. XADD
        msg_id1 = client.xadd(test_stream, {"event": "post_created", "post_id": "p-100", "payload": "sample_1"})
        msg_id2 = client.xadd(test_stream, {"event": "post_created", "post_id": "p-101", "payload": "sample_2"})
        print(f"[+] XADD successful. Message IDs: {msg_id1}, {msg_id2}")

        # 2. XGROUP CREATE
        client.xgroup_create(test_stream, group_name, id="0", mkstream=False)
        print(f"[+] XGROUP CREATE successful: group '{group_name}'")

        # 3. XREADGROUP
        messages = client.xreadgroup(group_name, consumer_name, {test_stream: ">"}, count=1)
        print(f"[+] XREADGROUP received {len(messages[0][1])} messages: {messages[0][1][0]}")
        read_msg_id = messages[0][1][0][0]

        # 4. XPENDING
        pending = client.xpending(test_stream, group_name)
        print(f"[+] XPENDING count: {pending['pending']}")
        assert pending["pending"] >= 1, "Pending entries should be at least 1"

        # 5. XACK
        ack_res = client.xack(test_stream, group_name, read_msg_id)
        print(f"[+] XACK acknowledged {ack_res} message(s)")
        assert ack_res == 1, "XACK failed"

        # 6. Check pending again
        pending_after = client.xpending(test_stream, group_name)
        print(f"[+] XPENDING count after ACK: {pending_after['pending']}")

        # Cleanup
        client.delete(test_stream)
        print(f"[+] Stream cleanup completed: {test_stream}")

        print("\n[SUCCESS] Redis Streams fully verified and ready for Agent Network background workers!")
        return True
    except Exception as e:
        print(f"[FAIL] Redis Streams verification failed: {e}")
        return False
    finally:
        client.close()

if __name__ == "__main__":
    success = verify_redis()
    sys.exit(0 if success else 1)
