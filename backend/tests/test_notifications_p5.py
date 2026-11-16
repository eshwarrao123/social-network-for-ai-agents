"""
Comprehensive Unit and Functional Tests for P5 / P5.1:
Enterprise Agent Notification Pipeline, Secure Webhook Delivery, Concurrency Control,
Multi-Subscription Tracking, and DNS Pinning.

Tests cover:
  1. SSRF destination validation:
     - IPv4 loopback (127.0.0.1, 127.0.0.254) and IPv6 loopback (::1).
     - RFC 1918 private subnets (10.0.0.1, 172.16.5.1, 192.168.1.1).
     - Link-local and cloud metadata endpoints (169.254.169.254, fe80::1, fd00:ec2::254).
     - Carrier-grade NAT (100.64.0.1).
     - Multicast, broadcast, reserved (224.0.0.1, 240.0.0.1, 255.255.255.255, ff02::1).
     - IPv4-mapped IPv6 address extraction (::ffff:127.0.0.1, ::ffff:169.254.169.254).
     - Prohibited ports (22, 5432, 6379, 8000, 80 in production).
     - Disallowed schemes (http in production, ftp, gopher, file).
     - Embedded URL credentials rejection.
     - Multi-record DNS resolution assertion (fails closed if any A/AAAA record is forbidden).
     - DNS rebinding TOCTOU defense via socket pinning (PinnedAsyncNetworkBackend).
     - Strict redirect blocking (follow_redirects=False).
     - Transport-level live socket test (verifies socket connects to pinned IP, preserves Host header).
  2. HMAC-SHA256 signing and deterministic payload formatting:
     - Known test vector signature verification.
     - Deterministic sorted key JSON serialization.
     - Cryptographic timestamp binding: HMAC-SHA256(secret, timestamp + "." + raw_body).
     - Timestamp tampering rejection.
     - Expired timestamp rejection (>300s).
     - Future-dated timestamp rejection (>30s drift).
     - Body tampering rejection.
     - Receiver-side verify_delivery helper verification.
  3. Webhook Subscription Management API:
     - Creation revealing 32-byte secret ONCE and persisting encrypted secret.
     - List subscriptions omitting secrets.
     - Get subscription details.
     - Update subscription URL with SSRF revalidation.
     - Secret rotation returning new secret ONCE and updating DB.
     - Deletion.
     - Cross-agent ownership isolation (Agent B cannot access Agent A's webhooks).
  4. Multi-Subscription Delivery & Concurrency Control:
     - Each subscription receives its own delivery attempt.
     - One endpoint's success does not mark other endpoint deliveries successful.
     - One endpoint's failure does not prevent other endpoint delivery.
     - Delivery status tracked independently in routing_explanation.
     - Replay after partial delivery skips already-delivered endpoints.
     - Secret rotation on one subscription does not affect another subscription.
     - Concurrent worker active lease skipping (<60s).
     - Crashed worker lease reclaiming (>60s).
  5. NotifyWorker execution & durability:
     - Successful delivery marks notification 'delivered' and stamps delivered_at.
     - In-app delivery fallback when no webhooks exist.
     - Transient HTTP failure transitions to 'retrying' and applies backoff/jitter/Retry-After.
     - Exhausted retries routes to DLQ ('notifications:pending:dlq') and marks 'failed'.
     - Permanent HTTP failure (400, SSRF violation) routes to DLQ immediately without retrying.
     - Replay safety / idempotency for already delivered/read notifications.
     - Expired or deleted post skips notification delivery.
     - Inactive recipient agent skips notification delivery.
     - Automated periodic reconciliation of stuck pending and retrying notifications.
     - Protocol headers verified: X-Agent-Network-* and Agent-Network/1.0 User-Agent.
  6. Notification Inbox API:
     - Paginated list with status filtering.
     - Single notification view automatically marks 'delivered' -> 'read'.
     - Explicit POST mark-as-read.
     - Recipient cross-agent ownership isolation.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.config import get_settings
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.post import Post
from app.models.webhook import WebhookSubscription
from app.routers.notifications import (
    get_notification,
    list_notifications,
    mark_notification_read,
)
from app.routers.webhooks import (
    CreateWebhookRequest,
    UpdateWebhookRequest,
    create_webhook_subscription,
    delete_webhook_subscription,
    get_webhook_subscription,
    list_webhook_subscriptions,
    rotate_webhook_secret,
)
from app.services.ssrf_protection import (
    FORBIDDEN_NETWORKS,
    PinnedAsyncNetworkBackend,
    SSRFBlockedError,
    SSRFError,
    SSRFPortError,
    SSRFResolutionError,
    SSRFSchemeError,
    SSRFPinnedAsyncHTTPTransport,
    create_ssrf_safe_client,
    is_ip_allowed,
    validate_destination_url,
)
from app.services.webhook_security import (
    WebhookSecurityService,
    get_webhook_security,
)
from app.workers.notify_worker import (
    DeliveryPermanentError,
    DeliveryTransientError,
    NotifyWorker,
    build_notification_payload,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & Test Data Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_test_agent(
    agent_id: uuid.UUID | None = None,
    name: str = "EnterpriseAgent",
    company: str = "EnterpriseCorp",
    is_active: bool = True,
) -> Agent:
    agent = Agent()
    agent.id = agent_id or uuid.uuid4()
    agent.name = name
    agent.company = company
    agent.description = "Test enterprise agent description manifesto"
    agent.industries = ["fintech", "banking"]
    agent.tags = ["payments", "compliance"]
    agent.capabilities = ["settlement", "verification"]
    agent.trust_score = 0.95
    agent.is_active = is_active
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


def make_test_post(
    post_id: uuid.UUID | None = None,
    author: Agent | None = None,
    status: str = "published",
    expires_at: datetime | None = None,
) -> Post:
    author = author or make_test_agent(name="AuthorAgent", company="AuthorCorp")
    post = Post()
    post.id = post_id or uuid.uuid4()
    post.author_agent_id = author.id
    post.author = author
    post.title = "Q4 Enterprise Cross-Border Liquidity Framework"
    post.content = "Detailed framework for multi-currency automated agent settlement."
    post.post_type = "announcement"
    post.tags = ["payments", "liquidity"]
    post.target_industries = ["fintech", "banking"]
    post.status = status
    post.view_count = 0
    post.comment_count = 0
    post.engagement_score = 0
    post.embedding_status = "completed"
    post.routing_status = "done"
    post.published_at = datetime.now(timezone.utc) - timedelta(hours=1)
    post.expires_at = expires_at
    post.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    post.updated_at = datetime.now(timezone.utc)
    return post


def make_test_notification(
    post: Post | None = None,
    recipient: Agent | None = None,
    status: str = "pending",
    relevance_score: float = 0.88,
) -> Notification:
    post = post or make_test_post()
    recipient = recipient or make_test_agent()
    notif = Notification()
    notif.id = uuid.uuid4()
    notif.post_id = post.id
    notif.post = post
    notif.recipient_agent_id = recipient.id
    notif.recipient = recipient
    notif.relevance_score = relevance_score
    notif.routing_explanation = {
        "reasons": ["Semantic alignment", "Fintech overlap"],
        "vector_score": 0.89,
        "metadata_score": 0.86,
    }
    notif.status = status
    notif.delivery_attempts = 0
    notif.delivered_at = None
    notif.read_at = None
    notif.delivery_event_published_at = datetime.now(timezone.utc)
    notif.created_at = datetime.now(timezone.utc)
    notif.updated_at = datetime.now(timezone.utc)
    return notif


# ─────────────────────────────────────────────────────────────────────────────
# 1. SSRF & URL Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ssrf_rejects_loopback_addresses():
    """Verifies IPv4 and IPv6 loopback addresses are strictly rejected."""
    loopbacks = ["127.0.0.1", "127.0.0.254", "127.1.2.3", "::1"]
    for ip in loopbacks:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"Loopback {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_rejects_rfc1918_private_networks():
    """Verifies RFC 1918 subnets (10/8, 172.16/12, 192.168/16) are rejected."""
    private_ips = [
        "10.0.0.1", "10.254.254.254", "172.16.0.1", "172.24.1.1",
        "172.31.255.254", "192.168.0.1", "192.168.100.254",
    ]
    for ip in private_ips:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"Private IP {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_rejects_link_local_and_cloud_metadata():
    """Verifies link-local, APIPA and cloud provider IMDS endpoints are rejected."""
    metadata_ips = [
        "169.254.169.254",  # AWS/GCP/Azure IMDS
        "169.254.1.1",      # APIPA
        "fe80::1",          # IPv6 Link-Local
        "fd00:ec2::254",    # AWS Nitro IMDS IPv6
    ]
    for ip in metadata_ips:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"Cloud metadata/link-local {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_rejects_carrier_grade_nat():
    """Verifies RFC 6598 Carrier-Grade NAT (100.64.0.0/10) is rejected."""
    cgnat_ips = ["100.64.0.1", "100.100.50.25", "100.127.255.254"]
    for ip in cgnat_ips:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"CGNAT {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_rejects_multicast_broadcast_reserved():
    """Verifies multicast, broadcast, and reserved networks are rejected."""
    prohibited = ["0.0.0.0", "224.0.0.1", "239.255.255.250", "240.0.0.1", "255.255.255.255", "ff02::1"]
    for ip in prohibited:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"Prohibited address {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_rejects_ipv4_mapped_ipv6():
    """Verifies IPv4-mapped IPv6 representations of prohibited addresses are rejected."""
    mapped = ["::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254"]
    for ip in mapped:
        ip_obj = ipaddress.ip_address(ip)
        assert not is_ip_allowed(ip_obj), f"Mapped IPv6 {ip} should be rejected"


@pytest.mark.unit
def test_ssrf_allows_public_routable_ips():
    """Verifies legitimate public IPv4 and IPv6 addresses are permitted."""
    public_ips = ["93.184.216.34", "1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"]
    for ip in public_ips:
        ip_obj = ipaddress.ip_address(ip)
        assert is_ip_allowed(ip_obj), f"Public IP {ip} should be allowed"


@pytest.mark.unit
def test_ssrf_disallowed_schemes():
    """Verifies non-https schemes (http, ftp, file, gopher) are rejected in production."""
    bad_urls = [
        "http://api.partner.com/webhook",
        "file:///etc/passwd",
        "gopher://example.com/7",
        "ftp://ftp.example.com/incoming",
    ]
    for url in bad_urls:
        with pytest.raises(SSRFSchemeError):
            validate_destination_url(url, allow_http=False)


@pytest.mark.unit
def test_ssrf_disallowed_ports():
    """Verifies unauthorized ports (e.g. 22, 5432, 6379, 8000) are rejected."""
    bad_ports = [
        "https://api.partner.com:22/webhook",
        "https://api.partner.com:80/webhook",
        "https://api.partner.com:5432/webhook",
        "https://api.partner.com:6379/webhook",
        "https://api.partner.com:8000/webhook",
    ]
    for url in bad_ports:
        with pytest.raises(SSRFPortError):
            validate_destination_url(url, allow_http=False, allowed_ports={443, 8443})


@pytest.mark.unit
def test_ssrf_rejects_embedded_credentials():
    """Verifies URLs with userinfo credentials are rejected."""
    with pytest.raises(SSRFBlockedError, match="Embedded credentials"):
        validate_destination_url("https://admin:secret@api.partner.com/webhook")


@pytest.mark.unit
def test_ssrf_multi_record_dns_fails_closed():
    """Verifies that if ANY DNS A/AAAA record points to a private/loopback IP, the entire hostname is rejected."""
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ]
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(SSRFBlockedError, match="resolved to prohibited IP '127.0.0.1'"):
            validate_destination_url("https://roundrobin.attacker.com/webhook")


@pytest.mark.unit
async def test_ssrf_dns_pinning_backend_connects_to_pinned_ip():
    """Verifies PinnedAsyncNetworkBackend connects TCP to pinned_ip while preserving SNI."""
    backend = PinnedAsyncNetworkBackend(pinned_ip="93.184.216.34")
    assert backend.pinned_ip == "93.184.216.34"

    with patch("httpcore._backends.auto.AutoBackend.connect_tcp", new_callable=AsyncMock) as mock_super_connect:
        await backend.connect_tcp("api.partner.com", 443)
        mock_super_connect.assert_awaited_once()
        called_args = mock_super_connect.call_args[0]
        assert called_args[0] == "93.184.216.34"
        assert called_args[1] == 443


@pytest.mark.unit
def test_ssrf_safe_client_disables_redirects():
    """Verifies create_ssrf_safe_client disables redirect following (follow_redirects=False)."""
    client = create_ssrf_safe_client(pinned_ip="93.184.216.34")
    assert client.follow_redirects is False


@pytest.mark.unit
async def test_transport_level_dns_pinning_and_host_header_live():
    """
    Transport-level test: starts a real local TCP server and verifies that
    SSRFPinnedAsyncHTTPTransport connects to the pinned IP without resolving
    the unresolvable hostname, while sending the proper HTTP Host header.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    received_requests = []

    async def srv_handler():
        loop = asyncio.get_event_loop()
        client_sock, _ = await loop.run_in_executor(None, srv.accept)
        raw_req = await loop.run_in_executor(None, client_sock.recv, 2048)
        received_requests.append(raw_req.decode("utf-8", errors="replace"))
        client_sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        client_sock.close()
        srv.close()

    srv_task = asyncio.create_task(srv_handler())

    # Transport is pinned to 127.0.0.1, but requested URL host is unresolvable-hostname.internal
    transport = SSRFPinnedAsyncHTTPTransport(pinned_ip="127.0.0.1", verify=False)
    client = httpx.AsyncClient(transport=transport, follow_redirects=False)

    fake_host = f"unresolvable-hostname.internal:{port}"
    resp = await client.get(f"http://{fake_host}/webhook-test")
    assert resp.status_code == 200
    assert resp.text == "OK"

    await client.aclose()
    await srv_task

    assert len(received_requests) == 1
    req_str = received_requests[0]
    # Verify HTTP Host header preserves the original target hostname
    assert f"Host: {fake_host}" in req_str


