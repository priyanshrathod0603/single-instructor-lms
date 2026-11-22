"""Assignment, Rubric, Submission, and GradeOverride data access repository.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
"""

from datetime import datetime
from typing import List, Optional, Tuple
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.assignment import (
    SUBMISSION_STATUS_GRADED,
    SUBMISSION_STATUS_SUBMITTED,
    Assignment,
    AssignmentSubmission,
    GradeOverride,
    Rubric,
    RubricCriteria,
    RubricScore,
)
from app.models.base import utc_now


class AssignmentRepository:
    """Persistence operations for assignments, rubrics, submissions, and grading."""

    # =========================================================================
    # 1. Assignment CRUD
    # =========================================================================

    def create_assignment(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        title: str,
        instructions: str,
        max_score: float = 100.00,
        pass_score: float = 50.00,
        allow_late: bool = False,
        due_date: Optional[datetime] = None,
    ) -> Assignment:
        """Create and persist an assignment configuration for a lesson."""
        assignment = Assignment(
            lesson_id=lesson_id,
            title=title,
            instructions=instructions,
            max_score=max_score,
            pass_score=pass_score,
            allow_late=allow_late,
            due_date=due_date,
        )
        session.add(assignment)
        session.flush()
        return assignment

    def get_assignment_by_id(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Assignment]:
        """Fetch assignment by primary key."""
        stmt = select(Assignment).where(Assignment.id == assignment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def get_assignment_by_lesson_id(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Assignment]:
        """Fetch assignment linked to a curriculum lesson."""
        stmt = select(Assignment).where(Assignment.lesson_id == lesson_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def update_assignment(
        self,
        session: Session,
        assignment: Assignment,
        **kwargs,
    ) -> Assignment:
        """Update assignment fields and refresh updated_at."""
        for field, value in kwargs.items():
            if hasattr(assignment, field) and value is not None:
                setattr(assignment, field, value)
        assignment.updated_at = utc_now()
        session.flush()
        return assignment

    # =========================================================================
    # 2. Rubric & Criteria Management
    # =========================================================================

    def get_active_rubric(
        self,
        session: Session,
        assignment_id: uuid.UUID,
    ) -> Optional[Rubric]:
        """Fetch currently active rubric version for an assignment."""
        stmt = (
            select(Rubric)
            .where(
                Rubric.assignment_id == assignment_id,
                Rubric.is_active == True,
            )
            .order_by(desc(Rubric.version))
        )
        return session.execute(stmt).scalars().first()

    def get_latest_rubric_version(
        self,
        session: Session,
        assignment_id: uuid.UUID,
    ) -> int:
        """Get the highest version number for an assignment's rubrics."""
        stmt = select(func.max(Rubric.version)).where(Rubric.assignment_id == assignment_id)
        latest = session.execute(stmt).scalar()
        return latest or 0

    def deactivate_active_rubrics(
        self,
        session: Session,
        assignment_id: uuid.UUID,
    ) -> None:
        """Set is_active = False for all existing rubrics of an assignment."""
        stmt = select(Rubric).where(
            Rubric.assignment_id == assignment_id,
            Rubric.is_active == True,
        )
        active_rubrics = session.execute(stmt).scalars().all()
        for r in active_rubrics:
            r.is_active = False
        session.flush()

    def create_rubric(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        title: str,
        version: int = 1,
        is_active: bool = True,
    ) -> Rubric:
        """Create a new rubric version."""
        rubric = Rubric(
            assignment_id=assignment_id,
            title=title,
            version=version,
            is_active=is_active,
        )
        session.add(rubric)
        session.flush()
        return rubric

    def create_criteria(
        self,
        session: Session,
        rubric_id: uuid.UUID,
        title: str,
        max_points: float,
        description: Optional[str] = None,
        weight: float = 1.0,
        sort_order: int = 0,
    ) -> RubricCriteria:
        """Create an evaluation criterion within a rubric."""
        criteria = RubricCriteria(
            rubric_id=rubric_id,
            title=title,
            description=description,
            max_points=max_points,
            weight=weight,
            sort_order=sort_order,
        )
        session.add(criteria)
        session.flush()
        return criteria

    def has_graded_submissions(
        self,
        session: Session,
        assignment_id: uuid.UUID,
    ) -> bool:
        """True if any submission for this assignment has been graded."""
        stmt = select(func.count(AssignmentSubmission.id)).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.status == SUBMISSION_STATUS_GRADED,
        )
        count = session.execute(stmt).scalar_one()
        return count > 0

    # =========================================================================
    # 3. Submission Management
    # =========================================================================

    def get_latest_attempt_no(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> int:
        """Get the highest attempt number for a student's submissions on an assignment."""
        stmt = select(func.max(AssignmentSubmission.attempt_no)).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.student_id == student_id,
        )
        latest = session.execute(stmt).scalar()
        return latest or 0

    def create_submission(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        student_id: uuid.UUID,
        file_url: str,
        attempt_no: int = 1,
        text_notes: Optional[str] = None,
    ) -> AssignmentSubmission:
        """Record a new student project submission."""
        submission = AssignmentSubmission(
            assignment_id=assignment_id,
            student_id=student_id,
            attempt_no=attempt_no,
            file_url=file_url,
            text_notes=text_notes,
            status=SUBMISSION_STATUS_SUBMITTED,
            submitted_at=utc_now(),
        )
        session.add(submission)
        session.flush()
        return submission

    def get_submission_by_id(
        self,
        session: Session,
        submission_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[AssignmentSubmission]:
        """Fetch submission by primary key."""
        stmt = select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def list_submissions_for_assignment(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        status: Optional[str] = None,
        student_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[AssignmentSubmission], int]:
        """List paginated submissions for an assignment (evaluator view)."""
        base_query = select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment_id)
        count_query = select(func.count(AssignmentSubmission.id)).where(AssignmentSubmission.assignment_id == assignment_id)

        if status:
            base_query = base_query.where(AssignmentSubmission.status == status)
            count_query = count_query.where(AssignmentSubmission.status == status)
        if student_id:
            base_query = base_query.where(AssignmentSubmission.student_id == student_id)
            count_query = count_query.where(AssignmentSubmission.student_id == student_id)

        total = session.execute(count_query).scalar_one()
        stmt = base_query.order_by(desc(AssignmentSubmission.submitted_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    def list_student_submissions(
        self,
        session: Session,
        student_id: uuid.UUID,
        assignment_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[AssignmentSubmission], int]:
        """List paginated submissions belonging to a student (student view)."""
        base_query = select(AssignmentSubmission).where(AssignmentSubmission.student_id == student_id)
        count_query = select(func.count(AssignmentSubmission.id)).where(AssignmentSubmission.student_id == student_id)

        if assignment_id:
            base_query = base_query.where(AssignmentSubmission.assignment_id == assignment_id)
            count_query = count_query.where(AssignmentSubmission.assignment_id == assignment_id)

        total = session.execute(count_query).scalar_one()
        stmt = base_query.order_by(desc(AssignmentSubmission.submitted_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    # =========================================================================
    # 4. Grading & Overrides
    # =========================================================================

    def create_rubric_score(
        self,
        session: Session,
        submission_id: uuid.UUID,
        criteria_id: uuid.UUID,
        points_awarded: float,
        feedback: Optional[str] = None,
    ) -> RubricScore:
        """Record awarded criterion points."""
        score = RubricScore(
            submission_id=submission_id,
            criteria_id=criteria_id,
            points_awarded=points_awarded,
            feedback=feedback,
        )
        session.add(score)
        session.flush()
        return score

    def create_grade_override(
        self,
        session: Session,
        submission_id: uuid.UUID,
        original_score: float,
        overridden_score: float,
        reason: str,
        overridden_by: uuid.UUID,
    ) -> GradeOverride:
        """Record an administrative score adjustment in immutable audit trail."""
        override = GradeOverride(
            submission_id=submission_id,
            original_score=original_score,
            overridden_score=overridden_score,
            reason=reason,
            overridden_by=overridden_by,
        )
        session.add(override)
        session.flush()
        return override
