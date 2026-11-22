"""User Management and Staff Administration REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.2)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK203, TASK204)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3, 8]
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_permissions,
)
from app.core.exceptions import ForbiddenException
from app.core.permissions import (
    ROLES_ASSIGN,
    STAFF_INVITE,
    USERS_EDIT,
    USERS_MANAGE_STATUS,
    USERS_VIEW,
    USERS_VIEW_ALL,
)
from app.models.user import ROLE_ADMIN, ROLE_SUPER_ADMIN, User
from app.schemas.user import (
    StaffInviteRequest,
    StudentLearningSummaryResponse,
    UserCreateRequest,
    UserDirectoryResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


def get_user_service() -> UserService:
    """Dependency providing configured UserService instance."""
    return UserService()


def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Enforces caller has an active, authenticated SUPER_ADMIN role."""
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        raise ForbiddenException(
            message="User provisioning is restricted strictly to Super Administrators.",
            code="SUPER_ADMIN_REQUIRED",
        )
    return current_user


@router.get(
    "",
    response_model=UserDirectoryResponse,
    summary="Paginated user directory with search/role filters and sorting",
)
async def list_users_endpoint(
    search: Optional[str] = Query(None, description="Search query for name or email"),
    role: Optional[str] = Query(None, description="Filter by assigned system role"),
    is_active: Optional[bool] = Query(None, description="Filter by activation status"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification status"),
    sort_by: Optional[str] = Query("created_at", description="Sort field: created_at, full_name, email"),
    sort_order: Optional[str] = Query("desc", description="Sort direction: asc, desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(USERS_VIEW_ALL)),
    user_service: UserService = Depends(get_user_service),
) -> UserDirectoryResponse:
    """List platform users with filtering, sorting, and pagination. Requires users:view_all."""
    return await user_service.list_users(
        db,
        search=search,
        role=role,
        is_active=is_active,
        is_verified=is_verified,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )


@router.post(
    "",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user account (Super Admin only)",
)
async def create_user_endpoint(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Super Admin manual user creation with credentials, role, and audit logging."""
    user = await user_service.create_user(db, data, actor=current_user)
    db.commit()
    return user


@router.get(
    "/{id}",
    response_model=UserProfileResponse,
    summary="Retrieve detailed user profile",
)
async def get_user_profile_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Retrieve detailed profile. Allowed for own profile, or callers with users:view permission."""
    is_self = current_user.id == id
    is_super = ROLE_SUPER_ADMIN in current_user.roles
    has_perm = current_user.has_permission(USERS_VIEW)

    if not (is_self or is_super or has_perm):
        raise ForbiddenException(
            message="Not authorized to inspect this user's profile.",
            code="PERMISSION_DENIED",
        )

    return await user_service.get_user_profile(db, id)


@router.get(
    "/{id}/learning-records",
    response_model=StudentLearningSummaryResponse,
    summary="Retrieve comprehensive learning records and performance for a student",
)
async def get_student_learning_records_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> StudentLearningSummaryResponse:
    """Retrieve enrollments, quiz attempts, assignments, certificates, and audit log for a student."""
    is_self = current_user.id == id
    is_super = ROLE_SUPER_ADMIN in current_user.roles
    has_perm = current_user.has_permission(USERS_VIEW)

    if not (is_self or is_super or has_perm):
        raise ForbiddenException(
            message="Not authorized to inspect this user's learning records.",
            code="PERMISSION_DENIED",
        )

    return await user_service.get_student_learning_summary(db, id)


@router.patch(
    "/{id}",
    response_model=UserProfileResponse,
    summary="Update user profile data",
)
async def update_user_profile_endpoint(
    id: uuid.UUID,
    payload: UserProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Update user profile. Allowed for own profile, or callers with users:edit permission."""
    is_self = current_user.id == id
    is_super = ROLE_SUPER_ADMIN in current_user.roles
    has_perm = current_user.has_permission(USERS_EDIT)

    if not (is_self or is_super or has_perm):
        raise ForbiddenException(
            message="Not authorized to edit this user's profile.",
            code="PERMISSION_DENIED",
        )

    return await user_service.update_profile(
        db,
        id,
        full_name=payload.full_name,
        avatar_url=payload.avatar_url,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.patch(
    "/{id}/status",
    response_model=UserProfileResponse,
    summary="Activate, suspend, or restore user account",
)
async def update_user_status_endpoint(
    id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(USERS_MANAGE_STATUS)),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Activate or suspend a user account. Requires users:manage_status.

    Enforces Sole Super Admin Protection Invariant:
    Cannot suspend the final active Super Admin account.
    """
    return await user_service.update_user_status(
        db,
        user_id=id,
        is_active=payload.is_active,
        reason=payload.reason,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post(
    "/staff/invite",
    status_code=status.HTTP_201_CREATED,
    summary="Send onboarding invitation token to new staff member",
)
async def invite_staff_endpoint(
    payload: StaffInviteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(STAFF_INVITE)),
    user_service: UserService = Depends(get_user_service),
) -> dict:
    """Invite a new staff member or administrator with a 48h token. Requires staff:invite.

    Privilege Escalation Protection: Inviting an ADMIN requires SUPER_ADMIN caller role.
    """
    if payload.role == ROLE_ADMIN and not current_user.has_role(ROLE_SUPER_ADMIN):
        raise ForbiddenException(
            message="Only Super Administrators can invite administrators.",
            code="SUPER_ADMIN_REQUIRED",
        )

    return await user_service.invite_staff(
        db,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.patch(
    "/{id}/roles",
    response_model=UserProfileResponse,
    summary="Assign or revoke system roles for a user",
)
async def manage_user_roles_endpoint(
    id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ROLES_ASSIGN)),
    user_service: UserService = Depends(get_user_service),
) -> UserProfileResponse:
    """Assign or revoke user roles. Requires roles:assign.

    Enforces Sole Super Admin Protection Invariant:
    Cannot revoke SUPER_ADMIN role from the final active Super Admin.
    """
    return await user_service.manage_user_role(
        db,
        user_id=id,
        role_id=payload.role_id,
        action=payload.action,
        actor_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
