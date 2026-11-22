"""Pydantic schemas for Blog CMS (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 4)
- docs/backend/06-API-ARCHITECTURE.md
"""

from datetime import datetime
import re
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.blog import (
    BLOG_STATUS_ARCHIVED,
    BLOG_STATUS_DRAFT,
    BLOG_STATUS_PUBLISHED,
    VALID_BLOG_STATUSES,
)

SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    """Normalize text into a URL-friendly slug."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class BlogPostAuthorSummary(BaseModel):
    """Author summary for blog posts."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class BlogPostCreateRequest(BaseModel):
    """Payload for creating a new blog post."""
    title: str = Field(..., min_length=1, max_length=255, description="Blog post title")
    slug: Optional[str] = Field(None, max_length=255, description="Unique slug; generated if omitted")
    excerpt: Optional[str] = Field(None, description="Optional brief summary / lead")
    content: str = Field(..., min_length=1, description="Markdown content body")
    category: str = Field(default="General", max_length=64, description="Classification category")
    thumbnail_url: Optional[str] = Field(None, max_length=512, description="Thumbnail URL")
    thumbnail_media_id: Optional[uuid.UUID] = Field(None, description="MediaAsset ID")
    status: str = Field(default=BLOG_STATUS_DRAFT, description="Initial status (DRAFT or PUBLISHED)")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Blog title cannot be empty")
        return cleaned

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if not cleaned or not SLUG_REGEX.match(cleaned):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        upper_v = v.strip().upper()
        if upper_v not in VALID_BLOG_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_BLOG_STATUSES)}")
        return upper_v


class BlogPostUpdateRequest(BaseModel):
    """Payload for updating an existing blog post."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = Field(None, max_length=64)
    thumbnail_url: Optional[str] = Field(None, max_length=512)
    thumbnail_media_id: Optional[uuid.UUID] = None
    status: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Blog title cannot be empty")
        return cleaned

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if not cleaned or not SLUG_REGEX.match(cleaned):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        upper_v = v.strip().upper()
        if upper_v not in VALID_BLOG_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_BLOG_STATUSES)}")
        return upper_v


class BlogPostStatusRequest(BaseModel):
    """Payload for transitioning blog post publication status."""
    status: str = Field(..., description="Target status: DRAFT, PUBLISHED, ARCHIVED")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        upper_v = v.strip().upper()
        if upper_v not in VALID_BLOG_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_BLOG_STATUSES)}")
        return upper_v


class BlogPostResponse(BaseModel):
    """Full representation of a blog post."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    excerpt: Optional[str] = None
    content: str
    category: str
    thumbnail_url: Optional[str] = None
    thumbnail_media_id: Optional[uuid.UUID] = None
    status: str
    published_at: Optional[datetime] = None
    author_id: uuid.UUID
    author: Optional[BlogPostAuthorSummary] = None
    created_at: datetime
    updated_at: datetime


class BlogPostListResponse(BaseModel):
    """Paginated blog post response."""
    items: List[BlogPostResponse]
    total: int
    page: int
    per_page: int
    pages: int
