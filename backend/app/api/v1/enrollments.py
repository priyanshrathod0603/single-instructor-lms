"""Student Course Enrollment REST API endpoints.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.8)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK603, TASK604)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-012)
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
)
from app.core.permissions import (
    ENROLLMENT_GRANT,
    ENROLLMENT_REVOKE,
    ENROLLMENT_VIEW_ALL,
    ENROLLMENT_VIEW_OWN,
)
from app.models.user import User
from app.schemas.enrollment import (
    EnrollmentCheckResponse,
    EnrollmentListResponse,
    EnrollmentResponse,
    EnrollmentRevokeRequest,
    ManualEnrollmentGrantRequest,
)
from app.services.enrollment_service import EnrollmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])


def get_enrollment_service() -> EnrollmentService:
    """Dependency providing EnrollmentService instance."""
    return EnrollmentService()


@router.get(
    "",
    response_model=EnrollmentListResponse,
    summary="List enrolled courses for current student",
)
def list_own_enrollments_endpoint(
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, REVOKED, EXPIRED"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ENROLLMENT_VIEW_OWN)),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> EnrollmentListResponse:
    """Returns paginated course enrollments for the requesting student user."""
    return service.list_student_enrollments(
        session=db,
        student_id=current_user.id,
        status=status,
        page=page,
        size=size,
    )


@router.get(
    "/all",
    response_model=EnrollmentListResponse,
    summary="List all platform course enrollments for administrators",
)
def list_all_enrollments_endpoint(
    course_id: Optional[uuid.UUID] = Query(None, description="Filter by course UUID"),
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student user UUID"),
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, REVOKED, EXPIRED"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ENROLLMENT_VIEW_ALL)),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> EnrollmentListResponse:
    """Returns paginated platform-wide enrollments. Restricted strictly to administrators."""
    return service.list_all_enrollments(
        session=db,
        course_id=course_id,
        student_id=student_id,
        status=status,
        page=page,
        size=size,
    )


@router.post(
    "/grant-manual",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually provision student course enrollment (scholarship / admin override)",
)
def grant_manual_enrollment_endpoint(
    data: ManualEnrollmentGrantRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ENROLLMENT_GRANT)),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> EnrollmentResponse:
    """Administrative manual course provisioning without commercial gateway checkout.

    Emits durable outbox notification and records immutable security audit log.
    """
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.grant_manual_enrollment(
        session=db,
        student_id=data.student_id,
        course_id=data.course_id,
        expires_at=data.expires_at,
        reason=data.reason,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.patch(
    "/{id}/revoke",
    response_model=EnrollmentResponse,
    summary="Revoke active course enrollment for a student",
)
def revoke_enrollment_endpoint(
    id: uuid.UUID,
    data: EnrollmentRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ENROLLMENT_REVOKE)),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> EnrollmentResponse:
    """Terminates student course access with recorded justification and timestamp.

    Emits durable outbox notification and records immutable security audit log.
    """
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.revoke_enrollment(
        session=db,
        enrollment_id=id,
        reason=data.reason,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.get(
    "/check/{course_id}",
    response_model=EnrollmentCheckResponse,
    summary="Quick boolean access check for current user",
)
def check_enrollment_endpoint(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> EnrollmentCheckResponse:
    """Evaluates whether the caller has an active, unexpired enrollment in target course."""
    return service.check_access(
        session=db,
        student_id=current_user.id,
        course_id=course_id,
    )
