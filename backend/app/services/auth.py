"""
Authentication service: API key generation, secure hashing, and JWT token management.

Security Architecture:
  1. API Key Design:
     - Generated with 256 bits of cryptographically secure pseudorandomness (`secrets.token_urlsafe(32)`).
     - Formatted with a recognizable prefix: 'asama_live_' (e.g. 'asama_live_Xk9A...').
     - Indexed prefix: First 16 characters stored in `api_key_prefix` to facilitate fast lookups
       without exposing the secret payload.
     - Storage: Stored only as an irreversible SHA-256 hash in `api_key_hash`.
     - Raw keys are shown ONCE at registration and NEVER logged or persisted in plaintext.
     - Verification employs `hmac.compare_digest` to prevent timing attacks.

  2. JWT Token Design:
     - Short-lived Bearer tokens for machine-to-machine authorized session calls.
     - Strict claims validation: subject (UUID), issuer ('asama.ai'), audience ('asama:agent'),
       issued-at, and expiration timestamps.
     - Explicit algorithm enforcement matching `settings.jwt_algorithm` (HS256).
     - Distinguishes expired tokens from structurally malformed tokens for clear diagnostics.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.agent import Agent

logger = structlog.get_logger(__name__)

# Constants
API_KEY_LIVE_PREFIX = "asama_live_"
API_KEY_PREFIX_LENGTH = 16
JWT_ISSUER = "asama.ai"
JWT_AUDIENCE = "asama:agent"


class AuthError(Exception):
    """Base exception for authentication errors."""


class TokenExpiredError(AuthError):
    """Raised when a JWT access token has expired."""


class InvalidTokenError(AuthError):
    """Raised when a JWT access token is malformed or invalid."""


class InvalidIssuerError(InvalidTokenError):
    """Raised when the token issuer claim does not match configured issuer."""


class InvalidAudienceError(InvalidTokenError):
    """Raised when the token audience claim does not match configured audience."""


# ─────────────────────────────────────────────────────────────────────────────
# API Key Management
# ─────────────────────────────────────────────────────────────────────────────

def generate_api_key(prefix: str = API_KEY_LIVE_PREFIX) -> tuple[str, str, str]:
    """
    Generates a cryptographically strong random API key.
    
    Returns:
      (raw_key, api_key_prefix, api_key_hash)
      - raw_key: Returned once to the agent upon registration. NEVER saved or logged.
      - api_key_prefix: First 16 characters for index lookup (e.g. 'asama_live_ab12').
      - api_key_hash: SHA-256 hex digest stored in the database.
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_part}"
    key_prefix = raw_key[:API_KEY_PREFIX_LENGTH]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


def hash_api_key(raw_key: str) -> str:
    """Computes deterministic SHA-256 digest of raw API key for database storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verifies a raw API key against a stored hash using constant-time comparison."""
    if not raw_key or not stored_hash:
        return False
    computed_hash = hash_api_key(raw_key)
    return hmac.compare_digest(computed_hash, stored_hash)


async def authenticate_agent_by_api_key(
    api_key: str,
    db: AsyncSession,
) -> Agent | None:
    """
    Authenticates an agent using its raw API key.
    
    Lookup strategy:
      1. Slices the first 16 characters of the incoming key.
      2. Queries the indexed `api_key_prefix` to narrow down the candidate.
      3. Performs constant-time comparison of SHA-256 hashes.
    """
    if len(api_key) < API_KEY_PREFIX_LENGTH:
        return None

    prefix = api_key[:API_KEY_PREFIX_LENGTH]
    computed_hash = hash_api_key(api_key)

    stmt = select(Agent).where(Agent.api_key_prefix == prefix)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    for candidate in agents:
        if hmac.compare_digest(candidate.api_key_hash, computed_hash):
            return candidate

    return None


# ─────────────────────────────────────────────────────────────────────────────
# JWT Token Management
# ─────────────────────────────────────────────────────────────────────────────

def create_access_token(
    agent: Agent,
    expire_minutes: int | None = None,
) -> tuple[str, int]:
    """
    Generates a signed JWT Bearer access token for an authenticated agent.
    
    Returns:
      (token_str, expires_in_seconds)
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    effective_minutes = expire_minutes if expire_minutes is not None else settings.token_expire_minutes
    expires_delta = timedelta(minutes=effective_minutes)
    expire_time = now + expires_delta
    expires_in_seconds = int(expires_delta.total_seconds())

    claims: dict[str, Any] = {
        "sub": str(agent.id),
        "agent_id": str(agent.id),
        "name": agent.name,
        "company": agent.company,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expire_time.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(
        claims,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and validates a JWT Bearer access token.
    Enforces strict signature verification, expiration, issuer, audience, and algorithm.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        sub = payload.get("sub")
        if not sub:
            raise InvalidTokenError("Missing subject (sub) claim in token")
        return payload

    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token signature has expired") from exc
    except JWTClaimsError as exc:
        err_msg = str(exc).lower()
        if "issuer" in err_msg:
            raise InvalidIssuerError(f"Token issuer validation failed: {exc}") from exc
        if "audience" in err_msg:
            raise InvalidAudienceError(f"Token audience validation failed: {exc}") from exc
        raise InvalidTokenError(f"Token claims validation failed: {exc}") from exc
    except JWTError as exc:
        raise InvalidTokenError(f"Token validation failed: {exc}") from exc


async def verify_token(token: str, db: AsyncSession) -> Agent | None:
    """
    Decodes JWT token and retrieves the corresponding Agent from the database.
    Returns None if token is invalid or agent does not exist.
    """
    try:
        payload = decode_access_token(token)
    except AuthError:
        return None

    agent_id_str = payload.get("sub")
    if not agent_id_str:
        return None

    try:
        agent_id = uuid.UUID(agent_id_str)
    except (ValueError, TypeError):
        return None

    stmt = select(Agent).where(Agent.id == agent_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
