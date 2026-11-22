"""Pydantic schemas for Notes CMS (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 5)
- docs/backend/06-API-ARCHITECTURE.md
"""

from datetime import datetime
import re
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.note import (
    NOTE_STATUS_ARCHIVED,
    NOTE_STATUS_DRAFT,
    NOTE_STATUS_PUBLISHED,
    VALID_NOTE_STATUSES,
)

SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    """Normalize text into a URL-friendly slug."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


class NoteAuthorSummary(BaseModel):
    """Author summary for study notes."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class NoteCreateRequest(BaseModel):
    """Payload for creating a study note entity."""
    title: str = Field(..., min_length=1, max_length=255, description="Note title")
    slug: Optional[str] = Field(None, max_length=255, description="Unique slug; generated if omitted")
    description: Optional[str] = Field(None, description="Optional description / overview")
    category: str = Field(default="General", max_length=64, description="Classification category")
    pdf_media_id: Optional[uuid.UUID] = Field(None, description="Reference to uploaded PDF MediaAsset")
    pdf_url: Optional[str] = Field(None, max_length=512, description="Storage location of the PDF")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="PDF file size in bytes")
    status: str = Field(default=NOTE_STATUS_DRAFT, description="Initial status (DRAFT or PUBLISHED)")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Note title cannot be empty")
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
        if upper_v not in VALID_NOTE_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_NOTE_STATUSES)}")
        return upper_v


class NoteUpdateRequest(BaseModel):
    """Payload for updating an existing study note."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    pdf_media_id: Optional[uuid.UUID] = None
    pdf_url: Optional[str] = Field(None, max_length=512)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Note title cannot be empty")
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
        if upper_v not in VALID_NOTE_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_NOTE_STATUSES)}")
        return upper_v


class NoteStatusRequest(BaseModel):
    """Payload for transitioning note publication status."""
    status: str = Field(..., description="Target status: DRAFT, PUBLISHED, ARCHIVED")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        upper_v = v.strip().upper()
        if upper_v not in VALID_NOTE_STATUSES:
            raise ValueError(f"Status must be one of {sorted(VALID_NOTE_STATUSES)}")
        return upper_v


class NoteReplacePdfRequest(BaseModel):
    """Payload for replacing note PDF document."""
    pdf_media_id: Optional[uuid.UUID] = Field(None, description="MediaAsset UUID")
    pdf_url: str = Field(..., max_length=512, description="New storage path or URL")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="New file size")


class NoteResponse(BaseModel):
    """Full representation of a study note."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    description: Optional[str] = None
    category: str
    pdf_media_id: Optional[uuid.UUID] = None
    pdf_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    published_at: Optional[datetime] = None
    author_id: uuid.UUID
    author: Optional[NoteAuthorSummary] = None
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    """Paginated note list response."""
    items: List[NoteResponse]
    total: int
    page: int
    per_page: int
    pages: int
