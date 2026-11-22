"""NotificationOutbox and OutboxEvent persistence models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Strict Invariants:
1. Transactional atomicity: Outbox events are written in the same ACID transaction
   as the originating domain mutation.
2. High-throughput polling: Queue polling leverages PostgreSQL's FOR UPDATE SKIP LOCKED.
3. Exponential backoff: Failed dispatches increment retry_count and schedule next_retry_at
   using 30 * 2^retry_count seconds.
4. Dead-letter queue: After 5 consecutive failures (retry_count >= 5), event transitions
   to FAILED.
5. Idempotent dispatch: Optional dedupe_key enforces uniqueness to prevent duplicate
   message dispatching across retries or concurrent events.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

if TYPE_CHECKING:
    from app.models.user import User

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now


# Canonical event status constants
OUTBOX_STATUS_PENDING = "PENDING"
OUTBOX_STATUS_PROCESSING = "PROCESSING"
OUTBOX_STATUS_SENT = "SENT"
OUTBOX_STATUS_FAILED = "FAILED"

VALID_OUTBOX_STATUSES = frozenset({
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSING,
    OUTBOX_STATUS_SENT,
    OUTBOX_STATUS_FAILED,
})

# Canonical delivery channel constants
OUTBOX_CHANNEL_EMAIL = "EMAIL"
OUTBOX_CHANNEL_IN_APP = "IN_APP"
OUTBOX_CHANNEL_WEBHOOK = "WEBHOOK"

VALID_OUTBOX_CHANNELS = frozenset({
    OUTBOX_CHANNEL_EMAIL,
    OUTBOX_CHANNEL_IN_APP,
    OUTBOX_CHANNEL_WEBHOOK,
})


class EncryptedOutboxPayload(sa.types.TypeDecorator):
    """Transparently encrypts sensitive payload tokens before database persistence and decrypts on load (P0-06)."""

    impl = JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, dict) and not value.get("is_encrypted"):
            has_sensitive = (
                any(k in value for k in ("verification_token", "reset_token", "invitation_token", "token"))
                or any("token=" in str(v) for v in value.values() if isinstance(v, str))
            )
            if has_sensitive:
                from app.core.security import encrypt_payload
                return {
                    "_encrypted": encrypt_payload(value),
                    "is_encrypted": True,
                }
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        if isinstance(value, dict) and value.get("is_encrypted") and "_encrypted" in value:
            try:
                from app.core.security import decrypt_payload
                return decrypt_payload(value["_encrypted"])
            except Exception:
                return value
        return value or {}


class NotificationOutbox(Base, UUIDPrimaryKeyMixin):
    """Transactional outbox model for reliable asynchronous delivery.
    
    Guarantees that notifications, emails, and external webhooks are staged
    atomically with domain state changes, eliminating dual-write failure modes.
    """

    __tablename__ = "notification_outbox"

    # Event identification & routing
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Canonical event name (e.g. AUTH_VERIFY_EMAIL, ENROLLMENT_RECEIPT)",
    )
    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OUTBOX_CHANNEL_EMAIL,
        server_default=sa.text("'EMAIL'"),
        doc="Delivery channel: EMAIL, IN_APP, or WEBHOOK",
    )
    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default=sa.text("''"),
        doc="Target recipient: email address, user ID string, or endpoint URL",
    )
    subject: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Message subject line for email dispatches or title for in-app feeds",
    )

    # Event data & idempotency
    payload: Mapped[dict[str, Any]] = mapped_column(
        EncryptedOutboxPayload,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'"),
        doc="Structured event payload containing template variables and dispatch metadata",
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
        index=True,
        doc="Deterministic idempotency key guarding against duplicate event queuing",
    )

    # Lifecycle state & retry scheduling
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OUTBOX_STATUS_PENDING,
        server_default=sa.text("'PENDING'"),
        index=True,
        doc="Processing state: PENDING, PROCESSING, SENT, or FAILED",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Total number of failed delivery attempts",
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=sa.text("5"),
        doc="Maximum allowed retry attempts before dead-letter transition to FAILED",
    )
    next_retry_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        index=True,
        doc="Timestamp after which this event is eligible for worker processing",
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Timestamp when the event was successfully dispatched or marked FAILED",
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Sanitized error description or exception traceback from last failure",
    )

    # Audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        index=True,
        doc="UTC timestamp when the event was recorded in the database",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate NotificationOutbox with client-side defaults."""
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = uuid.uuid4()
        if "channel" not in kwargs or kwargs["channel"] is None:
            kwargs["channel"] = OUTBOX_CHANNEL_EMAIL
        if "recipient" not in kwargs or kwargs["recipient"] is None:
            kwargs["recipient"] = ""
        if "payload" not in kwargs or kwargs["payload"] is None:
            kwargs["payload"] = {}
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = OUTBOX_STATUS_PENDING
        if "retry_count" not in kwargs or kwargs["retry_count"] is None:
            kwargs["retry_count"] = 0
        if "max_retries" not in kwargs or kwargs["max_retries"] is None:
            kwargs["max_retries"] = 5
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = utc_now()
        if "next_retry_at" not in kwargs or kwargs["next_retry_at"] is None:
            kwargs["next_retry_at"] = kwargs["created_at"]

        # Ensure datetime objects are timezone-aware UTC
        for dt_field in ("created_at", "next_retry_at", "processed_at"):
            val = kwargs.get(dt_field)
            if val is not None and isinstance(val, datetime) and val.tzinfo is None:
                from datetime import timezone
                kwargs[dt_field] = val.replace(tzinfo=timezone.utc)

        super().__init__(**kwargs)

    @property
    def decrypted_payload(self) -> dict[str, Any]:
        """Explicit decrypted payload dictionary."""
        p = self.payload
        if isinstance(p, dict) and p.get("is_encrypted") and "_encrypted" in p:
            try:
                from app.core.security import decrypt_payload
                return decrypt_payload(p["_encrypted"])
            except Exception:
                return p
        return p or {}

    def __repr__(self) -> str:
        """Safe string representation without sensitive payload exposure."""
        return (
            f"<NotificationOutbox id={self.id} "
            f"event_type={self.event_type!r} "
            f"channel={self.channel!r} "
            f"status={self.status!r} "
            f"retries={self.retry_count}/{self.max_retries}>"
        )


