"""Super Admin Control Dashboard & Analytics REST API endpoints (SA-01).

Architecture Specifications:
- docs/MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md (Section 6, SA-01)
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md

Strict Invariants:
1. Super Admin Only: Restricted strictly to callers with the active SUPER_ADMIN role.
2. Verified Metrics Only: Never returns fabricated, simulated, or randomized numbers.
3. Server-Side Protection: Unauthenticated and non-super-admin callers receive 401/403.
"""

from datetime import datetime
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_and_session, get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.models.auth_session import AuthSession
from app.models.user import ROLE_SUPER_ADMIN, User
from app.schemas.control import (
    ControlOverviewResponse,
    CourseGovernanceItemResponse,
    CourseGovernanceListResponse,
    CourseStatusUpdateRequest,
    DetailedSecurityMetricsResponse,
    EmergencyRevocationRequest,
    EmergencyRevocationResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionRevokeRequest,
    UserSessionsRevokeResponse,
)
from app.schemas.blog import (
    BlogPostCreateRequest,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostStatusRequest,
    BlogPostUpdateRequest,
)
from app.schemas.note import (
    NoteCreateRequest,
    NoteListResponse,
    NoteReplacePdfRequest,
    NoteResponse,
    NoteStatusRequest,
    NoteUpdateRequest,
)
from app.services.control_service import ControlService
from app.services.session_service import SessionService
from app.services.blog_service import BlogService
from app.services.note_service import NoteService
from app.services.course_governance_service import CourseGovernanceService
from app.schemas.offer import (
    OfferCreateRequest,
    OfferListResponse,
    OfferResponse,
    OfferStatusRequest,
    OfferUpdateRequest,
)
from app.schemas.payment_overview import (
    PaymentMetricsResponse,
    TransactionItemResponse,
    TransactionListResponse,
)
from app.schemas.settings import (
    PlatformSettingsUpdateRequest,
    PublicPlatformInfoResponse,
)
from app.schemas.user import (
    UserCreateRequest,
    UserProfileResponse,
)
from app.services.user_service import UserService
from app.services.offer_service import OfferService
from app.services.payment_overview_service import PaymentOverviewService
from app.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/control", tags=["Super Admin Control"])


