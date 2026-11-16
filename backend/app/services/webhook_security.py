"""
Webhook security service: authenticated encryption at rest and HMAC-SHA256 signing.

Security Architecture:
  1. Encryption at rest:
     - Webhook signing secrets are confidential symmetric keys shared between Asama.ai
       and the subscriber's endpoint.
     - They must NEVER be stored in plaintext and CANNOT be one-way hashed (bcrypt),
       because the server must recover the secret to compute outbound HMAC signatures.
     - We use Fernet (AES-128 in CBC mode with PKCS7 padding and HMAC-SHA256 authenticated
       encryption with a timestamp) from the standard `cryptography` library.
     - The master encryption key is loaded from the environment (`WEBHOOK_ENCRYPTION_KEY`)
       and is NEVER persisted to the database or exposed via APIs.

  2. Outbound request signing:
     - Outbound webhook HTTP requests include the `X-Asama-Signature` header.
     - Signature format: `sha256=<hex_digest>` computed using HMAC-SHA256 over the raw request body.
     - Timing attacks are mitigated using constant-time comparison (`hmac.compare_digest`).

  3. Key Management & Rotation:
     - Fernet supports key rotation via `MultiFernet`.
     - When rotating keys:
       1. Set `WEBHOOK_ENCRYPTION_KEY="<new_key>,<old_key>"` (comma-separated list).
       2. The first key is used for all new encryptions.
       3. All listed keys are attempted in order for decryptions.
       4. A background maintenance job can re-encrypt all existing secrets with the primary key.
       5. Once re-encryption is verified, remove the old key from the environment.

  4. Future Webhook Delivery SSRF Prevention Architecture (Phase 7):
     When dispatching HTTP payloads to subscriber webhook URLs, the background notification
     worker must enforce strict Server-Side Request Forgery (SSRF) countermeasures:
     - URL Scheme Whitelist: Only 'https://' URLs are permitted in production.
       Plain 'http://' is strictly prohibited except in explicit local development modes.
     - Destination IP Denylist & Blacklisting:
       Target hostnames must be resolved via DNS prior to connecting and verified against:
         * IPv4 Loopback: 127.0.0.0/8 (e.g. 127.0.0.1)
         * IPv6 Loopback: ::1/128
         * RFC 1918 Private Ranges: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
         * Link-Local / APIPA: 169.254.0.0/16, fe80::/10
         * Cloud Provider Metadata Endpoints (AWS/GCP/Azure IMDS): 169.254.169.254, fd00:ec2::254
         * Unique Local IPv6: fc00::/7
         * Carrier-Grade NAT: 100.64.0.0/10
         * Broadcast / Multicast: 224.0.0.0/4, 240.0.0.0/4, ff00::/8
     - DNS Rebinding Mitigation (TOCTOU Defense):
       Resolve host IP immediately prior to connection, assert non-private status, and pin the
       socket connection directly to the resolved IP address while passing the user hostname in
       the HTTP 'Host' header and TLS SNI extension.
     - HTTP Redirect Hardening:
       Disable automatic HTTP redirect following (`follow_redirects=False`) to prevent redirects
       to internal networks or cloud metadata APIs. If redirects are supported, every redirect
       target must undergo the exact same IP denylist and scheme verification.
     - Port Restrictions:
       Restrict outbound connections strictly to standard HTTPS port 443 (and optionally 8443).
       Explicitly forbid connections to internal ports (e.g., 22, 5432, 6379, 8000, 11434).
     - Execution Timeouts:
       Enforce aggressive connect timeouts (max 3.0s) and read timeouts (max 5.0s) to guard
       against slowloris connection exhaustion.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Sequence

import structlog
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings

logger = structlog.get_logger(__name__)


class WebhookSecurityError(Exception):
    """Base exception for webhook security errors."""


class WebhookKeyConfigurationError(WebhookSecurityError):
    """Raised when the master webhook encryption key is missing or invalid."""


class WebhookDecryptionError(WebhookSecurityError):
    """Raised when an encrypted secret cannot be decrypted (e.g. wrong key or corruption)."""


class WebhookSecurityService:
    """
    Handles authenticated encryption at rest and HMAC signature generation/verification.
    """

    def __init__(self, encryption_key: str | Sequence[str] | None = None):
        self._custom_key = encryption_key

    def _get_fernet(self) -> MultiFernet:
        """
        Initializes MultiFernet from configured encryption key(s).
        Supports comma-separated keys for zero-downtime key rotation.
        """
        raw_key = self._custom_key
        if raw_key is None:
            settings = get_settings()
            raw_key = settings.webhook_encryption_key

        if not raw_key:
            raise WebhookKeyConfigurationError(
                "WEBHOOK_ENCRYPTION_KEY environment variable is not configured."
            )

        if isinstance(raw_key, str):
            key_list = [k.strip() for k in raw_key.split(",") if k.strip()]
        else:
            key_list = list(raw_key)

        if not key_list:
            raise WebhookKeyConfigurationError("No valid webhook encryption keys provided.")

        try:
            fernets = [Fernet(k.encode("utf-8") if isinstance(k, str) else k) for k in key_list]
            return MultiFernet(fernets)
        except Exception as exc:
            raise WebhookKeyConfigurationError(
                f"Invalid Fernet encryption key configuration: {exc}"
            ) from exc

    def generate_secret(self, nbytes: int = 32) -> str:
        """
        Generates a cryptographically strong random hex secret for an agent webhook.
        Returned in plaintext ONCE to the agent upon subscription creation.
        """
        return secrets.token_hex(nbytes)

    def encrypt_secret(self, secret: str) -> str:
        """
        Encrypts a plaintext secret into an authenticated ciphertext string.
        Safe to persist in database columns. Never logs the secret.
        """
        if not secret:
            raise ValueError("Cannot encrypt an empty webhook secret.")

        fernet = self._get_fernet()
        ciphertext_bytes = fernet.encrypt(secret.encode("utf-8"))
        return ciphertext_bytes.decode("utf-8")

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """
        Decrypts an encrypted secret from the database.
        Used strictly in-memory during outbound webhook dispatch.
        Never log the output of this function.
        """
        if not encrypted_secret:
            raise ValueError("Cannot decrypt an empty ciphertext.")

        fernet = self._get_fernet()
        try:
            decrypted_bytes = fernet.decrypt(encrypted_secret.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as exc:
            # SECURITY: Log failure context without printing any secret material
            logger.error("webhook_secret_decryption_failed", reason="InvalidToken")
            raise WebhookDecryptionError(
                "Failed to decrypt webhook secret. The master encryption key may have changed."
            ) from exc

    def sign_payload(self, payload: bytes | str, secret: str) -> str:
        """
        Computes HMAC-SHA256 signature for an outbound webhook payload.
        Returns format: 'sha256=<hex_digest>'
        """
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload

        secret_bytes = secret.encode("utf-8")
        digest = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def verify_signature(
        self,
        payload: bytes | str,
        secret: str,
        received_signature: str,
    ) -> bool:
        """
        Verifies received webhook signature using constant-time comparison to prevent timing attacks.
        Accepts signature formats: 'sha256=<hex_digest>' or bare '<hex_digest>'.
        """
        if not received_signature:
            return False

        expected = self.sign_payload(payload, secret)

        # Normalize comparison: compare both bare digest and prefixed format safely
        if received_signature.startswith("sha256="):
            return hmac.compare_digest(expected, received_signature)
        else:
            expected_bare = expected.removeprefix("sha256=")
            return hmac.compare_digest(expected_bare, received_signature)


# Module-level singleton
_webhook_security: WebhookSecurityService | None = None


def get_webhook_security() -> WebhookSecurityService:
    global _webhook_security
    if _webhook_security is None:
        _webhook_security = WebhookSecurityService()
    return _webhook_security
