"""MediaTranscodeJob SQLAlchemy 2.0 persistence model.

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. Transactional Job Creation: Transcode jobs are enqueued atomically when upload confirmation succeeds.
2. High-Throughput Worker Claiming: Polling leverages PostgreSQL FOR UPDATE SKIP LOCKED.
3. Bounded Exponential Backoff: Failed jobs retry with exponential backoff up to max_retries.
4. Idempotent Processing: At most one active job (QUEUED/PROCESSING) per media asset at any time.
5. Strict Asset Status Alignment: MediaAsset transitions to READY only after HLS output is validated and stored.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)
from app.models.media import json_type

if TYPE_CHECKING:
    from app.models.media import MediaAsset

# Canonical Job Status Constants
TRANSCODE_STATUS_QUEUED = "QUEUED"
TRANSCODE_STATUS_PROCESSING = "PROCESSING"
TRANSCODE_STATUS_COMPLETED = "COMPLETED"
TRANSCODE_STATUS_FAILED = "FAILED"
TRANSCODE_STATUS_CANCELLED = "CANCELLED"

VALID_TRANSCODE_STATUSES = frozenset({
    TRANSCODE_STATUS_QUEUED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_COMPLETED,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_CANCELLED,
})

# Failure Category Diagnostics
ERROR_CATEGORY_PROBE_FAILED = "PROBE_FAILED"
ERROR_CATEGORY_UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
ERROR_CATEGORY_CORRUPT_MEDIA = "CORRUPT_MEDIA"
ERROR_CATEGORY_FFMPEG_TIMEOUT = "FFMPEG_TIMEOUT"
ERROR_CATEGORY_FFMPEG_CRASH = "FFMPEG_CRASH"
ERROR_CATEGORY_VALIDATION_FAILED = "VALIDATION_FAILED"
ERROR_CATEGORY_STORAGE_FAILED = "STORAGE_FAILED"
ERROR_CATEGORY_DISK_EXHAUSTED = "DISK_EXHAUSTED"
ERROR_CATEGORY_UNKNOWN = "UNKNOWN"


class MediaTranscodeJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistence model tracking asynchronous multi-resolution FFmpeg HLS transcoding jobs."""

    __tablename__ = "media_transcode_jobs"

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="MediaAsset identifier undergoing HLS transcoding",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TRANSCODE_STATUS_QUEUED,
        server_default=text("'QUEUED'"),
        index=True,
        doc="Job lifecycle status: QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=text("100"),
        doc="Priority weighting (lower number = higher execution priority)",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Consecutive failure count",
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
        doc="Maximum permitted retries before permanent failure",
    )
    next_retry_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="Earliest timestamp when this job may be claimed for execution",
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Timestamp when an active worker claimed this job",
    )
    locked_by: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Worker hostname / process identifier currently leasing this job",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Diagnostic summary error message if job failed",
    )
    error_details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        json_type,
        nullable=True,
        doc="Structured failure diagnostics (category, exit code, stderr snippet)",
    )
    job_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        json_type,
        nullable=True,
        doc="Transcoding input/output metadata, profiles, progress, duration",
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Execution start timestamp",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Execution completion or termination timestamp",
    )

    __table_args__ = (
        Index("ix_media_transcode_jobs_status_next_retry", "status", "next_retry_at"),
        Index("ix_media_transcode_jobs_media_created", "media_id", "created_at"),
    )

    # Relationships
    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        backref="transcode_jobs",
        lazy="joined",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = TRANSCODE_STATUS_QUEUED
        if "priority" not in kwargs or kwargs["priority"] is None:
            kwargs["priority"] = 100
        if "retry_count" not in kwargs or kwargs["retry_count"] is None:
            kwargs["retry_count"] = 0
        if "max_retries" not in kwargs or kwargs["max_retries"] is None:
            kwargs["max_retries"] = 3
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<MediaTranscodeJob id={self.id} "
            f"media_id={self.media_id} "
            f"status={self.status!r} "
            f"retry={self.retry_count}/{self.max_retries}>"
        )
