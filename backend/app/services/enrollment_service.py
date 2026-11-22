"""Student Course Enrollment domain service.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.8)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601, TASK602, TASK603, TASK604)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-012)

Strict Invariants:
1. Zero Trust on Browser Redirect: Paid enrollments are granted exclusively upon verified webhook.
2. Administrative Grants: Admins can manually grant or revoke access with mandatory audit records.
3. Access Invalidation: Revocation or expiration immediately terminates student access.
4. Transactional Outbox: State mutations emit durable notifications for email delivery.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenException, ResourceNotFoundException
from app.models.course import COURSE_STATUS_PUBLISHED, Course
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.notification import NotificationOutbox
from app.models.user import User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.notification_repo import NotificationOutboxRepository
from app.schemas.enrollment import (
    EnrollmentCheckResponse,
    EnrollmentListResponse,
    EnrollmentResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _to_enrollment_response(enrollment: Enrollment) -> EnrollmentResponse:
    """Helper to convert Enrollment model to Pydantic EnrollmentResponse."""
    return EnrollmentResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        order_id=enrollment.order_id,
        status=enrollment.status,
        granted_at=enrollment.granted_at,
        expires_at=enrollment.expires_at,
        revoked_at=enrollment.revoked_at,
        revoked_reason=enrollment.revoked_reason,
        course_title=enrollment.course.title if enrollment.course else None,
        course_slug=enrollment.course.slug if enrollment.course else None,
    )


class EnrollmentService:
    """Domain service managing student course enrollments and access rights."""

    def __init__(
        self,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_repo: Optional[NotificationOutboxRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.enrollment_repo = enrollment_repo or EnrollmentRepository()
        self.audit_service = audit_service or AuditService()
        self.outbox_repo = outbox_repo or NotificationOutboxRepository()
        self.settings = settings or get_settings()

    def _log_audit(
        self,
        session: Session,
        action: str,
        resource_id: str,
        actor_id: Optional[uuid.UUID] = None,
        actor_type: str = "SYSTEM",
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
        request_context: Optional[Any] = None,
    ) -> None:
        """Internal helper to record audit logs synchronously."""
        req_id, ip, ua = None, None, None
        if isinstance(request_context, tuple) and len(request_context) == 3:
            req_id, ip, ua = request_context
        elif isinstance(request_context, dict):
            req_id = request_context.get("request_id")
            ip = request_context.get("ip_address")
            ua = request_context.get("user_agent")

        self.audit_service.record_sync_event(
            session=session,
            action=action,
            resource_type="enrollment",
            resource_id=resource_id,
            actor_id=actor_id,
            actor_type=actor_type,
            before_state=before_state,
            after_state=after_state,
            request_id=req_id,
            ip_address=ip,
            user_agent=ua,
        )

    def _emit_outbox_event(
        self,
        session: Session,
        event_type: str,
        recipient_email: str,
        subject: str,
        payload: dict[str, Any],
        dedupe_key: Optional[str] = None,
    ) -> None:
        """Helper to create durable outbox notification records."""
        if not recipient_email:
            return
        outbox_item = NotificationOutbox(
            event_type=event_type,
            channel="EMAIL",
            recipient=recipient_email,
            subject=subject,
            payload=payload,
            dedupe_key=dedupe_key,
            status="PENDING",
        )
        session.add(outbox_item)

    def grant_manual_enrollment(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        expires_at: Optional[datetime] = None,
        reason: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        request_context: Optional[Any] = None,
    ) -> EnrollmentResponse:
        """Manually provisions or reactivates student course access without payment.

        Restricted strictly to administrators with enrollment:grant permission.
        """
        # 1. Verify student exists and is active
        student = session.get(User, student_id)
        if not student:
            raise ResourceNotFoundException("User", str(student_id))
        if not student.is_active:
            raise ForbiddenException(
                message="Cannot grant enrollment to a suspended user account",
                code="ACCOUNT_SUSPENDED",
            )

        # 2. Verify course exists
        course = session.get(Course, course_id)
        if not course:
            raise ResourceNotFoundException("Course", str(course_id))

        # 3. Create or activate enrollment row idempotently
        enrollment = self.enrollment_repo.create_or_activate_enrollment(
            session=session,
            student_id=student_id,
            course_id=course_id,
            order_id=None,
            expires_at=expires_at,
        )

        # 4. Outbox notification for student
        self._emit_outbox_event(
            session=session,
            event_type="ENROLLMENT_MANUAL_GRANTED",
            recipient_email=student.email,
            subject=f"Access Granted to Course: {course.title}",
            payload={
                "student_id": str(student.id),
                "course_id": str(course.id),
                "course_title": course.title,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "reason": reason,
            },
            dedupe_key=f"manual_grant_{student.id}_{course.id}_{uuid.uuid4().hex[:8]}",
        )

        # 5. Immutable security audit record
        self._log_audit(
            session=session,
            action="ENROLLMENT_MANUALLY_GRANTED",
            resource_id=str(enrollment.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            after_state={
                "id": str(enrollment.id),
                "student_id": str(student_id),
                "course_id": str(course_id),
                "status": enrollment.status,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "reason": reason,
            },
            request_context=request_context,
        )

        return _to_enrollment_response(enrollment)

    def revoke_enrollment(
        self,
        session: Session,
        enrollment_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> EnrollmentResponse:
        """Revokes active course access for a student.

        Restricted strictly to administrators with enrollment:revoke permission.
        """
        enrollment = self.enrollment_repo.get_by_id(session, enrollment_id, for_update=True)
        if not enrollment:
            raise ResourceNotFoundException("Enrollment", str(enrollment_id))

        before_status = enrollment.status
        revoked = self.enrollment_repo.revoke_enrollment(
            session=session,
            enrollment=enrollment,
            reason=reason,
        )

        # Outbox notification for student
        student_email = revoked.student.email if revoked.student else ""
        course_title = revoked.course.title if revoked.course else "Course"
        self._emit_outbox_event(
            session=session,
            event_type="ENROLLMENT_REVOKED",
            recipient_email=student_email,
            subject=f"Course Access Revoked: {course_title}",
            payload={
                "enrollment_id": str(revoked.id),
                "course_id": str(revoked.course_id),
                "reason": reason,
            },
            dedupe_key=f"revoked_{revoked.id}_{uuid.uuid4().hex[:8]}",
        )

        # Immutable security audit record
        self._log_audit(
            session=session,
            action="ENROLLMENT_REVOKED",
            resource_id=str(revoked.id),
            actor_id=actor_id,
            actor_type="USER",
            before_state={"status": before_status},
            after_state={
                "status": revoked.status,
                "revoked_at": revoked.revoked_at.isoformat() if revoked.revoked_at else None,
                "reason": reason,
            },
            request_context=request_context,
        )

        return _to_enrollment_response(revoked)

    def check_access(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> EnrollmentCheckResponse:
        """Quick boolean verification of student access rights for a specific course."""
        enrollment = self.enrollment_repo.get_by_student_and_course(
            session,
            student_id=student_id,
            course_id=course_id,
        )
        if not enrollment:
            return EnrollmentCheckResponse(
                course_id=course_id,
                is_enrolled=False,
                status=None,
                access_granted=False,
            )

        return EnrollmentCheckResponse(
            course_id=course_id,
            is_enrolled=True,
            status=enrollment.status,
            access_granted=enrollment.is_access_valid,
        )

    def list_student_enrollments(
        self,
        session: Session,
        student_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> EnrollmentListResponse:
        """Returns paginated course enrollments for the requesting student."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.enrollment_repo.list_student_enrollments(
            session=session,
            student_id=student_id,
            status=status,
            skip=skip,
            limit=size,
        )

        return EnrollmentListResponse(
            items=[_to_enrollment_response(e) for e in items],
            total=total,
            page=page,
            size=size,
        )

    def list_all_enrollments(
        self,
        session: Session,
        course_id: Optional[uuid.UUID] = None,
        student_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> EnrollmentListResponse:
        """Returns paginated platform enrollments for administrators."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.enrollment_repo.list_all_enrollments(
            session=session,
            course_id=course_id,
            student_id=student_id,
            status=status,
            skip=skip,
            limit=size,
        )

        return EnrollmentListResponse(
            items=[_to_enrollment_response(e) for e in items],
            total=total,
            page=page,
            size=size,
        )
