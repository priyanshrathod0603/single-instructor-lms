"""Progress repository for granular lesson playback and course completion summaries.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902)
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence
import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.progress import CourseProgressSummary, LessonProgress


class ProgressRepository:
    """Repository handling persistence and aggregation for student progress."""

    def get_lesson_progress(
        self,
        session: Session,
        student_id: uuid.UUID,
        lesson_id: uuid.UUID,
    ) -> Optional[LessonProgress]:
        """Fetch granular lesson progress record for a student."""
        stmt = select(LessonProgress).where(
            LessonProgress.student_id == student_id,
            LessonProgress.lesson_id == lesson_id,
        )
        return session.execute(stmt).scalars().first()

    def upsert_lesson_progress(
        self,
        session: Session,
        student_id: uuid.UUID,
        lesson_id: uuid.UUID,
        watch_position_seconds: int,
        is_completed: bool,
    ) -> tuple[LessonProgress, bool]:
        """Atomically upsert lesson progress enforcing non-decreasing completion and position.
        
        Returns:
            Tuple of (LessonProgress, transitioned_to_completed: bool).
        """
        now = datetime.now(timezone.utc)
        record = self.get_lesson_progress(session, student_id, lesson_id)
        transitioned_to_completed = False

        if record is None:
            transitioned_to_completed = is_completed
            record = LessonProgress(
                student_id=student_id,
                lesson_id=lesson_id,
                watch_position_seconds=watch_position_seconds,
                is_completed=is_completed,
                completed_at=now if is_completed else None,
                updated_at=now,
            )
            session.add(record)
        else:
            # Enforce non-decreasing position
            if watch_position_seconds > record.watch_position_seconds:
                record.watch_position_seconds = watch_position_seconds

            # Transition check: if not previously completed and now meets completion
            if not record.is_completed and is_completed:
                record.is_completed = True
                record.completed_at = now
                transitioned_to_completed = True

            record.updated_at = now

        session.flush()
        return record, transitioned_to_completed

    def get_course_progress_summary(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> Optional[CourseProgressSummary]:
        """Fetch materialized course progress summary."""
        stmt = select(CourseProgressSummary).where(
            CourseProgressSummary.student_id == student_id,
            CourseProgressSummary.course_id == course_id,
        )
        return session.execute(stmt).scalars().first()

    def upsert_course_progress_summary(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        completed_lessons_count: int,
        total_lessons_count: int,
        progress_percentage: Decimal,
    ) -> CourseProgressSummary:
        """Atomically update or insert materialized course progress summary."""
        now = datetime.now(timezone.utc)
        summary = self.get_course_progress_summary(session, student_id, course_id)

        if summary is None:
            summary = CourseProgressSummary(
                student_id=student_id,
                course_id=course_id,
                completed_lessons_count=completed_lessons_count,
                total_lessons_count=total_lessons_count,
                progress_percentage=progress_percentage,
                last_activity_at=now,
            )
            session.add(summary)
        else:
            summary.completed_lessons_count = completed_lessons_count
            summary.total_lessons_count = total_lessons_count
            summary.progress_percentage = progress_percentage
            summary.last_activity_at = now

        session.flush()
        return summary

    def get_completed_lesson_ids_for_course(
        self,
        session: Session,
        student_id: uuid.UUID,
        lesson_ids: Sequence[uuid.UUID],
    ) -> set[uuid.UUID]:
        """Retrieve completed lesson UUIDs belonging to a course for a student."""
        if not lesson_ids:
            return set()

        stmt = select(LessonProgress.lesson_id).where(
            LessonProgress.student_id == student_id,
            LessonProgress.lesson_id.in_(lesson_ids),
            LessonProgress.is_completed.is_(True),
        )
        return set(session.execute(stmt).scalars().all())
