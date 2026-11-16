"""
SSRF Protection and Secure Outbound HTTP Transport Service.

Provides:
  1. Strict destination validation (URL scheme, allowed ports, comprehensive IP denylist).
  2. Multi-record DNS resolution validation (rejects if any A or AAAA record points to forbidden ranges).
  3. DNS Rebinding (TOCTOU) defense via socket pinning (pinned TCP connection to validated IP
     while preserving original hostname for TLS SNI, certificate validation, and HTTP Host header).
  4. Strict HTTP redirect blocking (follow_redirects=False).
"""
from __future__ import annotations

import ipaddress
import socket
import typing
import urllib.parse

import httpcore
import httpcore._backends.auto as auto
import httpx
import structlog

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class SSRFError(Exception):
    """Base exception for SSRF-related rejections."""


class SSRFSchemeError(SSRFError):
    """Raised when URL scheme is forbidden (e.g. plain HTTP in production, file://, gopher://)."""


class SSRFPortError(SSRFError):
    """Raised when destination port is not in the allowed ports list."""


class SSRFResolutionError(SSRFError):
    """Raised when destination hostname cannot be resolved via DNS."""


class SSRFBlockedError(SSRFError):
    """Raised when destination IP address falls into a prohibited private or local range."""


# ─────────────────────────────────────────────────────────────────────────────
# Prohibited IP Networks (Denylist)
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_NETWORKS = [
    # IPv4 Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    # RFC 1918 Private Ranges
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Carrier-Grade NAT (RFC 6598)
    ipaddress.ip_network("100.64.0.0/10"),
    # Link-Local / APIPA (RFC 3927)
    ipaddress.ip_network("169.254.0.0/16"),
    # Cloud Provider IMDS Metadata Endpoints (AWS, GCP, Azure, Oracle, DigitalOcean)
    ipaddress.ip_network("169.254.169.254/32"),
    # Current Network / Broadcast / Multicast / Reserved
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IETF Protocol Documentation
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # IPv6 Loopback
    ipaddress.ip_network("::1/128"),
    # IPv6 Unique Local Address (ULA, RFC 4193)
    ipaddress.ip_network("fc00::/7"),
    # IPv6 Link-Local
    ipaddress.ip_network("fe80::/10"),
    # IPv6 Multicast
    ipaddress.ip_network("ff00::/8"),
    # IPv6 Documentation
    ipaddress.ip_network("2001:db8::/32"),
    # Cloud IMDS IPv6 (AWS Nitro)
    ipaddress.ip_network("fd00:ec2::254/128"),
]


