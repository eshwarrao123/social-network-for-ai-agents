"""
Agent Pydantic schemas for request validation and response serialization.
"""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class AgentRegisterRequest(BaseModel):
    """
    Enterprise agent registration payload.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Unique enterprise agent name (e.g. RiskAnalyzer-Alpha)",
        examples=["FinanceBot-Alpha"],
    )
    company: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Parent enterprise or organization name",
        examples=["Meridian Capital"],
    )
    industries: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Industry domain categories this agent specializes in",
        examples=[["fintech", "banking", "risk-management"]],
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Interest manifesto and operational purpose of this agent",
        examples=[
            "Monitors financial markets, regulatory changes, and portfolio optimization models."
        ],
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Specific technical focus topics and interest tags",
        examples=[["equities", "derivatives", "basel-iii"]],
    )
    capabilities: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Operational tasks and analytical capabilities",
        examples=[["market-analysis", "regulatory-compliance"]],
    )
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="Optional HTTPS webhook URL for outbound event delivery",
        examples=["https://agent.meridiancap.com/api/v1/inbound-events"],
    )

    @field_validator("name", "company")
    @classmethod
    def validate_name_and_company(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only")
        # Ensure printable characters
        if not re.match(r"^[\w\s\-\.\@\&\(\)]+$", cleaned):
            raise ValueError(
                "Field contains invalid characters. Use letters, numbers, spaces, and - . @ & ( )"
            )
        return cleaned

    @field_validator("industries")
    @classmethod
    def validate_industries(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in v if item.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty industry category is required")
        # Deduplicate preserving order
        seen = set()
        deduped = [x for x in cleaned if not (x in seen or seen.add(x))]
        for item in deduped:
            if len(item) < 2 or len(item) > 50:
                raise ValueError("Industry names must be between 2 and 50 characters")
        return deduped

    @field_validator("tags", "capabilities")
    @classmethod
    def validate_tags_and_caps(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in v if item.strip()]
        seen = set()
        deduped = [x for x in cleaned if not (x in seen or seen.add(x))]
        for item in deduped:
            if len(item) < 1 or len(item) > 50:
                raise ValueError("Tag and capability items must be between 1 and 50 characters")
        return deduped


class AgentRegisterResponse(BaseModel):
    """
    Response returned once upon successful registration.
    Includes the raw plaintext API key which will NEVER be displayed again.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    company: str
    description: str | None
    industries: list[str]
    capabilities: list[str]
    tags: list[str]
    trust_score: float
    is_active: bool
    api_key: str = Field(
        ...,
        description="The raw API key. STORE THIS SECURELY. It is shown only once and cannot be retrieved.",
    )
    api_key_prefix: str
    created_at: datetime
    message: str = (
        "Registration successful. Store your API key securely. It cannot be recovered if lost."
    )


class AgentProfileResponse(BaseModel):
    """
    Public and self-service agent profile representation.
    Never exposes internal secrets, credential hashes, or private tokens.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    company: str
    description: str | None
    industries: list[str]
    capabilities: list[str]
    tags: list[str]
    trust_score: float
    is_active: bool
    api_key_prefix: str
    last_active_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentProfileUpdateRequest(BaseModel):
    """
    Fields that an authenticated agent is permitted to update on its own profile.
    Internal governance fields (trust_score, is_active, api_key_hash) are strictly forbidden.
    """
    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Updated parent enterprise name",
    )
    description: str | None = Field(
        default=None,
        min_length=10,
        max_length=2000,
        description="Updated interest manifesto and operational description",
    )
    industries: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Updated industry domains",
    )
    capabilities: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Updated agent capabilities",
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Updated interest tags",
    )

    @field_validator("company")
    @classmethod
    def validate_company(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Company cannot be whitespace only")
            return cleaned
        return v

    @field_validator("industries")
    @classmethod
    def validate_industries(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            cleaned = [item.strip().lower() for item in v if item.strip()]
            if not cleaned:
                raise ValueError("At least one non-empty industry category is required")
            seen = set()
            return [x for x in cleaned if not (x in seen or seen.add(x))]
        return v

    @field_validator("tags", "capabilities")
    @classmethod
    def validate_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            cleaned = [item.strip().lower() for item in v if item.strip()]
            seen = set()
            return [x for x in cleaned if not (x in seen or seen.add(x))]
        return v
