"""Pydantic schemas for Media Upload Intents, Playback Tokens, and Asset Tracking.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.10)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401-TASK404)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)
"""

from datetime import datetime
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.media import (
    ALLOWED_MIME_TYPES,
    MAX_VIDEO_SIZE_BYTES,
    VALID_MEDIA_STATUSES,
    validate_media_file,
)


class UploadIntentRequest(BaseModel):
    """Payload for initiating a direct presigned upload to S3/R2."""
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    mime_type: str = Field(..., description="File MIME type (e.g. 'video/mp4', 'application/pdf')")
    file_size_bytes: int = Field(..., gt=0, le=MAX_VIDEO_SIZE_BYTES, description="File size in bytes")

    @field_validator("filename")
    @classmethod
    def sanitize_filename(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Filename cannot be empty")
        if "\x00" in cleaned:
            raise ValueError("Filename contains invalid null byte character")
        if "\r" in cleaned or "\n" in cleaned:
            raise ValueError("Filename contains invalid newline character")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("Filename cannot contain directory separators or path traversal sequences")
        return cleaned

    @field_validator("mime_type")
    @classmethod
    def validate_mime(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Disallowed MIME type '{clean}'. Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}")
        return clean


class UploadIntentResponse(BaseModel):
    """Presigned upload instructions returned to client."""
    media_id: uuid.UUID
    file_key: str
    bucket: str
    presigned_url: str
    headers: dict[str, str]
    expires_in_seconds: int = 900


class UploadConfirmRequest(BaseModel):
    """Payload to confirm successful upload and trigger transcode or asset readiness."""
    duration_seconds: Optional[int] = Field(None, ge=0, description="Video duration in seconds if known")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Optional extra media attributes")


class TranscodeJobResponse(BaseModel):
    """Asynchronous HLS video transcoding job representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_id: uuid.UUID
    status: str
    priority: int
    retry_count: int
    max_retries: int
    next_retry_at: datetime
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict[str, Any]] = None
    job_metadata: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MediaAssetResponse(BaseModel):
    """Persisted media asset representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    uploader_id: uuid.UUID
    filename: str
    file_key: str
    bucket: str
    mime_type: str
    file_size_bytes: int
    status: str
    transcode_output: Optional[dict[str, Any]] = None
    public_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _populate_public_url(self) -> "MediaAssetResponse":
        """Expose canonical public thumbnail URL only for verified READY public images."""
        if (
            self.public_url is None
            and self.status == "READY"
            and self.file_key.startswith("public-images/")
            and self.mime_type in {"image/png", "image/jpeg", "image/webp"}
        ):
            self.public_url = f"/api/v1/media/public/{self.id}"
        return self


class MediaAssetListResponse(BaseModel):
    """Paginated list of media assets."""
    items: List[MediaAssetResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class PlaybackTokenRequest(BaseModel):
    """Request for a signed HLS video playback token."""
    lesson_id: Optional[uuid.UUID] = Field(None, description="Optional curriculum lesson identifier")
    course_id: Optional[uuid.UUID] = Field(None, description="Optional course container identifier")


class PlaybackTokenResponse(BaseModel):
    """Signed HLS playback credentials."""
    media_id: uuid.UUID
    playback_token: str
    stream_url: str
    expires_at: datetime
    ttl_seconds: int = 7200


class VerifyPlaybackTokenRequest(BaseModel):
    """Request payload for verifying an HLS playback token."""
    token: str = Field(..., description="Signed HLS playback token to verify")
