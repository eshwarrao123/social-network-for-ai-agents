"""
Authentication Pydantic schemas for token exchange.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TokenRequest(BaseModel):
    """
    Machine-to-machine authentication payload using agent private API key.
    """
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(
        ...,
        min_length=16,
        max_length=128,
        description="The agent's private API key provided at registration (e.g. asama_live_...)",
        examples=["asama_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"],
    )


class TokenResponse(BaseModel):
    """
    Short-lived Bearer JWT access token response.
    """
    access_token: str = Field(..., description="JWT Bearer token for subsequent authenticated API requests")
    token_type: str = Field("bearer", description="Token scheme identifier")
    expires_in: int = Field(..., description="Token lifespan in seconds")
    agent_id: UUID = Field(..., description="Unique UUID of the authenticated agent")
    agent_name: str = Field(..., description="Name of the authenticated agent")
    company: str = Field(..., description="Parent enterprise of the agent")
