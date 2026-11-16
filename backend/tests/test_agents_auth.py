"""
Comprehensive unit and integration tests for P1 Agent Registration and Authentication.

Tests cover:
  1. Successful agent registration schema & logic.
  2. Missing or invalid registration fields.
  3. API key generation and hashing.
  4. API key verification.
  5. Successful token issuance logic.
  6. Invalid API key rejection.
  7. JWT verification.
  8. Expired JWT rejection.
  9. Malformed JWT rejection.
  10. Inactive agent rejection.
  11. Agent profile retrieval.
  12. Unauthorized profile update rejection (extra/immutable fields forbidden).
  13. Agent ownership isolation (context derived from verified JWT subject).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.dependencies import get_active_agent
from app.models.agent import Agent
from app.schemas.agent import (
    AgentProfileResponse,
    AgentProfileUpdateRequest,
    AgentRegisterRequest,
    AgentRegisterResponse,
)
from app.schemas.auth import TokenRequest
from app.services.auth import (
    API_KEY_LIVE_PREFIX,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2: Registration Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_agent_registration_valid_payload():
    payload = {
        "name": "AuditBot-Alpha",
        "company": "Sentinel AI",
        "industries": ["cybersecurity", "banking"],
        "description": "Performs continuous automated risk evaluation and audit monitoring across agents.",
        "tags": ["threat-intel", "siem"],
        "capabilities": ["incident-triage"],
    }
    req = AgentRegisterRequest.model_validate(payload)
    assert req.name == "AuditBot-Alpha"
    assert req.company == "Sentinel AI"
    assert len(req.industries) == 2
    assert "cybersecurity" in req.industries


@pytest.mark.unit
def test_agent_registration_missing_required_fields():
    # Missing description and industries
    with pytest.raises(ValidationError) as exc:
        AgentRegisterRequest.model_validate({"name": "Bot", "company": "Co"})
    errors = str(exc.value)
    assert "description" in errors
    assert "industries" in errors


@pytest.mark.unit
def test_agent_registration_empty_or_whitespace_strings():
    with pytest.raises(ValidationError):
        AgentRegisterRequest.model_validate({
            "name": "   ",
            "company": "Valid Corp",
            "industries": ["tech"],
            "description": "Valid description greater than 10 characters",
        })


@pytest.mark.unit
def test_agent_registration_description_too_short():
    with pytest.raises(ValidationError):
        AgentRegisterRequest.model_validate({
            "name": "AuditBot",
            "company": "Valid Corp",
            "industries": ["tech"],
            "description": "Short",  # < 10 characters
        })


@pytest.mark.unit
def test_agent_registration_empty_industries_list():
    with pytest.raises(ValidationError):
        AgentRegisterRequest.model_validate({
            "name": "AuditBot",
            "company": "Valid Corp",
            "industries": [],  # Min 1 required
            "description": "Valid description greater than 10 characters",
        })


@pytest.mark.unit
def test_agent_registration_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        AgentRegisterRequest.model_validate({
            "name": "AuditBot",
            "company": "Valid Corp",
            "industries": ["tech"],
            "description": "Valid description greater than 10 characters",
            "trust_score": 1.0,  # Cannot self-assign trust score
        })


# ─────────────────────────────────────────────────────────────────────────────
# 3 & 4: API Key Generation, Hashing & Verification
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_api_key_generation_and_properties():
    raw_key, prefix, key_hash = generate_api_key()
    assert raw_key.startswith(API_KEY_LIVE_PREFIX)
    assert len(prefix) == 16
    assert prefix == raw_key[:16]
    assert len(key_hash) == 64  # SHA-256 hex string
    assert raw_key != key_hash
    assert prefix not in key_hash


@pytest.mark.unit
def test_api_key_hashing_deterministic():
    raw_key = "asama_live_testkey1234567890abcdef"
    h1 = hash_api_key(raw_key)
    h2 = hash_api_key(raw_key)
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.unit
def test_api_key_verification_success():
    raw_key, _, key_hash = generate_api_key()
    assert verify_api_key(raw_key, key_hash) is True


@pytest.mark.unit
def test_api_key_verification_tampered():
    raw_key, _, key_hash = generate_api_key()
    tampered_key = raw_key[:-2] + "xx"
    assert verify_api_key(tampered_key, key_hash) is False
    assert verify_api_key("", key_hash) is False
    assert verify_api_key(raw_key, "") is False


# ─────────────────────────────────────────────────────────────────────────────
# 5, 7, 8, 9: JWT Token Lifecycle & Security Hardening
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_jwt_token_generation_and_verification():
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = uuid.uuid4()
    mock_agent.name = "FinanceBot-Alpha"
    mock_agent.company = "Meridian Capital"

    token, expires_in = create_access_token(mock_agent)
    assert isinstance(token, str)
    # Default configured lifetime is 30 minutes (1800 seconds)
    assert expires_in == 1800

    claims = decode_access_token(token)
    assert claims["sub"] == str(mock_agent.id)
    assert claims["name"] == "FinanceBot-Alpha"
    assert claims["company"] == "Meridian Capital"
    assert claims["iss"] == "social-network-for-ai-agents"
    assert claims["aud"] == "agent-network"
    assert claims["exp"] - claims["iat"] == 1800


@pytest.mark.unit
def test_jwt_token_legacy_issuer_rejection():
    """P5.2: Verifies tokens issued under legacy issuer 'asama.ai' are invalid and rejected."""
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "LegacyIssuerBot",
        "iss": "asama.ai",  # Legacy issuer is no longer accepted
        "aud": settings.jwt_audience,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidIssuerError) as exc_info:
        decode_access_token(token)

    assert "issuer" in str(exc_info.value).lower()


@pytest.mark.unit
def test_jwt_token_legacy_audience_rejection():
    """P5.2: Verifies tokens issued under legacy audience 'asama:agent' are invalid and rejected."""
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "LegacyAudienceBot",
        "iss": settings.jwt_issuer,
        "aud": "asama:agent",  # Legacy audience is no longer accepted
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidAudienceError) as exc_info:
        decode_access_token(token)

    assert "audience" in str(exc_info.value).lower()


@pytest.mark.unit
def test_jwt_token_custom_expiration():
    mock_agent = MagicMock(spec=Agent)
    mock_agent.id = uuid.uuid4()
    mock_agent.name = "CustomExpireBot"
    mock_agent.company = "Alpha Dynamics"

    # Custom 15-minute token (900 seconds)
    token, expires_in = create_access_token(mock_agent, expire_minutes=15)
    assert expires_in == 900

    claims = decode_access_token(token)
    assert claims["exp"] - claims["iat"] == 900


@pytest.mark.unit
def test_jwt_token_wrong_issuer_rejection():
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "SpoofedIssuerBot",
        "iss": "untrusted-issuer.org",  # Incorrect issuer
        "aud": settings.jwt_audience,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    # Must raise InvalidIssuerError, which subclasses InvalidTokenError
    with pytest.raises(InvalidIssuerError) as exc_info:
        decode_access_token(token)

    assert "issuer" in str(exc_info.value).lower()
    assert issubclass(InvalidIssuerError, InvalidTokenError)


@pytest.mark.unit
def test_jwt_token_wrong_audience_rejection():
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "WrongAudienceBot",
        "iss": settings.jwt_issuer,
        "aud": "wrong:audience:target",  # Incorrect audience
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    # Must raise InvalidAudienceError, which subclasses InvalidTokenError
    with pytest.raises(InvalidAudienceError) as exc_info:
        decode_access_token(token)

    assert "audience" in str(exc_info.value).lower()
    assert issubclass(InvalidAudienceError, InvalidTokenError)


@pytest.mark.unit
def test_jwt_token_wrong_signature_key_rejection():
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "WrongKeyBot",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
    }
    wrong_secret = "tampered-secret-key-different-from-settings"
    token = jwt.encode(claims, wrong_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError) as exc_info:
        decode_access_token(token)

    assert "validation failed" in str(exc_info.value).lower()


@pytest.mark.unit
def test_expired_jwt_token_rejection():
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
    claims = {
        "sub": str(uuid.uuid4()),
        "name": "OldBot",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int((expired_time - timedelta(minutes=10)).timestamp()),
        "exp": int(expired_time.timestamp()),
    }
    expired_token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenExpiredError):
        decode_access_token(expired_token)


@pytest.mark.unit
def test_malformed_jwt_token_rejection():
    with pytest.raises(InvalidTokenError):
        decode_access_token("this-is-not-a-valid-jwt-token")

    with pytest.raises(InvalidTokenError):
        decode_access_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.badpayload.badsig")


@pytest.mark.unit
def test_jwt_token_missing_subject_rejection():
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    claims = {
        "name": "NoSubBot",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError) as exc:
        decode_access_token(token)
    assert "Missing subject" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# 10: Inactive Agent Rejection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_inactive_agent_dependency_rejection():
    inactive_agent = MagicMock(spec=Agent)
    inactive_agent.id = uuid.uuid4()
    inactive_agent.is_active = False

    with pytest.raises(HTTPException) as exc:
        await get_active_agent(inactive_agent)

    assert exc.value.status_code == 403
    assert "inactive" in str(exc.value.detail).lower()


@pytest.mark.unit
async def test_active_agent_dependency_accepted():
    active_agent = MagicMock(spec=Agent)
    active_agent.id = uuid.uuid4()
    active_agent.is_active = True

    resolved = await get_active_agent(active_agent)
    assert resolved == active_agent


# ─────────────────────────────────────────────────────────────────────────────
# 11 & 12: Agent Profile Response and Update Validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_agent_profile_response_serialization():
    agent_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    profile_data = {
        "id": agent_id,
        "name": "GovBot",
        "company": "Apex Corp",
        "description": "Enterprise compliance monitoring agent.",
        "industries": ["legal", "compliance"],
        "capabilities": ["contract-nlp"],
        "tags": ["gdpr"],
        "trust_score": 0.1,
        "is_active": True,
        "api_key_prefix": "asama_live_1234",
        "last_active_at": None,
        "created_at": now,
        "updated_at": now,
    }

    profile = AgentProfileResponse.model_validate(profile_data)
    assert profile.name == "GovBot"
    assert profile.trust_score == 0.1
    # Ensure api_key_hash is not in the schema
    assert not hasattr(profile, "api_key_hash")


@pytest.mark.unit
def test_profile_update_forbids_governance_tampering():
    # Attempting to modify trust_score or is_active must fail validation
    with pytest.raises(ValidationError):
        AgentProfileUpdateRequest.model_validate({
            "trust_score": 0.99,
        })

    with pytest.raises(ValidationError):
        AgentProfileUpdateRequest.model_validate({
            "is_active": True,
            "id": str(uuid.uuid4()),
        })


@pytest.mark.unit
def test_profile_update_allows_permitted_fields():
    update_data = {
        "company": "Apex Technologies Global",
        "description": "Updated manifesto covering global risk and supply chain analytics.",
        "industries": ["logistics", "manufacturing"],
        "tags": ["supply-chain", "nearshoring"],
    }
    req = AgentProfileUpdateRequest.model_validate(update_data)
    assert req.company == "Apex Technologies Global"
    assert len(req.industries) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 13: Agent Ownership Isolation Logic
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_agent_ownership_isolation_contract():
    """
    Verifies that the AgentProfileUpdateRequest accepts no client-provided agent_id.
    Identity is derived exclusively from the verified JWT in the dependency chain.
    """
    with pytest.raises(ValidationError):
        AgentProfileUpdateRequest.model_validate({
            "agent_id": str(uuid.uuid4()),
            "description": "Trying to impersonate another agent",
        })


# ─────────────────────────────────────────────────────────────────────────────
# Integration Test Stub (PostgreSQL + pgvector required)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_full_agent_registration_and_auth_postgres(postgres_session, client):
    """
    End-to-end integration test: registers agent, issues token, gets me, updates me.
    Automatically skipped if PostgreSQL is not reachable at DATABASE_TEST_URL.
    """
    # 1. Register agent
    register_payload = {
        "name": f"IntegrationAgent-{uuid.uuid4().hex[:6]}",
        "company": "Test Enterprise",
        "industries": ["fintech", "banking"],
        "description": "Integration test agent for automated validation.",
        "tags": ["test-tag"],
    }
    reg_res = await client.post("/api/v1/agents/register", json=register_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    api_key = reg_data["api_key"]
    agent_id = reg_data["id"]

    # 2. Issue token
    token_res = await client.post("/api/v1/auth/token", json={"api_key": api_key})
    assert token_res.status_code == 200
    token_data = token_res.json()
    access_token = token_data["access_token"]

    # 3. Access protected GET /api/v1/agents/me
    headers = {"Authorization": f"Bearer {access_token}"}
    me_res = await client.get("/api/v1/agents/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["id"] == agent_id
    assert me_data["company"] == "Test Enterprise"

    # 4. Access protected PATCH /api/v1/agents/me
    patch_res = await client.patch(
        "/api/v1/agents/me",
        headers=headers,
        json={"company": "Updated Enterprise Corp"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["company"] == "Updated Enterprise Corp"
