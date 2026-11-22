"""ProgressService orchestrating lesson completion logic, course summaries, and certificate triggers.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902, TASK903)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Server-Authoritative Evaluation: Video completes at >= 90% watch duration, quizzes upon pass.
2. Anti-Cheating: Students cannot manually complete quizzes or assignments via heartbeat payload.
3. Access Authorization: Progress tracking requires an active, unexpired course enrollment.
4. Materialized Course Summary: Updates completed count and percentage upon every lesson transition.
5. Automated Certificate Pipeline: Triggered when progress reaches 100.00%.
"""

from decimal import Decimal
import logging
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ForbiddenException,
    ResourceNotFoundException,
)
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Course, CourseRevision
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_ASSIGNMENT,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE
from app.models.progress import CourseProgressSummary, LessonProgress
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository
from app.schemas.progress import (
    CourseProgressSummaryResponse,
    LessonProgressResponse,
)
from app.services.certificate_service import CertificateService

logger = logging.getLogger(__name__)


class ProgressService:
    """Service handling lesson progress recording, validation, summary recalculation, and certificate triggers."""

    def __init__(
        self,
        progress_repo: Optional[ProgressRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        certificate_service: Optional[CertificateService] = None,
    ) -> None:
        self.progress_repo = progress_repo or ProgressRepository()
        self.enrollment_repo = enrollment_repo or EnrollmentRepository()
        self.certificate_service = certificate_service or CertificateService()

    def record_lesson_progress(
        self,
        session: Session,
        student: User,
        lesson_id: uuid.UUID,
        watch_position_seconds: int = 0,
        is_completed: Optional[bool] = None,
    ) -> LessonProgressResponse:
        """Record video playback position or article completion, validating enrollment and server rules."""
        # 1. User status checks
        if getattr(student, "status", "ACTIVE") == "SUSPENDED":
            raise ForbiddenException(
                message="Account is suspended. Access denied.",
                code="ACCOUNT_SUSPENDED",
            )
        if not getattr(student, "is_verified", True):
            raise ForbiddenException(
                message="Email address must be verified to track course progress.",
                code="EMAIL_NOT_VERIFIED",
            )

        # 2. Fetch lesson and parent curriculum hierarchy
        lesson = session.get(CurriculumLesson, lesson_id)
        if not lesson:
            raise ResourceNotFoundException(
                message="Lesson not found",
                code="LESSON_NOT_FOUND",
            )

        section = session.get(CurriculumSection, lesson.section_id)
        if not section:
            raise ResourceNotFoundException(
                message="Parent curriculum section not found",
                code="SECTION_NOT_FOUND",
            )

        revision = session.get(CourseRevision, section.course_revision_id)
        if not revision:
            raise ResourceNotFoundException(
                message="Parent course revision not found",
                code="REVISION_NOT_FOUND",
            )

        course_id = revision.course_id
        course = session.get(Course, course_id)
        if not course:
            raise ResourceNotFoundException(
                message="Course not found",
                code="COURSE_NOT_FOUND",
            )

        # 3. Active course enrollment check
        enrollment = self.enrollment_repo.get_by_student_and_course(session, student.id, course_id)
        if not enrollment or not enrollment.is_access_valid:
            raise ForbiddenException(
                message="Active course enrollment required to access lessons and record progress",
                code="ENROLLMENT_REQUIRED",
            )

        # 4. Server-authoritative completion evaluation
        meets_completion = False
        if lesson.lesson_type == LESSON_TYPE_VIDEO:
            if lesson.duration_seconds > 0:
                # Video completes at >= 90% watch duration
                threshold = int(0.90 * lesson.duration_seconds)
                meets_completion = watch_position_seconds >= threshold
            else:
                meets_completion = bool(is_completed) or watch_position_seconds > 0
        elif lesson.lesson_type == LESSON_TYPE_ARTICLE:
            # Articles complete via learner mark-as-completed confirmation
            meets_completion = bool(is_completed)
        elif lesson.lesson_type == LESSON_TYPE_QUIZ:
            # Server-side evaluation: student cannot manually mark quiz complete; requires passing attempt
            quiz = session.execute(
                select(Quiz).where(Quiz.lesson_id == lesson.id)
            ).scalars().first()
            if quiz:
                passed_attempt = session.execute(
                    select(QuizAttempt).where(
                        QuizAttempt.quiz_id == quiz.id,
                        QuizAttempt.student_id == student.id,
                        QuizAttempt.is_passed.is_(True),
                    )
                ).scalars().first()
                meets_completion = passed_attempt is not None
            else:
                meets_completion = bool(is_completed)
        elif lesson.lesson_type == LESSON_TYPE_ASSIGNMENT:
            # Server-side evaluation: requires valid submitted or graded assignment submission
            assignment = session.execute(
                select(Assignment).where(Assignment.lesson_id == lesson.id)
            ).scalars().first()
            if assignment:
                sub = session.execute(
                    select(AssignmentSubmission).where(
                        AssignmentSubmission.assignment_id == assignment.id,
                        AssignmentSubmission.student_id == student.id,
                        AssignmentSubmission.status.in_(["SUBMITTED", "GRADED"]),
                    )
                ).scalars().first()
                meets_completion = sub is not None
            else:
                meets_completion = bool(is_completed)
        else:
            meets_completion = bool(is_completed)

        # 5. Atomic progress UPSERT
        progress_record, transitioned = self.progress_repo.upsert_lesson_progress(
            session=session,
            student_id=student.id,
            lesson_id=lesson.id,
            watch_position_seconds=watch_position_seconds,
            is_completed=meets_completion,
        )

        # 6. Recalculate course progress summary
        summary_response = self.recalculate_course_progress(
            session=session,
            student=student,
            course=course,
            active_revision=revision,
        )

        return LessonProgressResponse(
            lesson_id=lesson.id,
            is_completed=progress_record.is_completed,
            watch_position_seconds=progress_record.watch_position_seconds,
            completed_at=progress_record.completed_at,
            course_progress=summary_response,
        )

    def recalculate_course_progress(
        self,
        session: Session,
        student: User,
        course: Course,
        active_revision: Optional[CourseRevision] = None,
    ) -> CourseProgressSummaryResponse:
        """Recalculate materialized course completion metrics and trigger certificate if 100%."""
        course_id = course.id

        # Determine revision to evaluate against: prefer published revision, fallback to active revision
        published_revision = session.execute(
            select(CourseRevision)
            .where(
                CourseRevision.course_id == course_id,
                CourseRevision.status == "PUBLISHED",
            )
            .order_by(CourseRevision.revision_no.desc())
        ).scalars().first()

        target_revision = published_revision or active_revision
        if not target_revision:
            target_revision = session.execute(
                select(CourseRevision)
                .where(CourseRevision.course_id == course_id)
                .order_by(CourseRevision.revision_no.desc())
            ).scalars().first()

        total_lessons_count = 0
        all_lesson_ids: list[uuid.UUID] = []

        if target_revision:
            # Query all lesson IDs in this revision
            lessons_stmt = (
                select(CurriculumLesson.id)
                .join(CurriculumSection, CurriculumLesson.section_id == CurriculumSection.id)
                .where(CurriculumSection.course_revision_id == target_revision.id)
            )
            all_lesson_ids = list(session.execute(lessons_stmt).scalars().all())
            total_lessons_count = len(all_lesson_ids)

        completed_lesson_ids: set[uuid.UUID] = set()
        completed_lessons_count = 0
        progress_percentage = Decimal("0.00")

        if total_lessons_count > 0:
            completed_lesson_ids = self.progress_repo.get_completed_lesson_ids_for_course(
                session=session,
                student_id=student.id,
                lesson_ids=all_lesson_ids,
            )
            completed_lessons_count = len(completed_lesson_ids)
            pct = (Decimal(completed_lessons_count) / Decimal(total_lessons_count)) * Decimal("100.00")
            progress_percentage = round(pct, 2)

        summary = self.progress_repo.upsert_course_progress_summary(
            session=session,
            student_id=student.id,
            course_id=course_id,
            completed_lessons_count=completed_lessons_count,
            total_lessons_count=total_lessons_count,
            progress_percentage=progress_percentage,
        )

        # 7. Automated certificate issuance trigger if 100% completed
        if summary.is_completed and total_lessons_count > 0:
            self.certificate_service.issue_certificate_if_eligible(session, student, course)

        return CourseProgressSummaryResponse(
            course_id=course_id,
            completed_lessons_count=summary.completed_lessons_count,
            total_lessons_count=summary.total_lessons_count,
            progress_percentage=summary.progress_percentage,
            is_completed=summary.is_completed,
            completed_lesson_ids=sorted(list(completed_lesson_ids)),
            last_activity_at=summary.last_activity_at,
        )

    def get_course_progress(
        self,
        session: Session,
        student: User,
        course_id: uuid.UUID,
    ) -> CourseProgressSummaryResponse:
        """Retrieve course progress summary for student, validating active enrollment."""
        course = session.get(Course, course_id)
        if not course:
            raise ResourceNotFoundException(
                message="Course not found",
                code="COURSE_NOT_FOUND",
            )

        # Active enrollment check
        enrollment = self.enrollment_repo.get_by_student_and_course(session, student.id, course_id)
        if not enrollment or not enrollment.is_access_valid:
            raise ForbiddenException(
                message="Active course enrollment required to view progress",
                code="ENROLLMENT_REQUIRED",
            )

        # Recalculate to ensure accurate fresh data
        return self.recalculate_course_progress(session, student, course)
