"""Pydantic v2 schemas for Super Admin Control Dashboard & Analytics (SA-01).

Architecture Specifications:
- docs/MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md (Section 6, SA-01)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3]
"""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.audit import AuditLogResponse


class UserMetrics(BaseModel):
    """Aggregate statistics for user personas across the platform."""

    total_students: int = Field(0, description="Total verified/unverified student accounts")
    total_admins: int = Field(0, description="Total administrative users")
    total_staff: int = Field(0, description="Total staff members / teaching assistants")
    total_super_admins: int = Field(0, description="Total super administrator accounts")
    active_users: int = Field(0, description="Total currently active user accounts")


class CourseMetrics(BaseModel):
    """Aggregate course counts by publication lifecycle status."""

    total_courses: int = Field(0, description="Total course containers in system")
    published_courses: int = Field(0, description="Courses currently live on public storefront")
    draft_courses: int = Field(0, description="Courses currently in draft/authoring state")
    archived_courses: int = Field(0, description="Courses archived from catalog")


class EnrollmentMetrics(BaseModel):
    """Aggregate enrollment counts across courses."""

    total_enrollments: int = Field(0, description="Total lifetime course enrollments")
    active_enrollments: int = Field(0, description="Enrollments with active access status")


class FinancialMetrics(BaseModel):
    """Commercial revenue and transaction metrics computed strictly from verified records."""

    verified_revenue_paise: int = Field(0, description="Total gross verified revenue in minor currency units (paise)")
    verified_revenue_inr: float = Field(0.0, description="Total gross verified revenue in INR")
    successful_transactions: int = Field(0, description="Total count of verified paid commercial orders")
    refunded_amount_paise: int = Field(0, description="Total processed refunds in minor currency units (paise)")
    refunded_amount_inr: float = Field(0.0, description="Total processed refunds in INR")
    net_revenue_paise: int = Field(0, description="Net revenue (gross revenue minus processed refunds)")
    net_revenue_inr: float = Field(0.0, description="Net revenue in INR")
    currency: str = Field("INR", description="Three-letter ISO currency code")


class SecurityMetrics(BaseModel):
    """Platform security and audit health indicators."""

    total_audit_events: int = Field(0, description="Total events recorded in immutable audit log")
    security_events_count: int = Field(0, description="Security-sensitive events (revocations, suspensions, failures)")
    active_staff_count: int = Field(0, description="Currently active staff members")
    security_model: str = Field(
        "Tier 1 Hardened (Single-Active-Session & Signed Tokens)",
        description="Active platform security profile",
    )


class DailyTrendPoint(BaseModel):
    """Time-series data point for daily activity tracking."""

    date: str = Field(..., description="Date formatted as YYYY-MM-DD")
    count: int = Field(0, description="Activity count recorded on this date")


class ControlOverviewResponse(BaseModel):
    """Authoritative Super Admin platform overview and analytics payload."""

    user_metrics: UserMetrics
    course_metrics: CourseMetrics
    enrollment_metrics: EnrollmentMetrics
    financial_metrics: FinancialMetrics
    security_metrics: SecurityMetrics
    registration_trends: List[DailyTrendPoint] = Field(default_factory=list)
    enrollment_trends: List[DailyTrendPoint] = Field(default_factory=list)
    recent_activity: List[AuditLogResponse] = Field(default_factory=list)
    generated_at: datetime = Field(..., description="UTC timestamp when metrics were computed")


# =============================================================================
# SA-03: Security Governance & Session Management Schemas
# =============================================================================

class SessionUserSummary(BaseModel):
    """Compact summary of the user account associated with a session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    roles: List[str] = Field(default_factory=list)
    is_active: bool


class SessionItemResponse(BaseModel):
    """Representation of an authentication session for Super Admin surveillance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user: Optional[SessionUserSummary] = None
    status: str = Field(..., description="Session state: ACTIVE, REVOKED, EXPIRED")
    ip_address: Optional[str] = Field(None, description="Client IPv4 or IPv6 address")
    user_agent: Optional[str] = Field(None, description="Client browser user agent header")
    last_active_at: datetime
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[uuid.UUID] = None
    revocation_reason: Optional[str] = None


