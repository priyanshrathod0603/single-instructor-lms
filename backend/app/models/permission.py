"""Permission and RolePermission database models for granular RBAC.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 2, 3)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK201)

Strict Invariants:
1. Standardized hierarchical permission strings: id is VARCHAR(64) PK (e.g. 'course:create').
2. Multi-role permission aggregation: RolePermission defines mappings per canonical role.
3. Foreign key cascades: Deleting a role or permission cascades to clean up mappings.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.user import Role


class Permission(Base):
    """Granular permission keys for the Single-Instructor LMS RBAC engine."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Canonical permission key in domain:action format (e.g. 'course:create')",
    )
    module: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        doc="Functional subsystem module (e.g. 'courses', 'assignments', 'users')",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Human-readable explanation of capability granted by this permission",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when permission was registered",
    )

    # Relationships
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id!r} module={self.module!r}>"


class RolePermission(Base):
    """Join association linking system roles to granular permission grants."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Target role foreign key (e.g. 'STUDENT', 'STAFF', 'ADMIN')",
    )
    permission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Granted permission foreign key (e.g. 'course:create')",
    )
    assigned_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when permission was mapped to role",
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions", lazy="joined")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions", lazy="joined")

    def __repr__(self) -> str:
        return f"<RolePermission role_id={self.role_id!r} permission_id={self.permission_id!r}>"
