"""UserRepository managing user identities, roles, and credential updates.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 1, 4, 5)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK103)

Strict Invariants:
1. Email uniqueness: Normalized lowercase lookup and uniqueness checks.
2. Conflict handling: Raises ConflictException(code="EMAIL_ALREADY_EXISTS") on collision.
3. Default role: Newly registered users receive ROLE_STUDENT.
4. Atomicity: Flushes records without committing, preserving caller transaction boundaries.
"""

import logging
from typing import Any, Optional, Sequence, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.base import utc_now
from app.models.user import ROLE_STUDENT, Role, User, UserRole

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository handling database operations for User and UserRole entities."""

    async def create_user(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
        full_name: str,
        phone: Optional[str] = None,
        password_hash: Optional[str] = None,
        avatar_url: Optional[str] = None,
        is_verified: bool = False,
        role_id: str = ROLE_STUDENT,
        assigned_by: Optional[Union[uuid.UUID, str]] = None,
    ) -> User:
        """Create a new user with normalized email and default role assignment.

        Args:
            session: Active database session.
            email: User's raw email address (will be normalized).
            full_name: User's display name.
            password_hash: Argon2id hash (None for OAuth users).
            avatar_url: Optional object storage URL.
            is_verified: Email verification flag.
            role_id: System role identifier (defaults to STUDENT).
            assigned_by: Admin UUID who created/assigned this user, if applicable.

        Returns:
            The created and flushed User entity with user_roles populated.

        Raises:
            ConflictException: If a user with this normalized email already exists.
        """
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise ValidationException(
                message="Email address cannot be empty.",
                code="EMPTY_EMAIL",
            )

        # Check existing user
        existing = await self.get_by_email(session, normalized_email)
        if existing is not None:
            raise ConflictException(
                message="An account with this email address already exists.",
                code="EMAIL_ALREADY_EXISTS",
                details={"email": normalized_email},
            )

        # Verify role exists
        role_stmt = select(Role).where(Role.id == role_id)
        if isinstance(session, AsyncSession):
            role_res = await session.execute(role_stmt)
        else:
            role_res = session.execute(role_stmt)
        role = role_res.scalar_one_or_none()
        if role is None:
            raise ValidationException(
                message=f"Invalid system role: {role_id}",
                code="INVALID_ROLE",
            )

        # Instantiate User
        user = User(
            email=normalized_email,
            full_name=full_name.strip(),
            phone=phone.strip() if phone else None,
            password_hash=password_hash,
            avatar_url=avatar_url,
            is_verified=is_verified,
            is_active=True,
        )
        session.add(user)

        # Flush to obtain generated user.id
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()

        # Parse assigned_by UUID
        assigned_by_uuid: Optional[uuid.UUID] = None
        if assigned_by is not None:
            assigned_by_uuid = uuid.UUID(str(assigned_by)) if not isinstance(assigned_by, uuid.UUID) else assigned_by

        # Assign initial role
        user_role = UserRole(
            user_id=user.id,
            role_id=role_id,
            assigned_by=assigned_by_uuid,
        )
        session.add(user_role)

        if isinstance(session, AsyncSession):
            await session.flush()
            # Refresh user with user_roles loaded
            stmt = select(User).options(selectinload(User.user_roles)).where(User.id == user.id)
            refreshed = (await session.execute(stmt)).scalar_one()
            return refreshed
        else:
            session.flush()
            stmt = select(User).options(selectinload(User.user_roles)).where(User.id == user.id)
            refreshed = session.execute(stmt).scalar_one()
            return refreshed

    async def get_by_id(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
    ) -> Optional[User]:
        """Retrieve a user by primary key UUID, preloading user_roles."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = (
            select(User)
            .options(selectinload(User.user_roles))
            .where(User.id == uid)
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(
        self,
        session: Union[AsyncSession, Session],
        email: str,
    ) -> Optional[User]:
        """Retrieve a user by normalized lowercase email, preloading user_roles."""
        normalized = email.strip().lower()
        if not normalized:
            return None
        stmt = (
            select(User)
            .options(selectinload(User.user_roles))
            .where(func.lower(User.email) == normalized)
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_password_hash(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        password_hash: str,
    ) -> None:
        """Update a user's password hash and touch updated_at."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = (
            update(User)
            .where(User.id == uid)
            .values(password_hash=password_hash, updated_at=utc_now())
        )
        if isinstance(session, AsyncSession):
            await session.execute(stmt)
            await session.flush()
        else:
            session.execute(stmt)
            session.flush()

    async def mark_email_verified(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
    ) -> None:
        """Mark a user's email as verified and touch updated_at."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = (
            update(User)
            .where(User.id == uid)
            .values(is_verified=True, updated_at=utc_now())
        )
        if isinstance(session, AsyncSession):
            await session.execute(stmt)
            await session.flush()
        else:
            session.execute(stmt)
            session.flush()

    async def update_status(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        is_active: bool,
    ) -> None:
        """Update a user's account activation status."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = (
            update(User)
            .where(User.id == uid)
            .values(is_active=is_active, updated_at=utc_now())
        )
        if isinstance(session, AsyncSession):
            await session.execute(stmt)
            await session.flush()
        else:
            session.execute(stmt)
            session.flush()

    async def assign_role(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        role_id: str,
        assigned_by: Optional[Union[uuid.UUID, str]] = None,
    ) -> UserRole:
        """Assign an additional role to a user if not already assigned."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        assigned_by_uuid = (
            uuid.UUID(str(assigned_by))
            if assigned_by is not None and not isinstance(assigned_by, uuid.UUID)
            else assigned_by
        )

        # Check existing role assignment
        check_stmt = select(UserRole).where(
            UserRole.user_id == uid,
            UserRole.role_id == role_id,
        )
        if isinstance(session, AsyncSession):
            existing = (await session.execute(check_stmt)).scalar_one_or_none()
        else:
            existing = session.execute(check_stmt).scalar_one_or_none()

        if existing is not None:
            return existing

        user_role = UserRole(
            user_id=uid,
            role_id=role_id,
            assigned_by=assigned_by_uuid,
        )
        session.add(user_role)
        if isinstance(session, AsyncSession):
            await session.flush()
            user = await session.get(User, uid)
            if user is not None:
                session.expire(user, ["user_roles"])
        else:
            session.flush()
            user = session.get(User, uid)
            if user is not None:
                session.expire(user, ["user_roles"])
        return user_role

    async def remove_role(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        role_id: str,
    ) -> bool:
        """Remove a role assignment from a user."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        stmt = delete(UserRole).where(
            UserRole.user_id == uid,
            UserRole.role_id == role_id,
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
            await session.flush()
            user = await session.get(User, uid)
            if user is not None:
                session.expire(user, ["user_roles"])
        else:
            result = session.execute(stmt)
            session.flush()
            user = session.get(User, uid)
            if user is not None:
                session.expire(user, ["user_roles"])
        return result.rowcount > 0

    async def update_profile(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        *,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> User:
        """Update full_name or avatar_url on a user entity."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        values: dict[str, Any] = {"updated_at": utc_now()}
        if full_name is not None:
            values["full_name"] = full_name.strip()
        if avatar_url is not None:
            values["avatar_url"] = avatar_url.strip() if avatar_url else None

        stmt = update(User).where(User.id == uid).values(**values)
        if isinstance(session, AsyncSession):
            await session.execute(stmt)
            await session.flush()
        else:
            session.execute(stmt)
            session.flush()

        user = await self.get_by_id(session, uid)
        if user is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")
        return user

    async def count_active_super_admins(
        self,
        session: Union[AsyncSession, Session],
    ) -> int:
        """Count active users holding the SUPER_ADMIN role."""
        from app.models.user import ROLE_SUPER_ADMIN
        stmt = (
            select(func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                UserRole.role_id == ROLE_SUPER_ADMIN,
                User.is_active.is_(True),
            )
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
        else:
            res = session.execute(stmt)
        return int(res.scalar() or 0)

    async def list_users(
        self,
        session: Union[AsyncSession, Session],
        *,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[User], int]:
        """Query paginated user list with optional search, filters, and dynamic sorting."""
        stmt = select(User).options(selectinload(User.user_roles))
        count_stmt = select(func.count(func.distinct(User.id)))

        if role:
            stmt = stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == role)
            count_stmt = count_stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == role)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

        if is_verified is not None:
            stmt = stmt.where(User.is_verified == is_verified)
            count_stmt = count_stmt.where(User.is_verified == is_verified)

        if search:
            term = f"%{search.strip().lower()}%"
            filter_crit = sa.or_(
                func.lower(User.email).like(term),
                func.lower(User.full_name).like(term),
            )
            stmt = stmt.where(filter_crit)
            count_stmt = count_stmt.where(filter_crit)

        # Dynamic sorting by allowed fields
        sort_col = User.created_at
        if sort_by == "full_name":
            sort_col = User.full_name
        elif sort_by == "email":
            sort_col = User.email
        elif sort_by == "created_at":
            sort_col = User.created_at

        if sort_order and sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_col.asc())
        else:
            stmt = stmt.order_by(sort_col.desc())

        stmt = stmt.offset((page - 1) * per_page).limit(per_page)

        if isinstance(session, AsyncSession):
            total = int((await session.execute(count_stmt)).scalar() or 0)
            items = list((await session.execute(stmt)).scalars().all())
        else:
            total = int(session.execute(count_stmt).scalar() or 0)
            items = list(session.execute(stmt).scalars().all())

        return items, total

