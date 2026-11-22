"""Pydantic v2 schemas for Assignments, Rubrics, Submissions, and Grading.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.5)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
"""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# 1. Rubric Schemas
# =============================================================================

class RubricCriteriaCreateRequest(BaseModel):
    """Payload to define an evaluation dimension within a rubric."""

    title: str = Field(..., min_length=1, max_length=255, description="Criterion headline")
    description: Optional[str] = Field(None, max_length=2000, description="Guidance notes for grading")
    max_points: float = Field(..., ge=0.0, le=1000.0, description="Maximum point ceiling")
    weight: float = Field(default=1.0, ge=0.0, le=100.0, description="Multiplier weight")
    sort_order: int = Field(default=0, ge=0, description="Relative sort ordering")


class RubricCriteriaResponse(BaseModel):
    """Schema representing an individual evaluation criterion."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rubric_id: uuid.UUID
    title: str
    description: Optional[str] = None
    max_points: float
    weight: float
    sort_order: int


class RubricCreateRequest(BaseModel):
    """Payload to configure a grading rubric template."""

    title: str = Field(..., min_length=1, max_length=255, description="Rubric template title")
    criteria: List[RubricCriteriaCreateRequest] = Field(
        ...,
        min_length=1,
        description="At least one rubric criterion is required",
    )


class RubricResponse(BaseModel):
    """Schema representing an active rubric template."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    title: str
    version: int
    is_active: bool
    created_at: datetime
    criteria: List[RubricCriteriaResponse] = []


# =============================================================================
# 2. Assignment Schemas
# =============================================================================

class AssignmentCreateRequest(BaseModel):
    """Payload to configure an assignment for a curriculum lesson."""

    title: str = Field(..., min_length=1, max_length=255, description="Assignment headline")
    instructions: str = Field(..., min_length=1, description="Markdown instructions and prompt")
    max_score: float = Field(default=100.0, gt=0.0, le=1000.0, description="Maximum possible score")
    pass_score: float = Field(default=50.0, ge=0.0, le=1000.0, description="Minimum score to pass")
    allow_late: bool = Field(default=False, description="Accept submissions after due date")
    due_date: Optional[datetime] = Field(default=None, description="UTC submission deadline")
    rubric: Optional[RubricCreateRequest] = Field(default=None, description="Optional initial rubric")


class AssignmentUpdateRequest(BaseModel):
    """Payload to update assignment configuration."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    instructions: Optional[str] = Field(None, min_length=1)
    max_score: Optional[float] = Field(None, gt=0.0, le=1000.0)
    pass_score: Optional[float] = Field(None, ge=0.0, le=1000.0)
    allow_late: Optional[bool] = None
    due_date: Optional[datetime] = None


class AssignmentResponse(BaseModel):
    """Schema representing an assignment configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    instructions: str
    max_score: float
    pass_score: float
    allow_late: bool
    due_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    active_rubric: Optional[RubricResponse] = None


# =============================================================================
# 3. Submission & Grading Schemas
# =============================================================================

class SubmissionCreateRequest(BaseModel):
    """Payload for student project upload submission."""

    file_url: str = Field(..., min_length=1, max_length=512, description="Storage URL or asset key")
    text_notes: Optional[str] = Field(None, max_length=5000, description="Student notes or explanation")


class RubricScoreInput(BaseModel):
    """Point allocation per rubric criterion during grading."""

    criteria_id: uuid.UUID
    points_awarded: float = Field(..., ge=0.0, description="Points awarded for criterion")
    feedback: Optional[str] = Field(None, max_length=2000, description="Dimension-specific feedback")


class RubricScoreResponse(BaseModel):
    """Schema representing an awarded rubric criterion score."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    criteria_id: uuid.UUID
    criteria_title: Optional[str] = None
    max_points: Optional[float] = None
    weight: Optional[float] = None
    points_awarded: float
    feedback: Optional[str] = None


class GradeSubmissionRequest(BaseModel):
    """Payload for staff rubric evaluation of a submission."""

    scores: List[RubricScoreInput] = Field(
        ...,
        min_length=1,
        description="Rubric points awarded for every criterion",
    )
    overall_feedback: Optional[str] = Field(
        None,
        max_length=5000,
        description="Overall evaluator qualitative feedback",
    )


class GradeOverrideRequest(BaseModel):
    """Payload for Super Admin manual score override."""

    new_score: float = Field(..., ge=0.0, le=1000.0, description="Adjusted score")
    reason: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Mandatory justification note explaining adjustment",
    )


class GradeOverrideResponse(BaseModel):
    """Schema representing an administrative grade override record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    original_score: float
    overridden_score: float
    reason: str
    overridden_by: uuid.UUID
    overrider_name: Optional[str] = None
    created_at: datetime


class SubmissionResponse(BaseModel):
    """Schema representing a student submission and its evaluation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    attempt_no: int
    file_url: str
    text_notes: Optional[str] = None
    status: str
    submitted_at: datetime
    final_score: Optional[float] = None
    graded_at: Optional[datetime] = None
    graded_by: Optional[uuid.UUID] = None
    grader_name: Optional[str] = None
    feedback: Optional[str] = None
    rubric_scores: List[RubricScoreResponse] = []
    grade_overrides: List[GradeOverrideResponse] = []


class SubmissionListResponse(BaseModel):
    """Paginated envelope for assignment submissions."""

    items: List[SubmissionResponse]
    total: int
    page: int
    size: int
