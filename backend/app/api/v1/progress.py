"""Student Progress REST API endpoints.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
)
from app.models.user import User
from app.schemas.progress import (
    CourseProgressSummaryResponse,
    LessonProgressHeartbeatRequest,
    LessonProgressResponse,
)
from app.services.progress_service import ProgressService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["Progress"])


def get_progress_service() -> ProgressService:
    """Dependency providing ProgressService instance."""
    return ProgressService()


@router.post(
    "/lessons/{lesson_id}",
    response_model=LessonProgressResponse,
    status_code=status.HTTP_200_OK,
    summary="Record video watch seconds or toggle completion for a lesson",
)
def record_lesson_progress_endpoint(
    lesson_id: uuid.UUID,
    payload: LessonProgressHeartbeatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> LessonProgressResponse:
    """Record video playback position or article completion, validating enrollment and server rules."""
    return service.record_lesson_progress(
        session=db,
        student=current_user,
        lesson_id=lesson_id,
        watch_position_seconds=payload.watch_position_seconds,
        is_completed=payload.is_completed,
    )


@router.get(
    "/courses/{course_id}",
    response_model=CourseProgressSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get course progress summary and completed lessons for current student",
)
def get_course_progress_endpoint(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ProgressService = Depends(get_progress_service),
) -> CourseProgressSummaryResponse:
    """Retrieve aggregated course progress metrics and list of completed lesson IDs."""
    return service.get_course_progress(
        session=db,
        student=current_user,
        course_id=course_id,
    )
