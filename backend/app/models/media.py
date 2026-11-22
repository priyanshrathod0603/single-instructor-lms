"""MediaAsset SQLAlchemy 2.0 persistence model and storage metadata.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 32)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)

Strict Invariants:
1. Direct Presigned Ingestion: Large binaries never proxy through app server RAM.
2. MIME Whitelist & Size Enforcement: Validated before generating presigned upload URLs.
3. Protected Delivery: Raw files never made public; accessed via signed HLS tokens or watermarked streams.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.exceptions import ValidationException
from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.user import User

# Canonical Media Status Constants
MEDIA_STATUS_UPLOADING = "UPLOADING"
MEDIA_STATUS_UPLOADED = "UPLOADED"
MEDIA_STATUS_PROCESSING = "PROCESSING"
MEDIA_STATUS_READY = "READY"
MEDIA_STATUS_FAILED = "FAILED"

VALID_MEDIA_STATUSES = frozenset({
    MEDIA_STATUS_UPLOADING,
    MEDIA_STATUS_UPLOADED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_FAILED,
})

# Permitted MIME Types
MIME_VIDEO_MP4 = "video/mp4"
MIME_VIDEO_QUICKTIME = "video/quicktime"
MIME_VIDEO_WEBM = "video/webm"
MIME_PDF = "application/pdf"
MIME_IMAGE_PNG = "image/png"
MIME_IMAGE_JPEG = "image/jpeg"
MIME_IMAGE_WEBP = "image/webp"
MIME_ZIP = "application/zip"
MIME_TAR = "application/x-tar"
MIME_GZIP = "application/gzip"

# Strict Size Limits (in bytes)
MAX_VIDEO_SIZE_BYTES = 5_242_880_000      # 5 GB
MAX_PDF_SIZE_BYTES = 52_428_800           # 50 MB
MAX_IMAGE_SIZE_BYTES = 5_242_880          # 5 MB
MAX_RESOURCE_SIZE_BYTES = 104_857_600     # 100 MB

# Mapping of MIME type to category limits and storage prefixes
MIME_CONFIG: dict[str, dict[str, Any]] = {
    MIME_VIDEO_MP4: {"category": "video", "max_bytes": MAX_VIDEO_SIZE_BYTES, "prefix": "raw-videos"},
    MIME_VIDEO_QUICKTIME: {"category": "video", "max_bytes": MAX_VIDEO_SIZE_BYTES, "prefix": "raw-videos"},
    MIME_VIDEO_WEBM: {"category": "video", "max_bytes": MAX_VIDEO_SIZE_BYTES, "prefix": "raw-videos"},
    MIME_PDF: {"category": "pdf", "max_bytes": MAX_PDF_SIZE_BYTES, "prefix": "protected-docs"},
    MIME_IMAGE_PNG: {"category": "image", "max_bytes": MAX_IMAGE_SIZE_BYTES, "prefix": "public-images"},
    MIME_IMAGE_JPEG: {"category": "image", "max_bytes": MAX_IMAGE_SIZE_BYTES, "prefix": "public-images"},
    MIME_IMAGE_WEBP: {"category": "image", "max_bytes": MAX_IMAGE_SIZE_BYTES, "prefix": "public-images"},
    MIME_ZIP: {"category": "resource", "max_bytes": MAX_RESOURCE_SIZE_BYTES, "prefix": "lesson-resources"},
    MIME_TAR: {"category": "resource", "max_bytes": MAX_RESOURCE_SIZE_BYTES, "prefix": "lesson-resources"},
    MIME_GZIP: {"category": "resource", "max_bytes": MAX_RESOURCE_SIZE_BYTES, "prefix": "lesson-resources"},
}

ALLOWED_MIME_TYPES = frozenset(MIME_CONFIG.keys())


def validate_media_file(mime_type: str, file_size_bytes: int) -> dict[str, Any]:
    """Validate MIME whitelist and file size boundaries.

    Raises:
        ValidationException: If MIME type is disallowed or file size exceeds maximum limits.
    """
    clean_mime = mime_type.strip().lower()
    if clean_mime not in ALLOWED_MIME_TYPES:
        raise ValidationException(
            message=f"Disallowed MIME type '{clean_mime}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
            code="INVALID_MIME_TYPE",
            details={"mime_type": clean_mime, "allowed_mime_types": list(sorted(ALLOWED_MIME_TYPES))},
        )

    cfg = MIME_CONFIG[clean_mime]
    max_bytes = cfg["max_bytes"]
    if file_size_bytes <= 0:
        raise ValidationException(
            message="File size must be strictly positive.",
            code="INVALID_FILE_SIZE",
            details={"file_size_bytes": file_size_bytes},
        )

    if file_size_bytes > max_bytes:
        raise ValidationException(
            message=f"File size {file_size_bytes} bytes exceeds maximum permitted {max_bytes} bytes for {cfg['category']} files.",
            code="FILE_TOO_LARGE",
            details={"file_size_bytes": file_size_bytes, "max_bytes": max_bytes, "category": cfg["category"]},
        )

    return cfg


# Dual-dialect JSON type
json_type = JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Catalog of uploaded video, PDF, image, and resource files in Cloudflare R2 / S3."""

    __tablename__ = "media_assets"

    uploader_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="User ID of instructor or staff member who uploaded the asset",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Original uploaded file name",
    )
    file_key: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique S3 / R2 object key",
    )
    bucket: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Storage bucket identifier",
    )
    mime_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Validated file MIME type",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="File size in bytes",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MEDIA_STATUS_UPLOADING,
        server_default=text("'UPLOADING'"),
        index=True,
        doc="Upload and transcode lifecycle status: UPLOADING, UPLOADED, PROCESSING, READY, FAILED",
    )
    transcode_output: Mapped[Optional[dict[str, Any]]] = mapped_column(
        json_type,
        nullable=True,
        doc="HLS manifest URLs, available resolutions (1080p, 720p), duration",
    )

    __table_args__ = (
        Index("ix_media_assets_uploader_created", "uploader_id", "created_at"),
        Index("ix_media_assets_status_created", "status", "created_at"),
    )

    # Relationships
    uploader: Mapped["User"] = relationship(
        "User",
        back_populates="media_assets",
        lazy="joined",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = MEDIA_STATUS_UPLOADING
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<MediaAsset id={self.id} "
            f"filename={self.filename!r} "
            f"status={self.status!r} "
            f"size={self.file_size_bytes}>"
        )