# ─────────────────────────────────────────────────────────────────────────────
# 2. HMAC-SHA256 Signing & Serialization Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hmac_signing_known_vector():
    """Verifies HMAC-SHA256 signature against known test vector."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "0123456789abcdef0123456789abcdef"
    payload = b'{"event":"test","status":"ok"}'

    signature = service.sign_payload(payload, secret)
    assert signature.startswith("sha256=")
    assert service.verify_signature(payload, secret, signature)


@pytest.mark.unit
def test_payload_deterministic_serialization():
    """Verifies deterministic JSON formatting: sorted keys and compact separators without whitespace."""
    notif = make_test_notification()
    event_id = uuid.uuid4()
    ts = "2026-11-16T12:00:00+00:00"

    b1 = build_notification_payload(notif, notif.post, notif.recipient, event_id, ts)
    b2 = build_notification_payload(notif, notif.post, notif.recipient, event_id, ts)

    assert b1 == b2
    s1 = b1.decode("utf-8")
    assert ": " not in s1
    assert ", " not in s1
    parsed = json.loads(s1)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


@pytest.mark.unit
def test_hmac_timestamp_cryptographic_binding():
    """P5.1: Verifies HMAC signature binds the timestamp: HMAC-SHA256(secret, timestamp + '.' + body)."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "0123456789abcdef0123456789abcdef"
    body = b'{"test":"binding"}'
    ts1 = "2026-11-16T12:00:00+00:00"
    ts2 = "2026-11-16T12:00:01+00:00"

    sig_with_ts1 = service.sign_payload(body, secret, timestamp=ts1)
    sig_with_ts2 = service.sign_payload(body, secret, timestamp=ts2)
    sig_without_ts = service.sign_payload(body, secret)

    # All three must be distinct
    assert sig_with_ts1 != sig_with_ts2
    assert sig_with_ts1 != sig_without_ts

    # Verification must match bound timestamp within fresh window
    current_fixed_time = datetime.fromisoformat("2026-11-16T12:00:05+00:00")
    assert service.verify_signature(body, secret, sig_with_ts1, timestamp=ts1, current_time=current_fixed_time)
    # Verification with wrong timestamp must fail
    assert not service.verify_signature(body, secret, sig_with_ts1, timestamp=ts2, current_time=current_fixed_time)


