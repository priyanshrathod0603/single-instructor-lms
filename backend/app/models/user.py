"""User, Role, and UserRole identity and authorization models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 1, 4, 5)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK102)

Strict Invariants:
1. Product Architecture: Single-instructor direct sales platform.
2. Email uniqueness: Normalized case-insensitive uniqueness.
3. Password security: Argon2id hash stored in password_hash; NULL for OAuth-only users.
4. Mandatory email verification: is_verified gates access to private course content.
5. Role isolation: Default signup role is strictly STUDENT. Staff/Admin roles assigned only by authorization.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
import uuid

if TYPE_CHECKING:
    from app.models.auth_session import AuthSession
    from app.models.auth_token import AuthToken
    from app.models.enrollment import Enrollment
    from app.models.media import MediaAsset
    from app.models.notification import Notification
    from app.models.payment import Order
    from app.models.permission import RolePermission

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

# Canonical role constants
ROLE_VISITOR = "VISITOR"
ROLE_STUDENT = "STUDENT"
ROLE_STAFF = "STAFF"
ROLE_ADMIN = "ADMIN"
ROLE_SUPER_ADMIN = "SUPER_ADMIN"

SYSTEM_ROLES = frozenset({
    ROLE_VISITOR,
    ROLE_STUDENT,
    ROLE_STAFF,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
})


class Role(Base):
    """System-defined authorization roles for the Single-Instructor LMS."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        doc="Canonical role identifier (e.g. STUDENT, STAFF, ADMIN, SUPER_ADMIN)",
    )
    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Human-readable role label",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed description of permissions and operational scope",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when role was created",
    )

    # Relationships
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id!r} name={self.name!r}>"


class UserRole(Base):
    """Join association linking users to assigned system roles."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Target user foreign key",
    )
    role_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
        doc="Assigned role foreign key",
    )
    assigned_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when role was granted",
    )
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Admin user UUID who granted this role (NULL for system assignment)",
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", lazy="joined")

    def __repr__(self) -> str:
        return f"<UserRole user_id={self.user_id} role_id={self.role_id!r}>"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Core user entity representing students, staff, administrators, and the primary instructor."""

    __tablename__ = "users"

    # Identity and authentication
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        doc="Normalized case-insensitive email address",
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Argon2id password hash string (NULL for OAuth-only users)",
    )
    full_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="User's full display name",
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="User contact phone number",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Public URL to avatar image in object storage",
    )

    # Security and status flags
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
        doc="Mandatory email verification flag; false blocks learning content access",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=sa.text("true"),
        nullable=False,
        doc="Account suspension toggle; false blocks login and revokes active sessions",
    )

    # Exclude sensitive password hash from automatic dictionary serialization
    __sensitive_fields__ = {"password_hash"}

    # Relationships
    user_roles: Mapped[List["UserRole"]] = relationship(
        "UserRole",
        foreign_keys=[UserRole.user_id],
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[List["AuthSession"]] = relationship(
        "AuthSession",
        foreign_keys="[AuthSession.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    tokens: Mapped[List["AuthToken"]] = relationship(
        "AuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    media_assets: Mapped[List["MediaAsset"]] = relationship(
        "MediaAsset",
        back_populates="uploader",
        cascade="all, delete-orphan",
        lazy="select",
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="student",
        foreign_keys="Order.student_id",
        lazy="select",
    )
    enrollments: Mapped[List["Enrollment"]] = relationship(
        "Enrollment",
        back_populates="student",
        foreign_keys="Enrollment.student_id",
        lazy="select",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate user with normalized email and defaults."""
        if "email" in kwargs and kwargs["email"]:
            kwargs["email"] = str(kwargs["email"]).strip().lower()
        if "phone" in kwargs and kwargs["phone"]:
            kwargs["phone"] = str(kwargs["phone"]).strip()
        if "is_verified" not in kwargs or kwargs["is_verified"] is None:
            kwargs["is_verified"] = False
        if "is_active" not in kwargs or kwargs["is_active"] is None:
            kwargs["is_active"] = True
        super().__init__(**kwargs)

    @property
    def roles(self) -> list[str]:
        """Convenience helper returning assigned role identifiers."""
        return [ur.role_id for ur in self.user_roles]

    def has_role(self, role_id: str) -> bool:
        """Check if user has a specific assigned role."""
        return role_id in self.roles

    def get_aggregated_permissions(self) -> set[str]:
        """Aggregate granular permissions across all assigned user roles.
        
        Super Admin automatically receives all platform permissions.
        """
        if ROLE_SUPER_ADMIN in self.roles:
            from app.core.permissions import ALL_PERMISSION_KEYS
            return set(ALL_PERMISSION_KEYS)

        perms: set[str] = set()
        for ur in self.user_roles:
            if ur.role and hasattr(ur.role, "role_permissions"):
                for rp in ur.role.role_permissions:
                    perms.add(rp.permission_id)
        return perms

    def has_permission(self, permission_key: str) -> bool:
        """Check whether user possesses a specific permission key."""
        if ROLE_SUPER_ADMIN in self.roles:
            return True
        return permission_key in self.get_aggregated_permissions()

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} "
            f"email={self.email!r} "
            f"is_verified={self.is_verified} "
            f"is_active={self.is_active}>"
        )
