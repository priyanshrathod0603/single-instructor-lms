"""Authentication session persistence model.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Table 2)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK102, TASK103)

Strict Invariants:
1. Single-Active-Session: At most ONE active session per user.
   Enforced at DB level via partial unique index:
   CREATE UNIQUE INDEX idx_auth_sessions_unique_active_user ON auth_sessions(user_id) WHERE status='ACTIVE';
2. Session Token Storage: Raw token never persisted; only SHA-256 hex digest (64 chars) is stored.
3. Session Expiration: Absolute lifetime (default 7 days) and inactivity threshold (default 24 hours).
4. Sensitive Masking: session_token_hash excluded from logging and dictionary serialization.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

# Status constants
SESSION_STATUS_ACTIVE = "ACTIVE"
SESSION_STATUS_REVOKED = "REVOKED"
SESSION_STATUS_EXPIRED = "EXPIRED"

SESSION_STATUSES = frozenset({
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_REVOKED,
    SESSION_STATUS_EXPIRED,
})


class AuthSession(Base, UUIDPrimaryKeyMixin):
    """User authentication session record tracking active, revoked, and expired sessions."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Owner user UUID",
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        doc="SHA-256 hex digest of the raw session token",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        doc="Client IPv4 or IPv6 address captured at login/refresh",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Client User-Agent header (truncated to 512 chars)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SESSION_STATUS_ACTIVE,
        server_default=sa.text(f"'{SESSION_STATUS_ACTIVE}'"),
        doc="Session status: ACTIVE, REVOKED, or EXPIRED",
    )
    last_active_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp of last authenticated activity (throttled updates)",
    )
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        index=True,
        doc="UTC timestamp when session strictly expires",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when session was established",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        default=None,
        doc="UTC timestamp when session was transitioned to REVOKED status",
    )
    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        doc="Actor UUID who authorized or triggered session revocation (NULL for system/anonymous)",
    )
    revocation_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        default=None,
        doc="Canonical reason code and justification for session revocation",
    )

    # Exclude hashed token from dictionary serializations
    __sensitive_fields__ = {"session_token_hash"}

    # Database indexes
    __table_args__ = (
        # Partial unique index enforcing single active session per user
        Index(
            "idx_auth_sessions_unique_active_user",
            "user_id",
            unique=True,
            postgresql_where=(sa.column("status") == SESSION_STATUS_ACTIVE),
            sqlite_where=(sa.column("status") == SESSION_STATUS_ACTIVE),
        ),
        # Composite index for filtering user's sessions by status
        Index("ix_auth_sessions_user_status", "user_id", "status"),
        # Composite index for admin session surveillance (filtering by status and sorting by created_at DESC)
        Index(
            "ix_auth_sessions_status_created_at",
            "status",
            sa.text("created_at DESC"),
        ),
        # Partial index for client IP filtering on active/investigated sessions
        Index(
            "ix_auth_sessions_ip_address",
            "ip_address",
            postgresql_where=(sa.column("ip_address").is_not(None)),
            sqlite_where=(sa.column("ip_address").is_not(None)),
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="sessions",
        lazy="selectin",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate auth session with default active status and timestamps."""
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = SESSION_STATUS_ACTIVE
        if "last_active_at" not in kwargs or kwargs["last_active_at"] is None:
            kwargs["last_active_at"] = utc_now()
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)

    def is_active(self) -> bool:
        """Check if session is currently active and not expired."""
        if self.status != SESSION_STATUS_ACTIVE:
            return False
        return utc_now() < self.expires_at

    def revoke(
        self,
        reason: Optional[str] = None,
        revoked_by: Optional[uuid.UUID] = None,
    ) -> None:
        """Mark session as revoked with timestamp, actor, and canonical reason."""
        self.status = SESSION_STATUS_REVOKED
        self.revoked_at = utc_now()
        if reason:
            self.revocation_reason = reason[:255]
        if revoked_by:
            self.revoked_by = revoked_by

    def expire(self) -> None:
        """Mark session as expired."""
        self.status = SESSION_STATUS_EXPIRED

    def __repr__(self) -> str:
        return (
            f"<AuthSession id={self.id} "
            f"user_id={self.user_id} "
            f"status={self.status!r} "
            f"expires_at={self.expires_at.isoformat()}>"
        )
