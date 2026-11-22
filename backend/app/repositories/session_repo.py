"""SessionRepository implementing concurrency controls and single-active-session invariant.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Table 2)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK103)

Strict Invariants:
1. Single-Active-Session Invariant: At most ONE active session per user.
   Enforced concurrently by:
   a. Row-level lock: SELECT ... WHERE user_id = :user_id AND status = 'ACTIVE' FOR UPDATE.
   b. Status transition: Existing active session is atomically set to 'REVOKED'.
   c. Partial unique index: CREATE UNIQUE INDEX ON auth_sessions(user_id) WHERE status='ACTIVE'.
2. Activity Throttling: touch_last_active updates last_active_at at most once every 5 minutes.
3. Token Hashing: Lookup by SHA-256 hex digest only; raw tokens are never persisted or queried.
"""

from datetime import datetime, timedelta
import logging
from typing import Optional, Sequence, Tuple, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import distinct, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, noload, selectinload

from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.base import utc_now
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


class SessionRepository:
    """Repository handling database persistence and concurrency for AuthSession entities."""

    async def create_session(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        session_token_hash: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuthSession:
        """Create and flush an active session record without displacement."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        auth_session = AuthSession(
            user_id=uid,
            session_token_hash=session_token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
            status=SESSION_STATUS_ACTIVE,
            last_active_at=utc_now(),
        )
        session.add(auth_session)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return auth_session

    async def atomic_displace_session(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        new_session_token_hash: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[AuthSession, Optional[AuthSession]]:
        """Atomically displace existing active session and create new active session.

        Guarantees the Single-Active-Session Invariant [LMS Blueprint v2.0, Page 8]:
        1. Queries existing active session with row-level lock (FOR UPDATE).
        2. Sets existing active session status to 'REVOKED'.
        3. Inserts new active session.
        4. Flushes to active database transaction.

        Args:
            session: Active database session.
            user_id: Owner user UUID.
            new_session_token_hash: SHA-256 hex digest of new session token.
            expires_at: UTC expiration timestamp.
            ip_address: Client IP address.
            user_agent: Client User-Agent header.

        Returns:
            Tuple of (new_active_session, displaced_session_or_none).
        """
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id

        # 1. Query existing active session with FOR UPDATE OF auth_sessions
        # and noload(AuthSession.user) to eliminate any outer join that would trigger
        # PostgreSQL FeatureNotSupported ("FOR UPDATE cannot be applied to the nullable side of an outer join")
        lock_stmt = (
            select(AuthSession)
            .options(noload(AuthSession.user))
            .where(
                AuthSession.user_id == uid,
                AuthSession.status == SESSION_STATUS_ACTIVE,
            )
            .with_for_update(of=AuthSession)
        )

        if isinstance(session, AsyncSession):
            lock_res = await session.execute(lock_stmt)
            existing_active = lock_res.scalars().all()
        else:
            lock_res = session.execute(lock_stmt)
            existing_active = lock_res.scalars().all()

        displaced_session: Optional[AuthSession] = None

        # 2. Mark existing active session(s) as REVOKED with displacement metadata
        now = utc_now()
        for active in existing_active:
            active.status = SESSION_STATUS_REVOKED
            active.revoked_at = now
            active.revoked_by = uid
            active.revocation_reason = "LOGIN_DISPLACEMENT"
            displaced_session = active

        # Flush revocation first to guarantee partial unique index isolation
        if existing_active:
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()

        # 3. Create new active session
        new_session = AuthSession(
            user_id=uid,
            session_token_hash=new_session_token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
            status=SESSION_STATUS_ACTIVE,
            last_active_at=utc_now(),
        )
        session.add(new_session)

        # 4. Flush to database
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()

        return new_session, displaced_session

    async def get_active_session_by_user_id(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
    ) -> Optional[AuthSession]:
        """Retrieve the currently active session for a user, if one exists."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = (
            select(AuthSession)
            .where(
                AuthSession.user_id == uid,
                AuthSession.status == SESSION_STATUS_ACTIVE,
            )
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

    async def get_session_by_token_hash(
        self,
        session: Union[AsyncSession, Session],
        token_hash: str,
    ) -> Optional[AuthSession]:
        """Retrieve a session by its SHA-256 token hash, joining owner User."""
        stmt = (
            select(AuthSession)
            .options(selectinload(AuthSession.user).selectinload(User.user_roles))
            .where(AuthSession.session_token_hash == token_hash)
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

    async def get_session_by_id(
        self,
        session: Union[AsyncSession, Session],
        session_id: Union[uuid.UUID, str],
    ) -> Optional[AuthSession]:
        """Retrieve a session by its UUID, joining owner User and roles."""
        sid = uuid.UUID(str(session_id)) if not isinstance(session_id, uuid.UUID) else session_id
        stmt = (
            select(AuthSession)
            .options(selectinload(AuthSession.user).selectinload(User.user_roles))
            .where(AuthSession.id == sid)
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

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
    ) -> tuple[list[AuthSession], int]:
        """Query sessions with filtering by status, user, role, IP, and date ranges.

        Includes pagination and eager loading of user and roles to prevent N+1 queries.
        """
        stmt = (
            select(AuthSession)
            .join(User, AuthSession.user_id == User.id)
            .options(selectinload(AuthSession.user).selectinload(User.user_roles))
        )
        count_stmt = (
            select(func.count(distinct(AuthSession.id)))
            .select_from(AuthSession)
            .join(User, AuthSession.user_id == User.id)
        )

        if role:
            clean_role = role.strip().upper()
            stmt = stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == clean_role)
            count_stmt = count_stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == clean_role)

        if status:
            clean_status = status.strip().upper()
            stmt = stmt.where(AuthSession.status == clean_status)
            count_stmt = count_stmt.where(AuthSession.status == clean_status)

        if user_id:
            uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
            stmt = stmt.where(AuthSession.user_id == uid)
            count_stmt = count_stmt.where(AuthSession.user_id == uid)

        if ip_address:
            clean_ip = ip_address.strip()
            stmt = stmt.where(AuthSession.ip_address == clean_ip)
            count_stmt = count_stmt.where(AuthSession.ip_address == clean_ip)

        if search:
            pattern = f"%{search.strip()}%"
            search_clause = or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            stmt = stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        if date_from:
            stmt = stmt.where(AuthSession.created_at >= date_from)
            count_stmt = count_stmt.where(AuthSession.created_at >= date_from)

        if date_to:
            stmt = stmt.where(AuthSession.created_at <= date_to)
            count_stmt = count_stmt.where(AuthSession.created_at <= date_to)

        # Sorting
        sort_attr = getattr(AuthSession, sort_by, AuthSession.created_at)
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_attr.asc())
        else:
            stmt = stmt.order_by(sort_attr.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        stmt = stmt.offset(offset).limit(per_page)

        if isinstance(session, AsyncSession):
            total_count = (await session.execute(count_stmt)).scalar() or 0
            results = (await session.execute(stmt)).scalars().all()
            return list(results), int(total_count)
        else:
            total_count = session.execute(count_stmt).scalar() or 0
            results = session.execute(stmt).scalars().all()
            return list(results), int(total_count)

    async def revoke_session(
        self,
        session: Union[AsyncSession, Session],
        session_id: Union[uuid.UUID, str],
        *,
        reason: Optional[str] = None,
        revoked_by: Optional[Union[uuid.UUID, str]] = None,
    ) -> bool:
        """Mark a specific session as REVOKED if currently ACTIVE.

        Guarantees idempotency and records revocation metadata.
        """
        sid = uuid.UUID(str(session_id)) if not isinstance(session_id, uuid.UUID) else session_id
        revoker_uuid = (
            uuid.UUID(str(revoked_by))
            if revoked_by and not isinstance(revoked_by, uuid.UUID)
            else revoked_by
        )
        now = utc_now()
        stmt = (
            update(AuthSession)
            .where(
                AuthSession.id == sid,
                AuthSession.status == SESSION_STATUS_ACTIVE,
            )
            .values(
                status=SESSION_STATUS_REVOKED,
                revoked_at=now,
                revoked_by=revoker_uuid,
                revocation_reason=reason,
            )
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount > 0

    async def revoke_all_user_sessions(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        *,
        reason: Optional[str] = None,
        revoked_by: Optional[Union[uuid.UUID, str]] = None,
    ) -> int:
        """Revoke all active sessions for a user, recording metadata."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        revoker_uuid = (
            uuid.UUID(str(revoked_by))
            if revoked_by and not isinstance(revoked_by, uuid.UUID)
            else revoked_by
        )
        now = utc_now()
        stmt = (
            update(AuthSession)
            .where(
                AuthSession.user_id == uid,
                AuthSession.status == SESSION_STATUS_ACTIVE,
            )
            .values(
                status=SESSION_STATUS_REVOKED,
                revoked_at=now,
                revoked_by=revoker_uuid,
                revocation_reason=reason,
            )
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount

    async def revoke_other_active_sessions(
        self,
        session: Union[AsyncSession, Session],
        *,
        caller_session_id: Union[uuid.UUID, str],
        reason: Optional[str] = None,
        revoked_by: Optional[Union[uuid.UUID, str]] = None,
    ) -> int:
        """Emergency platform containment: revokes ALL other active sessions.

        Mandatory Invariant: Strictly preserves the caller's verified active session.
        """
        caller_sid = (
            uuid.UUID(str(caller_session_id))
            if not isinstance(caller_session_id, uuid.UUID)
            else caller_session_id
        )
        revoker_uuid = (
            uuid.UUID(str(revoked_by))
            if revoked_by and not isinstance(revoked_by, uuid.UUID)
            else revoked_by
        )
        now = utc_now()
        stmt = (
            update(AuthSession)
            .where(
                AuthSession.status == SESSION_STATUS_ACTIVE,
                AuthSession.id != caller_sid,
            )
            .values(
                status=SESSION_STATUS_REVOKED,
                revoked_at=now,
                revoked_by=revoker_uuid,
                revocation_reason=reason,
            )
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount

    async def touch_last_active(
        self,
        session: Union[AsyncSession, Session],
        auth_session: AuthSession,
        threshold_seconds: int = 300,
    ) -> bool:
        """Update last_active_at timestamp if threshold_seconds have elapsed.

        Throttles database write load on high-frequency authenticated HTTP requests.

        Args:
            session: Active database session.
            auth_session: AuthSession instance.
            threshold_seconds: Minimum elapsed seconds before DB touch (default 300s = 5m).

        Returns:
            True if timestamp was updated, False if throttled.
        """
        now = utc_now()
        elapsed = (now - auth_session.last_active_at).total_seconds()
        if elapsed < threshold_seconds:
            return False

        auth_session.last_active_at = now
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return True

    async def cleanup_expired_sessions(
        self,
        session: Union[AsyncSession, Session],
    ) -> int:
        """Transition past-due ACTIVE sessions to EXPIRED status."""
        now = utc_now()
        stmt = (
            update(AuthSession)
            .where(
                AuthSession.status == SESSION_STATUS_ACTIVE,
                AuthSession.expires_at <= now,
            )
            .values(status=SESSION_STATUS_EXPIRED)
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount
