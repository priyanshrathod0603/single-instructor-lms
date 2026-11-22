"""Quiz and Question Bank domain service.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-008, ADR-011, ADR-012, ADR-013)

Strict Invariants:
1. Server-Authoritative Quiz Timers (ADR-011): Timer starts at started_at = NOW(). Submissions received
   after started_at + time_limit_minutes + 30s grace window are marked EXPIRED.
2. Anti-Cheating & Answer Protection: Correct answers and explanations are NEVER exposed during in-progress attempts.
3. Enrollment Access Gate: Only actively enrolled learners can attempt quizzes.
4. Attempt Limit Enforcement: max_attempts constraint prevents infinite retries.
5. Idempotent Autosave: Periodic autosaves update answer rows without creating duplicates.
"""

import csv
from datetime import datetime, timedelta, timezone
import io
import logging
import random
from typing import Any, List, Optional, Sequence, Set, Tuple
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.permissions import (
    QUIZ_ATTEMPT,
    QUIZ_IMPORT_CSV,
    QUIZ_MANAGE,
    QUIZ_VIEW_ATTEMPTS,
)
from app.models.base import utc_now
from app.models.course import CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import ENROLLMENT_STATUS_REVOKED
from app.models.notification import NotificationOutbox
from app.models.quiz import (
    ATTEMPT_STATUS_EXPIRED,
    ATTEMPT_STATUS_IN_PROGRESS,
    ATTEMPT_STATUS_SUBMITTED,
    QUESTION_TYPE_MCQ_MULTI,
    QUESTION_TYPE_MCQ_SINGLE,
    QUESTION_TYPE_TEXT_SHORT,
    QUESTION_TYPE_TRUE_FALSE,
    QUESTION_TYPES,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionOption,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.notification_repo import NotificationOutboxRepository
from app.repositories.quiz_repo import QuizRepository
from app.schemas.quiz import (
    AnswerReviewResponse,
    AutosaveAnswerRequest,
    AutosaveAnswerResponse,
    BulkCSVImportResponse,
    QuestionCreateRequest,
    QuestionOptionResponse,
    QuestionResponse,
    QuizAttemptListResponse,
    QuizAttemptResultResponse,
    QuizAttemptStartResponse,
    QuizCreateRequest,
    QuizResponse,
    QuizSubmitRequest,
    QuizUpdateRequest,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _to_question_response(
    question: QuizQuestion,
    reveal_answers: bool = True,
) -> QuestionResponse:
    """Helper to convert QuizQuestion model to QuestionResponse schema."""
    options = [
        QuestionOptionResponse(
            id=opt.id,
            option_text=opt.option_text,
            is_correct=opt.is_correct if reveal_answers else None,
            sort_order=opt.sort_order,
        )
        for opt in question.options
    ]
    return QuestionResponse(
        id=question.id,
        quiz_id=question.quiz_id,
        question_type=question.question_type,
        prompt=question.prompt,
        points=float(question.points),
        explanation=question.explanation if reveal_answers else None,
        sort_order=question.sort_order,
        options=options,
    )


def _to_quiz_response(
    quiz: Quiz,
    include_questions: bool = True,
    reveal_answers: bool = True,
) -> QuizResponse:
    """Helper to convert Quiz model to QuizResponse schema."""
    question_count = len(quiz.questions) if quiz.questions else 0
    total_points = sum(float(q.points) for q in quiz.questions) if quiz.questions else 0.0

    questions_data = None
    if include_questions and quiz.questions:
        questions_data = [
            _to_question_response(q, reveal_answers=reveal_answers)
            for q in quiz.questions
        ]

    return QuizResponse(
        id=quiz.id,
        lesson_id=quiz.lesson_id,
        title=quiz.title,
        description=quiz.description,
        pass_percentage=quiz.pass_percentage,
        time_limit_minutes=quiz.time_limit_minutes,
        shuffle_questions=quiz.shuffle_questions,
        max_attempts=quiz.max_attempts,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        question_count=question_count,
        total_points=total_points,
        questions=questions_data,
    )


class QuizService:
    """Domain service managing quizzes, questions, timer enforcement, and attempt scoring."""

    def __init__(
        self,
        repository: Optional[QuizRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_repo: Optional[NotificationOutboxRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.repo = repository or QuizRepository()
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
        """Helper to synchronously record audit log entries."""
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
            resource_type="quiz",
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
        """Helper to stage transactional outbox notifications."""
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

        Assessments attached to published or archived revisions cannot be modified.
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
                message="Active course enrollment required to access quiz.",
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
    # 1. Quiz & Question Configuration (TASK801)
    # =========================================================================

    def create_quiz(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        data: QuizCreateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> QuizResponse:
        """Configure a quiz assessment attached to a curriculum lesson."""
        lesson = session.get(CurriculumLesson, lesson_id)
        if not lesson:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        self._assert_lesson_revision_is_draft(session, lesson_id)

        existing = self.repo.get_quiz_by_lesson_id(session, lesson_id)
        if existing:
            raise BadRequestException(
                message="A quiz configuration already exists for this lesson.",
                code="QUIZ_ALREADY_EXISTS",
            )

        quiz = self.repo.create_quiz(
            session=session,
            lesson_id=lesson_id,
            title=data.title,
            description=data.description,
            pass_percentage=data.pass_percentage,
            time_limit_minutes=data.time_limit_minutes,
            shuffle_questions=data.shuffle_questions,
            max_attempts=data.max_attempts,
        )

        if data.questions:
            for q_idx, q_data in enumerate(data.questions):
                q = self.repo.add_question(
                    session=session,
                    quiz_id=quiz.id,
                    question_type=q_data.question_type,
                    prompt=q_data.prompt,
                    points=q_data.points,
                    explanation=q_data.explanation,
                    sort_order=q_data.sort_order if q_data.sort_order else q_idx,
                )
                for o_idx, opt_data in enumerate(q_data.options):
                    self.repo.add_question_option(
                        session=session,
                        question_id=q.id,
                        option_text=opt_data.option_text,
                        is_correct=opt_data.is_correct,
                        sort_order=opt_data.sort_order if opt_data.sort_order else o_idx,
                    )

        session.flush()
        session.refresh(quiz)

        self._log_audit(
            session=session,
            action="QUIZ_CREATED",
            resource_id=str(quiz.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "id": str(quiz.id),
                "lesson_id": str(lesson_id),
                "title": quiz.title,
                "time_limit_minutes": quiz.time_limit_minutes,
                "pass_percentage": quiz.pass_percentage,
            },
            request_context=request_context,
        )

        return _to_quiz_response(quiz, include_questions=True, reveal_answers=True)

    def update_quiz(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        data: QuizUpdateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> QuizResponse:
        """Update existing quiz settings."""
        quiz = self.repo.get_quiz_by_id(session, quiz_id, for_update=True)
        if not quiz:
            raise ResourceNotFoundException("Quiz", str(quiz_id))

        self._assert_lesson_revision_is_draft(session, quiz.lesson_id)

        updated = self.repo.update_quiz(
            session=session,
            quiz=quiz,
            title=data.title,
            description=data.description,
            pass_percentage=data.pass_percentage,
            time_limit_minutes=data.time_limit_minutes,
            shuffle_questions=data.shuffle_questions,
            max_attempts=data.max_attempts,
        )

        session.flush()
        session.refresh(updated)

        self._log_audit(
            session=session,
            action="QUIZ_UPDATED",
            resource_id=str(quiz.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "title": updated.title,
                "pass_percentage": updated.pass_percentage,
                "time_limit_minutes": updated.time_limit_minutes,
            },
            request_context=request_context,
        )

        return _to_quiz_response(updated, include_questions=True, reveal_answers=True)

    def add_question(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        data: QuestionCreateRequest,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> QuestionResponse:
        """Add an individual question with answer options to a quiz."""
        quiz = self.repo.get_quiz_by_id(session, quiz_id, for_update=True)
        if not quiz:
            raise ResourceNotFoundException("Quiz", str(quiz_id))

        self._assert_lesson_revision_is_draft(session, quiz.lesson_id)

        # Validate options based on question type
        if data.question_type in (QUESTION_TYPE_MCQ_SINGLE, QUESTION_TYPE_MCQ_MULTI, QUESTION_TYPE_TRUE_FALSE):
            if not data.options:
                raise BadRequestException(
                    message=f"Questions of type {data.question_type} require selectable options.",
                    code="OPTIONS_REQUIRED",
                )
            correct_count = sum(1 for o in data.options if o.is_correct)
            if data.question_type == QUESTION_TYPE_MCQ_SINGLE and correct_count != 1:
                raise BadRequestException(
                    message="MCQ_SINGLE questions must have exactly one correct option.",
                    code="INVALID_CORRECT_OPTIONS_COUNT",
                )
            if data.question_type == QUESTION_TYPE_TRUE_FALSE and correct_count != 1:
                raise BadRequestException(
                    message="TRUE_FALSE questions must have exactly one correct option.",
                    code="INVALID_CORRECT_OPTIONS_COUNT",
                )
            if data.question_type == QUESTION_TYPE_MCQ_MULTI and correct_count < 1:
                raise BadRequestException(
                    message="MCQ_MULTI questions must have at least one correct option.",
                    code="INVALID_CORRECT_OPTIONS_COUNT",
                )

        question = self.repo.add_question(
            session=session,
            quiz_id=quiz.id,
            question_type=data.question_type,
            prompt=data.prompt,
            points=data.points,
            explanation=data.explanation,
            sort_order=data.sort_order,
        )

        for idx, opt in enumerate(data.options):
            self.repo.add_question_option(
                session=session,
                question_id=question.id,
                option_text=opt.option_text,
                is_correct=opt.is_correct,
                sort_order=opt.sort_order if opt.sort_order else idx,
            )

        session.flush()
        session.refresh(question)

        self._log_audit(
            session=session,
            action="QUIZ_QUESTION_ADDED",
            resource_id=str(question.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "id": str(question.id),
                "quiz_id": str(quiz_id),
                "question_type": question.question_type,
                "points": float(question.points),
            },
            request_context=request_context,
        )

        return _to_question_response(question, reveal_answers=True)

    def get_quiz(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        current_user: Optional[User] = None,
    ) -> QuizResponse:
        """Fetch quiz configuration. Verifies enrollment if student."""
        quiz = self.repo.get_quiz_by_id(session, quiz_id)
        if not quiz:
            raise ResourceNotFoundException("Quiz", str(quiz_id))

        if current_user:
            course_id = self._resolve_course_id_from_lesson(session, quiz.lesson_id)
            if course_id:
                self._verify_course_access(session, course_id, current_user)

        is_staff_or_admin = current_user and any(
            r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)
        )
        return _to_quiz_response(
            quiz,
            include_questions=True,
            reveal_answers=is_staff_or_admin,
        )

    def get_quiz_by_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        current_user: Optional[User] = None,
    ) -> QuizResponse:
        """Fetch quiz attached to curriculum lesson."""
        quiz = self.repo.get_quiz_by_lesson_id(session, lesson_id)
        if not quiz:
            raise ResourceNotFoundException("Quiz", f"for lesson {lesson_id}")

        if current_user:
            course_id = self._resolve_course_id_from_lesson(session, lesson_id)
            if course_id:
                self._verify_course_access(session, course_id, current_user)

        is_staff_or_admin = current_user and any(
            r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)
        )
        return _to_quiz_response(
            quiz,
            include_questions=True,
            reveal_answers=is_staff_or_admin,
        )

    # =========================================================================
    # 2. Bulk CSV Question Bank Importer (TASK802)
    # =========================================================================

    def import_questions_from_csv(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        csv_content: str,
        actor_id: uuid.UUID,
        request_context: Optional[Any] = None,
    ) -> BulkCSVImportResponse:
        """Bulk import question bank from CSV specification.

        Format:
        question_type,prompt,points,explanation,option_1,option_2,option_3,option_4,correct_options
        """
        quiz = self.repo.get_quiz_by_id(session, quiz_id, for_update=True)
        if not quiz:
            raise ResourceNotFoundException("Quiz", str(quiz_id))

        self._assert_lesson_revision_is_draft(session, quiz.lesson_id)

        if not csv_content or not csv_content.strip():
            raise BadRequestException(message="CSV content is empty.", code="EMPTY_CSV")

        try:
            reader = csv.DictReader(io.StringIO(csv_content.strip()))
        except Exception as err:
            raise BadRequestException(message=f"Malformed CSV: {err}", code="INVALID_CSV")

        required_headers = {"question_type", "prompt"}
        if not reader.fieldnames or not required_headers.issubset(set(reader.fieldnames)):
            raise BadRequestException(
                message=f"CSV missing required headers. Must include: {sorted(required_headers)}",
                code="MISSING_CSV_HEADERS",
            )

        created_question_ids: List[uuid.UUID] = []

        for row_idx, row in enumerate(reader, start=1):
            q_type = (row.get("question_type") or "").strip().upper()
            prompt = (row.get("prompt") or "").strip()
            explanation = (row.get("explanation") or "").strip() or None

            if not q_type or q_type not in QUESTION_TYPES:
                raise BadRequestException(
                    message=f"Row {row_idx}: Invalid question_type '{q_type}'. Allowed: {sorted(QUESTION_TYPES)}",
                    code="INVALID_CSV_ROW",
                )
            if not prompt:
                raise BadRequestException(
                    message=f"Row {row_idx}: Prompt cannot be empty.",
                    code="INVALID_CSV_ROW",
                )

            try:
                points = float(row.get("points") or 1.0)
                if points <= 0.0:
                    points = 1.0
            except ValueError:
                points = 1.0

            # Parse correct_options indices (e.g. "1" or "1,2")
            correct_indices_str = (row.get("correct_options") or "").strip()
            correct_indices: Set[int] = set()
            for part in correct_indices_str.split(","):
                part_clean = part.strip()
                if part_clean.isdigit():
                    correct_indices.add(int(part_clean))

            # Collect options (option_1, option_2, ...)
            options_to_add: List[Tuple[str, bool]] = []
            for col_name, col_val in row.items():
                if col_name and col_name.startswith("option_"):
                    opt_text = (col_val or "").strip()
                    if opt_text:
                        # Extract option index from column name
                        idx_part = col_name.replace("option_", "")
                        opt_idx = int(idx_part) if idx_part.isdigit() else len(options_to_add) + 1
                        is_corr = opt_idx in correct_indices
                        options_to_add.append((opt_text, is_corr))

            # Default TRUE_FALSE options if missing
            if q_type == QUESTION_TYPE_TRUE_FALSE and not options_to_add:
                options_to_add = [("True", 1 in correct_indices), ("False", 2 in correct_indices)]

            # Validation per type
            if q_type in (QUESTION_TYPE_MCQ_SINGLE, QUESTION_TYPE_TRUE_FALSE):
                corr_count = sum(1 for _, is_c in options_to_add if is_c)
                if corr_count != 1:
                    raise BadRequestException(
                        message=f"Row {row_idx}: {q_type} must have exactly one correct option (specified in correct_options).",
                        code="INVALID_CSV_CORRECT_OPTIONS",
                    )
            elif q_type == QUESTION_TYPE_MCQ_MULTI:
                corr_count = sum(1 for _, is_c in options_to_add if is_c)
                if corr_count < 1:
                    raise BadRequestException(
                        message=f"Row {row_idx}: MCQ_MULTI must have at least one correct option.",
                        code="INVALID_CSV_CORRECT_OPTIONS",
                    )

            # Persist question
            question = self.repo.add_question(
                session=session,
                quiz_id=quiz.id,
                question_type=q_type,
                prompt=prompt,
                points=points,
                explanation=explanation,
                sort_order=row_idx,
            )

            for opt_idx, (opt_text, is_corr) in enumerate(options_to_add):
                self.repo.add_question_option(
                    session=session,
                    question_id=question.id,
                    option_text=opt_text,
                    is_correct=is_corr,
                    sort_order=opt_idx,
                )

            created_question_ids.append(question.id)

        session.flush()

        self._log_audit(
            session=session,
            action="QUIZ_QUESTIONS_IMPORTED_CSV",
            resource_id=str(quiz.id),
            actor_id=actor_id,
            actor_type="USER",
            after_state={
                "quiz_id": str(quiz.id),
                "imported_count": len(created_question_ids),
            },
            request_context=request_context,
        )

        return BulkCSVImportResponse(
            imported_count=len(created_question_ids),
            question_ids=created_question_ids,
        )

    # =========================================================================
    # 3. Server-Authoritative Quiz Timer & Attempt Initiation (TASK803)
    # =========================================================================

    def start_quiz_attempt(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student: User,
        request_context: Optional[Any] = None,
    ) -> QuizAttemptStartResponse:
        """Start a new timed assessment attempt session.

        Enforces:
        1. Student account active & verified (ADR-008).
        2. Course enrollment valid (TASK604).
        3. Attempt limit checks (max_attempts).
        4. Expiration of stale in-progress attempts.
        5. Question delivery randomization (shuffle_questions).
        6. Answer concealment: is_correct and explanation omitted.
        """
        if not student.is_active:
            raise ForbiddenException(message="User account has been suspended.", code="ACCOUNT_SUSPENDED")
        if not student.is_verified:
            raise ForbiddenException(message="Email verification is required before taking quizzes.", code="EMAIL_NOT_VERIFIED")

        quiz = self.repo.get_quiz_by_id(session, quiz_id)
        if not quiz:
            raise ResourceNotFoundException("Quiz", str(quiz_id))

        if not quiz.questions:
            raise BadRequestException(message="Cannot start quiz with zero configured questions.", code="EMPTY_QUIZ")

        # Verify course enrollment
        course_id = self._resolve_course_id_from_lesson(session, quiz.lesson_id)
        if not course_id:
            raise ResourceNotFoundException("Course", f"linked to quiz {quiz_id}")
        self._verify_course_access(session, course_id, student)

        now = utc_now()

        # Handle existing IN_PROGRESS attempt
        existing_attempt = self.repo.get_in_progress_attempt(session, quiz.id, student.id)
        if existing_attempt:
            # Check if existing attempt has exceeded time limit (+30s grace)
            if quiz.time_limit_minutes > 0:
                deadline = existing_attempt.started_at + timedelta(minutes=quiz.time_limit_minutes) + timedelta(seconds=30)
                if now > deadline:
                    existing_attempt.status = ATTEMPT_STATUS_EXPIRED
                    existing_attempt.score = 0.0
                    existing_attempt.is_passed = False
                    existing_attempt.completed_at = now
                    session.flush()
                else:
                    # Return existing in-progress attempt to preserve in-flight state
                    return self._build_attempt_start_response(existing_attempt, quiz)

        # Check attempt limits
        prior_attempts_count = self.repo.count_attempts(session, quiz.id, student.id)
        if quiz.max_attempts > 0 and prior_attempts_count >= quiz.max_attempts:
            raise BadRequestException(
                message=f"Maximum attempt limit ({quiz.max_attempts}) reached for this quiz.",
                code="MAX_ATTEMPTS_EXCEEDED",
                details={
                    "max_attempts": quiz.max_attempts,
                    "attempts_made": prior_attempts_count,
                },
            )

        attempt_no = self.repo.get_latest_attempt_no(session, quiz.id, student.id) + 1
        attempt = self.repo.create_attempt(
            session=session,
            quiz_id=quiz.id,
            student_id=student.id,
            attempt_no=attempt_no,
            started_at=now,
        )

        session.flush()

        self._log_audit(
            session=session,
            action="QUIZ_ATTEMPT_STARTED",
            resource_id=str(attempt.id),
            actor_id=student.id,
            actor_type="USER",
            after_state={
                "attempt_id": str(attempt.id),
                "quiz_id": str(quiz.id),
                "attempt_no": attempt_no,
                "started_at": attempt.started_at.isoformat(),
            },
            request_context=request_context,
        )

        return self._build_attempt_start_response(attempt, quiz)

    def _build_attempt_start_response(
        self,
        attempt: QuizAttempt,
        quiz: Quiz,
    ) -> QuizAttemptStartResponse:
        """Helper to construct sanitized QuizAttemptStartResponse."""
        questions = list(quiz.questions)
        if quiz.shuffle_questions:
            # Deterministic per-attempt shuffle so repeated calls yield the same ordering
            rng = random.Random(attempt.id.int)
            rng.shuffle(questions)

        sanitized_questions: List[QuestionResponse] = []
        for q in questions:
            opts = list(q.options)
            if quiz.shuffle_questions:
                rng = random.Random(attempt.id.int + q.id.int)
                rng.shuffle(opts)

            sanitized_opts = [
                QuestionOptionResponse(
                    id=opt.id,
                    option_text=opt.option_text,
                    is_correct=None,  # CONCEALED
                    sort_order=idx,
                )
                for idx, opt in enumerate(opts)
            ]
            sanitized_questions.append(
                QuestionResponse(
                    id=q.id,
                    quiz_id=q.quiz_id,
                    question_type=q.question_type,
                    prompt=q.prompt,
                    points=float(q.points),
                    explanation=None,  # CONCEALED
                    sort_order=q.sort_order,
                    options=sanitized_opts,
                )
            )

        server_deadline = None
        if quiz.time_limit_minutes > 0:
            server_deadline = attempt.started_at + timedelta(minutes=quiz.time_limit_minutes)

        return QuizAttemptStartResponse(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            attempt_no=attempt.attempt_no,
            started_at=attempt.started_at,
            server_deadline=server_deadline,
            time_limit_minutes=quiz.time_limit_minutes,
            questions=sanitized_questions,
        )

    # =========================================================================
    # 4. Incremental Answer Autosave (TASK804)
    # =========================================================================

    def autosave_answer(
        self,
        session: Session,
        attempt_id: uuid.UUID,
        data: AutosaveAnswerRequest,
        student: User,
        request_context: Optional[Any] = None,
    ) -> AutosaveAnswerResponse:
        """Autosave single student answer incrementally during assessment."""
        attempt = self.repo.get_attempt_by_id(session, attempt_id)
        if not attempt:
            raise ResourceNotFoundException("QuizAttempt", str(attempt_id))

        if attempt.student_id != student.id:
            raise ForbiddenException(
                message="You are not authorized to save answers for this attempt.",
                code="ATTEMPT_ACCESS_DENIED",
            )

        # Re-verify student enrollment and account status (BUG-009)
        course_id = self._resolve_course_id_from_lesson(session, attempt.quiz.lesson_id)
        if course_id:
            self._verify_course_access(session, course_id, student)

        if attempt.status != ATTEMPT_STATUS_IN_PROGRESS:
            raise BadRequestException(
                message=f"Cannot autosave answers for an attempt in status '{attempt.status}'.",
                code="ATTEMPT_NOT_IN_PROGRESS",
            )

        # Timer enforcement (+30s grace)
        now = utc_now()
        quiz = attempt.quiz
        if quiz.time_limit_minutes > 0:
            deadline = attempt.started_at + timedelta(minutes=quiz.time_limit_minutes) + timedelta(seconds=30)
            if now > deadline:
                attempt.status = ATTEMPT_STATUS_EXPIRED
                attempt.score = 0.0
                attempt.is_passed = False
                attempt.completed_at = now
                session.commit()  # Durably persist expiration so rollback cannot restore IN_PROGRESS (BUG-010)
                raise BadRequestException(
                    message="Quiz time limit exceeded. Attempt has expired.",
                    code="QUIZ_ATTEMPT_EXPIRED",
                )

        # Verify question belongs to quiz
        question = session.get(QuizQuestion, data.question_id)
        if not question or question.quiz_id != quiz.id:
            raise BadRequestException(
                message="Target question does not belong to this quiz.",
                code="INVALID_QUESTION",
            )

        selected_opt_strings = [str(opt_id) for opt_id in data.selected_option_ids] if data.selected_option_ids else None

        ans = self.repo.upsert_answer(
            session=session,
            attempt_id=attempt.id,
            question_id=data.question_id,
            selected_option_ids=selected_opt_strings,
            text_response=data.text_response,
        )

        return AutosaveAnswerResponse(
            success=True,
            question_id=data.question_id,
            autosaved_at=ans.autosaved_at,
        )

    # =========================================================================
    # 5. Attempt Finalization & Automated Score Calculation (TASK805)
    # =========================================================================

    def submit_quiz_attempt(
        self,
        session: Session,
        attempt_id: uuid.UUID,
        data: Optional[QuizSubmitRequest],
        student: User,
        request_context: Optional[Any] = None,
    ) -> QuizAttemptResultResponse:
        """Finalize attempt, verify timer, and compute automated score server-side."""
        attempt = self.repo.get_attempt_by_id(session, attempt_id, for_update=True)
        if not attempt:
            raise ResourceNotFoundException("QuizAttempt", str(attempt_id))

        if attempt.student_id != student.id:
            raise ForbiddenException(
                message="You are not authorized to submit this attempt.",
                code="ATTEMPT_ACCESS_DENIED",
            )

        # Re-verify student enrollment and account status (BUG-009)
        course_id = self._resolve_course_id_from_lesson(session, attempt.quiz.lesson_id)
        if course_id:
            self._verify_course_access(session, course_id, student)

        # Idempotent response if attempt already expired
        if attempt.status == ATTEMPT_STATUS_EXPIRED:
            return self._to_attempt_result_response(attempt, reveal_answers=True)

        if attempt.status != ATTEMPT_STATUS_IN_PROGRESS:
            raise BadRequestException(
                message=f"Attempt has already been finalized with status '{attempt.status}'.",
                code="ATTEMPT_ALREADY_FINALIZED",
            )

        quiz = attempt.quiz
        now = utc_now()

        # Check server deadline (+30s grace)
        if quiz.time_limit_minutes > 0:
            deadline = attempt.started_at + timedelta(minutes=quiz.time_limit_minutes) + timedelta(seconds=30)
            if now > deadline:
                attempt.status = ATTEMPT_STATUS_EXPIRED
                attempt.score = 0.0
                attempt.is_passed = False
                attempt.completed_at = now

                self._emit_outbox_event(
                    session=session,
                    event_type="QUIZ_EXPIRED",
                    recipient_email=student.email,
                    subject=f"Quiz Expired: {quiz.title}",
                    payload={"attempt_id": str(attempt.id), "quiz_title": quiz.title},
                    dedupe_key=f"quiz_expire_{attempt.id}",
                )

                session.commit()
                return self._to_attempt_result_response(attempt, reveal_answers=True)

                return self._to_attempt_result_response(attempt, reveal_answers=True)

        # Ingest any batch answers submitted with request
        if data and data.answers:
            for ans_in in data.answers:
                sel_opts = [str(x) for x in ans_in.selected_option_ids] if ans_in.selected_option_ids else None
                self.repo.upsert_answer(
                    session=session,
                    attempt_id=attempt.id,
                    question_id=ans_in.question_id,
                    selected_option_ids=sel_opts,
                    text_response=ans_in.text_response,
                )

        # Evaluate all questions server-side
        answers = self.repo.get_answers_for_attempt(session, attempt.id)
        answer_map = {a.question_id: a for a in answers}

        total_possible = 0.0
        total_earned = 0.0

        for q in quiz.questions:
            q_pts = float(q.points)
            total_possible += q_pts
            ans = answer_map.get(q.id)
            if not ans:
                continue

            if q.question_type == QUESTION_TYPE_MCQ_SINGLE:
                correct_opt_ids = {str(opt.id) for opt in q.options if opt.is_correct}
                selected_ids = set(ans.selected_option_ids or [])
                if len(selected_ids) == 1 and selected_ids == correct_opt_ids:
                    ans.is_correct = True
                    ans.points_earned = q_pts
                    total_earned += q_pts
                else:
                    ans.is_correct = False
                    ans.points_earned = 0.0

            elif q.question_type == QUESTION_TYPE_MCQ_MULTI:
                correct_opt_ids = {str(opt.id) for opt in q.options if opt.is_correct}
                selected_ids = set(ans.selected_option_ids or [])
                if selected_ids and selected_ids == correct_opt_ids:
                    ans.is_correct = True
                    ans.points_earned = q_pts
                    total_earned += q_pts
                else:
                    ans.is_correct = False
                    ans.points_earned = 0.0

            elif q.question_type == QUESTION_TYPE_TRUE_FALSE:
                correct_opt_ids = {str(opt.id) for opt in q.options if opt.is_correct}
                selected_ids = set(ans.selected_option_ids or [])
                if len(selected_ids) == 1 and selected_ids == correct_opt_ids:
                    ans.is_correct = True
                    ans.points_earned = q_pts
                    total_earned += q_pts
                else:
                    ans.is_correct = False
                    ans.points_earned = 0.0

            elif q.question_type == QUESTION_TYPE_TEXT_SHORT:
                student_txt = (ans.text_response or "").strip().lower()
                correct_texts = {opt.option_text.strip().lower() for opt in q.options if opt.is_correct}
                if student_txt and student_txt in correct_texts:
                    ans.is_correct = True
                    ans.points_earned = q_pts
                    total_earned += q_pts
                else:
                    ans.is_correct = False
                    ans.points_earned = 0.0

        # Calculate percentage score
        score_pct = (total_earned / total_possible * 100.0) if total_possible > 0.0 else 0.0
        score_pct = round(score_pct, 2)
        is_passed = score_pct >= float(quiz.pass_percentage)

        attempt.status = ATTEMPT_STATUS_SUBMITTED
        attempt.score = score_pct
        attempt.is_passed = is_passed
        attempt.completed_at = now

        session.flush()
        session.refresh(attempt)

        # Outbox notification for student
        self._emit_outbox_event(
            session=session,
            event_type="QUIZ_COMPLETED",
            recipient_email=student.email,
            subject=f"Quiz Results: {quiz.title} ({'Passed' if is_passed else 'Failed'})",
            payload={
                "attempt_id": str(attempt.id),
                "quiz_title": quiz.title,
                "score": score_pct,
                "is_passed": is_passed,
                "pass_percentage": quiz.pass_percentage,
            },
            dedupe_key=f"quiz_result_{attempt.id}",
        )

        # Audit log
        self._log_audit(
            session=session,
            action="QUIZ_ATTEMPT_SUBMITTED",
            resource_id=str(attempt.id),
            actor_id=student.id,
            actor_type="USER",
            after_state={
                "score": score_pct,
                "is_passed": is_passed,
                "status": attempt.status,
            },
            request_context=request_context,
        )

        return self._to_attempt_result_response(attempt, reveal_answers=True)

    def get_attempt_result(
        self,
        session: Session,
        attempt_id: uuid.UUID,
        current_user: User,
    ) -> QuizAttemptResultResponse:
        """Fetch attempt details and score. Verifies attempt ownership or evaluator role."""
        attempt = self.repo.get_attempt_by_id(session, attempt_id)
        if not attempt:
            raise ResourceNotFoundException("QuizAttempt", str(attempt_id))

        is_owner = attempt.student_id == current_user.id
        is_staff_or_admin = any(
            r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)
        ) or current_user.has_permission(QUIZ_VIEW_ATTEMPTS)

        if not (is_owner or is_staff_or_admin):
            raise ForbiddenException(
                message="You are not authorized to view this quiz attempt.",
                code="ATTEMPT_ACCESS_DENIED",
            )

        # Do not reveal answers/explanations if attempt is still IN_PROGRESS and viewed by student
        reveal = is_staff_or_admin or (attempt.status in (ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_EXPIRED))
        return self._to_attempt_result_response(attempt, reveal_answers=reveal)

    def list_quiz_attempts(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> QuizAttemptListResponse:
        """List attempts for a quiz (evaluator view)."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.repo.list_attempts_for_quiz(
            session=session,
            quiz_id=quiz_id,
            student_id=student_id,
            status=status,
            skip=skip,
            limit=size,
        )

        return QuizAttemptListResponse(
            items=[self._to_attempt_result_response(a, reveal_answers=True) for a in items],
            total=total,
            page=page,
            size=size,
        )

    def list_own_attempts(
        self,
        session: Session,
        student_id: uuid.UUID,
        quiz_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 20,
    ) -> QuizAttemptListResponse:
        """List student's own attempts."""
        page = max(1, page)
        size = max(1, min(100, size))
        skip = (page - 1) * size

        items, total = self.repo.list_attempts_for_student(
            session=session,
            student_id=student_id,
            quiz_id=quiz_id,
            skip=skip,
            limit=size,
        )

        return QuizAttemptListResponse(
            items=[self._to_attempt_result_response(a, reveal_answers=(a.status != ATTEMPT_STATUS_IN_PROGRESS)) for a in items],
            total=total,
            page=page,
            size=size,
        )

    def _to_attempt_result_response(
        self,
        attempt: QuizAttempt,
        reveal_answers: bool = True,
    ) -> QuizAttemptResultResponse:
        """Helper to convert QuizAttempt to QuizAttemptResultResponse schema."""
        quiz = attempt.quiz
        server_deadline = None
        if quiz and quiz.time_limit_minutes > 0:
            server_deadline = attempt.started_at + timedelta(minutes=quiz.time_limit_minutes)

        answers_data: List[AnswerReviewResponse] = []
        if quiz and quiz.questions:
            answer_map = {a.question_id: a for a in attempt.answers}
            for q in quiz.questions:
                ans = answer_map.get(q.id)
                options = [
                    QuestionOptionResponse(
                        id=opt.id,
                        option_text=opt.option_text,
                        is_correct=opt.is_correct if reveal_answers else None,
                        sort_order=opt.sort_order,
                    )
                    for opt in q.options
                ]
                answers_data.append(
                    AnswerReviewResponse(
                        question_id=q.id,
                        prompt=q.prompt,
                        question_type=q.question_type,
                        points_possible=float(q.points),
                        points_earned=float(ans.points_earned) if (ans and ans.points_earned is not None and reveal_answers) else None,
                        is_correct=ans.is_correct if (ans and reveal_answers) else None,
                        selected_option_ids=ans.selected_option_ids if ans else None,
                        text_response=ans.text_response if ans else None,
                        explanation=q.explanation if reveal_answers else None,
                        options=options,
                    )
                )

        return QuizAttemptResultResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            student_id=attempt.student_id,
            student_name=attempt.student.full_name if attempt.student else None,
            attempt_no=attempt.attempt_no,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            time_limit_minutes=quiz.time_limit_minutes if quiz else 0,
            server_deadline=server_deadline,
            status=attempt.status,
            score=float(attempt.score) if attempt.score is not None else None,
            is_passed=attempt.is_passed,
            pass_percentage=quiz.pass_percentage if quiz else 70,
            answers=answers_data if reveal_answers else None,
        )
