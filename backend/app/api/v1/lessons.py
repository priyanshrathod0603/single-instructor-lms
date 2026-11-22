"""Curriculum Lesson and Resource management REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.4)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK303)
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import (
    check_course_access,
    get_db,
    get_optional_current_user,
    require_permissions,
)
from app.core.exceptions import ForbiddenException, ResourceNotFoundException
from app.core.permissions import COURSE_EDIT
from app.models.course import (
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import CurriculumSection
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.schemas.course import (
    CurriculumLessonResponse,
    LessonResourceResponse,
    LessonUpdateRequest,
    ResourceCreateRequest,
)
from app.services.course_service import CourseService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Curriculum Lessons"])


def get_course_service() -> CourseService:
    """Dependency providing CourseService instance."""
    return CourseService()


@router.get(
    "/lessons/{id}",
    response_model=CurriculumLessonResponse,
    summary="Retrieve lesson details and content",
)
def get_lesson_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    course_service: CourseService = Depends(get_course_service),
) -> CurriculumLessonResponse:
    """Retrieve lesson details.

    Allowed if:
    - Lesson is flagged as preview (`is_preview=True`).
    - Caller has `course:edit` permission or elevated staff role.
    - Caller is enrolled in the course (or student access).
    """
    lesson = course_service.get_lesson(db, id)

    # 1. Resolve parent course revision and course for this lesson
    parent_info = (
        db.query(
            CourseRevision.id,
            CourseRevision.course_id,
            CourseRevision.status,
            Course.status,
            Course.live_revision_id,
        )
        .join(CurriculumSection, CurriculumSection.course_revision_id == CourseRevision.id)
        .join(Course, Course.id == CourseRevision.course_id)
        .filter(CurriculumSection.id == lesson.section_id)
        .first()
    )
    if not parent_info:
        raise ResourceNotFoundException("Course", f"associated with lesson {id}")

    rev_id, course_id, rev_status, course_status, live_rev_id = parent_info

    # 2. Elevated role or course:edit permission has authorized access (including drafts & archived)
    if current_user is not None:
        is_elevated = any(r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        has_perm = current_user.has_permission(COURSE_EDIT)
        if is_elevated or has_perm:
            return lesson

    # 3. Preview access validation (P0-03):
    # Free preview is ONLY granted if parent course is PUBLISHED and lesson belongs to live revision.
    # Prevents draft/unpublished/archived course disclosure.
    if lesson.is_preview:
        if (
            course_status == COURSE_STATUS_PUBLISHED
            and rev_status == REVISION_STATUS_PUBLISHED
            and live_rev_id == rev_id
        ):
            return lesson

        raise ForbiddenException(
            message="Preview access is only available for published courses.",
            code="COURSE_NOT_PUBLISHED",
        )

    # 4. If unauthenticated and not an authorized preview lesson, authentication is required
    if current_user is None:
        raise ForbiddenException(
            message="Enrollment or instructor permissions required to access this lesson.",
            code="ENROLLMENT_REQUIRED",
        )

    # 5. Enforce active enrollment for student
    check_course_access(course_id, current_user, db)
    return lesson


@router.patch(
    "/lessons/{id}",
    response_model=CurriculumLessonResponse,
    summary="Update lesson content, duration, preview flag",
)
def update_lesson_endpoint(
    id: uuid.UUID,
    data: LessonUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CurriculumLessonResponse:
    """Update lesson properties in a draft revision. Requires course:edit."""
    return course_service.update_lesson(db, id, data)


@router.delete(
    "/lessons/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove lesson from section",
)
def delete_lesson_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> None:
    """Delete a lesson and its child resources. Requires course:edit."""
    course_service.delete_lesson(db, id)


@router.post(
    "/lessons/{id}/resources",
    response_model=LessonResourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach downloadable or external resource to lesson",
)
def add_resource_endpoint(
    id: uuid.UUID,
    data: ResourceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> LessonResourceResponse:
    """Attach a resource (PDF, code, link) to a lesson in a draft revision. Requires course:edit."""
    return course_service.add_resource(db, id, data)


@router.delete(
    "/resources/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete resource from lesson",
)
def delete_resource_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> None:
    """Delete a resource. Requires course:edit."""
    course_service.delete_resource(db, id)