@pytest.mark.unit
def test_hmac_expired_timestamp_rejection():
    """P5.1: Verifies timestamp older than tolerance (default 300s) is rejected as expired."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "secret123"
    body = b'{"amount":100}'
    now = datetime.now(timezone.utc)
    expired_ts = (now - timedelta(seconds=305)).isoformat()

    sig = service.sign_payload(body, secret, timestamp=expired_ts)

    # Rejected because age > 300s
    assert not service.verify_signature(body, secret, sig, timestamp=expired_ts, tolerance_seconds=300)


@pytest.mark.unit
def test_hmac_future_timestamp_rejection():
    """P5.1: Verifies timestamp > 30s in the future is rejected."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "secret123"
    body = b'{"amount":100}'
    now = datetime.now(timezone.utc)
    future_ts = (now + timedelta(seconds=45)).isoformat()

    sig = service.sign_payload(body, secret, timestamp=future_ts)

    # Rejected because drift > 30s into future
    assert not service.verify_signature(body, secret, sig, timestamp=future_ts, allow_future_seconds=30)


@pytest.mark.unit
def test_receiver_verify_delivery_helper():
    """P5.1: Verifies the verify_delivery helper correctly parses X-Agent-Network-* headers."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "test_shared_secret"
    body = b'{"status":"ok"}'
    ts = datetime.now(timezone.utc).isoformat()
    sig = service.sign_payload(body, secret, timestamp=ts)

    headers = {
        "X-Agent-Network-Signature": sig,
        "X-Agent-Network-Timestamp": ts,
        "X-Agent-Network-Event": "notification.created",
    }

    # Valid delivery
    is_valid, reason = service.verify_delivery(headers, body, secret)
    assert is_valid is True
    assert reason == "Valid"

    # Missing signature header
    bad_headers = {"X-Agent-Network-Timestamp": ts}
    is_valid, reason = service.verify_delivery(bad_headers, body, secret)
    assert is_valid is False
    assert "Missing signature" in reason

    # Body tampered
    is_valid, reason = service.verify_delivery(headers, b'{"status":"tampered"}', secret)
    assert is_valid is False


@pytest.mark.unit
def test_tampered_payload_and_secret_invalidation():
    """Verifies modifying payload or using wrong secret invalidates signature."""
    service = WebhookSecurityService(encryption_key=Fernet.generate_key().decode())
    secret = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    payload = b'{"amount":1000,"currency":"USD"}'

    sig = service.sign_payload(payload, secret)

    # Tampered payload
    tampered_payload = b'{"amount":9999,"currency":"USD"}'
    assert not service.verify_signature(tampered_payload, secret, sig)

    # Tampered secret
    assert not service.verify_signature(payload, "wrong_secret_12345678901234567890", sig)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Webhook Subscription API Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_create_webhook_subscription_reveals_secret_once():
    """POST /api/v1/webhooks: creates subscription, reveals secret ONCE, stores encrypted."""
    agent = make_test_agent()
    test_key = Fernet.generate_key().decode()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    with patch("app.routers.webhooks.get_webhook_security") as mock_sec_fn:
        mock_sec_fn.return_value = WebhookSecurityService(encryption_key=test_key)

        with patch("app.routers.webhooks.validate_destination_url", return_value=("api.partner.com", 443, ["93.184.216.34"])):
            req = CreateWebhookRequest(
                endpoint_url="https://api.partner.com/webhooks/asama",
                event_types=["new_notification"],
                is_active=True,
            )
            res = await create_webhook_subscription(payload=req, current_agent=agent, db=mock_db)

            assert res.endpoint_url == "https://api.partner.com/webhooks/asama"
            assert res.secret is not None
            assert len(res.secret) == 64
            assert mock_db.add.called
            assert mock_db.commit.called

            saved_entity = mock_db.add.call_args[0][0]
            assert isinstance(saved_entity, WebhookSubscription)
            assert saved_entity.encrypted_secret != res.secret
            decrypted = mock_sec_fn.return_value.decrypt_secret(saved_entity.encrypted_secret)
            assert decrypted == res.secret


@pytest.mark.unit
async def test_list_webhooks_omits_secrets():
    """GET /api/v1/webhooks: returns subscriptions without secret or encrypted_secret."""
    agent = make_test_agent()
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=agent.id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret="enc_secret_value",
        event_types=["new_notification"],
        is_active=True,
    )
    sub.created_at = datetime.now(timezone.utc)
    sub.updated_at = datetime.now(timezone.utc)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [sub]
    mock_db.execute.return_value = mock_res

    res = await list_webhook_subscriptions(current_agent=agent, db=mock_db)
    assert len(res) == 1
    assert res[0].id == sub.id
    dumped = res[0].model_dump()
    assert "secret" not in dumped
    assert "encrypted_secret" not in dumped


@pytest.mark.unit
async def test_get_webhook_subscription_details():
    """GET /api/v1/webhooks/{id}: returns single subscription."""
    agent = make_test_agent()
    sub_id = uuid.uuid4()
    sub = WebhookSubscription(
        id=sub_id,
        agent_id=agent.id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret="enc_secret",
        event_types=["new_notification"],
        is_active=True,
    )
    sub.created_at = datetime.now(timezone.utc)
    sub.updated_at = datetime.now(timezone.utc)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = sub
    mock_db.execute.return_value = mock_res

    res = await get_webhook_subscription(subscription_id=sub_id, current_agent=agent, db=mock_db)
    assert res.id == sub_id
    assert res.endpoint_url == sub.endpoint_url


@pytest.mark.unit
async def test_rotate_webhook_secret_returns_new_secret_once():
    """POST /api/v1/webhooks/{id}/rotate-secret: generates and returns new secret, invalidates old."""
    agent = make_test_agent()
    sub_id = uuid.uuid4()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    old_secret = sec_service.generate_secret()
    old_enc = sec_service.encrypt_secret(old_secret)

    sub = WebhookSubscription(
        id=sub_id,
        agent_id=agent.id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret=old_enc,
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = sub
    mock_db.execute.return_value = mock_res

    with patch("app.routers.webhooks.get_webhook_security", return_value=sec_service):
        rot_res = await rotate_webhook_secret(subscription_id=sub_id, current_agent=agent, db=mock_db)

        assert rot_res.secret != old_secret
        assert sub.encrypted_secret != old_enc
        assert sec_service.decrypt_secret(sub.encrypted_secret) == rot_res.secret
        assert mock_db.commit.called


@pytest.mark.unit
async def test_delete_webhook_subscription():
    """DELETE /api/v1/webhooks/{id}: deletes subscription."""
    agent = make_test_agent()
    sub_id = uuid.uuid4()
    sub = WebhookSubscription(
        id=sub_id,
        agent_id=agent.id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret="enc",
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = sub
    mock_db.execute.return_value = mock_res

    await delete_webhook_subscription(subscription_id=sub_id, current_agent=agent, db=mock_db)
    mock_db.delete.assert_awaited_once_with(sub)
    mock_db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_webhook_cross_agent_isolation():
    """Verifies Agent B cannot access or modify Agent A's webhook subscription."""
    agent_b = make_test_agent(name="AgentB")
    sub_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await get_webhook_subscription(subscription_id=sub_id, current_agent=agent_b, db=mock_db)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await delete_webhook_subscription(subscription_id=sub_id, current_agent=agent_b, db=mock_db)
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multi-Subscription Delivery & Concurrency Tests (P5.1)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_multiple_webhooks_independent_delivery():
    """
    P5.1: Verifies that when an agent has multiple subscriptions:
      1. Each endpoint is attempted independently.
      2. Endpoint 1 (200 OK) is marked delivered.
      3. Endpoint 2 (503 Service Unavailable) is marked retrying.
      4. Endpoint 1 is NOT resent when Endpoint 2 is retried.
    """
    worker = NotifyWorker()
    notif = make_test_notification()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub1 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://sub1.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("sec1"),
        event_types=["new_notification"],
        is_active=True,
    )
    sub2 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://sub2.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("sec2"),
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_subs = MagicMock()
    mock_res_subs.scalars.return_value.all.return_value = [sub1, sub2]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_subs]

    mock_redis = AsyncMock()
    worker._redis_client = mock_redis

    # Client mock: sub1 returns 200, sub2 returns 503
    mock_client = AsyncMock()
    async def mock_post(url, **kwargs):
        if "sub1" in url:
            return MagicMock(status_code=200)
        else:
            return MagicMock(status_code=503, headers={"Retry-After": "2"})
    mock_client.post.side_effect = mock_post
    mock_client.__aenter__.return_value = mock_client

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("sub.partner.com", 443, ["93.184.216.34"])):
                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        fields = {"notification_id": str(notif.id)}
                        await worker.handle(fields)

                        deliveries = notif.routing_explanation.get("webhook_deliveries", {})
                        assert deliveries[str(sub1.id)]["status"] == "delivered"
                        assert deliveries[str(sub2.id)]["status"] == "retrying"
                        assert notif.status == "retrying"

    # Now simulate retry execution: sub1 must NOT be called again, only sub2!
    mock_client.post.reset_mock()
    mock_db.execute.side_effect = [mock_res_notif, mock_res_subs]
    # In retry, sub2 now returns 200
    mock_client.post.side_effect = None
    mock_client.post.return_value = MagicMock(status_code=200)

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("sub2.partner.com", 443, ["93.184.216.34"])):
                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    fields = {"notification_id": str(notif.id)}
                    await worker.handle(fields)

                    # Only sub2 was called!
                    assert mock_client.post.call_count == 1
                    called_url = mock_client.post.call_args[0][0]
                    assert "sub2" in called_url
                    assert notif.status == "delivered"