def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Enforces that caller has an active, authenticated SUPER_ADMIN role."""
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        raise ForbiddenException(
            message="This administrative command center is restricted strictly to Super Administrators.",
            code="SUPER_ADMIN_REQUIRED",
        )
    return current_user


async def require_super_admin_and_session(
    auth_tuple: tuple[User, Optional[AuthSession]] = Depends(get_current_user_and_session),
) -> tuple[User, AuthSession]:
    """Enforce Super Admin role and extract verified server-side active session.

    Guarantees caller session is derived strictly from server-authenticated context.
    """
    user, session = auth_tuple
    if not user.has_role(ROLE_SUPER_ADMIN):
        raise ForbiddenException(
            message="This administrative command center is restricted strictly to Super Administrators.",
            code="SUPER_ADMIN_REQUIRED",
        )
    if session is None:
        raise UnauthorizedException(
            message="Active session required for emergency containment operations.",
            code="SESSION_REQUIRED",
        )
    return user, session


def get_control_service() -> ControlService:
    """Dependency providing configured ControlService instance."""
    return ControlService()


def get_session_service() -> SessionService:
    """Dependency providing configured SessionService instance."""
    return SessionService()


def get_user_service() -> UserService:
    """Dependency providing configured UserService instance."""
    return UserService()


@router.get(
    "/overview",
    response_model=ControlOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Super Admin command center overview and platform analytics",
)
def get_control_overview_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    control_service: ControlService = Depends(get_control_service),
) -> ControlOverviewResponse:
    """Computes and returns verified real-time platform statistics for Super Admin.

    Includes:
    - User metrics (students, staff, admins, super admins, active accounts)
    - Course metrics (total, published, draft, archived)
    - Enrollment metrics (total, active)
    - Financial metrics (verified revenue in paise/INR, successful orders, net revenue)
    - Security metrics (audit event counts, security incident count, active staff)
    - 14-day rolling activity trends (registrations, enrollments)
    - Recent platform audit activity feed
    """
    return control_service.get_overview(db)


# =============================================================================
# SA-03: Session Governance Endpoints
# =============================================================================

@router.get(
    "/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter authentication sessions across the platform",
)
async def list_sessions_endpoint(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (ACTIVE, REVOKED, EXPIRED)"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by owner user UUID"),
    role: Optional[str] = Query(None, description="Filter by assigned role"),
    ip_address: Optional[str] = Query(None, description="Filter by client IP address"),
    search: Optional[str] = Query(None, description="Search user name or email"),
    date_from: Optional[datetime] = Query(None, description="Earliest session creation date"),
    date_to: Optional[datetime] = Query(None, description="Latest session creation date"),
    sort_by: str = Query("created_at", description="Field to sort by (created_at, last_active_at, expires_at)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    session_service: SessionService = Depends(get_session_service),
) -> SessionListResponse:
    """Super Admin live session surveillance and directory search."""
    return await session_service.list_sessions(
        db,
        status=status_filter,
        user_id=user_id,
        role=role,
        ip_address=ip_address,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/sessions/{id}",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get comprehensive single-session details and correlated auth events",
)
async def get_session_detail_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    session_service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    """Retrieve full session profile with correlated auth events."""
    return await session_service.get_session_detail(db, id)


@router.post(
    "/sessions/{id}/revoke",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke an individual session with justification",
)
async def revoke_session_endpoint(
    id: uuid.UUID,
    payload: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    session_service: SessionService = Depends(get_session_service),
) -> SessionDetailResponse:
    """Targeted session termination with mandatory justification and audit logging."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    res = await session_service.revoke_session_admin(
        db,
        id,
        reason=payload.reason,
        actor_id=current_user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()
    return res


@router.post(
    "/users/{id}/revoke-sessions",
    response_model=UserSessionsRevokeResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke all active sessions for a specific user",
)
async def revoke_user_sessions_endpoint(
    id: uuid.UUID,
    payload: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    session_service: SessionService = Depends(get_session_service),
) -> UserSessionsRevokeResponse:
    """Revoke all active sessions for a target user (e.g. on compromise or theft)."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    res = await session_service.revoke_user_sessions_admin(
        db,
        id,
        reason=payload.reason,
        actor_id=current_user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()
    return res


@router.post(
    "/users",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Super Admin manual user provisioning",
)
async def create_user_control_endpoint(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Provisions a new user account with personal details, credentials, and role.

    Strictly restricted to authorized Super Admins.
    """
    user = await user_service.create_user(db, data, actor=current_user)
    db.commit()
    return user


@router.post(
    "/sessions/revoke-others",
    response_model=EmergencyRevocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Emergency platform containment: revoke all other active sessions",
)
async def revoke_other_sessions_endpoint(
    payload: EmergencyRevocationRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_data: tuple[User, AuthSession] = Depends(require_super_admin_and_session),
    session_service: SessionService = Depends(get_session_service),
) -> EmergencyRevocationResponse:
    """Emergency platform containment.

    Revokes all active sessions across all accounts while strictly preserving
    the authenticated caller session derived from verified server context.
    """
    caller_user, caller_session = auth_data
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    res = await session_service.revoke_other_active_sessions_admin(
        db,
        caller_session_id=caller_session.id,
        caller_id=caller_user.id,
        reason=payload.reason,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()
    return res


# =============================================================================
# SA-03: Security Governance Metrics Endpoint
# =============================================================================

@router.get(
    "/security/metrics",
    response_model=DetailedSecurityMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Authoritative real-time security governance metrics",
)
async def get_security_metrics_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    session_service: SessionService = Depends(get_session_service),
) -> DetailedSecurityMetricsResponse:
    """Compute and deliver technical security surveillance metrics."""
    return await session_service.get_security_metrics(db)


# =============================================================================
# SA-04.1: Course Governance Endpoints
# =============================================================================

