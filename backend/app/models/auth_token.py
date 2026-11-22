"""Single-use authentication tokens (email verification & password reset).

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Table 3)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK102, TASK104, TASK106)

Strict Invariants:
1. Cryptographic Security: High-entropy raw token (32 bytes URL-safe) generated in-memory.
2. Token Hashing: Only the SHA-256 hex digest (64 chars) is stored in the database.
3. Single-Use Guarantee: Marked is_used=True atomically on consumption.
4. Expiration: Strict expiry timestamp (e.g., 24h for email verification, 1h for password reset).
5. Sensitive Masking: token_hash excluded from logging and serialization.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

# Token types
TOKEN_TYPE_EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
TOKEN_TYPE_PASSWORD_RESET = "PASSWORD_RESET"
TOKEN_TYPE_STAFF_ONBOARDING = "STAFF_ONBOARDING"

AUTH_TOKEN_TYPES = frozenset({
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_STAFF_ONBOARDING,
})


class AuthToken(Base, UUIDPrimaryKeyMixin):
    """Single-use cryptographic token record for email verification and password reset flows."""

    __tablename__ = "auth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Owner user UUID",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        doc="SHA-256 hex digest of the raw secret token",
    )
    token_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Token purpose: EMAIL_VERIFICATION or PASSWORD_RESET",
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
        doc="Single-use consumption indicator; true if consumed",
    )
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        index=True,
        doc="UTC timestamp when token strictly expires",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when token was generated",
    )

    # Exclude hashed token from dictionary serializations
    __sensitive_fields__ = {"token_hash"}

    # Database indexes
    __table_args__ = (
        Index("ix_auth_tokens_hash_type_used", "token_hash", "token_type", "is_used"),
        Index("ix_auth_tokens_user_type", "user_id", "token_type"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tokens", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate auth token with default single-use status and timestamps."""
        if "is_used" not in kwargs or kwargs["is_used"] is None:
            kwargs["is_used"] = False
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)

    def is_valid(self) -> bool:
        """Check if token is not yet used and not expired."""
        if self.is_used:
            return False
        return utc_now() < self.expires_at

    def mark_used(self) -> None:
        """Mark token as consumed."""
        self.is_used = True

    def __repr__(self) -> str:
        return (
            f"<AuthToken id={self.id} "
            f"user_id={self.user_id} "
            f"type={self.token_type!r} "
            f"is_used={self.is_used} "
            f"expires_at={self.expires_at.isoformat()}>"
        )