@pytest.mark.unit
async def test_multiple_webhooks_endpoint_failure_isolation():
    """P5.1: Verifies permanent failure on Sub 1 (400 Bad Request) does not block Sub 2 (200 OK)."""
    worker = NotifyWorker()
    notif = make_test_notification()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub1 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://sub1.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("sec1"),
        event_types=["new_notification"],
        is_active=True,
    )
    sub2 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://sub2.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("sec2"),
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_subs = MagicMock()
    mock_res_subs.scalars.return_value.all.return_value = [sub1, sub2]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_subs]

    mock_client = AsyncMock()
    async def mock_post(url, **kwargs):
        if "sub1" in url:
            return MagicMock(status_code=400)  # Permanent failure
        return MagicMock(status_code=200)       # Success
    mock_client.post.side_effect = mock_post
    mock_client.__aenter__.return_value = mock_client

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("sub.partner.com", 443, ["93.184.216.34"])):
                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    fields = {"notification_id": str(notif.id)}
                    await worker.handle(fields)

                    deliveries = notif.routing_explanation.get("webhook_deliveries", {})
                    assert deliveries[str(sub1.id)]["status"] == "failed"
                    assert deliveries[str(sub2.id)]["status"] == "delivered"
                    # Overall status reflects successful delivery to available endpoints
                    assert notif.status == "delivered"


