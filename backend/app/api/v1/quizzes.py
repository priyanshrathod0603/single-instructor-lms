"""FastAPI REST API router for Quizzes, Question Banks, and Timed Attempts.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-008, ADR-011)
"""

import json
import logging
from typing import Optional
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_permissions,
    require_verified_student,
)
from app.core.exceptions import BadRequestException
from app.core.permissions import (
    QUIZ_ATTEMPT,
    QUIZ_IMPORT_CSV,
    QUIZ_MANAGE,
    QUIZ_VIEW_ATTEMPTS,
)
from app.models.user import User
from app.schemas.quiz import (
    AutosaveAnswerRequest,
    AutosaveAnswerResponse,
    BulkCSVImportResponse,
    QuestionCreateRequest,
    QuestionResponse,
    QuizAttemptListResponse,
    QuizAttemptResultResponse,
    QuizAttemptStartResponse,
    QuizCreateRequest,
    QuizResponse,
    QuizSubmitRequest,
    QuizUpdateRequest,
)
from app.services.quiz_service import QuizService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Quizzes & Question Banks"])


def get_quiz_service() -> QuizService:
    """Dependency providing QuizService instance."""
    return QuizService()


# =============================================================================
# 1. Quiz Configuration & Question Management (TASK801)
# =============================================================================

@router.post(
    "/lessons/{id}/quiz",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure quiz parameters for a curriculum lesson",
)
def create_lesson_quiz_endpoint(
    id: uuid.UUID,
    data: QuizCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(QUIZ_MANAGE)),
    service: QuizService = Depends(get_quiz_service),
) -> QuizResponse:
    """Create a quiz assessment attached to a curriculum lesson."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.create_quiz(
        session=db,
        lesson_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.get(
    "/lessons/{id}/quiz",
    response_model=QuizResponse,
    summary="Get quiz configuration for a lesson",
)
def get_lesson_quiz_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_student),
    service: QuizService = Depends(get_quiz_service),
) -> QuizResponse:
    """Retrieve quiz configuration for a lesson."""
    return service.get_quiz_by_lesson(
        session=db,
        lesson_id=id,
        current_user=current_user,
    )


@router.get(
    "/quizzes/{id}",
    response_model=QuizResponse,
    summary="Get quiz configuration and questions by quiz ID",
)
def get_quiz_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_student),
    service: QuizService = Depends(get_quiz_service),
) -> QuizResponse:
    """Retrieve quiz configuration by quiz ID."""
    return service.get_quiz(
        session=db,
        quiz_id=id,
        current_user=current_user,
    )


@router.patch(
    "/quizzes/{id}",
    response_model=QuizResponse,
    summary="Update quiz settings (timer, pass percentage, attempts)",
)
def update_quiz_endpoint(
    id: uuid.UUID,
    data: QuizUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(QUIZ_MANAGE)),
    service: QuizService = Depends(get_quiz_service),
) -> QuizResponse:
    """Update quiz parameters. Requires quiz:manage."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.update_quiz(
        session=db,
        quiz_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


@router.post(
    "/quizzes/{id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an individual question to a quiz",
)
def add_question_endpoint(
    id: uuid.UUID,
    data: QuestionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(QUIZ_MANAGE)),
    service: QuizService = Depends(get_quiz_service),
) -> QuestionResponse:
    """Add a question with answer options to a quiz."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.add_question(
        session=db,
        quiz_id=id,
        data=data,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


# =============================================================================
# 2. Bulk CSV Question Bank Importer (TASK802)
# =============================================================================

@router.post(
    "/quizzes/{id}/questions/bulk-csv",
    response_model=BulkCSVImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import questions in bulk via CSV raw content or JSON payload",
)
async def bulk_import_csv_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(QUIZ_MANAGE)),
    service: QuizService = Depends(get_quiz_service),
) -> BulkCSVImportResponse:
    """Upload question bank via CSV. Supports raw CSV text body or JSON with csv_content field."""
    body_bytes = await request.body()
    content = body_bytes.decode("utf-8", errors="replace")

    if content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "csv_content" in parsed:
                content = parsed["csv_content"]
        except Exception:
            pass

    if not content or not content.strip():
        raise BadRequestException(message="No CSV content provided.", code="EMPTY_CSV")

    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.import_questions_from_csv(
        session=db,
        quiz_id=id,
        csv_content=content,
        actor_id=current_user.id,
        request_context=req_ctx,
    )


# =============================================================================
# 3. Quiz Attempt Initiation (TASK803)
# =============================================================================

@router.post(
    "/quizzes/{id}/attempts",
    response_model=QuizAttemptStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a quiz attempt session (initializes server-authoritative timer)",
)
def start_quiz_attempt_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_student),
    service: QuizService = Depends(get_quiz_service),
) -> QuizAttemptStartResponse:
    """Initialize a quiz attempt session. Enforces enrollment and attempt limits."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.start_quiz_attempt(
        session=db,
        quiz_id=id,
        student=current_user,
        request_context=req_ctx,
    )