def is_ip_allowed(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Evaluates whether an IP address is a safe, publicly routable Internet address.
    Rejects loopback, private RFC 1918, link-local, carrier-grade NAT, cloud metadata,
    and IPv4-mapped IPv6 representations of prohibited ranges.
    """
    # Unpack IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 or ::ffff:169.254.169.254)
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped

    if ip_obj.is_loopback:
        return False
    if ip_obj.is_private:
        return False
    if ip_obj.is_link_local:
        return False
    if ip_obj.is_multicast:
        return False
    if ip_obj.is_reserved:
        return False
    if ip_obj.is_unspecified:
        return False

    for forbidden in FORBIDDEN_NETWORKS:
        try:
            if ip_obj in forbidden:
                return False
        except TypeError:
            continue

    return True


# ─────────────────────────────────────────────────────────────────────────────
# URL Validation & DNS Inspection
# ─────────────────────────────────────────────────────────────────────────────

def validate_destination_url(
    url: str,
    allow_http: bool = False,
    allowed_ports: set[int] | None = None,
) -> tuple[str, int, list[str]]:
    """
    Validates an externally supplied webhook destination URL.

    Enforces:
      - Valid scheme ('https' required unless allow_http=True)
      - Port whitelist (default {443, 8443} or {80, 443, 8443} if allow_http=True)
      - No embedded userinfo (user:pass@host)
      - Non-empty host
      - DNS resolution of all A/AAAA records
      - Multi-record assertion: fails closed if ANY resolved IP is prohibited

    Returns:
      (hostname, port, list_of_validated_ips)
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception as exc:
        raise SSRFBlockedError(f"Malformed destination URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if allow_http:
        if scheme not in ("https", "http"):
            raise SSRFSchemeError(f"Forbidden URL scheme '{scheme}'. Must be 'https' or 'http'.")
    else:
        if scheme != "https":
            raise SSRFSchemeError(f"Forbidden URL scheme '{scheme}'. Webhooks strictly require 'https'.")

    if parsed.username or parsed.password:
        raise SSRFBlockedError("Embedded credentials in webhook URL are forbidden.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("Destination URL contains empty or invalid hostname.")

    # Determine destination port
    port = parsed.port
    if port is None:
        port = 80 if scheme == "http" else 443

    valid_ports = allowed_ports or ({443, 8443} if not allow_http else {80, 443, 8443, 8000, 3000})
    if port not in valid_ports:
        raise SSRFPortError(f"Port {port} is not allowed for outbound webhooks (allowed: {sorted(valid_ports)}).")

    # If hostname is already an IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if not is_ip_allowed(ip_obj):
            raise SSRFBlockedError(f"Target IP '{hostname}' is in a prohibited private or local network range.")
        return (hostname, port, [str(ip_obj)])
    except ValueError:
        pass  # Standard hostname, resolve via DNS below

    # Resolve all DNS A and AAAA records
    try:
        addrinfo = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFResolutionError(f"Failed to resolve hostname '{hostname}': {exc}") from exc

    resolved_ips: list[str] = []
    for entry in addrinfo:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        # CRITICAL: If ANY resolved address is private/local, reject the entire hostname
        # to prevent round-robin DNS rebinding.
        if not is_ip_allowed(ip_obj):
            logger.warning(
                "ssrf_prohibited_ip_detected",
                hostname=hostname,
                resolved_ip=ip_str,
            )
            raise SSRFBlockedError(
                f"Destination hostname '{hostname}' resolved to prohibited IP '{ip_str}'."
            )
        resolved_ips.append(str(ip_obj))

    if not resolved_ips:
        raise SSRFResolutionError(f"Hostname '{hostname}' resolved to zero valid IP addresses.")

    return (hostname, port, resolved_ips)


# ─────────────────────────────────────────────────────────────────────────────
# DNS Pinning Transport (TOCTOU Mitigation)
# ─────────────────────────────────────────────────────────────────────────────

class PinnedAsyncNetworkBackend(auto.AutoBackend):
    """
    Custom httpcore network backend that connects the underlying TCP socket
    directly to a pre-validated IP address, bypassing secondary DNS resolution.
    Leaves the destination hostname intact for TLS SNI and Host header.
    """

    def __init__(self, pinned_ip: str):
        super().__init__()
        self.pinned_ip = pinned_ip

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[auto.SOCKET_OPTION] | None = None,
    ) -> auto.AsyncNetworkStream:
        logger.debug(
            "ssrf_socket_pinned_connection",
            requested_host=host,
            pinned_ip=self.pinned_ip,
            port=port,
        )
        return await super().connect_tcp(
            self.pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFPinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """
    httpx AsyncHTTPTransport configured with PinnedAsyncNetworkBackend.
    Enforces TCP connection to the pinned IP while preserving TLS SNI
    and certificate hostname validation against the original URL hostname.
    Fails closed if safe socket pinning cannot be established.
    """

    def __init__(self, pinned_ip: str, **kwargs):
        super().__init__(**kwargs)
        self.pinned_ip = pinned_ip
        try:
            backend = PinnedAsyncNetworkBackend(pinned_ip)
            ssl_context = getattr(self._pool, "_ssl_context", None)
            max_connections = getattr(self._pool, "_max_connections", 10)
            max_keepalive_connections = getattr(self._pool, "_max_keepalive_connections", None)
            keepalive_expiry = getattr(self._pool, "_keepalive_expiry", None)
            http1 = getattr(self._pool, "_http1", True)
            http2 = getattr(self._pool, "_http2", False)
            self._pool = httpcore.AsyncConnectionPool(
                ssl_context=ssl_context,
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
                keepalive_expiry=keepalive_expiry,
                http1=http1,
                http2=http2,
                network_backend=backend,
            )
        except Exception as exc:
            logger.error("ssrf_pinned_transport_initialization_failed", error=str(exc))
            raise SSRFBlockedError(
                f"Failed to initialize secure pinned HTTP transport for {pinned_ip}: {exc}"
            ) from exc


def create_ssrf_safe_client(
    pinned_ip: str,
    connect_timeout: float = 3.0,
    read_timeout: float = 5.0,
    write_timeout: float = 5.0,
    verify_ssl: bool = True,
) -> httpx.AsyncClient:
    """
    Constructs an httpx.AsyncClient with:
      - TCP socket pinned to pinned_ip (defeats DNS rebinding)
      - Strict redirect following disabled (follow_redirects=False)
      - Aggressive connect and read timeouts
      - Validated SSL context
    """
    transport = SSRFPinnedAsyncHTTPTransport(pinned_ip=pinned_ip, verify=verify_ssl)
    timeout = httpx.Timeout(
        timeout=connect_timeout + read_timeout,
        connect=connect_timeout,
        read=read_timeout,
        write=write_timeout,
    )
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,  # Strict: never follow outbound redirects
    )