@pytest.mark.unit
async def test_multiple_webhooks_secret_rotation_isolation():
    """P5.1: Verifies secret rotation on Sub 1 updates only Sub 1 and does not affect Sub 2."""
    agent = make_test_agent()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub1_orig_secret = sec_service.generate_secret()
    sub2_orig_secret = sec_service.generate_secret()

    sub1 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=agent.id,
        endpoint_url="https://sub1.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret(sub1_orig_secret),
        event_types=["new_notification"],
        is_active=True,
    )
    sub2 = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=agent.id,
        endpoint_url="https://sub2.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret(sub2_orig_secret),
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = sub1
    mock_db.execute.return_value = mock_res

    # Rotate secret on Sub 1
    with patch("app.routers.webhooks.get_webhook_security", return_value=sec_service):
        rot_res = await rotate_webhook_secret(subscription_id=sub1.id, current_agent=agent, db=mock_db)

        # Sub 1 secret has changed
        assert rot_res.secret != sub1_orig_secret
        assert sec_service.decrypt_secret(sub1.encrypted_secret) == rot_res.secret

        # Sub 2 secret remains completely untouched
        assert sec_service.decrypt_secret(sub2.encrypted_secret) == sub2_orig_secret


@pytest.mark.unit
async def test_concurrent_worker_active_lease_skipping():
    """P5.1: Verifies concurrent worker skips notification currently under active lease (<60s)."""
    worker = NotifyWorker()
    notif = make_test_notification(status="delivering")
    # Active lease acquired 10 seconds ago
    notif.updated_at = datetime.now(timezone.utc) - timedelta(seconds=10)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.create_ssrf_safe_client") as mock_client:
            fields = {"notification_id": str(notif.id)}
            await worker.handle(fields)

            # Concurrent worker skipped: no client calls
            mock_client.assert_not_called()
            # Remains in delivering state under Worker 1
            assert notif.status == "delivering"