# =============================================================================
# 4. Incremental Answer Autosave (TASK804)
# =============================================================================

@router.patch(
    "/quiz-attempts/{id}/autosave",
    response_model=AutosaveAnswerResponse,
    summary="Autosave selected answers incrementally without completing attempt",
)
def autosave_answer_endpoint(
    id: uuid.UUID,
    data: AutosaveAnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: QuizService = Depends(get_quiz_service),
) -> AutosaveAnswerResponse:
    """Autosave single question response. Verified against server timer."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.autosave_answer(
        session=db,
        attempt_id=id,
        data=data,
        student=current_user,
        request_context=req_ctx,
    )


# =============================================================================
# 5. Attempt Finalization & Scoring (TASK805)
# =============================================================================

@router.post(
    "/quiz-attempts/{id}/submit",
    response_model=QuizAttemptResultResponse,
    summary="Finalize attempt, evaluate timer, calculate score and pass/fail",
)
def submit_quiz_attempt_endpoint(
    id: uuid.UUID,
    request: Request,
    data: Optional[QuizSubmitRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: QuizService = Depends(get_quiz_service),
) -> QuizAttemptResultResponse:
    """Finalize quiz attempt. Server validates timer and computes automated score."""
    req_ctx = {
        "request_id": getattr(request.state, "request_id", None),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    return service.submit_quiz_attempt(
        session=db,
        attempt_id=id,
        data=data,
        student=current_user,
        request_context=req_ctx,
    )


@router.get(
    "/quiz-attempts/{id}",
    response_model=QuizAttemptResultResponse,
    summary="Review attempt results, score, and explanations",
)
def get_attempt_result_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: QuizService = Depends(get_quiz_service),
) -> QuizAttemptResultResponse:
    """View attempt results. Allowed for attempt owner or staff evaluators."""
    return service.get_attempt_result(
        session=db,
        attempt_id=id,
        current_user=current_user,
    )


@router.get(
    "/quizzes/{id}/attempts",
    response_model=QuizAttemptListResponse,
    summary="List attempts for a quiz (evaluator view)",
)
def list_quiz_attempts_endpoint(
    id: uuid.UUID,
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student UUID"),
    status: Optional[str] = Query(None, description="Filter by status: IN_PROGRESS, SUBMITTED, EXPIRED"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(QUIZ_VIEW_ATTEMPTS)),
    service: QuizService = Depends(get_quiz_service),
) -> QuizAttemptListResponse:
    """List attempts for a quiz. Restricted to staff and administrators."""
    return service.list_quiz_attempts(
        session=db,
        quiz_id=id,
        student_id=student_id,
        status=status,
        page=page,
        size=size,
    )


@router.get(
    "/quiz-attempts",
    response_model=QuizAttemptListResponse,
    summary="List student's own quiz attempts",
)
def list_own_quiz_attempts_endpoint(
    quiz_id: Optional[uuid.UUID] = Query(None, description="Filter by quiz UUID"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: QuizService = Depends(get_quiz_service),
) -> QuizAttemptListResponse:
    """List own attempts for the authenticated student."""
    return service.list_own_attempts(
        session=db,
        student_id=current_user.id,
        quiz_id=quiz_id,
        page=page,
        size=size,
    )
