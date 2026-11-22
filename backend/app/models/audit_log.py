"""AuditLog SQLAlchemy 2.0 model for append-only audit trail.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 35)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-013)

Strict Invariants:
1. Immutability: Permanently append-only. Does NOT inherit TimestampMixin and does NOT have updated_at.
2. Primary Key: UUIDv4 via UUIDPrimaryKeyMixin.
3. No foreign key on actor_id in Part 0 (the users table does not exist yet).
4. Timezone-aware created_at via UTCDateTime.
5. JSONB columns for before_state, after_state, and metadata (mapped to metadata_).
6. Request ID correlation with ASGI logging middleware.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import (
    Index,
    JSON,
    String,
    Uuid,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, UTCDateTime, utc_now


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit log entity capturing state transitions and security events."""

    __tablename__ = "audit_logs"

    # Optional model-level sensitive fields to exclude from serialization
    __sensitive_fields__ = frozenset()

    # Actor reference (nullable UUID without foreign key in Part 0)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    # Actor persona category (e.g. 'STUDENT', 'STAFF', 'ADMIN', 'SUPER_ADMIN', 'SYSTEM', 'ANONYMOUS')
    actor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SYSTEM",
        server_default=text("'SYSTEM'"),
    )

    # Action verb in canonical screaming snake_case
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # Resource/entity domain and identifier
    resource_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    # State snapshots (JSONB on PostgreSQL, JSON on SQLite)
    before_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    after_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    # Contextual metadata mapped to DB column 'metadata'
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    # Correlation and client network context
    request_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )

    # Immutable creation timestamp
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_logs_actor_id_created_at", "actor_id", desc("created_at")),
        Index("ix_audit_logs_resource_created_at", "resource_type", "resource_id", desc("created_at")),
        Index("ix_audit_logs_action_created_at", "action", desc("created_at")),
        Index("ix_audit_logs_request_id", "request_id"),
        Index("ix_audit_logs_created_at", desc("created_at")),
    )

    def __init__(self, **kwargs: Any) -> None:
        """Initialize AuditLog with secure defaults."""
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "actor_type" not in kwargs:
            kwargs["actor_type"] = "SYSTEM"
        if "metadata_" not in kwargs:
            kwargs["metadata_"] = {}
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        elif kwargs["created_at"] is not None:
            dt = kwargs["created_at"]
            if isinstance(dt, datetime) and dt.tzinfo is None:
                kwargs["created_at"] = dt.replace(tzinfo=timezone.utc)
        super().__init__(**kwargs)