# Canonical alias for domain event outbox semantics
OutboxEvent = NotificationOutbox


# In-App Notification types
NOTIFICATION_TYPE_ENROLLMENT = "ENROLLMENT"
NOTIFICATION_TYPE_GRADE_RELEASED = "GRADE_RELEASED"
NOTIFICATION_TYPE_ANNOUNCEMENT = "ANNOUNCEMENT"
NOTIFICATION_TYPE_ACCOUNT = "ACCOUNT"

VALID_NOTIFICATION_TYPES = frozenset({
    NOTIFICATION_TYPE_ENROLLMENT,
    NOTIFICATION_TYPE_GRADE_RELEASED,
    NOTIFICATION_TYPE_ANNOUNCEMENT,
    NOTIFICATION_TYPE_ACCOUNT,
})


class Notification(Base, UUIDPrimaryKeyMixin):
    """In-app notification message delivered to authenticated users.
    
    Architecture Specifications:
    - docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 33)
    - docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
    - docs/backend/16-NOTIFICATION-ARCHITECTURE.md
    - docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK201, TASK205)
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Target recipient user UUID",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Short headline or subject of the notification",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Detailed message content or announcement body",
    )
    notification_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=NOTIFICATION_TYPE_ANNOUNCEMENT,
        server_default=sa.text("'ANNOUNCEMENT'"),
        doc="Category: ENROLLMENT, GRADE_RELEASED, ANNOUNCEMENT, or ACCOUNT",
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
        doc="Read receipt indicator; false indicates unread message",
    )
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=True,
        default=None,
        doc="Optional deep-linking metadata, course IDs, or route targets",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when notification was generated",
    )

    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "is_read", sa.text("created_at DESC")),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate in-app notification with default unread state and timestamps."""
        if "id" not in kwargs or kwargs["id"] is None:
            kwargs["id"] = uuid.uuid4()
        if "is_read" not in kwargs or kwargs["is_read"] is None:
            kwargs["is_read"] = False
        if "notification_type" not in kwargs or kwargs["notification_type"] is None:
            kwargs["notification_type"] = NOTIFICATION_TYPE_ANNOUNCEMENT
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} "
            f"user_id={self.user_id} "
            f"type={self.notification_type!r} "
            f"is_read={self.is_read}>"
        )

