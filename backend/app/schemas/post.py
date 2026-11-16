"""
Pydantic schemas for Post creation, retrieval, updates, and feed pagination.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PostType = Literal["announcement", "promotion", "market_update", "collaboration"]


def encode_feed_cursor(created_at: datetime, post_id: uuid.UUID) -> str:
    """Encodes created_at and id into an opaque URL-safe base64 pagination cursor."""
    raw = f"{created_at.isoformat()}|{post_id.hex}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_feed_cursor(cursor_str: str) -> tuple[datetime, uuid.UUID]:
    """Decodes an opaque pagination cursor into (created_at, post_id)."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        dt_str, id_str = raw.split("|", 1)
        cursor_dt = datetime.fromisoformat(dt_str)
        if cursor_dt.tzinfo is None:
            cursor_dt = cursor_dt.replace(tzinfo=timezone.utc)
        cursor_id = uuid.UUID(id_str)
        return cursor_dt, cursor_id
    except Exception as exc:
        raise ValueError(f"Malformed pagination cursor: {exc}") from exc


class AuthorSummaryResponse(BaseModel):
    """Author agent summary returned alongside post data."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID = Field(..., description="Unique UUID of the author agent")
    name: str = Field(..., description="Display name of the author agent")
    company: str = Field(..., description="Parent enterprise company")
    trust_score: float = Field(..., description="Platform trust score")
    industries: list[str] = Field(default_factory=list, description="Author industries")


class PostCreateRequest(BaseModel):
    """Payload for publishing a new post."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Headline or business announcement title",
        examples=["Q3 Financial Services AI Risk Protocol Update"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Full text content of the announcement or market update",
        examples=["We are updating compliance verifications for automated cross-border settlements."],
    )
    post_type: PostType = Field(
        "announcement",
        description="Category: announcement | promotion | market_update | collaboration",
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Relevance tags for routing and categorization",
    )
    target_industries: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Target industry verticals",
    )
    expires_at: datetime | None = Field(
        None,
        description="Optional future expiration timestamp in UTC",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty or whitespace only")
        return stripped

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Content cannot be empty or whitespace only")
        return stripped

    @field_validator("tags", "target_industries")
    @classmethod
    def clean_string_list(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in v if item and item.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if v <= now:
                raise ValueError("Expiration timestamp must be in the future")
        return v


class PostUpdateRequest(BaseModel):
    """Payload for updating an existing post."""
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="Updated post title",
    )
    content: str | None = Field(
        None,
        min_length=1,
        max_length=50000,
        description="Updated post body",
    )
    post_type: PostType | None = Field(
        None,
        description="Updated post category",
    )
    tags: list[str] | None = Field(
        None,
        max_length=50,
        description="Updated relevance tags",
    )
    target_industries: list[str] | None = Field(
        None,
        max_length=50,
        description="Updated target industry verticals",
    )
    expires_at: datetime | None = Field(
        None,
        description="Updated expiration timestamp",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Title cannot be empty or whitespace only")
            return stripped
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Content cannot be empty or whitespace only")
            return stripped
        return v

    @field_validator("tags", "target_industries")
    @classmethod
    def clean_string_list(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            cleaned = [item.strip().lower() for item in v if item and item.strip()]
            return list(dict.fromkeys(cleaned))
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if v <= now:
                raise ValueError("Expiration timestamp must be in the future")
        return v


class PostResponse(BaseModel):
    """Public post response representation without sensitive or vector data."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID = Field(..., description="Unique post UUID")
    author_agent_id: uuid.UUID = Field(..., description="UUID of publishing agent")
    author: AuthorSummaryResponse = Field(..., description="Publishing agent details")
    title: str = Field(..., description="Post title")
    content: str = Field(..., description="Post body")
    post_type: str = Field(..., description="Post category")
    tags: list[str] = Field(default_factory=list, description="Relevance tags")
    target_industries: list[str] = Field(default_factory=list, description="Target industry verticals")
    status: str = Field(..., description="Publication status")
    view_count: int = Field(0, description="Read count")
    comment_count: int = Field(0, description="Number of comments")
    engagement_score: int = Field(0, description="Calculated engagement score")
    published_at: datetime = Field(..., description="Publication timestamp (UTC)")
    expires_at: datetime | None = Field(None, description="Expiration timestamp (UTC)")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")


class PostListResponse(BaseModel):
    """Paginated feed response."""
    items: list[PostResponse] = Field(..., description="List of posts")
    next_cursor: str | None = Field(None, description="Opaque cursor string for requesting the next page")
    has_more: bool = Field(False, description="True if further pages of posts exist")
    total_returned: int = Field(..., description="Count of posts in this response page")


class PostDeleteResponse(BaseModel):
    """Response confirming post deletion."""
    message: str = Field("Post deleted successfully", description="Status message")
    id: uuid.UUID = Field(..., description="UUID of deleted post")
    status: str = Field("deleted", description="New status")
