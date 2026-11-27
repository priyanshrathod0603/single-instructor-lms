"""Assignment, Rubrics, Project Submissions, and Grading REST API endpoints.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.5)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-008, ADR-012, ADR-013)
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_permissions,
    require_verified_student,
)
from app.core.permissions import (
    ASSIGNMENT_GRADE,
    ASSIGNMENT_MANAGE,
    ASSIGNMENT_OVERRIDE,
    ASSIGNMENT_SUBMIT,
    ASSIGNMENT_VIEW_ALL,
)
from app.models.user import User
from app.schemas.assignment import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentUpdateRequest,
    GradeOverrideRequest,
    GradeOverrideResponse,
    GradeSubmissionRequest,
    RubricCreateRequest,
    RubricResponse,
    SubmissionCreateRequest,
    SubmissionListResponse,
    SubmissionResponse,
)
from app.services.assignment_service import AssignmentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Assignments & Rubric Grading"])


def get_assignment_service() -> AssignmentService:
    """Dependency providing AssignmentService instance."""
    return AssignmentService()


# =============================================================================
# 1. Assignment Configuration & Rubrics (TASK701)
# =============================================================================

@router.post(
    "/lessons/{id}/assignment",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure assignment for a curriculum lesson",
)
def create_lesson_assignment_endpoint(
    id: uuid.UUID,
    data: AssignmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_MANAGE)),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    """Create an assignment configuration attached to a curriculum lesson."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.create_assignment(
        session=db,
        lesson_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.get(
    "/lessons/{id}/assignment",
    response_model=AssignmentResponse,
    summary="Get assignment instructions and active rubric for a lesson",
)
def get_lesson_assignment_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_student),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    """Retrieve assignment details for a lesson. Verifies student enrollment or staff access."""
    return service.get_assignment_by_lesson(
        session=db,
        lesson_id=id,
        current_user=current_user,
    )


@router.get(
    "/assignments/{id}",
    response_model=AssignmentResponse,
    summary="Get assignment details and active rubric",
)
def get_assignment_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_student),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    """Retrieve assignment details. Verifies student enrollment or staff access."""
    return service.get_assignment(
        session=db,
        assignment_id=id,
        current_user=current_user,
    )


@router.patch(
    "/assignments/{id}",
    response_model=AssignmentResponse,
    summary="Update assignment instructions and due date",
)
def update_assignment_endpoint(
    id: uuid.UUID,
    data: AssignmentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_MANAGE)),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    """Update assignment properties. Requires assignment:manage."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.update_assignment(
        session=db,
        assignment_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.post(
    "/assignments/{id}/rubric",
    response_model=RubricResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update rubric version for an assignment",
)
def create_rubric_endpoint(
    id: uuid.UUID,
    data: RubricCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_MANAGE)),
    service: AssignmentService = Depends(get_assignment_service),
) -> RubricResponse:
    """Define a new rubric version for an assignment. Enforces criteria immutability."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.create_or_update_rubric(
        session=db,
        assignment_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


# =============================================================================
# 2. Student Submissions (TASK702)
# =============================================================================

@router.post(
    "/assignments/{id}/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit student project work",
)
def submit_project_endpoint(
    id: uuid.UUID,
    data: SubmissionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_SUBMIT)),
    service: AssignmentService = Depends(get_assignment_service),
) -> SubmissionResponse:
    """Student submits project work (file URL, commentary). Enforces enrollment and deadlines."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.submit_project(
        session=db,
        assignment_id=id,
        data=data,
        student=current_user,
        request_context=req_ctx,
    )


@router.get(
    "/assignments/{id}/submissions",
    response_model=SubmissionListResponse,
    summary="List submissions for grading",
)
def list_assignment_submissions_endpoint(
    id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter by status: SUBMITTED, GRADING, GRADED, REJECTED"),
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student UUID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_VIEW_ALL)),
    service: AssignmentService = Depends(get_assignment_service),
) -> SubmissionListResponse:
    """List submissions for an assignment. Restricted to staff and administrators."""
    return service.list_assignment_submissions(
        session=db,
        assignment_id=id,
        status=status,
        student_id=student_id,
        page=page,
        size=size,
    )


@router.get(
    "/assignments/{id}/my-submissions",
    response_model=SubmissionListResponse,
    summary="List current student's own submissions for an assignment",
)
def list_my_assignment_submissions_endpoint(
    id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_SUBMIT)),
    service: AssignmentService = Depends(get_assignment_service),
) -> SubmissionListResponse:
    """List the authenticated student's own submissions for an assignment."""
    return service.list_own_submissions(
        session=db,
        student_id=current_user.id,
        assignment_id=id,
        page=page,
        size=size,
    )


@router.get(
    "/submissions/{id}",
    response_model=SubmissionResponse,
    summary="View submission details, rubric scores, and grade overrides",
)
def get_submission_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: AssignmentService = Depends(get_assignment_service),
) -> SubmissionResponse:
    """View submission details. Allowed for submission owner student or evaluators."""
    return service.get_submission(
        session=db,
        submission_id=id,
        current_user=current_user,
    )


# =============================================================================
# 3. Rubric Grading (TASK703)
# =============================================================================

@router.post(
    "/submissions/{id}/grade",
    response_model=SubmissionResponse,
    summary="Submit rubric criteria points and qualitative feedback",
)
def grade_submission_endpoint(
    id: uuid.UUID,
    data: GradeSubmissionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_GRADE)),
    service: AssignmentService = Depends(get_assignment_service),
) -> SubmissionResponse:
    """Evaluate submission against active rubric. Calculates weighted score and releases grade."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.grade_submission(
        session=db,
        submission_id=id,
        data=data,
        grader=current_user,
        request_context=req_ctx,
    )


# =============================================================================
# 4. Super Admin Grade Override (TASK704)
# =============================================================================

@router.post(
    "/submissions/{id}/override-grade",
    response_model=GradeOverrideResponse,
    summary="Apply administrative grade override with mandatory justification",
)
def override_grade_endpoint(
    id: uuid.UUID,
    data: GradeOverrideRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ASSIGNMENT_OVERRIDE)),
    service: AssignmentService = Depends(get_assignment_service),
) -> GradeOverrideResponse:
    """Super Admin overrides finalized submission grade with mandatory justification."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.override_grade(
        session=db,
        submission_id=id,
        data=data,
        admin=current_user,
        request_context=req_ctx,
    )
