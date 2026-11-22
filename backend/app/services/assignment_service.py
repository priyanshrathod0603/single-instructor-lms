"""Assignment, Rubric evaluation, Student project submission, and Grade Override domain service.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.5)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-008, ADR-012, ADR-013)

Strict Invariants:
1. Student Enrollment Gate: Only students with an active, unexpired course enrollment can submit assignments.
2. Deadline Enforcement: Submissions past due_date are rejected unless allow_late=True.
3. Attempt Tracking: Every submission is uniquely versioned (attempt_no) per student.
4. Rubric Immutability: Evaluated rubrics are frozen; modifications create a new version.
5. Audited Overrides: Grade adjustments require mandatory justification and are permanently recorded.
"""

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.permissions import (
    ASSIGNMENT_GRADE,
    ASSIGNMENT_MANAGE,
    ASSIGNMENT_OVERRIDE,
    ASSIGNMENT_VIEW_ALL,
)
from app.models.assignment import (
    SUBMISSION_STATUS_GRADED,
    SUBMISSION_STATUS_GRADING,
    SUBMISSION_STATUS_REJECTED,
    SUBMISSION_STATUS_SUBMITTED,
    Assignment,
    AssignmentSubmission,
    GradeOverride,
    Rubric,
    RubricCriteria,
    RubricScore,
)
from app.models.base import utc_now
from app.models.course import CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import ENROLLMENT_STATUS_REVOKED
from app.models.notification import NotificationOutbox
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.repositories.assignment_repo import AssignmentRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.notification_repo import NotificationOutboxRepository
from app.schemas.assignment import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentUpdateRequest,
    GradeOverrideRequest,
    GradeOverrideResponse,
    GradeSubmissionRequest,
    RubricCreateRequest,
    RubricCriteriaResponse,
    RubricResponse,
    RubricScoreResponse,
    SubmissionCreateRequest,
    SubmissionListResponse,
    SubmissionResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _to_rubric_response(rubric: Rubric) -> RubricResponse:
    """Helper to convert Rubric model to RubricResponse schema."""
    criteria_responses = [
        RubricCriteriaResponse(
            id=c.id,
            rubric_id=c.rubric_id,
            title=c.title,
            description=c.description,
            max_points=float(c.max_points),
            weight=float(c.weight),
            sort_order=c.sort_order,
        )
        for c in rubric.criteria
    ]
    return RubricResponse(
        id=rubric.id,
        assignment_id=rubric.assignment_id,
        title=rubric.title,
        version=rubric.version,
        is_active=rubric.is_active,
        created_at=rubric.created_at,
        criteria=criteria_responses,
    )


def _to_assignment_response(assignment: Assignment, active_rubric: Optional[Rubric] = None) -> AssignmentResponse:
    """Helper to convert Assignment model to AssignmentResponse schema."""
    rubric_resp = _to_rubric_response(active_rubric) if active_rubric else None
    return AssignmentResponse(
        id=assignment.id,
        lesson_id=assignment.lesson_id,
        title=assignment.title,
        instructions=assignment.instructions,
        max_score=float(assignment.max_score),
        pass_score=float(assignment.pass_score),
        allow_late=assignment.allow_late,
        due_date=assignment.due_date,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        active_rubric=rubric_resp,
    )


def _to_submission_response(submission: AssignmentSubmission) -> SubmissionResponse:
    """Helper to convert AssignmentSubmission model to SubmissionResponse schema."""
    rubric_score_responses = [
        RubricScoreResponse(
            id=s.id,
            submission_id=s.submission_id,
            criteria_id=s.criteria_id,
            criteria_title=s.criteria.title if s.criteria else None,
            max_points=float(s.criteria.max_points) if s.criteria else None,
            weight=float(s.criteria.weight) if s.criteria else None,
            points_awarded=float(s.points_awarded),
            feedback=s.feedback,
        )
        for s in submission.rubric_scores
    ]

    grade_override_responses = [
        GradeOverrideResponse(
            id=o.id,
            submission_id=o.submission_id,
            original_score=float(o.original_score),
            overridden_score=float(o.overridden_score),
            reason=o.reason,
            overridden_by=o.overridden_by,
            overrider_name=o.overrider.full_name if o.overrider else None,
            created_at=o.created_at,
        )
        for o in submission.grade_overrides
    ]

    return SubmissionResponse(
        id=submission.id,
        assignment_id=submission.assignment_id,
        student_id=submission.student_id,
        student_name=submission.student.full_name if submission.student else None,
        student_email=submission.student.email if submission.student else None,
        attempt_no=submission.attempt_no,
        file_url=submission.file_url,
        text_notes=submission.text_notes,
        status=submission.status,
        submitted_at=submission.submitted_at,
        final_score=float(submission.final_score) if submission.final_score is not None else None,
        graded_at=submission.graded_at,
        graded_by=submission.graded_by,
        grader_name=submission.grader.full_name if submission.grader else None,
        feedback=submission.feedback,
        rubric_scores=rubric_score_responses,
        grade_overrides=grade_override_responses,
    )


