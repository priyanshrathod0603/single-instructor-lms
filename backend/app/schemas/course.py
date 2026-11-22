"""Pydantic schemas for Course Catalog, Curriculum Hierarchy, and Revision Control.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 8-13)
- docs/backend/06-API-ARCHITECTURE.md (Sections 2.3, 2.4, 3.1)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301, TASK302, TASK303, TASK304, TASK305)
"""

from datetime import datetime
import re
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    VALID_COURSE_STATUSES,
    VALID_REVISION_STATUSES,
)
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    RESOURCE_TYPE_PDF,
    VALID_LESSON_TYPES,
    VALID_RESOURCE_TYPES,
)

SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    """Normalize text into a URL-friendly slug."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ============================================================================
# Course Schemas
# ============================================================================

class CourseCreateRequest(BaseModel):
    """Payload for creating a new course entity and initial draft revision."""
    title: str = Field(..., min_length=1, max_length=255, description="Course title")
    slug: Optional[str] = Field(None, max_length=255, description="Unique slug; generated if omitted")
    headline: Optional[str] = Field(None, max_length=512, description="Short marketing tagline")
    description: Optional[str] = Field(None, description="Detailed course description")
    thumbnail_url: Optional[str] = Field(None, max_length=512, description="Course card thumbnail image URL")
    price_inr: int = Field(default=0, ge=0, description="Price in paise (e.g. 499900 for ₹4,999.00)")
    is_free: bool = Field(default=False, description="Whether the course is free of charge")
    tags: Optional[List[str]] = Field(default_factory=list, description="Categorization tags")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Course title cannot be empty or whitespace only")
        return cleaned

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if not cleaned or not SLUG_REGEX.match(cleaned):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens (e.g. 'deep-learning-mastery')")
        return cleaned


class CourseUpdateRequest(BaseModel):
    """Payload for updating top-level course container metadata."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    headline: Optional[str] = Field(None, max_length=512)
    description: Optional[str] = None
    thumbnail_url: Optional[str] = Field(None, max_length=512)
    price_inr: Optional[int] = Field(None, ge=0)
    is_free: Optional[bool] = None
    tags: Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Course title cannot be empty")
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


# ============================================================================
# Revision & Curriculum Schemas
# ============================================================================

class CourseRevisionCreateRequest(BaseModel):
    """Payload for spawning a new draft revision from the published course."""
    changelog: Optional[str] = Field(None, description="Instructor notes explaining changes in this revision")


class SectionCreateRequest(BaseModel):
    """Payload for creating a section in a draft revision."""
    title: str = Field(..., min_length=1, max_length=255, description="Section title")
    description: Optional[str] = Field(None, description="Optional section overview")
    sort_order: Optional[int] = Field(None, ge=0, description="Explicit sort order index")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Section title cannot be empty")
        return cleaned


