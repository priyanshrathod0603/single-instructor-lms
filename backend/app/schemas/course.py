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
import urllib.parse
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    DEFAULT_COURSE_CATEGORIES,
    DEFAULT_COURSE_LANGUAGES,
    DEFAULT_CURRENCY_INR,
    DIFFICULTY_ADVANCED,
    DIFFICULTY_ALL_LEVELS,
    DIFFICULTY_BEGINNER,
    DIFFICULTY_INTERMEDIATE,
    DIFFICULTY_LEVEL_LABELS,
    VALID_COURSE_STATUSES,
    VALID_DIFFICULTY_LEVELS,
    VALID_REVISION_STATUSES,
)
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    RESOURCE_TYPE_PDF,
    VALID_LESSON_TYPES,
    VALID_RESOURCE_TYPES,
)

SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DANGEROUS_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z!/?][^>]*>")
_DANGEROUS_URI_RE = re.compile(r"(javascript:|vbscript:|data\s*:\s*text/html)", re.IGNORECASE)

_DIFFICULTY_INPUT_MAP: dict[str, str] = {
    "beginner": DIFFICULTY_BEGINNER,
    "intermediate": DIFFICULTY_INTERMEDIATE,
    "advanced": DIFFICULTY_ADVANCED,
    "all levels": DIFFICULTY_ALL_LEVELS,
    "all_levels": DIFFICULTY_ALL_LEVELS,
    "all-levels": DIFFICULTY_ALL_LEVELS,
}


def sanitize_plain_text(
    value: Optional[str],
    *,
    preserve_newlines: bool = True,
    max_length: Optional[int] = None,
) -> Optional[str]:
    """Strip unsafe HTML/script tags and control characters from text inputs."""
    if value is None:
        return None
    cleaned = _CONTROL_CHARS_RE.sub("", value)
    cleaned = _DANGEROUS_BLOCK_RE.sub("", cleaned)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _DANGEROUS_URI_RE.sub("", cleaned)
    if preserve_newlines:
        cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()
    else:
        cleaned = " ".join(cleaned.split())
    if max_length is not None and len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned


def normalize_difficulty_level(value: Optional[str]) -> Optional[str]:
    """Normalize display labels or canonical codes to stored difficulty constant."""
    if value is None:
        return None
    cleaned = " ".join(value.strip().lower().split())
    if cleaned in _DIFFICULTY_INPUT_MAP:
        return _DIFFICULTY_INPUT_MAP[cleaned]
    upper = cleaned.upper()
    if upper in VALID_DIFFICULTY_LEVELS:
        return upper
    raise ValueError(
        "Difficulty level must be one of: Beginner, Intermediate, Advanced, All Levels"
    )


def validate_safe_thumbnail_url(value: Optional[str]) -> Optional[str]:
    """Allow safe HTTP(S) URLs or canonical /api/v1/media/public/<uuid> paths."""
    if value is None:
        return None
    cleaned = _CONTROL_CHARS_RE.sub("", value).strip()
    if not cleaned:
        return None
    if len(cleaned) > 512:
        raise ValueError("Thumbnail URL must be 512 characters or fewer")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError("Thumbnail URL cannot contain whitespace")
    lower = cleaned.lower()
    if lower.startswith(("javascript:", "vbscript:", "data:")):
        raise ValueError("Thumbnail URL uses a prohibited scheme")
    if cleaned.startswith("/api/v1/media/public/"):
        return cleaned
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "Thumbnail URL must be a valid http(s) URL or uploaded media image path"
        )
    return cleaned