class AssignmentService:
    """Domain service managing assignment lifecycle, rubrics, submissions, and grading."""

    def __init__(
        self,
        repository: Optional[AssignmentRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_repo: Optional[NotificationOutboxRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.repo = repository or AssignmentRepository()
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
            resource_type="assignment",
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
        """Internal helper to stage outbox notification records."""
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

    def _resolve_course_id_from_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        """Traverse lesson -> section -> revision -> course_id."""
        return (
            session.query(CourseRevision.course_id)
            .join(CurriculumSection, CurriculumSection.course_revision_id == CourseRevision.id)
            .join(CurriculumLesson, CurriculumLesson.section_id == CurriculumSection.id)
            .filter(CurriculumLesson.id == lesson_id)
            .scalar()
        )

    def _assert_lesson_revision_is_draft(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> None:
        """Enforce Published Assessment Immutability (BUG-018).

        Assignments and rubrics attached to published or archived revisions cannot be modified.
        Modifications are strictly restricted to working DRAFT revisions.
        """
        from app.models.course import REVISION_STATUS_DRAFT, CourseRevision
        from app.models.curriculum import CurriculumLesson, CurriculumSection
        rev_status = (
            session.query(CourseRevision.status)
            .join(CurriculumSection, CurriculumSection.course_revision_id == CourseRevision.id)
            .join(CurriculumLesson, CurriculumLesson.section_id == CurriculumSection.id)
            .filter(CurriculumLesson.id == lesson_id)
            .scalar()
        )
        if rev_status and rev_status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot modify assessment belonging to an immutable published course revision. Create a new draft revision to make changes.",
                code="REVISION_IMMUTABLE",
            )

    def _verify_course_access(
        self,
        session: Session,
        course_id: uuid.UUID,
        user: User,
    ) -> None:
        """Verify student possesses valid course access, or user has elevated role bypass."""
        if not user.is_active:
            raise ForbiddenException(message="User account has been suspended.", code="ACCOUNT_SUSPENDED")
        if any(r in user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)):
            return
        enrollment = self.enrollment_repo.get_by_student_and_course(session, user.id, course_id)
        if not enrollment:
            raise ForbiddenException(
                message="Active course enrollment required to access assignment.",
                code="ENROLLMENT_REQUIRED",
            )
        if enrollment.status == ENROLLMENT_STATUS_REVOKED:
            raise ForbiddenException(
                message="Your enrollment in this course has been revoked.",
                code="ENROLLMENT_REVOKED",
            )
        if not enrollment.is_access_valid:
            raise ForbiddenException(
                message="Your enrollment in this course has expired.",
                code="ENROLLMENT_EXPIRED",
            )

    # =========================================================================
    # 1. Assignment Configuration & Rubrics (TASK701)
    # =========================================================================

    def create_assignment(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        data: AssignmentCreateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> AssignmentResponse:
        """Configure a practical assignment for a curriculum lesson."""
        # 1. Verify target lesson exists
        lesson = session.get(CurriculumLesson, lesson_id)
        if not lesson:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        self._assert_lesson_revision_is_draft(session, lesson_id)

        # 2. Prevent duplicate assignments on same lesson
        existing = self.repo.get_assignment_by_lesson_id(session, lesson_id)
        if existing:
            raise BadRequestException(
                message="An assignment configuration already exists for this lesson.",
                code="ASSIGNMENT_ALREADY_EXISTS",
            )

        # 3. Create assignment
        assignment = self.repo.create_assignment(
            session=session,
            lesson_id=lesson_id,
            title=data.title,
            instructions=data.instructions,
            max_score=data.max_score,
            pass_score=data.pass_score,
            allow_late=data.allow_late,
            due_date=data.due_date,
        )

        # 4. Create initial rubric if provided
        active_rubric = None
        if data.rubric:
            active_rubric = self._create_rubric_internal(
                session=session,
                assignment_id=assignment.id,
                rubric_data=data.rubric,
            )

        # 5. Audit log
        self._log_audit(
            session=session,
            action="ASSIGNMENT_CREATED",
            resource_id=str(assignment.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "id": str(assignment.id),
                "lesson_id": str(lesson_id),
                "title": assignment.title,
                "max_score": float(assignment.max_score),
                "pass_score": float(assignment.pass_score),
            },
            request_context=request_context,
        )

        return _to_assignment_response(assignment, active_rubric=active_rubric)

    def update_assignment(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        data: AssignmentUpdateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> AssignmentResponse:
        """Update assignment properties."""
        assignment = self.repo.get_assignment_by_id(session, assignment_id, for_update=True)
        if not assignment:
            raise ResourceNotFoundException("Assignment", str(assignment_id))

        self._assert_lesson_revision_is_draft(session, assignment.lesson_id)

        updated = self.repo.update_assignment(
            session=session,
            assignment=assignment,
            title=data.title,
            instructions=data.instructions,
            max_score=data.max_score,
            pass_score=data.pass_score,
            allow_late=data.allow_late,
            due_date=data.due_date,
        )

        active_rubric = self.repo.get_active_rubric(session, assignment.id)

        self._log_audit(
            session=session,
            action="ASSIGNMENT_UPDATED",
            resource_id=str(assignment.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "title": updated.title,
                "max_score": float(updated.max_score),
                "due_date": updated.due_date.isoformat() if updated.due_date else None,
            },
            request_context=request_context,
        )

        return _to_assignment_response(updated, active_rubric=active_rubric)

    def create_or_update_rubric(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        data: RubricCreateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> RubricResponse:
        """Create a new rubric version for an assignment.

        Enforces Criteria Immutability (ADR-003):
        If any submission has already been graded, the existing rubric is deactivated and
        a new version is spawned (version = V + 1).
        """
        assignment = self.repo.get_assignment_by_id(session, assignment_id)
        if not assignment:
            raise ResourceNotFoundException("Assignment", str(assignment_id))

        self._assert_lesson_revision_is_draft(session, assignment.lesson_id)

        rubric = self._create_rubric_internal(
            session=session,
            assignment_id=assignment.id,
            rubric_data=data,
        )

        self._log_audit(
            session=session,
            action="RUBRIC_VERSION_CREATED",
            resource_id=str(rubric.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "id": str(rubric.id),
                "assignment_id": str(assignment_id),
                "title": rubric.title,
                "version": rubric.version,
                "criteria_count": len(rubric.criteria),
            },
            request_context=request_context,
        )

        return _to_rubric_response(rubric)

    def _create_rubric_internal(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        rubric_data: RubricCreateRequest,
    ) -> Rubric:
        """Internal helper to deactivate previous active rubrics and spawn new version."""
        # Deactivate existing active rubrics
        self.repo.deactivate_active_rubrics(session, assignment_id)

        # Calculate next version
        next_version = self.repo.get_latest_rubric_version(session, assignment_id) + 1

        rubric = self.repo.create_rubric(
            session=session,
            assignment_id=assignment_id,
            title=rubric_data.title,
            version=next_version,
            is_active=True,
        )

        for idx, crit_data in enumerate(rubric_data.criteria):
            self.repo.create_criteria(
                session=session,
                rubric_id=rubric.id,
                title=crit_data.title,
                max_points=crit_data.max_points,
                description=crit_data.description,
                weight=crit_data.weight,
                sort_order=crit_data.sort_order if crit_data.sort_order else idx,
            )

        session.flush()
        return rubric

    def get_assignment(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        current_user: Optional[User] = None,
    ) -> AssignmentResponse:
        """Retrieve assignment details and its active rubric."""
        assignment = self.repo.get_assignment_by_id(session, assignment_id)
        if not assignment:
            raise ResourceNotFoundException("Assignment", str(assignment_id))

        if current_user:
            course_id = self._resolve_course_id_from_lesson(session, assignment.lesson_id)
            if course_id:
                self._verify_course_access(session, course_id, current_user)

        active_rubric = self.repo.get_active_rubric(session, assignment.id)
        return _to_assignment_response(assignment, active_rubric=active_rubric)

    def get_assignment_by_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        current_user: Optional[User] = None,
    ) -> AssignmentResponse:
        """Retrieve assignment details linked to a lesson."""
        assignment = self.repo.get_assignment_by_lesson_id(session, lesson_id)
        if not assignment:
            raise ResourceNotFoundException("Assignment", f"for lesson {lesson_id}")

        if current_user:
            course_id = self._resolve_course_id_from_lesson(session, lesson_id)
            if course_id:
                self._verify_course_access(session, course_id, current_user)

        active_rubric = self.repo.get_active_rubric(session, assignment.id)
        return _to_assignment_response(assignment, active_rubric=active_rubric)

    # =========================================================================
    # 2. Student Submission Workflow (TASK702)
    # =========================================================================

    def submit_project(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        data: SubmissionCreateRequest,
        student: User,
        request_context: Optional[Any] = None,
    ) -> SubmissionResponse:
        """Upload and stage a student project submission.

        Enforces:
        1. Student account is active and email verified (ADR-008).
        2. Student possesses an active enrollment in the course (TASK604 / ADR-004).
        3. Submission deadline check: if due_date is past and not allow_late, rejects request.
        4. Unique attempt counter: attempt_no is incremented monotonically.
        5. Emits outbox notification and audit record.
        """
        # 1. Student verification & account state
        if not student.is_active:
            raise ForbiddenException(
                message="User account has been suspended.",
                code="ACCOUNT_SUSPENDED",
            )
        if not student.is_verified:
            raise ForbiddenException(
                message="Email verification is required before submitting project work.",
                code="EMAIL_NOT_VERIFIED",
            )

        # 2. Fetch assignment
        assignment = self.repo.get_assignment_by_id(session, assignment_id)
        if not assignment:
            raise ResourceNotFoundException("Assignment", str(assignment_id))

        # 3. Verify course enrollment
        course_id = self._resolve_course_id_from_lesson(session, assignment.lesson_id)
        if not course_id:
            raise ResourceNotFoundException("Course", f"linked to assignment {assignment_id}")
        self._verify_course_access(session, course_id, student)

        # 4. Enforce submission deadline policy
        now_utc = utc_now()
        if assignment.due_date is not None and now_utc > assignment.due_date:
            if not assignment.allow_late:
                raise BadRequestException(
                    message="Submission deadline has passed and late submissions are not allowed for this assignment.",
                    code="DEADLINE_PASSED",
                    details={
                        "due_date": assignment.due_date.isoformat(),
                        "submitted_at": now_utc.isoformat(),
                    },
                )

        # 5. Determine attempt counter
        latest_attempt = self.repo.get_latest_attempt_no(session, assignment.id, student.id)
        attempt_no = latest_attempt + 1

        # 6. Create submission record
        submission = self.repo.create_submission(
            session=session,
            assignment_id=assignment.id,
            student_id=student.id,
            file_url=data.file_url,
            attempt_no=attempt_no,
            text_notes=data.text_notes,
        )

        # 7. Transactional Outbox: Student confirmation receipt
        self._emit_outbox_event(
            session=session,
            event_type="ASSIGNMENT_SUBMITTED",
            recipient_email=student.email,
            subject=f"Submission Received: {assignment.title} (Attempt #{attempt_no})",
            payload={
                "submission_id": str(submission.id),
                "assignment_id": str(assignment.id),
                "assignment_title": assignment.title,
                "attempt_no": attempt_no,
                "submitted_at": submission.submitted_at.isoformat(),
            },
            dedupe_key=f"sub_receipt_{submission.id}",
        )

        # 8. Immutable audit log
        self._log_audit(
            session=session,
            action="ASSIGNMENT_SUBMISSION_CREATED",
            resource_id=str(submission.id),
            actor_id=student.id,
            actor_type="USER",
            after_state={
                "id": str(submission.id),
                "assignment_id": str(assignment.id),
                "student_id": str(student.id),
                "attempt_no": attempt_no,
                "file_url": submission.file_url,
                "status": submission.status,
            },
            request_context=request_context,
        )

        return _to_submission_response(submission)

    # =========================================================================
    # 3. Rubric-Based Grading & Weighted Score Calculation (TASK703)
    # =========================================================================

    def grade_submission(
        self,
        session: Session,
        submission_id: uuid.UUID,
        data: GradeSubmissionRequest,
        grader: User,
        request_context: Optional[Any] = None,
    ) -> SubmissionResponse:
        """Evaluate submission against active rubric criteria and calculate final score.

        Formula:
            Final Score = sum(points_awarded_i * weight_i)
        """
        # 1. Fetch submission with row lock
        submission = self.repo.get_submission_by_id(session, submission_id, for_update=True)
        if not submission:
            raise ResourceNotFoundException("AssignmentSubmission", str(submission_id))

        if submission.status == SUBMISSION_STATUS_REJECTED:
            raise BadRequestException(
                message="Cannot grade a rejected submission.",
                code="SUBMISSION_REJECTED",
            )

        # 2. Fetch active rubric
        active_rubric = self.repo.get_active_rubric(session, submission.assignment_id)
        if not active_rubric:
            raise BadRequestException(
                message="Cannot grade submission because no active rubric is configured for this assignment.",
                code="NO_ACTIVE_RUBRIC",
            )

        # 3. Validate criteria points
        rubric_criteria_map = {c.id: c for c in active_rubric.criteria}
        provided_criteria_ids = set()

        total_score = 0.0

        for score_in in data.scores:
            if score_in.criteria_id not in rubric_criteria_map:
                raise BadRequestException(
                    message=f"Criteria {score_in.criteria_id} does not belong to active rubric {active_rubric.id}.",
                    code="INVALID_RUBRIC_CRITERIA",
                )
            if score_in.criteria_id in provided_criteria_ids:
                raise BadRequestException(
                    message=f"Duplicate score provided for criteria {score_in.criteria_id}.",
                    code="DUPLICATE_CRITERIA_SCORE",
                )
            provided_criteria_ids.add(score_in.criteria_id)

            crit = rubric_criteria_map[score_in.criteria_id]
            max_pts = float(crit.max_points)
            if score_in.points_awarded < 0.0 or score_in.points_awarded > max_pts:
                raise BadRequestException(
                    message=f"Points awarded ({score_in.points_awarded}) for '{crit.title}' must be between 0 and {max_pts}.",
                    code="INVALID_CRITERIA_POINTS",
                )

            # Weight calculation
            weighted_points = score_in.points_awarded * float(crit.weight)
            total_score += weighted_points

            # Record or update RubricScore
            self.repo.create_rubric_score(
                session=session,
                submission_id=submission.id,
                criteria_id=crit.id,
                points_awarded=score_in.points_awarded,
                feedback=score_in.feedback,
            )

        # Ensure all rubric criteria were scored
        missing_criteria = set(rubric_criteria_map.keys()) - provided_criteria_ids
        if missing_criteria:
            raise BadRequestException(
                message=f"All {len(rubric_criteria_map)} rubric criteria must be evaluated.",
                code="INCOMPLETE_RUBRIC_EVALUATION",
                details={"missing_criteria_count": len(missing_criteria)},
            )

        # Cap at max_score
        max_possible = float(submission.assignment.max_score)
        calculated_final = min(total_score, max_possible)

        # Update submission state
        before_status = submission.status
        submission.status = SUBMISSION_STATUS_GRADED
        submission.final_score = calculated_final
        submission.graded_at = utc_now()
        submission.graded_by = grader.id
        submission.feedback = data.overall_feedback

        session.flush()
        session.refresh(submission)

        # Outbox notification for student: Grade Released
        student_email = submission.student.email if submission.student else ""
        assignment_title = submission.assignment.title if submission.assignment else "Assignment"
        self._emit_outbox_event(
            session=session,
            event_type="SUBMISSION_GRADED",
            recipient_email=student_email,
            subject=f"Grade Released: {assignment_title} (Score: {calculated_final:.2f}/{max_possible:.2f})",
            payload={
                "submission_id": str(submission.id),
                "assignment_title": assignment_title,
                "final_score": calculated_final,
                "max_score": max_possible,
                "feedback": data.overall_feedback,
            },
            dedupe_key=f"grade_release_{submission.id}_{submission.graded_at}",
        )

        # Immutable audit log
        self._log_audit(
            session=session,
            action="ASSIGNMENT_GRADED",
            resource_id=str(submission.id),
            actor_id=grader.id,
            actor_type="USER",
            before_state={"status": before_status},
            after_state={
                "status": submission.status,
                "final_score": calculated_final,
                "graded_by": str(grader.id),
                "feedback": data.overall_feedback,
            },
            request_context=request_context,
        )

        return _to_submission_response(submission)

    # =========================================================================
    # 4. Super Admin Grade Override & Audit Logging (TASK704)
    # =========================================================================

    def override_grade(
        self,
        session: Session,
        submission_id: uuid.UUID,
        data: GradeOverrideRequest,
        admin: User,
        request_context: Optional[Any] = None,
    ) -> GradeOverrideResponse:
        """Applies an administrative score adjustment following student appeal or audit.

        Restricted strictly to administrators with assignment:override permission.
        """
        # 1. Fetch submission with row lock
        submission = self.repo.get_submission_by_id(session, submission_id, for_update=True)
        if not submission:
            raise ResourceNotFoundException("AssignmentSubmission", str(submission_id))

        # 2. Status guard: only finalized graded submissions can have score overridden
        if submission.status != SUBMISSION_STATUS_GRADED or submission.final_score is None:
            raise BadRequestException(
                message="Cannot override grade for a submission that has not yet been graded.",
                code="SUBMISSION_NOT_GRADED",
            )

        # 3. Score boundary validation
        max_possible = float(submission.assignment.max_score)
        if data.new_score < 0.0 or data.new_score > max_possible:
            raise BadRequestException(
                message=f"Overridden score ({data.new_score}) cannot be negative or exceed max assignment score ({max_possible}).",
                code="INVALID_OVERRIDE_SCORE",
            )

        original = float(submission.final_score)

        # 4. Create GradeOverride record in persistent audit trail
        override = self.repo.create_grade_override(
            session=session,
            submission_id=submission.id,
            original_score=original,
            overridden_score=data.new_score,
            reason=data.reason,
            overridden_by=admin.id,
        )

        # 5. Update submission final score
        submission.final_score = data.new_score
        session.flush()
        session.refresh(submission)

        # 6. Outbox notification for student: Grade Adjustment
        student_email = submission.student.email if submission.student else ""
        assignment_title = submission.assignment.title if submission.assignment else "Assignment"
        self._emit_outbox_event(
            session=session,
            event_type="GRADE_OVERRIDDEN",
            recipient_email=student_email,
            subject=f"Grade Adjustment: {assignment_title} (New Score: {data.new_score:.2f}/{max_possible:.2f})",
            payload={
                "submission_id": str(submission.id),
                "assignment_title": assignment_title,
                "original_score": original,
                "new_score": data.new_score,
                "reason": data.reason,
            },
            dedupe_key=f"override_{override.id}",
        )

        # 7. Immutable security audit record
        self._log_audit(
            session=session,
            action="GRADE_OVERRIDDEN",
            resource_id=str(submission.id),
            actor_id=admin.id,
            actor_type="USER",
            before_state={"final_score": original},
            after_state={
                "final_score": data.new_score,
                "override_id": str(override.id),
                "reason": data.reason,
            },
            request_context=request_context,
        )

        return GradeOverrideResponse(
            id=override.id,
            submission_id=override.submission_id,
            original_score=float(override.original_score),
            overridden_score=float(override.overridden_score),
            reason=override.reason,
            overridden_by=override.overridden_by,
            overrider_name=admin.full_name,
            created_at=override.created_at,
        )

    # =========================================================================
    # 5. Queries & Listing
    # =========================================================================

    def get_submission(
        self,
        session: Session,
        submission_id: uuid.UUID,
        current_user: User,
    ) -> SubmissionResponse:
        """Fetch submission details verifying student ownership or evaluator permission."""
        submission = self.repo.get_submission_by_id(session, submission_id)
        if not submission:
            raise ResourceNotFoundException("AssignmentSubmission", str(submission_id))

        is_owner = submission.student_id == current_user.id
        is_elevated = any(r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        has_eval_perm = current_user.has_permission(ASSIGNMENT_VIEW_ALL) or current_user.has_permission(ASSIGNMENT_GRADE)

        if not (is_owner or is_elevated or has_eval_perm):
            raise ForbiddenException(
                message="You are not authorized to view this submission.",
                code="SUBMISSION_ACCESS_DENIED",
            )

        return _to_submission_response(submission)

    def list_assignment_submissions(
        self,
        session: Session,
        assignment_id: uuid.UUID,
        status: Optional[str] = None,
        student_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 20,
    ) -> SubmissionListResponse:
        """List paginated submissions for an assignment (evaluator view)."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.repo.list_submissions_for_assignment(
            session=session,
            assignment_id=assignment_id,
            status=status,
            student_id=student_id,
            skip=skip,
            limit=size,
        )

        return SubmissionListResponse(
            items=[_to_submission_response(s) for s in items],
            total=total,
            page=page,
            size=size,
        )

    def list_own_submissions(
        self,
        session: Session,
        student_id: uuid.UUID,
        assignment_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 20,
    ) -> SubmissionListResponse:
        """List paginated submissions for the current student."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.repo.list_student_submissions(
            session=session,
            student_id=student_id,
            assignment_id=assignment_id,
            skip=skip,
            limit=size,
        )

        return SubmissionListResponse(
            items=[_to_submission_response(s) for s in items],
            total=total,
            page=page,
            size=size,
        )