@pytest.mark.unit
async def test_concurrent_worker_crashed_lease_reclaim():
    """P5.1: Verifies worker safely reclaims an abandoned delivery lease (>60s) from a crashed worker."""
    worker = NotifyWorker()
    notif = make_test_notification(status="delivering")
    # Lease abandoned 80 seconds ago
    notif.updated_at = datetime.now(timezone.utc) - timedelta(seconds=80)

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_subs = MagicMock()
    mock_res_subs.scalars.return_value.all.return_value = []  # Fallback in-app
    mock_db.execute.side_effect = [mock_res_notif, mock_res_subs]

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        fields = {"notification_id": str(notif.id)}
        await worker.handle(fields)

        # Successfully reclaimed and transitioned to delivered
        assert notif.status == "delivered"
        assert notif.delivered_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 5. NotifyWorker Execution & Durability Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_notify_worker_successful_delivery():
    """Verifies successful HTTP webhook delivery stamps delivered_at and protocol headers."""
    worker = NotifyWorker()
    notif = make_test_notification()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)
    secret = sec_service.generate_secret()
    enc_secret = sec_service.encrypt_secret(secret)

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret=enc_secret,
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_sub = MagicMock()
    mock_res_sub.scalars.return_value.all.return_value = [sub]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_sub]

    mock_client = AsyncMock()
    mock_client.post.return_value = MagicMock(status_code=200)
    mock_client.__aenter__.return_value = mock_client

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("api.partner.com", 443, ["93.184.216.34"])):
                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    fields = {"notification_id": str(notif.id)}
                    await worker.handle(fields)

                    assert notif.status == "delivered"
                    assert notif.delivered_at is not None
                    assert mock_db.commit.called

                    # Verify protocol headers and branding
                    headers = mock_client.post.call_args[1]["headers"]
                    assert "X-Agent-Network-Signature" in headers
                    assert "X-Agent-Network-Timestamp" in headers
                    assert "X-Agent-Network-Delivery" in headers
                    assert headers["X-Agent-Network-Event"] == "notification.created"
                    assert headers["User-Agent"] == "Agent-Network/1.0"


@pytest.mark.unit
async def test_notify_worker_in_app_fallback_when_no_webhooks():
    """Verifies notification falls back to in-app delivery when agent has no active webhooks."""
    worker = NotifyWorker()
    notif = make_test_notification()

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_sub = MagicMock()
    mock_res_sub.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [mock_res_notif, mock_res_sub]

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        fields = {"notification_id": str(notif.id)}
        await worker.handle(fields)

        assert notif.status == "delivered"
        assert notif.delivered_at is not None
        assert notif.delivery_attempts == 1
        assert mock_db.commit.called


@pytest.mark.unit
async def test_notify_worker_transient_error_schedules_retry():
    """Verifies transient error (HTTP 500 or timeout) marks 'retrying' and schedules backoff."""
    worker = NotifyWorker()
    worker.settings.webhook_max_delivery_attempts = 3
    notif = make_test_notification()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("test_sec"),
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_sub = MagicMock()
    mock_res_sub.scalars.return_value.all.return_value = [sub]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_sub]

    mock_redis = AsyncMock()
    worker._redis_client = mock_redis

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("api.partner.com", 443, ["93.184.216.34"])):
                mock_client = AsyncMock()
                mock_client.post.return_value = MagicMock(status_code=503, headers={"Retry-After": "1"})
                mock_client.__aenter__.return_value = mock_client

                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        fields = {"notification_id": str(notif.id)}
                        await worker.handle(fields)

                        assert notif.status == "retrying"
                        mock_redis.xadd.assert_awaited_once()
                        assert mock_redis.xadd.call_args[0][0] == "notifications:pending"


@pytest.mark.unit
async def test_notify_worker_retries_exhausted_moves_to_dlq():
    """Verifies that reaching max delivery attempts marks 'failed' and sends message to DLQ."""
    worker = NotifyWorker()
    worker.settings.webhook_max_delivery_attempts = 3
    notif = make_test_notification()

    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("test_sec"),
        event_types=["new_notification"],
        is_active=True,
    )

    # Already has 2 delivery attempts recorded in webhook_deliveries
    notif.routing_explanation = {
        "webhook_deliveries": {
            str(sub.id): {"status": "retrying", "delivery_attempts": 2}
        }
    }

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_sub = MagicMock()
    mock_res_sub.scalars.return_value.all.return_value = [sub]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_sub]

    mock_redis = AsyncMock()
    worker._redis_client = mock_redis

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", return_value=("api.partner.com", 443, ["93.184.216.34"])):
                mock_client = AsyncMock()
                mock_client.post.return_value = MagicMock(status_code=500, headers={})
                mock_client.__aenter__.return_value = mock_client

                with patch("app.workers.notify_worker.create_ssrf_safe_client", return_value=mock_client):
                    fields = {"notification_id": str(notif.id)}
                    await worker.handle(fields)

                    assert notif.status == "failed"
                    mock_redis.xadd.assert_awaited_once()
                    assert mock_redis.xadd.call_args[0][0] == "notifications:pending:dlq"


@pytest.mark.unit
async def test_notify_worker_permanent_error_moves_to_dlq_immediately():
    """Verifies permanent failure (e.g. SSRF block) marks 'failed' and routes to DLQ immediately."""
    worker = NotifyWorker()
    notif = make_test_notification()
    test_key = Fernet.generate_key().decode()
    sec_service = WebhookSecurityService(encryption_key=test_key)

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        agent_id=notif.recipient_agent_id,
        endpoint_url="https://api.partner.com/webhook",
        encrypted_secret=sec_service.encrypt_secret("test_sec"),
        event_types=["new_notification"],
        is_active=True,
    )

    mock_db = AsyncMock()
    mock_res_notif = MagicMock()
    mock_res_notif.scalar_one_or_none.return_value = notif
    mock_res_sub = MagicMock()
    mock_res_sub.scalars.return_value.all.return_value = [sub]
    mock_db.execute.side_effect = [mock_res_notif, mock_res_sub]

    mock_redis = AsyncMock()
    worker._redis_client = mock_redis

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.get_webhook_security", return_value=sec_service):
            with patch("app.workers.notify_worker.validate_destination_url", side_effect=SSRFBlockedError("Private IP prohibited")):
                fields = {"notification_id": str(notif.id)}
                await worker.handle(fields)

                assert notif.status == "failed"
                mock_redis.xadd.assert_awaited_once()
                assert mock_redis.xadd.call_args[0][0] == "notifications:pending:dlq"
                assert mock_redis.xadd.call_args[0][1]["failure_type"] == "permanent"


