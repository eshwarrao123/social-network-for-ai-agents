"""Schemas for Comment creation and responses."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=2000, description="Comment text content")
    idempotency_key: str | None = Field(None, max_length=100, description="Optional idempotency key to prevent duplicates")

    @field_validator("content")
    @classmethod
    def validate_content_not_whitespace(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Comment content cannot be empty or pure whitespace")
        return clean


class CommentAuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company: str
    trust_score: float = 0.0


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    post_id: uuid.UUID
    author: CommentAuthorResponse
    content: str
    is_llm_generated: bool = False
    is_autonomous: bool = False
    llm_model: str | None = None
    confidence_score: float | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("is_llm_generated", "is_autonomous", mode="before")
    @classmethod
    def default_bool(cls, v: Any) -> bool:
        return bool(v) if v is not None else False


class CommentListResponse(BaseModel):
    items: list[CommentResponse]
    total: int
    limit: int
    offset: int
