"""Pydantic v2 schemas for lesson progress and course progress summaries.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902)
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class LessonProgressHeartbeatRequest(BaseModel):
    """Payload for recording video playback heartbeats or article completion toggles."""

    model_config = ConfigDict(extra="forbid")

    watch_position_seconds: int = Field(
        default=0,
        ge=0,
        description="Furthest playback position reached by student in seconds",
    )
    is_completed: Optional[bool] = Field(
        default=None,
        description="Optional manual completion toggle (applicable to article lessons)",
    )


class CourseProgressSummaryResponse(BaseModel):
    """Aggregated course completion metrics for student dashboard."""

    model_config = ConfigDict(from_attributes=True)

    course_id: uuid.UUID
    completed_lessons_count: int
    total_lessons_count: int
    progress_percentage: Decimal = Field(..., decimal_places=2)
    is_completed: bool
    completed_lesson_ids: list[uuid.UUID] = Field(default_factory=list)
    last_activity_at: datetime


class LessonProgressResponse(BaseModel):
    """Granular lesson completion and playback state."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: uuid.UUID
    is_completed: bool
    watch_position_seconds: int
    completed_at: Optional[datetime] = None
    course_progress: Optional[CourseProgressSummaryResponse] = None