def get_course_governance_service() -> CourseGovernanceService:
    """Dependency providing CourseGovernanceService instance."""
    return CourseGovernanceService()


@router.get(
    "/courses",
    response_model=CourseGovernanceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all courses for platform governance",
)
async def list_governed_courses_endpoint(
    search: Optional[str] = Query(None, description="Search course title, slug, or headline"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (DRAFT, PUBLISHED, ARCHIVED)"),
    sort_by: str = Query("created_at", description="Sort attribute"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: CourseGovernanceService = Depends(get_course_governance_service),
) -> CourseGovernanceListResponse:
    """Search and filter all courses with curriculum and enrollment statistics."""
    return service.list_governed_courses(
        db,
        search=search,
        status=status_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/courses/{id}",
    response_model=CourseGovernanceItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single course governance detail",
)
async def get_governed_course_detail_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: CourseGovernanceService = Depends(get_course_governance_service),
) -> CourseGovernanceItemResponse:
    """Inspect complete course governance metadata."""
    return service.get_course_governance_detail(db, id)


@router.patch(
    "/courses/{id}/status",
    response_model=CourseGovernanceItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Change course lifecycle status",
)
async def update_course_status_endpoint(
    id: uuid.UUID,
    payload: CourseStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: CourseGovernanceService = Depends(get_course_governance_service),
) -> CourseGovernanceItemResponse:
    """Transition course status (DRAFT, PUBLISHED, ARCHIVED) with audit logging."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return await service.update_course_status(
        db,
        current_user,
        id,
        target_status=payload.status,
        reason=payload.reason,
        ip_address=client_ip,
        user_agent=user_agent,
    )


# =============================================================================
# SA-04.2: Blog CMS Endpoints
# =============================================================================

def get_blog_service() -> BlogService:
    """Dependency providing BlogService instance."""
    return BlogService()


@router.get(
    "/blog/categories",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Get all unique blog categories",
)
async def get_blog_categories_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> list[str]:
    """Retrieve unique blog categories."""
    return service.get_categories(db)


@router.get(
    "/blog",
    response_model=BlogPostListResponse,
    status_code=status.HTTP_200_OK,
    summary="List blog posts with filtering",
)
async def list_blog_posts_endpoint(
    search: Optional[str] = Query(None, description="Search term for title, slug, or content"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (DRAFT, PUBLISHED, ARCHIVED)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sort_by: str = Query("created_at", description="Sort attribute"),
    sort_order: str = Query("desc", description="Sort direction"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> BlogPostListResponse:
    """List blog posts for Super Admin management."""
    return service.list_posts(
        db,
        search=search,
        status=status_filter,
        category=category,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/blog",
    response_model=BlogPostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new blog post",
)
async def create_blog_post_endpoint(
    data: BlogPostCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> BlogPostResponse:
    """Create a new blog post entity."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.create_post(
        db,
        current_user,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.get(
    "/blog/{id}",
    response_model=BlogPostResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single blog post",
)
async def get_blog_post_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> BlogPostResponse:
    """Retrieve full blog post details."""
    return service.get_post(db, id)


@router.put(
    "/blog/{id}",
    response_model=BlogPostResponse,
    status_code=status.HTTP_200_OK,
    summary="Update existing blog post",
)
async def update_blog_post_endpoint(
    id: uuid.UUID,
    data: BlogPostUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> BlogPostResponse:
    """Update blog post content and metadata."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.update_post(
        db,
        current_user,
        id,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.patch(
    "/blog/{id}/status",
    response_model=BlogPostResponse,
    status_code=status.HTTP_200_OK,
    summary="Change blog post publication status",
)
async def change_blog_status_endpoint(
    id: uuid.UUID,
    payload: BlogPostStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> BlogPostResponse:
    """Publish, unpublish, or archive a blog post."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.change_status(
        db,
        current_user,
        id,
        payload.status,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.delete(
    "/blog/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete blog post",
)
async def delete_blog_post_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: BlogService = Depends(get_blog_service),
) -> None:
    """Delete a blog post permanently."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    service.delete_post(
        db,
        current_user,
        id,
        ip_address=client_ip,
        user_agent=user_agent,
    )


# =============================================================================
# SA-04.3: Notes CMS Endpoints
# =============================================================================

def get_note_service() -> NoteService:
    """Dependency providing NoteService instance."""
    return NoteService()


@router.get(
    "/notes/categories",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Get all unique note categories",
)
async def get_notes_categories_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> list[str]:
    """Retrieve unique study note categories."""
    return service.get_categories(db)


@router.get(
    "/notes",
    response_model=NoteListResponse,
    status_code=status.HTTP_200_OK,
    summary="List study notes with filtering",
)
async def list_notes_endpoint(
    search: Optional[str] = Query(None, description="Search title, slug, or description"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (DRAFT, PUBLISHED, ARCHIVED)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sort_by: str = Query("created_at", description="Sort attribute"),
    sort_order: str = Query("desc", description="Sort direction"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteListResponse:
    """List study notes for Super Admin management."""
    return service.list_notes(
        db,
        search=search,
        status=status_filter,
        category=category,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new study note",
)
async def create_note_endpoint(
    data: NoteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Create a new study note entity."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.create_note(
        db,
        current_user,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.get(
    "/notes/{id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single study note",
)
async def get_note_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Retrieve full study note details."""
    return service.get_note(db, id)


@router.put(
    "/notes/{id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Update existing study note",
)
async def update_note_endpoint(
    id: uuid.UUID,
    data: NoteUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Update study note metadata."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.update_note(
        db,
        current_user,
        id,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.post(
    "/notes/{id}/pdf",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace note PDF document",
)
async def replace_note_pdf_endpoint(
    id: uuid.UUID,
    data: NoteReplacePdfRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Replace the attached PDF document for a note."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.replace_pdf(
        db,
        current_user,
        id,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.patch(
    "/notes/{id}/status",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Change note publication status",
)
async def change_note_status_endpoint(
    id: uuid.UUID,
    payload: NoteStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Publish, unpublish, or archive a note."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    return service.change_status(
        db,
        current_user,
        id,
        payload.status,
        ip_address=client_ip,
        user_agent=user_agent,
    )


@router.delete(
    "/notes/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete study note",
)
async def delete_note_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: NoteService = Depends(get_note_service),
) -> None:
    """Delete a study note permanently."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    service.delete_note(
        db,
        current_user,
        id,
        ip_address=client_ip,
        user_agent=user_agent,
    )


# =============================================================================
# SA-05.1: Offers Management Endpoints
# =============================================================================

def get_offer_service() -> OfferService:
    """Dependency providing OfferService instance."""
    return OfferService()


@router.get(
    "/offers",
    response_model=OfferListResponse,
    status_code=status.HTTP_200_OK,
    summary="List promotional offers with filtering and pagination",
)
async def list_offers_endpoint(
    search: Optional[str] = Query(None, description="Search by name, code, or description"),
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE, INACTIVE, ARCHIVED)"),
    discount_type: Optional[str] = Query(None, description="Filter by discount type (PERCENTAGE, FIXED)"),
    course_id: Optional[uuid.UUID] = Query(None, description="Filter by course target"),
    sort_by: str = Query("created_at", description="Sort attribute"),
    sort_order: str = Query("desc", description="Sort direction (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> OfferListResponse:
    """Retrieve promotional offers with filtering and pagination."""
    return service.list_offers(
        db,
        search=search,
        status=status,
        discount_type=discount_type,
        course_id=course_id,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/offers",
    response_model=OfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create promotional offer",
)
async def create_offer_endpoint(
    data: OfferCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Configure a new promotional discount offer."""
    client_ip = request.client.host if request.client else None
    return service.create_offer(
        db,
        current_user,
        data,
        ip_address=client_ip,
    )


@router.get(
    "/offers/{id}",
    response_model=OfferResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single promotional offer by ID",
)
async def get_offer_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Retrieve details for a single promotional offer."""
    return service.get_offer(db, id)


@router.put(
    "/offers/{id}",
    response_model=OfferResponse,
    status_code=status.HTTP_200_OK,
    summary="Update promotional offer",
)
async def update_offer_endpoint(
    id: uuid.UUID,
    data: OfferUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Update fields on an existing promotional offer."""
    client_ip = request.client.host if request.client else None
    return service.update_offer(
        db,
        current_user,
        id,
        data,
        ip_address=client_ip,
    )


@router.patch(
    "/offers/{id}/status",
    response_model=OfferResponse,
    status_code=status.HTTP_200_OK,
    summary="Change promotional offer status",
)
async def change_offer_status_endpoint(
    id: uuid.UUID,
    payload: OfferStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> OfferResponse:
    """Activate, deactivate, or archive an offer."""
    client_ip = request.client.host if request.client else None
    return service.change_status(
        db,
        current_user,
        id,
        payload.status,
        ip_address=client_ip,
    )


@router.delete(
    "/offers/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete promotional offer",
)
async def delete_offer_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: OfferService = Depends(get_offer_service),
) -> None:
    """Permanently delete a promotional offer."""
    client_ip = request.client.host if request.client else None
    service.delete_offer(
        db,
        current_user,
        id,
        ip_address=client_ip,
    )


# =============================================================================
# SA-05.2: Payment Overview Endpoints
# =============================================================================

def get_payment_overview_service() -> PaymentOverviewService:
    """Dependency providing PaymentOverviewService instance."""
    return PaymentOverviewService()


@router.get(
    "/payments/overview",
    response_model=PaymentMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get commercial payment metrics overview",
)
async def get_payment_overview_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: PaymentOverviewService = Depends(get_payment_overview_service),
) -> PaymentMetricsResponse:
    """Aggregate platform commercial metrics strictly from real database records."""
    return service.get_financial_metrics(db)


@router.get(
    "/payments/transactions",
    response_model=TransactionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List payment transactions with filters and pagination",
)
async def list_transactions_endpoint(
    search: Optional[str] = Query(None, description="Search by payment ID, order no, student, course"),
    status: Optional[str] = Query(None, description="Filter by status (SUCCESS, FAILED)"),
    start_date: Optional[datetime] = Query(None, description="Start timestamp"),
    end_date: Optional[datetime] = Query(None, description="End timestamp"),
    sort_by: str = Query("processed_at", description="Sort attribute"),
    sort_order: str = Query("desc", description="Sort direction"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: PaymentOverviewService = Depends(get_payment_overview_service),
) -> TransactionListResponse:
    """Paginated search and inspection of payment transactions."""
    return service.list_transactions(
        db,
        search=search,
        status=status,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/payments/transactions/{id}",
    response_model=TransactionItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single transaction detail",
)
async def get_transaction_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: PaymentOverviewService = Depends(get_payment_overview_service),
) -> TransactionItemResponse:
    """Retrieve full transaction details with order, student, and refund references."""
    return service.get_transaction(db, id)


# =============================================================================
# SA-05.3: Platform Information & Settings Endpoints
# =============================================================================

def get_platform_settings_service() -> PlatformSettingsService:
    """Dependency providing PlatformSettingsService instance."""
    return PlatformSettingsService()


@router.get(
    "/settings",
    response_model=PublicPlatformInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get safe public platform information and settings",
)
async def get_platform_settings_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: PlatformSettingsService = Depends(get_platform_settings_service),
) -> PublicPlatformInfoResponse:
    """Retrieve non-sensitive platform settings and branding context."""
    return service.get_public_platform_info(db)


@router.put(
    "/settings",
    response_model=PublicPlatformInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Update platform and branding settings",
)
async def update_platform_settings_endpoint(
    data: PlatformSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    service: PlatformSettingsService = Depends(get_platform_settings_service),
) -> PublicPlatformInfoResponse:
    """Update authorized platform and branding configuration."""
    client_ip = request.client.host if request.client else None
    return service.update_platform_settings(
        db,
        current_user,
        data,
        ip_address=client_ip,
    )