class SectionUpdateRequest(BaseModel):
    """Payload for editing a section in a draft revision."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Section title cannot be empty")
        return cleaned


class SectionReorderRequest(BaseModel):
    """Optimistically-locked reordering payload for curriculum sections."""
    section_ids: List[uuid.UUID] = Field(..., min_length=1, description="Ordered list of section UUIDs")
    version_timestamp: datetime = Field(..., description="Timestamp of revision at client fetch time")


class LessonCreateRequest(BaseModel):
    """Payload for adding a lesson to a section in a draft revision."""
    title: str = Field(..., min_length=1, max_length=255, description="Lesson title")
    lesson_type: str = Field(default=LESSON_TYPE_VIDEO, description="VIDEO, ARTICLE, QUIZ, ASSIGNMENT")
    duration_seconds: Optional[int] = Field(default=0, ge=0, description="Duration in seconds")
    is_preview: Optional[bool] = Field(default=False, description="Whether available for free preview")
    sort_order: Optional[int] = Field(None, ge=0, description="Explicit sort order index")
    content: Optional[dict[str, Any]] = Field(default_factory=dict, description="Structured content / configuration")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Lesson title cannot be empty")
        return cleaned

    @field_validator("lesson_type")
    @classmethod
    def validate_lesson_type(cls, v: str) -> str:
        normalized = v.strip().upper()
        if normalized not in VALID_LESSON_TYPES:
            raise ValueError(f"Invalid lesson_type '{v}'. Must be one of {sorted(VALID_LESSON_TYPES)}")
        return normalized


class LessonUpdateRequest(BaseModel):
    """Payload for editing lesson properties in a draft revision."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    lesson_type: Optional[str] = None
    duration_seconds: Optional[int] = Field(None, ge=0)
    is_preview: Optional[bool] = None
    content: Optional[dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Lesson title cannot be empty")
        return cleaned

    @field_validator("lesson_type")
    @classmethod
    def validate_lesson_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().upper()
        if normalized not in VALID_LESSON_TYPES:
            raise ValueError(f"Invalid lesson_type '{v}'. Must be one of {sorted(VALID_LESSON_TYPES)}")
        return normalized


class LessonReorderRequest(BaseModel):
    """Optimistically-locked reordering payload for lessons within a section."""
    lesson_ids: List[uuid.UUID] = Field(..., min_length=1, description="Ordered list of lesson UUIDs")
    version_timestamp: datetime = Field(..., description="Timestamp of revision at client fetch time")


class ResourceCreateRequest(BaseModel):
    """Payload for attaching a downloadable/external resource to a lesson."""
    title: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(default=RESOURCE_TYPE_PDF, description="PDF, SOURCE_CODE, LINK, ASSET")
    file_url: str = Field(..., min_length=1, max_length=512)
    file_size_bytes: Optional[int] = Field(default=0, ge=0)

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, v: str) -> str:
        normalized = v.strip().upper()
        if normalized not in VALID_RESOURCE_TYPES:
            raise ValueError(f"Invalid resource_type '{v}'. Must be one of {sorted(VALID_RESOURCE_TYPES)}")
        return normalized


# ============================================================================
# Responses
# ============================================================================

class LessonResourceResponse(BaseModel):
    """Resource attached to a curriculum lesson."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    resource_type: str
    file_url: str
    file_size_bytes: int
    created_at: datetime


class CurriculumLessonResponse(BaseModel):
    """Curriculum lesson details with attached resources."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    title: str
    lesson_type: str
    sort_order: int
    duration_seconds: int
    is_preview: bool
    content: Optional[dict[str, Any]] = None
    resources: List[LessonResourceResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CurriculumSectionResponse(BaseModel):
    """Curriculum section container with ordered lessons."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_revision_id: uuid.UUID
    title: str
    description: Optional[str] = None
    sort_order: int
    lessons: List[CurriculumLessonResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CourseRevisionResponse(BaseModel):
    """Course revision metadata and full curriculum tree."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    revision_no: int
    status: str
    title: str
    changelog: Optional[str] = None
    snapshot: Optional[dict[str, Any]] = None
    published_at: Optional[datetime] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    sections: List[CurriculumSectionResponse] = Field(default_factory=list)


class CourseSummaryResponse(BaseModel):
    """Summary item for public course catalog or administrative management list."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    headline: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    price_inr: int
    is_free: bool
    tags: List[str] = Field(default_factory=list)
    live_revision_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class CourseDetailResponse(BaseModel):
    """Complete course detail response with live curriculum or revision snapshot."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    headline: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    price_inr: int
    is_free: bool
    tags: List[str] = Field(default_factory=list)
    live_revision_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    curriculum: List[CurriculumSectionResponse] = Field(default_factory=list)


class CourseListResponse(BaseModel):
    """Paginated course list envelope."""
    items: List[CourseSummaryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# ============================================================================
# Pre-Flight Publishing Checklist
# ============================================================================

class PublishChecklistBlocker(BaseModel):
    """Hard publishing blocker condition."""
    code: str
    lesson_id: Optional[uuid.UUID] = None
    section_id: Optional[uuid.UUID] = None
    message: str


class PublishChecklistWarning(BaseModel):
    """Soft warning that does not prevent publication."""
    code: str
    message: str


class PublishChecklistResponse(BaseModel):
    """Pre-flight publishing checklist evaluation report."""
    can_publish: bool
    revision_id: uuid.UUID
    revision_no: int
    blockers: List[PublishChecklistBlocker] = Field(default_factory=list)
    warnings: List[PublishChecklistWarning] = Field(default_factory=list)