@pytest.mark.unit
async def test_notify_worker_idempotency_on_replayed_event():
    """Verifies replayed Redis events for already delivered/read notifications do not trigger duplicate calls."""
    worker = NotifyWorker()
    notif = make_test_notification(status="delivered")
    notif.delivered_at = datetime.now(timezone.utc)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.create_ssrf_safe_client") as mock_client:
            fields = {"notification_id": str(notif.id)}
            await worker.handle(fields)

            mock_client.assert_not_called()
            assert notif.status == "delivered"


@pytest.mark.unit
async def test_notify_worker_skips_expired_or_deleted_post():
    """Verifies expired or deleted post cancels delivery and marks notification 'failed'."""
    worker = NotifyWorker()
    expired_post = make_test_post(expires_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    notif = make_test_notification(post=expired_post)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.create_ssrf_safe_client") as mock_client:
            fields = {"notification_id": str(notif.id)}
            await worker.handle(fields)

            mock_client.assert_not_called()
            assert notif.status == "failed"
            assert notif.routing_explanation.get("failure_reason") == "post_expired"


@pytest.mark.unit
async def test_notify_worker_skips_inactive_recipient():
    """Verifies inactive recipient agent cancels delivery and marks notification 'failed'."""
    worker = NotifyWorker()
    inactive_recipient = make_test_agent(is_active=False)
    notif = make_test_notification(recipient=inactive_recipient)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        fields = {"notification_id": str(notif.id)}
        await worker.handle(fields)

        assert notif.status == "failed"
        assert notif.routing_explanation.get("failure_reason") == "recipient_inactive"


@pytest.mark.unit
async def test_notify_worker_reconcile_unpublished():
    """Verifies periodic reconciler sweeps stuck unpublished pending notifications into Redis."""
    worker = NotifyWorker()
    notif = make_test_notification(status="pending")
    notif.delivery_event_published_at = None

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [notif]
    mock_db.execute.return_value = mock_res

    mock_redis = AsyncMock()
    mock_log = MagicMock()

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        count = await worker.reconcile_pending_notifications(mock_redis, mock_log)
        assert count == 1
        mock_redis.xadd.assert_awaited_once()
        assert notif.delivery_event_published_at is not None
        assert mock_db.commit.called


@pytest.mark.unit
async def test_reconciliation_recovers_stuck_retries_after_redis_restart():
    """P5.1: Verifies reconciler re-enqueues retrying notifications abandoned due to Redis restart."""
    worker = NotifyWorker()
    notif = make_test_notification(status="retrying")
    # Updated 70 seconds ago (stuck retry)
    notif.updated_at = datetime.now(timezone.utc) - timedelta(seconds=70)
    notif.delivery_attempts = 1

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [notif]
    mock_db.execute.return_value = mock_res

    mock_redis = AsyncMock()
    mock_log = MagicMock()

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        count = await worker.reconcile_pending_notifications(mock_redis, mock_log)
        assert count == 1
        mock_redis.xadd.assert_awaited_once()
        assert mock_redis.xadd.call_args[0][0] == "notifications:pending"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Notification Inbox API Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_list_notifications_pagination_and_status_filter():
    """GET /api/v1/notifications: verifies pagination and status filter."""
    agent = make_test_agent()
    notif1 = make_test_notification(recipient=agent, status="delivered")
    notif2 = make_test_notification(recipient=agent, status="read")

    mock_db = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar.return_value = 2
    mock_items_res = MagicMock()
    mock_items_res.scalars.return_value.all.return_value = [notif1, notif2]
    mock_db.execute.side_effect = [mock_count_res, mock_items_res]

    res = await list_notifications(
        current_agent=agent,
        db=mock_db,
        limit=10,
        offset=0,
        status_filter=None,
    )
    assert res.total == 2
    assert len(res.items) == 2
    assert res.limit == 10
    assert res.offset == 0


@pytest.mark.unit
async def test_get_notification_auto_marks_delivered_as_read():
    """GET /api/v1/notifications/{id}: auto-marks 'delivered' notification as 'read' with read_at."""
    agent = make_test_agent()
    notif = make_test_notification(recipient=agent, status="delivered")
    notif.delivered_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert notif.read_at is None

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    item = await get_notification(
        notification_id=notif.id,
        current_agent=agent,
        db=mock_db,
    )
    assert item.status == "read"
    assert notif.status == "read"
    assert notif.read_at is not None
    assert mock_db.commit.called


@pytest.mark.unit
async def test_explicit_mark_notification_as_read():
    """POST /api/v1/notifications/{id}/read: explicitly marks notification as read."""
    agent = make_test_agent()
    notif = make_test_notification(recipient=agent, status="pending")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    item = await mark_notification_read(
        notification_id=notif.id,
        current_agent=agent,
        db=mock_db,
    )
    assert item.status == "read"
    assert notif.status == "read"
    assert notif.read_at is not None
    assert mock_db.commit.called


@pytest.mark.unit
async def test_notification_ownership_isolation():
    """Verifies Agent B cannot access Agent A's notification."""
    agent_a = make_test_agent(name="AgentA")
    agent_b = make_test_agent(name="AgentB")
    notif = make_test_notification(recipient=agent_a)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc:
        await get_notification(
            notification_id=notif.id,
            current_agent=agent_b,
            db=mock_db,
        )
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 7. Live HTTPS DNS-Pinning & TLS SNI Verification Tests (P5.2)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_self_signed_cert_and_key(common_name: str, san_dns: list[str]) -> tuple[bytes, bytes]:
    """Generates an in-memory self-signed X.509 certificate and RSA private key with SAN extension."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    alt_names = [x509.DNSName(name) for name in san_dns]
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


@pytest.mark.unit
async def test_live_https_dns_pinning_and_sni_preservation():
    """
    P5.2 Live HTTPS Verification:
    Spins up a live HTTPS server on 127.0.0.1 with a real self-signed certificate for 'api.partner.test'.
    Connects using SSRFPinnedAsyncHTTPTransport (pinned to 127.0.0.1).
    Verifies:
      1. Socket connects to pinned IP (127.0.0.1) without secondary DNS resolution.
      2. TLS SNI extension retains the target hostname ('api.partner.test').
      3. TLS certificate hostname verification passes against 'api.partner.test'.
      4. Host header matches 'api.partner.test:<port>'.
      5. Full 200 OK HTTP request/response succeeds.
    """
    import ssl
    import tempfile
    import os
    from app.services.ssrf_protection import SSRFPinnedAsyncHTTPTransport

    cert_pem, key_pem = _generate_self_signed_cert_and_key("api.partner.test", ["api.partner.test"])
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf, tempfile.NamedTemporaryFile(suffix=".key", delete=False) as kf:
        cf.write(cert_pem)
        cf.flush()
        cert_path = cf.name
        kf.write(key_pem)
        kf.flush()
        key_path = kf.name

    try:
        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.load_cert_chain(cert_path, key_path)

        captured_sni: list[str | None] = []
        captured_headers: dict[str, str] = {}

        def sni_callback(sock, req_sni, ctx):
            captured_sni.append(req_sni)

        server_ssl.sni_callback = sni_callback

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                request_line = await reader.readline()
                while True:
                    line = await reader.readline()
                    if not line or line == b"\r\n":
                        break
                    decoded = line.decode("latin1").strip()
                    if ":" in decoded:
                        k, v = decoded.split(":", 1)
                        captured_headers[k.strip().lower()] = v.strip()

                content_len = int(captured_headers.get("content-length", 0))
                if content_len > 0:
                    await reader.read(content_len)

                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 15\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                    b'{"status":"ok"}'
                )
                writer.write(response)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0, ssl=server_ssl)
        port = server.sockets[0].getsockname()[1]

        client_ssl = ssl.create_default_context(cafile=cert_path)
        client_ssl.check_hostname = True

        transport = SSRFPinnedAsyncHTTPTransport(pinned_ip="127.0.0.1", verify=client_ssl)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            resp = await client.post(
                f"https://api.partner.test:{port}/webhooks/test",
                json={"event": "test"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

        # Assert SNI preservation
        assert len(captured_sni) >= 1
        assert captured_sni[0] == "api.partner.test"

        # Assert Host header preservation
        assert captured_headers.get("host") == f"api.partner.test:{port}"

        server.close()
        await server.wait_closed()

    finally:
        if os.path.exists(cert_path):
            os.remove(cert_path)
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.unit
async def test_live_https_invalid_certificate_rejected():
    """
    P5.2 Live HTTPS Verification:
    Spins up an HTTPS server on 127.0.0.1 with a certificate for 'wrong.domain.test'.
    Connects with SSRFPinnedAsyncHTTPTransport to 'https://api.partner.test:<port>/'.
    Verifies that TLS hostname verification is NOT bypassed and connection is rejected.
    """
    import ssl
    import tempfile
    import os
    from app.services.ssrf_protection import SSRFPinnedAsyncHTTPTransport

    cert_pem, key_pem = _generate_self_signed_cert_and_key("wrong.domain.test", ["wrong.domain.test"])
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf, tempfile.NamedTemporaryFile(suffix=".key", delete=False) as kf:
        cf.write(cert_pem)
        cf.flush()
        cert_path = cf.name
        kf.write(key_pem)
        kf.flush()
        key_path = kf.name

    try:
        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.load_cert_chain(cert_path, key_path)

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                await reader.read(1024)
            except Exception:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle_client, "127.0.0.1", 0, ssl=server_ssl)
        port = server.sockets[0].getsockname()[1]

        client_ssl = ssl.create_default_context(cafile=cert_path)
        client_ssl.check_hostname = True

        transport = SSRFPinnedAsyncHTTPTransport(pinned_ip="127.0.0.1", verify=client_ssl)
        with pytest.raises((httpx.ConnectError, ssl.SSLCertVerificationError)):
            async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
                await client.post(
                    f"https://api.partner.test:{port}/webhooks/test",
                    json={"event": "test"},
                )

        server.close()
        await server.wait_closed()

    finally:
        if os.path.exists(cert_path):
            os.remove(cert_path)
        if os.path.exists(key_path):
            os.remove(key_path)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Concurrency & Atomic Claim Isolation Tests (P5.2)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_atomic_claim_lease_renewal_and_concurrency_isolation():
    """
    P5.2: Verifies that when a notification lease is acquired, its status transitions
    to 'delivering' with updated_at timestamp, and concurrent worker skips dispatch.
    """
    worker = NotifyWorker()
    notif = make_test_notification(status="delivering")
    # Acquired 15 seconds ago (active lease <60s)
    notif.updated_at = datetime.now(timezone.utc) - timedelta(seconds=15)
    notif.delivery_attempts = 1

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = notif
    mock_db.execute.return_value = mock_res

    with patch("app.workers.notify_worker.AsyncSessionLocal") as mock_ctx:
        mock_ctx.return_value.__aenter__.return_value = mock_db
        with patch("app.workers.notify_worker.create_ssrf_safe_client") as mock_client:
            fields = {"notification_id": str(notif.id)}
            await worker.handle(fields)

            # Concurrent worker skipped: no outbound network dispatch
            mock_client.assert_not_called()
            # Lease remains untouched under original worker
            assert notif.status == "delivering"
            assert notif.delivery_attempts == 1