class SessionListResponse(BaseModel):
    """Paginated collection of sessions with total counts."""

    items: List[SessionItemResponse]
    total: int
    page: int
    per_page: int
    pages: int


class SessionDetailResponse(SessionItemResponse):
    """Comprehensive single-session details including correlated authentication audit events."""

    correlated_events: List[AuditLogResponse] = Field(
        default_factory=list,
        description="Audit events correlated with this session via direct entity, metadata, or time-window match",
    )


class SessionRevokeRequest(BaseModel):
    """Payload to revoke a specific session."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Mandatory justification for session termination",
        examples=["Suspected credential compromise reported by user."],
    )


class UserSessionsRevokeResponse(BaseModel):
    """Confirmation payload after terminating all active sessions for a target user."""

    user_id: uuid.UUID
    revoked_sessions_count: int
    message: str


class EmergencyRevocationRequest(BaseModel):
    """Payload for platform-wide emergency session containment."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Mandatory justification for emergency containment",
        examples=["Emergency platform containment: Instructor credential rotation."],
    )


class EmergencyRevocationResponse(BaseModel):
    """Response confirming emergency session revocation preserving authenticated caller."""

    revoked_sessions_count: int
    caller_session_id: uuid.UUID
    caller_session_preserved: bool = True
    message: str


class DetailedSecurityMetricsResponse(BaseModel):
    """Authoritative technical security surveillance metrics computed strictly from database records."""

    active_sessions_total: int = Field(0, description="Total currently active, non-expired sessions")
    active_sessions_by_role: dict[str, int] = Field(
        default_factory=dict,
        description="Active session breakdown by canonical role (STUDENT, STAFF, ADMIN, SUPER_ADMIN, VISITOR)",
    )
    sessions_revoked_24h: int = Field(0, description="Sessions marked REVOKED in the last 24 hours")
    sessions_displaced_24h: int = Field(0, description="Session displacement events in the last 24 hours")
    sessions_expired_24h: int = Field(0, description="Sessions transitioned to EXPIRED in the last 24 hours")
    failed_logins_24h: int = Field(0, description="Recorded AUTH_LOGIN_FAILED audit events in the last 24 hours")
    rate_limit_breaches_24h: int = Field(0, description="Recorded AUTH_RATE_LIMIT_EXCEEDED events in the last 24 hours")
    suspended_accounts_total: int = Field(0, description="Total currently suspended/inactive user accounts")
    generated_at: datetime = Field(..., description="UTC timestamp when metrics were computed")


# =============================================================================
# SA-04: Course Governance Schemas
# =============================================================================


class CourseStatusUpdateRequest(BaseModel):
    """Payload for administrative course lifecycle status transition."""

    status: str = Field(
        ...,
        description="Target course status (DRAFT, PUBLISHED, ARCHIVED)",
        examples=["PUBLISHED"],
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Administrative justification recorded in audit log",
    )


class CourseGovernanceItemResponse(BaseModel):
    """Enriched course summary for Super Admin platform governance."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    headline: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    category: str = "General"
    difficulty_level: str = "ALL_LEVELS"
    language: str = "English"
    status: str
    price_inr: int
    compare_at_price_inr: Optional[int] = None
    currency: str = "INR"
    discount_percentage: Optional[int] = None
    is_free: bool
    tags: List[str] = Field(default_factory=list)
    live_revision_id: Optional[uuid.UUID] = None
    draft_revision_id: Optional[uuid.UUID] = None
    latest_revision_id: Optional[uuid.UUID] = None
    total_sections: int = 0
    total_lessons: int = 0
    total_duration_seconds: int = 0
    has_quiz: bool = False
    has_assignment: bool = False
    enrolled_students_count: int = 0
    created_at: datetime
    updated_at: datetime


class CourseGovernanceListResponse(BaseModel):
    """Paginated course governance list envelope."""

    items: List[CourseGovernanceItemResponse]
    total: int
    page: int
    per_page: int
    pages: int

