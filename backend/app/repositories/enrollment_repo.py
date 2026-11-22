"""Student Course Enrollment data access repository.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601, TASK602, TASK603, TASK604)
"""

from datetime import datetime
from typing import List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)


class EnrollmentRepository:
    """Persistence operations for course enrollments."""

    def create_or_activate_enrollment(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        order_id: Optional[uuid.UUID] = None,
        expires_at: Optional[datetime] = None,
    ) -> Enrollment:
        """Atomically provisions or reactivates student course access.

        Guarantees idempotency: if enrollment row already exists for (student_id, course_id),
        reactivates access without raising unique constraint violation.
        """
        stmt = select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
        )
        existing = session.execute(stmt).scalars().first()

        if existing:
            if existing.status != ENROLLMENT_STATUS_ACTIVE:
                existing.status = ENROLLMENT_STATUS_ACTIVE
                existing.granted_at = utc_now()
                existing.expires_at = expires_at
                existing.revoked_at = None
                existing.revoked_reason = None
            if order_id is not None:
                existing.order_id = order_id
            session.flush()
            return existing

        enrollment = Enrollment(
            student_id=student_id,
            course_id=course_id,
            order_id=order_id,
            status=ENROLLMENT_STATUS_ACTIVE,
            granted_at=utc_now(),
            expires_at=expires_at,
        )
        session.add(enrollment)
        session.flush()
        return enrollment

    def get_by_id(
        self,
        session: Session,
        enrollment_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Enrollment]:
        """Fetch enrollment by UUID with optional row-level lock."""
        stmt = select(Enrollment).where(Enrollment.id == enrollment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def get_by_student_and_course(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Enrollment]:
        """Fetch enrollment by student and course composite key."""
        stmt = select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def has_active_enrollment(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> bool:
        """Returns True if student possesses an active, unexpired enrollment in target course."""
        enrollment = self.get_by_student_and_course(session, student_id, course_id)
        if not enrollment:
            return False
        return enrollment.is_access_valid

    def list_student_enrollments(
        self,
        session: Session,
        student_id: uuid.UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Enrollment], int]:
        """Returns paginated course enrollments for a student."""
        base_query = select(Enrollment).where(Enrollment.student_id == student_id)
        count_query = select(func.count(Enrollment.id)).where(Enrollment.student_id == student_id)

        if status:
            base_query = base_query.where(Enrollment.status == status)
            count_query = count_query.where(Enrollment.status == status)

        total = session.execute(count_query).scalar_one()
        stmt = base_query.order_by(desc(Enrollment.granted_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    def list_all_enrollments(
        self,
        session: Session,
        course_id: Optional[uuid.UUID] = None,
        student_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Enrollment], int]:
        """Returns paginated platform enrollments for administrators."""
        base_query = select(Enrollment)
        count_query = select(func.count(Enrollment.id))

        if course_id:
            base_query = base_query.where(Enrollment.course_id == course_id)
            count_query = count_query.where(Enrollment.course_id == course_id)
        if student_id:
            base_query = base_query.where(Enrollment.student_id == student_id)
            count_query = count_query.where(Enrollment.student_id == student_id)
        if status:
            base_query = base_query.where(Enrollment.status == status)
            count_query = count_query.where(Enrollment.status == status)

        total = session.execute(count_query).scalar_one()
        stmt = base_query.order_by(desc(Enrollment.granted_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    def revoke_enrollment(
        self,
        session: Session,
        enrollment: Enrollment,
        reason: str = "ADMINISTRATIVE_REVOCATION",
    ) -> Enrollment:
        """Terminates student course access with recorded revocation timestamp and reason."""
        enrollment.status = ENROLLMENT_STATUS_REVOKED
        enrollment.revoked_at = utc_now()
        enrollment.revoked_reason = reason
        session.flush()
        return enrollment

    def expire_enrollment(
        self,
        session: Session,
        enrollment: Enrollment,
    ) -> Enrollment:
        """Transitions enrollment to EXPIRED status."""
        enrollment.status = ENROLLMENT_STATUS_EXPIRED
        session.flush()
        return enrollment
