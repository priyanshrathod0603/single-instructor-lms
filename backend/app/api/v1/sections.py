"""Curriculum Section management and lesson sequencing REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.4)
- docs/backend/11-COURSE-MANAGEMENT.md (Section 5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK303)
"""

import logging
from typing import List
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permissions
from app.core.permissions import COURSE_EDIT
from app.models.user import User
from app.schemas.course import (
    CurriculumLessonResponse,
    CurriculumSectionResponse,
    LessonCreateRequest,
    LessonReorderRequest,
    SectionUpdateRequest,
)
from app.services.course_service import CourseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sections", tags=["Curriculum Sections"])


def get_course_service() -> CourseService:
    """Dependency providing CourseService instance."""
    return CourseService()


@router.patch(
    "/{id}",
    response_model=CurriculumSectionResponse,
    summary="Update section title and description",
)
def update_section_endpoint(
    id: uuid.UUID,
    data: SectionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CurriculumSectionResponse:
    """Update section metadata in a draft revision. Requires course:edit."""
    return course_service.update_section(db, id, data)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove section and child lessons from draft",
)
def delete_section_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> None:
    """Delete a section and its child lessons and resources. Requires course:edit."""
    course_service.delete_section(db, id)


@router.post(
    "/{id}/lessons",
    response_model=CurriculumLessonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add lesson to section",
)
def add_lesson_endpoint(
    id: uuid.UUID,
    data: LessonCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CurriculumLessonResponse:
    """Add a new lesson to a section in a draft revision. Requires course:edit."""
    return course_service.add_lesson(db, id, data)


@router.put(
    "/{id}/lessons/reorder",
    response_model=List[CurriculumLessonResponse],
    summary="Bulk reorder lessons within section with version check",
)
def reorder_lessons_endpoint(
    id: uuid.UUID,
    data: LessonReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> List[CurriculumLessonResponse]:
    """Bulk reorder lessons within a section.

    Guarded by optimistic concurrency check (version_timestamp vs revision.updated_at).
    Requires course:edit.
    """
    return course_service.reorder_lessons(db, id, data)
