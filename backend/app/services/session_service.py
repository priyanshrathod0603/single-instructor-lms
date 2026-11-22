"""Session governance and security surveillance domain service (SA-03).

Architecture Specifications:
- docs/SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md

Strict Invariants:
1. Super Admin Authority: All operations are executed on behalf of verified Super Admin callers.
2. Verified Metrics Only: Never returns fabricated, simulated, or randomized numbers.
3. Caller Session Preservation: Emergency revocation strictly preserves the authenticated caller session.
4. Idempotency: Revoking already-revoked or expired sessions produces zero redundant updates.
5. Append-Only Auditing: Every administrative revocation emits an immutable audit log record.
"""

from datetime import datetime, timedelta
import logging
import math
from typing import Any, Dict, List, Optional, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestException,
    NotFoundException,
    ValidationException,
)
from app.models.audit_log import AuditLog
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.base import utc_now
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    ROLE_VISITOR,
    SYSTEM_ROLES,
    User,
    UserRole,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.schemas.audit import AuditLogResponse
from app.schemas.control import (
    DetailedSecurityMetricsResponse,
    EmergencyRevocationResponse,
    SessionDetailResponse,
    SessionItemResponse,
    SessionListResponse,
    SessionUserSummary,
    UserSessionsRevokeResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class SessionService:
    """Service handling session surveillance, targeted/emergency revocation, and security metrics."""

    def __init__(
        self,
        session_repo: Optional[SessionRepository] = None,
        user_repo: Optional[UserRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self.session_repo = session_repo or SessionRepository()
        self.user_repo = user_repo or UserRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.audit_service = audit_service or AuditService()

    def _to_user_summary(self, user: Optional[User]) -> Optional[SessionUserSummary]:
        if not user:
            return None
        roles = [ur.role_id for ur in user.user_roles] if user.user_roles else []
        return SessionUserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=roles,
            is_active=user.is_active,
        )

    def _to_item_response(self, auth_session: AuthSession) -> SessionItemResponse:
        return SessionItemResponse(
            id=auth_session.id,
            user_id=auth_session.user_id,
            user=self._to_user_summary(auth_session.user),
            status=auth_session.status,
            ip_address=auth_session.ip_address,
            user_agent=auth_session.user_agent,
            last_active_at=auth_session.last_active_at,
            expires_at=auth_session.expires_at,
            created_at=auth_session.created_at,
            revoked_at=auth_session.revoked_at,
            revoked_by=auth_session.revoked_by,
            revocation_reason=auth_session.revocation_reason,
        )

    async def list_sessions(
        self,
        session: Union[AsyncSession, Session],
        *,
        status: Optional[str] = None,
        user_id: Optional[Union[uuid.UUID, str]] = None,
        role: Optional[str] = None,
        ip_address: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> SessionListResponse:
        """Paginated search and surveillance of active and historical sessions."""
        sessions, total = await self.session_repo.list_sessions(
            session,
            status=status,
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
        items = [self._to_item_response(s) for s in sessions]
        pages = math.ceil(total / per_page) if per_page > 0 else 0

        return SessionListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    async def get_session_detail(
        self,
        session: Union[AsyncSession, Session],
        session_id: Union[uuid.UUID, str],
    ) -> SessionDetailResponse:
        """Fetch single session with user profile, roles, and correlated auth audit events."""
        auth_session = await self.session_repo.get_session_by_id(session, session_id)
        if not auth_session:
            raise NotFoundException(
                message="Session not found.",
                code="SESSION_NOT_FOUND",
            )

        # 3-tier correlation query for auth events
        sid_str = str(auth_session.id)
        session_start = auth_session.created_at
        session_end = auth_session.revoked_at or auth_session.expires_at

        # Match direct entity, metadata session_id, or time-window match for this actor
        direct_match = (AuditLog.resource_type == "auth_session") & (AuditLog.resource_id == sid_str)
        metadata_match = sa.cast(AuditLog.metadata_, sa.String).like(f"%{sid_str}%")
        time_match = (
            (AuditLog.actor_id == auth_session.user_id)
            & (AuditLog.created_at >= session_start)
            & (AuditLog.created_at <= session_end)
        )

        corr_stmt = (
            select(AuditLog)
            .where(or_(direct_match, metadata_match, time_match))
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )

        if isinstance(session, AsyncSession):
            corr_res = (await session.execute(corr_stmt)).scalars().all()
        else:
            corr_res = session.execute(corr_stmt).scalars().all()

        correlated_events = [AuditLogResponse.model_validate(log) for log in corr_res]

        item = self._to_item_response(auth_session)
        return SessionDetailResponse(
            **item.model_dump(),
            correlated_events=correlated_events,
        )

    async def revoke_session_admin(
        self,
        session: Union[AsyncSession, Session],
        session_id: Union[uuid.UUID, str],
        *,
        reason: str,
        actor_id: Union[uuid.UUID, str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SessionDetailResponse:
        """Revoke a single target session with required justification and immutable audit trail."""
        auth_session = await self.session_repo.get_session_by_id(session, session_id)
        if not auth_session:
            raise NotFoundException(
                message="Session not found.",
                code="SESSION_NOT_FOUND",
            )

        clean_reason = reason.strip()
        if len(clean_reason) < 5 or len(clean_reason) > 255:
            raise ValidationException(
                message="Revocation reason must be between 5 and 255 characters.",
                code="INVALID_REASON",
            )

        revocation_reason_text = f"ADMIN_REVOKED: {clean_reason}"

        # Execute idempotent revocation in repository
        was_active = await self.session_repo.revoke_session(
            session,
            session_id,
            reason=revocation_reason_text,
            revoked_by=actor_id,
        )

        # Record immutable audit event
        await self.audit_service.record_event(
            session,
            action="ADMIN_SESSION_REVOKED",
            resource_type="auth_session",
            resource_id=str(session_id),
            actor_id=actor_id,
            actor_type="SUPER_ADMIN",
            metadata={
                "reason": clean_reason,
                "target_user_id": str(auth_session.user_id),
                "was_active": was_active,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self.get_session_detail(session, session_id)

    async def revoke_user_sessions_admin(
        self,
        session: Union[AsyncSession, Session],
        target_user_id: Union[uuid.UUID, str],
        *,
        reason: str,
        actor_id: Union[uuid.UUID, str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSessionsRevokeResponse:
        """Revoke all active sessions for a specific user account."""
        user = await self.user_repo.get_by_id(session, target_user_id)
        if not user:
            raise NotFoundException(
                message="User not found.",
                code="USER_NOT_FOUND",
            )

        clean_reason = reason.strip()
        if len(clean_reason) < 5 or len(clean_reason) > 255:
            raise ValidationException(
                message="Revocation reason must be between 5 and 255 characters.",
                code="INVALID_REASON",
            )

        revocation_reason_text = f"ADMIN_REVOKED: {clean_reason}"
        count = await self.session_repo.revoke_all_user_sessions(
            session,
            target_user_id,
            reason=revocation_reason_text,
            revoked_by=actor_id,
        )

        await self.audit_service.record_event(
            session,
            action="USER_SESSIONS_REVOKED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            actor_type="SUPER_ADMIN",
            metadata={
                "reason": clean_reason,
                "revoked_sessions_count": count,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return UserSessionsRevokeResponse(
            user_id=user.id,
            revoked_sessions_count=count,
            message=f"All active sessions for user {user.email} revoked successfully ({count} session(s) affected).",
        )

    async def revoke_other_active_sessions_admin(
        self,
        session: Union[AsyncSession, Session],
        *,
        caller_session_id: Union[uuid.UUID, str],
        caller_id: Union[uuid.UUID, str],
        reason: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> EmergencyRevocationResponse:
        """Emergency platform containment: revokes ALL other active sessions.

        Mandatory Security Contract:
        1. Caller session is identified strictly from verified server authentication context.
        2. Caller session is strictly preserved to prevent administrative lockout.
        """
        clean_reason = reason.strip()
        if len(clean_reason) < 5 or len(clean_reason) > 255:
            raise ValidationException(
                message="Emergency containment reason must be between 5 and 255 characters.",
                code="INVALID_REASON",
            )

        caller_sid = (
            uuid.UUID(str(caller_session_id))
            if not isinstance(caller_session_id, uuid.UUID)
            else caller_session_id
        )
        revocation_reason_text = f"EMERGENCY_GLOBAL_REVOCATION: {clean_reason}"

        count = await self.session_repo.revoke_other_active_sessions(
            session,
            caller_session_id=caller_sid,
            reason=revocation_reason_text,
            revoked_by=caller_id,
        )

        await self.audit_service.record_event(
            session,
            action="EMERGENCY_GLOBAL_SESSIONS_REVOKED",
            resource_type="system",
            resource_id="auth_sessions",
            actor_id=caller_id,
            actor_type="SUPER_ADMIN",
            metadata={
                "reason": clean_reason,
                "revoked_sessions_count": count,
                "caller_session_id": str(caller_sid),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return EmergencyRevocationResponse(
            revoked_sessions_count=count,
            caller_session_id=caller_sid,
            caller_session_preserved=True,
            message=f"Emergency platform containment complete: {count} active session(s) revoked. Caller session preserved.",
        )

    async def get_security_metrics(
        self,
        session: Union[AsyncSession, Session],
    ) -> DetailedSecurityMetricsResponse:
        """Compute authoritative real-time security governance metrics from database records."""
        now = utc_now()
        yesterday = now - timedelta(hours=24)

        # 1. Total Active Sessions
        active_sess_stmt = (
            select(func.count(AuthSession.id))
            .where(
                AuthSession.status == SESSION_STATUS_ACTIVE,
                AuthSession.expires_at > now,
            )
        )

        # 2. Active Sessions by Role
        role_sess_stmt = (
            select(UserRole.role_id, func.count(distinct(AuthSession.id)))
            .join(User, AuthSession.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                AuthSession.status == SESSION_STATUS_ACTIVE,
                AuthSession.expires_at > now,
            )
            .group_by(UserRole.role_id)
        )

        # 3. Revoked in 24h
        revoked_24h_stmt = (
            select(func.count(AuthSession.id))
            .where(
                AuthSession.status == SESSION_STATUS_REVOKED,
                AuthSession.revoked_at >= yesterday,
            )
        )

        # 4. Displaced in 24h
        displaced_24h_stmt = (
            select(func.count(AuditLog.id))
            .where(
                AuditLog.action == "SESSION_DISPLACED",
                AuditLog.created_at >= yesterday,
            )
        )

        # 5. Expired in 24h
        expired_24h_stmt = (
            select(func.count(AuthSession.id))
            .where(
                AuthSession.status == SESSION_STATUS_EXPIRED,
                AuthSession.expires_at >= yesterday,
            )
        )

        # 6. Failed logins in 24h
        failed_logins_stmt = (
            select(func.count(AuditLog.id))
            .where(
                AuditLog.action == "AUTH_LOGIN_FAILED",
                AuditLog.created_at >= yesterday,
            )
        )

        # 7. Rate limit breaches in 24h
        rate_limits_stmt = (
            select(func.count(AuditLog.id))
            .where(
                AuditLog.action == "AUTH_RATE_LIMIT_EXCEEDED",
                AuditLog.created_at >= yesterday,
            )
        )

        # 8. Suspended Accounts Total
        suspended_users_stmt = (
            select(func.count(User.id))
            .where(User.is_active == False)
        )

        if isinstance(session, AsyncSession):
            active_sessions_total = (await session.execute(active_sess_stmt)).scalar() or 0
            role_sess_res = (await session.execute(role_sess_stmt)).all()
            sessions_revoked_24h = (await session.execute(revoked_24h_stmt)).scalar() or 0
            sessions_displaced_24h = (await session.execute(displaced_24h_stmt)).scalar() or 0
            sessions_expired_24h = (await session.execute(expired_24h_stmt)).scalar() or 0
            failed_logins_24h = (await session.execute(failed_logins_stmt)).scalar() or 0
            rate_limit_breaches_24h = (await session.execute(rate_limits_stmt)).scalar() or 0
            suspended_accounts_total = (await session.execute(suspended_users_stmt)).scalar() or 0
        else:
            active_sessions_total = session.execute(active_sess_stmt).scalar() or 0
            role_sess_res = session.execute(role_sess_stmt).all()
            sessions_revoked_24h = session.execute(revoked_24h_stmt).scalar() or 0
            sessions_displaced_24h = session.execute(displaced_24h_stmt).scalar() or 0
            sessions_expired_24h = session.execute(expired_24h_stmt).scalar() or 0
            failed_logins_24h = session.execute(failed_logins_stmt).scalar() or 0
            rate_limit_breaches_24h = session.execute(rate_limits_stmt).scalar() or 0
            suspended_accounts_total = session.execute(suspended_users_stmt).scalar() or 0

        # Construct roles dictionary ensuring 0 for unrepresented roles
        active_sessions_by_role: Dict[str, int] = {role: 0 for role in SYSTEM_ROLES}
        for role_id, count in role_sess_res:
            active_sessions_by_role[role_id] = count

        return DetailedSecurityMetricsResponse(
            active_sessions_total=active_sessions_total,
            active_sessions_by_role=active_sessions_by_role,
            sessions_revoked_24h=sessions_revoked_24h,
            sessions_displaced_24h=sessions_displaced_24h,
            sessions_expired_24h=sessions_expired_24h,
            failed_logins_24h=failed_logins_24h,
            rate_limit_breaches_24h=rate_limit_breaches_24h,
            suspended_accounts_total=suspended_accounts_total,
            generated_at=now,
        )