def normalize_string_list(
    values: Optional[List[str]],
    *,
    field_label: str,
    lowercase: bool = False,
    max_items: int = 30,
    max_item_length: int = 240,
) -> List[str]:
    """Validate, sanitize, trim, and deduplicate ordered string arrays."""
    if values is None:
        return []
    if len(values) > max_items:
        raise ValueError(f"{field_label} cannot contain more than {max_items} items")
    normalized: List[str] = []
    seen_lower: set[str] = set()
    for raw in values:
        item = sanitize_plain_text(raw, preserve_newlines=False) or ""
        if not item:
            raise ValueError(f"{field_label} items cannot be empty")
        if len(item) > max_item_length:
            raise ValueError(
                f"Each {field_label.lower()} item must be {max_item_length} characters or fewer"
            )
        if lowercase:
            item = item.lower()
        key = item.lower()
        if key not in seen_lower:
            seen_lower.add(key)
            normalized.append(item)
    return normalized


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
    title: str = Field(..., min_length=3, max_length=255, description="Course title (3-255 chars)")
    slug: Optional[str] = Field(None, max_length=255, description="Unique URL-safe slug; generated if omitted")
    headline: Optional[str] = Field(None, max_length=512, description="Short marketing tagline")
    description: Optional[str] = Field(None, max_length=20000, description="Detailed course description")
    thumbnail_url: Optional[str] = Field(None, max_length=512, description="Course card thumbnail image URL")
    thumbnail_media_id: Optional[uuid.UUID] = Field(None, description="Verified MediaAsset UUID for uploaded thumbnail")
    category: str = Field(default="General", min_length=1, max_length=64, description="Course category")
    difficulty_level: str = Field(default="ALL_LEVELS", description="Difficulty: Beginner, Intermediate, Advanced, All Levels")
    language: str = Field(default="English", min_length=1, max_length=32, description="Course instruction language")
    learning_outcomes: List[str] = Field(default_factory=list, description="Ordered learning outcomes")
    requirements: List[str] = Field(default_factory=list, description="Ordered course prerequisites")
    price_inr: int = Field(default=0, ge=0, description="Effective selling price in paise (e.g. 499900 for ₹4,999.00)")
    compare_at_price_inr: Optional[int] = Field(
        None,
        gt=0,
        description="Optional higher regular price in paise when a discount is applied",
    )
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO currency code (INR)")
    is_free: bool = Field(default=False, description="Whether the course is free of charge")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if len(cleaned) < 3:
            raise ValueError("Course title must be at least 3 characters")
        if len(cleaned) > 255:
            raise ValueError("Course title must be 255 characters or fewer")
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

    @field_validator("headline")
    @classmethod
    def validate_headline(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = sanitize_plain_text(v, preserve_newlines=False, max_length=512)
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return sanitize_plain_text(v, preserve_newlines=True, max_length=20000)

    @field_validator("thumbnail_url")
    @classmethod
    def validate_thumbnail(cls, v: Optional[str]) -> Optional[str]:
        return validate_safe_thumbnail_url(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if not cleaned:
            raise ValueError("Category cannot be empty")
        if len(cleaned) > 64:
            raise ValueError("Category must be 64 characters or fewer")
        return cleaned

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        return normalize_difficulty_level(v) or DIFFICULTY_ALL_LEVELS

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if not cleaned:
            raise ValueError("Language cannot be empty")
        if len(cleaned) > 32:
            raise ValueError("Language must be 32 characters or fewer")
        return cleaned

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned != DEFAULT_CURRENCY_INR:
            raise ValueError("Currency must be INR")
        return cleaned

    @field_validator("learning_outcomes")
    @classmethod
    def validate_learning_outcomes(cls, v: List[str]) -> List[str]:
        return normalize_string_list(v, field_label="Learning outcome", max_items=30, max_item_length=240)

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, v: List[str]) -> List[str]:
        return normalize_string_list(v, field_label="Requirement", max_items=30, max_item_length=240)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        return normalize_string_list(v, field_label="Tag", lowercase=True, max_items=20, max_item_length=64)

    @model_validator(mode="after")
    def validate_pricing_invariants(self) -> "CourseCreateRequest":
        if self.is_free:
            if self.price_inr != 0:
                raise ValueError("Free courses must have price_inr equal to 0")
            if self.compare_at_price_inr is not None:
                raise ValueError("Free courses cannot set a regular/compare-at price")
        else:
            if self.price_inr <= 0:
                raise ValueError("Paid courses must have a selling price greater than 0 INR")
            if self.compare_at_price_inr is not None:
                if self.compare_at_price_inr < self.price_inr:
                    raise ValueError("Discounted selling price cannot exceed regular price")
                if self.compare_at_price_inr == self.price_inr:
                    self.compare_at_price_inr = None
        return self


class CourseUpdateRequest(BaseModel):
    """Payload for updating top-level course container metadata."""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    headline: Optional[str] = Field(None, max_length=512)
    description: Optional[str] = Field(None, max_length=20000)
    thumbnail_url: Optional[str] = Field(None, max_length=512)
    thumbnail_media_id: Optional[uuid.UUID] = None
    category: Optional[str] = Field(None, min_length=1, max_length=64)
    difficulty_level: Optional[str] = None
    language: Optional[str] = Field(None, min_length=1, max_length=32)
    learning_outcomes: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    price_inr: Optional[int] = Field(None, ge=0)
    compare_at_price_inr: Optional[int] = Field(None, gt=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    is_free: Optional[bool] = None
    tags: Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if len(cleaned) < 3:
            raise ValueError("Course title must be at least 3 characters")
        if len(cleaned) > 255:
            raise ValueError("Course title must be 255 characters or fewer")
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

    @field_validator("headline")
    @classmethod
    def validate_headline(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return sanitize_plain_text(v, preserve_newlines=False, max_length=512)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return sanitize_plain_text(v, preserve_newlines=True, max_length=20000)

    @field_validator("thumbnail_url")
    @classmethod
    def validate_thumbnail(cls, v: Optional[str]) -> Optional[str]:
        return validate_safe_thumbnail_url(v)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if not cleaned:
            raise ValueError("Category cannot be empty")
        if len(cleaned) > 64:
            raise ValueError("Category must be 64 characters or fewer")
        return cleaned

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty(cls, v: Optional[str]) -> Optional[str]:
        return normalize_difficulty_level(v)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = sanitize_plain_text(v, preserve_newlines=False) or ""
        if not cleaned:
            raise ValueError("Language cannot be empty")
        if len(cleaned) > 32:
            raise ValueError("Language must be 32 characters or fewer")
        return cleaned

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        if cleaned != DEFAULT_CURRENCY_INR:
            raise ValueError("Currency must be INR")
        return cleaned

    @field_validator("learning_outcomes")
    @classmethod
    def validate_learning_outcomes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        return normalize_string_list(v, field_label="Learning outcome", max_items=30, max_item_length=240)

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        return normalize_string_list(v, field_label="Requirement", max_items=30, max_item_length=240)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        return normalize_string_list(v, field_label="Tag", lowercase=True, max_items=20, max_item_length=64)

    @model_validator(mode="after")
    def validate_partial_pricing(self) -> "CourseUpdateRequest":
        if self.is_free is True:
            if self.price_inr is not None and self.price_inr != 0:
                raise ValueError("Free courses must have price_inr equal to 0")
            if self.compare_at_price_inr is not None:
                raise ValueError("Free courses cannot set a regular/compare-at price")
        if (
            self.price_inr is not None
            and self.compare_at_price_inr is not None
            and self.compare_at_price_inr < self.price_inr
        ):
            raise ValueError("Discounted selling price cannot exceed regular price")
        return self


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
    thumbnail_media_id: Optional[uuid.UUID] = None
    category: str = "General"
    difficulty_level: str = "ALL_LEVELS"
    language: str = "English"
    status: str
    price_inr: int
    compare_at_price_inr: Optional[int] = None
    currency: str = "INR"
    discount_percentage: Optional[int] = None
    is_free: bool
    tags: List[str] = Field(default_factory=list)
    live_revision_id: Optional[uuid.UUID] = None
    draft_revision_id: Optional[uuid.UUID] = None
    latest_revision_id: Optional[uuid.UUID] = None
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
    thumbnail_media_id: Optional[uuid.UUID] = None
    category: str = "General"
    difficulty_level: str = "ALL_LEVELS"
    language: str = "English"
    learning_outcomes: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    status: str
    price_inr: int
    compare_at_price_inr: Optional[int] = None
    currency: str = "INR"
    discount_percentage: Optional[int] = None
    is_free: bool
    tags: List[str] = Field(default_factory=list)
    live_revision_id: Optional[uuid.UUID] = None
    draft_revision_id: Optional[uuid.UUID] = None
    latest_revision_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    curriculum: List[CurriculumSectionResponse] = Field(default_factory=list)


class CourseSlugCheckResponse(BaseModel):
    """Slug uniqueness verification response for real-time form validation."""
    slug: str
    available: bool
    reason: Optional[str] = None


class CourseMetadataOptionItem(BaseModel):
    value: str
    label: str


class CourseMetadataOptionsResponse(BaseModel):
    """Canonical metadata taxonomy options returned to admin forms & catalog filters."""
    categories: List[str] = Field(default_factory=lambda: list(DEFAULT_COURSE_CATEGORIES))
    difficulty_levels: List[CourseMetadataOptionItem] = Field(
        default_factory=lambda: [
            CourseMetadataOptionItem(value=k, label=v)
            for k, v in DIFFICULTY_LEVEL_LABELS.items()
        ]
    )
    languages: List[str] = Field(default_factory=lambda: list(DEFAULT_COURSE_LANGUAGES))
    currencies: List[str] = Field(default_factory=lambda: [DEFAULT_CURRENCY_INR])


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
