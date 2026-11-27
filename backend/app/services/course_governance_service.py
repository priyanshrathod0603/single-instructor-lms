"""Domain service for Super Admin Course Governance (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 3)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
"""

from datetime import datetime
import logging
from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import BadRequestException, ResourceNotFoundException
from app.models.audit_log import AuditLog
from app.models.base import utc_now
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    VALID_COURSE_STATUSES,
    Course,
    CourseRevision,
    CourseTag,
)
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import Enrollment, ENROLLMENT_STATUS_ACTIVE
from app.models.user import User
from app.schemas.control import (
    CourseGovernanceItemResponse,
    CourseGovernanceListResponse,
)

logger = logging.getLogger(__name__)


class CourseGovernanceService:
    """Super Admin Course Governance domain service."""

    def _compute_curriculum_stats(
        self,
        db: Session,
        course: Course,
    ) -> dict[str, Any]:
        """Compute aggregated curriculum metrics for a course."""
        target_rev_id = course.live_revision_id
        if not target_rev_id:
            # Check for latest revision
            latest_rev = (
                db.query(CourseRevision)
                .filter(CourseRevision.course_id == course.id)
                .order_by(desc(CourseRevision.revision_no))
                .first()
            )
            if latest_rev:
                target_rev_id = latest_rev.id

        total_sections = 0
        total_lessons = 0
        total_duration = 0
        has_quiz = False
        has_assignment = False

        if target_rev_id:
            sections = (
                db.query(CurriculumSection)
                .options(selectinload(CurriculumSection.lessons))
                .filter(CurriculumSection.course_revision_id == target_rev_id)
                .all()
            )
            total_sections = len(sections)
            for s in sections:
                total_lessons += len(s.lessons)
                for lesson in s.lessons:
                    total_duration += lesson.duration_seconds or 0
                    if lesson.lesson_type == "QUIZ":
                        has_quiz = True
                    elif lesson.lesson_type == "ASSIGNMENT":
                        has_assignment = True

        enrolled_count = (
            db.query(func.count(Enrollment.id))
            .filter(
                Enrollment.course_id == course.id,
                Enrollment.status == ENROLLMENT_STATUS_ACTIVE,
            )
            .scalar()
            or 0
        )

        return {
            "total_sections": total_sections,
            "total_lessons": total_lessons,
            "total_duration_seconds": total_duration,
            "has_quiz": has_quiz,
            "has_assignment": has_assignment,
            "enrolled_students_count": enrolled_count,
        }

    def _to_item_response(
        self,
        db: Session,
        course: Course,
    ) -> CourseGovernanceItemResponse:
        """Serialize course with curriculum stats into response model."""
        stats = self._compute_curriculum_stats(db, course)
        tags = [t.tag for t in course.tags] if course.tags else []

        draft_rev_id: Optional[uuid.UUID] = None
        latest_rev_id: Optional[uuid.UUID] = None
        if course.revisions:
            for rev in course.revisions:
                if rev.status == "DRAFT":
                    draft_rev_id = rev.id
                    break
            latest = max(course.revisions, key=lambda r: r.revision_no)
            latest_rev_id = latest.id

        return CourseGovernanceItemResponse(
            id=course.id,
            slug=course.slug,
            title=course.title,
            headline=course.headline,
            description=course.description,
            thumbnail_url=course.thumbnail_url,
            category=course.category,
            difficulty_level=course.difficulty_level,
            language=course.language,
            status=course.status,
            price_inr=course.price_inr,
            compare_at_price_inr=course.compare_at_price_inr,
            currency=course.currency,
            discount_percentage=course.discount_percentage,
            is_free=course.is_free,
            tags=tags,
            live_revision_id=course.live_revision_id,
            draft_revision_id=draft_rev_id,
            latest_revision_id=latest_rev_id,
            total_sections=stats["total_sections"],
            total_lessons=stats["total_lessons"],
            total_duration_seconds=stats["total_duration_seconds"],
            has_quiz=stats["has_quiz"],
            has_assignment=stats["has_assignment"],
            enrolled_students_count=stats["enrolled_students_count"],
            created_at=course.created_at,
            updated_at=course.updated_at,
        )

    def list_governed_courses(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> CourseGovernanceListResponse:
        """Paginated course list with search, status filtering, and enriched curriculum stats."""
        query = select(Course).options(
            selectinload(Course.tags),
            selectinload(Course.revisions),
            selectinload(Course.live_revision),
        )

        base_count_query = select(Course.id)

        if status and status.upper() != "ALL":
            query = query.where(Course.status == status.upper())
            base_count_query = base_count_query.where(Course.status == status.upper())

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            clause = or_(
                func.lower(Course.title).like(term),
                func.lower(Course.slug).like(term),
                func.lower(Course.headline).like(term),
            )
            query = query.where(clause)
            base_count_query = base_count_query.where(clause)

        # Count total matching courses
        count_stmt = select(func.count()).select_from(base_count_query.subquery())
        total = db.scalar(count_stmt) or 0

        # Sorting
        sort_col = getattr(Course, sort_by, Course.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        query = query.offset(offset).limit(per_page)

        courses = list(db.scalars(query).unique().all())
        items = [self._to_item_response(db, c) for c in courses]
        pages = (total + per_page - 1) // per_page if total > 0 else 0

        return CourseGovernanceListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    def get_course_governance_detail(
        self,
        db: Session,
        course_id: uuid.UUID,
    ) -> CourseGovernanceItemResponse:
        """Fetch detailed course governance information."""
        stmt = (
            select(Course)
            .options(
                selectinload(Course.tags),
                selectinload(Course.revisions),
                selectinload(Course.live_revision),
            )
            .where(Course.id == course_id)
        )
        course = db.scalar(stmt)
        if not course:
            raise ResourceNotFoundException("Course", str(course_id))
        return self._to_item_response(db, course)

    async def update_course_status(
        self,
        db: Session,
        current_user: User,
        course_id: uuid.UUID,
        target_status: str,
        reason: Optional[str] = None,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CourseGovernanceItemResponse:
        """Transition course status (DRAFT, PUBLISHED, ARCHIVED) with canonical checklist validation and audit tracking."""
        target_status = target_status.strip().upper()
        if target_status not in VALID_COURSE_STATUSES:
            raise BadRequestException(f"Invalid course status '{target_status}'. Must be one of {sorted(VALID_COURSE_STATUSES)}")

        stmt = (
            select(Course)
            .options(
                selectinload(Course.tags),
                selectinload(Course.revisions),
                selectinload(Course.live_revision),
            )
            .where(Course.id == course_id)
            .with_for_update()
        )
        course = db.scalar(stmt)
        if not course:
            raise ResourceNotFoundException("Course", str(course_id))

        old_status = course.status
        if old_status == target_status:
            return self._to_item_response(db, course)

        # Enforce canonical publication workflow and checklist (P0-04)
        if target_status == COURSE_STATUS_PUBLISHED:
            # If the course already has an active, valid published live revision, re-activation is allowed
            if course.live_revision_id and course.live_revision and course.live_revision.status == "PUBLISHED":
                course.status = COURSE_STATUS_PUBLISHED
            else:
                # Find the latest revision
                latest_rev = (
                    db.query(CourseRevision)
                    .filter(CourseRevision.course_id == course.id)
                    .order_by(desc(CourseRevision.revision_no))
                    .first()
                )
                if not latest_rev:
                    raise BadRequestException("Cannot publish course without any curriculum revision.")

                if latest_rev.status == "PUBLISHED":
                    course.live_revision_id = latest_rev.id
                    course.status = COURSE_STATUS_PUBLISHED
                else:
                    # Execute canonical CourseService.publish_revision to strictly validate:
                    # - Pre-flight checklist conditions (sections, lessons, durations, quizzes, assignments)
                    # - Curriculum snapshot generation
                    # - Prior revision archival
                    # - Atomic live revision update
                    from app.services.course_service import CourseService
                    course_service = CourseService()
                    await course_service.publish_revision(
                        db,
                        course.id,
                        latest_rev.id,
                        actor_id=current_user.id,
                        reason=reason,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    db.add(
                        AuditLog(
                            actor_id=current_user.id,
                            actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                            action="COURSE_STATUS_CHANGED",
                            resource_type="course",
                            resource_id=str(course.id),
                            before_state={"status": old_status},
                            after_state={"status": target_status, "reason": reason},
                            ip_address=ip_address,
                        )
                    )
                    db.commit()
                    db.refresh(course)
                    return self._to_item_response(db, course)
        else:
            course.status = target_status
        course.updated_at = utc_now()

        # Audit Event
        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="COURSE_STATUS_CHANGED",
                resource_type="course",
                resource_id=str(course.id),
                before_state={"status": old_status},
                after_state={"status": target_status, "reason": reason},
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(course)
        return self._to_item_response(db, course)
