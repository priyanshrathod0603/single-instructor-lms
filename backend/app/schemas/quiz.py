"""Pydantic v2 schemas for LMS Quizzes and Question Banks.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
"""

from datetime import datetime
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.quiz import (
    QUESTION_TYPE_MCQ_MULTI,
    QUESTION_TYPE_MCQ_SINGLE,
    QUESTION_TYPE_TEXT_SHORT,
    QUESTION_TYPE_TRUE_FALSE,
    QUESTION_TYPES,
)


class QuestionOptionCreateRequest(BaseModel):
    """Schema for creating a selectable answer option."""

    model_config = ConfigDict(extra="forbid")

    option_text: str = Field(..., min_length=1, description="Answer option text")
    is_correct: bool = Field(False, description="Whether this option is correct")
    sort_order: int = Field(0, ge=0, description="Sort order for presentation")


class QuestionCreateRequest(BaseModel):
    """Schema for adding a question to a quiz."""

    model_config = ConfigDict(extra="forbid")

    question_type: str = Field(
        ...,
        description="One of: MCQ_SINGLE, MCQ_MULTI, TRUE_FALSE, TEXT_SHORT",
    )
    prompt: str = Field(..., min_length=1, description="Question prompt / Markdown text")
    points: float = Field(1.0, gt=0.0, description="Points awarded for correct solution")
    explanation: Optional[str] = Field(None, description="Pedagogical explanation revealed after grading")
    sort_order: int = Field(0, ge=0, description="Display order")
    options: List[QuestionOptionCreateRequest] = Field(
        default_factory=list,
        description="Options for MCQ and TRUE_FALSE questions",
    )

    @field_validator("question_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in QUESTION_TYPES:
            raise ValueError(f"Invalid question_type '{v}'. Must be one of {sorted(QUESTION_TYPES)}")
        return v


class QuizCreateRequest(BaseModel):
    """Schema for creating a quiz configuration on a lesson."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255, description="Quiz title")
    description: Optional[str] = Field(None, description="Quiz instructions")
    pass_percentage: int = Field(70, ge=1, le=100, description="Passing percentage threshold")
    time_limit_minutes: int = Field(30, ge=0, le=360, description="Time limit in minutes (0 = untimed)")
    shuffle_questions: bool = Field(True, description="Randomize question sequence per attempt")
    max_attempts: int = Field(3, ge=0, le=100, description="Max allowed attempts (0 = unlimited)")
    questions: Optional[List[QuestionCreateRequest]] = Field(
        None,
        description="Optional initial questions to create alongside quiz",
    )


class QuizUpdateRequest(BaseModel):
    """Schema for updating an existing quiz configuration."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    pass_percentage: Optional[int] = Field(None, ge=1, le=100)
    time_limit_minutes: Optional[int] = Field(None, ge=0, le=360)
    shuffle_questions: Optional[bool] = None
    max_attempts: Optional[int] = Field(None, ge=0, le=100)


class QuestionOptionResponse(BaseModel):
    """Option representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    option_text: str
    is_correct: Optional[bool] = None  # Hidden during in-progress student attempts
    sort_order: int


class QuestionResponse(BaseModel):
    """Question representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quiz_id: uuid.UUID
    question_type: str
    prompt: str
    points: float
    explanation: Optional[str] = None  # Hidden during in-progress student attempts
    sort_order: int
    options: List[QuestionOptionResponse]


class QuizResponse(BaseModel):
    """Quiz response representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    description: Optional[str] = None
    pass_percentage: int
    time_limit_minutes: int
    shuffle_questions: bool
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    question_count: int = 0
    total_points: float = 0.0
    questions: Optional[List[QuestionResponse]] = None


class BulkCSVImportResponse(BaseModel):
    """Result of bulk question bank CSV import."""

    imported_count: int
    question_ids: List[uuid.UUID]


class QuizAttemptStartResponse(BaseModel):
    """Payload returned to student upon initiating a quiz attempt."""

    model_config = ConfigDict(from_attributes=True)

    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    attempt_no: int
    started_at: datetime
    server_deadline: Optional[datetime] = None
    time_limit_minutes: int
    questions: List[QuestionResponse]


class AutosaveAnswerRequest(BaseModel):
    """Schema for autosaving student answers incrementally."""

    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID
    selected_option_ids: Optional[List[uuid.UUID]] = Field(
        None,
        description="Option UUIDs selected for MCQ/TrueFalse questions",
    )
    text_response: Optional[str] = Field(
        None,
        description="Text answer for short text questions",
    )


class AutosaveAnswerResponse(BaseModel):
    """Confirmation of autosaved response."""

    success: bool = True
    question_id: uuid.UUID
    autosaved_at: datetime


class QuizAnswerSubmissionInput(BaseModel):
    """Answer input submitted at finalization."""

    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID
    selected_option_ids: Optional[List[uuid.UUID]] = None
    text_response: Optional[str] = None


class QuizSubmitRequest(BaseModel):
    """Optional payload when finalizing a quiz attempt."""

    model_config = ConfigDict(extra="forbid")

    answers: Optional[List[QuizAnswerSubmissionInput]] = Field(
        None,
        description="Optional final batch of answers to save before final scoring",
    )


class AnswerReviewResponse(BaseModel):
    """Detailed question response and grading review."""

    model_config = ConfigDict(from_attributes=True)

    question_id: uuid.UUID
    prompt: str
    question_type: str
    points_possible: float
    points_earned: Optional[float] = None
    is_correct: Optional[bool] = None
    selected_option_ids: Optional[List[str]] = None
    text_response: Optional[str] = None
    explanation: Optional[str] = None
    options: List[QuestionOptionResponse]


class QuizAttemptResultResponse(BaseModel):
    """Completed quiz attempt with score, pass/fail status, and optional review."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quiz_id: uuid.UUID
    student_id: uuid.UUID
    student_name: Optional[str] = None
    attempt_no: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    time_limit_minutes: int
    server_deadline: Optional[datetime] = None
    status: str
    score: Optional[float] = None
    is_passed: Optional[bool] = None
    pass_percentage: int
    answers: Optional[List[AnswerReviewResponse]] = None


class QuizAttemptListResponse(BaseModel):
    """Paginated list of quiz attempts."""

    items: List[QuizAttemptResultResponse]
    total: int
    page: int
    size: int
