"""MediaTranscodeJobRepository managing transcode job lifecycle and worker claiming.

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. Transactional Queueing: Jobs are safely registered and queried.
2. Concurrent Worker Claiming: Polling uses FOR UPDATE SKIP LOCKED on PostgreSQL.
3. Bounded Exponential Backoff: Failed jobs increment retry_count and schedule next_retry_at.
4. Stale Recovery: Abandoned processing jobs are recovered after configurable threshold.
5. Idempotent Active Registration: Avoids multiple concurrent active jobs per media asset.
"""

from datetime import datetime, timedelta
import logging
from typing import Any, Optional, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.transcode_job import (
    TRANSCODE_STATUS_CANCELLED,
    TRANSCODE_STATUS_COMPLETED,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_QUEUED,
    MediaTranscodeJob,
)

logger = logging.getLogger(__name__)


class MediaTranscodeJobRepository:
    """Repository managing database persistence and leasing for MediaTranscodeJob."""

    def create_job(
        self,
        session: Session,
        media_id: Union[uuid.UUID, str],
        priority: int = 100,
        max_retries: int = 3,
        job_metadata: Optional[dict[str, Any]] = None,
    ) -> MediaTranscodeJob:
        """Create a new transcoding job or return existing active job for media asset.

        Args:
            session: SQLAlchemy DB session.
            media_id: Target MediaAsset identifier.
            priority: Execution priority weighting (lower = higher priority).
            max_retries: Maximum permitted retries.
            job_metadata: Optional initial job metadata dictionary.

        Returns:
            Created or existing active MediaTranscodeJob.
        """
        parsed_id = uuid.UUID(str(media_id)) if not isinstance(media_id, uuid.UUID) else media_id

        # Idempotency check: look for active job
        active_job = self.get_active_job_by_media_id(session, parsed_id)
        if active_job:
            return active_job

        job = MediaTranscodeJob(
            media_id=parsed_id,
            status=TRANSCODE_STATUS_QUEUED,
            priority=priority,
            retry_count=0,
            max_retries=max_retries,
            next_retry_at=utc_now(),
            job_metadata=job_metadata or {},
        )
        session.add(job)
        session.flush()
        return job

    def get_by_id(
        self,
        session: Session,
        job_id: Union[uuid.UUID, str],
        for_update: bool = False,
    ) -> Optional[MediaTranscodeJob]:
        """Fetch transcode job by ID."""
        parsed_id = uuid.UUID(str(job_id)) if not isinstance(job_id, uuid.UUID) else job_id
        stmt = select(MediaTranscodeJob).where(MediaTranscodeJob.id == parsed_id)
        if for_update and session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalar_one_or_none()

    def get_active_job_by_media_id(
        self,
        session: Session,
        media_id: Union[uuid.UUID, str],
    ) -> Optional[MediaTranscodeJob]:
        """Return currently active (QUEUED or PROCESSING) job for media asset if present."""
        parsed_id = uuid.UUID(str(media_id)) if not isinstance(media_id, uuid.UUID) else media_id
        stmt = (
            select(MediaTranscodeJob)
            .where(
                MediaTranscodeJob.media_id == parsed_id,
                MediaTranscodeJob.status.in_([TRANSCODE_STATUS_QUEUED, TRANSCODE_STATUS_PROCESSING]),
            )
            .order_by(MediaTranscodeJob.created_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def get_latest_job_by_media_id(
        self,
        session: Session,
        media_id: Union[uuid.UUID, str],
    ) -> Optional[MediaTranscodeJob]:
        """Return the most recent transcode job for media asset regardless of status."""
        parsed_id = uuid.UUID(str(media_id)) if not isinstance(media_id, uuid.UUID) else media_id
        stmt = (
            select(MediaTranscodeJob)
            .where(MediaTranscodeJob.media_id == parsed_id)
            .order_by(MediaTranscodeJob.created_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def claim_pending_jobs(
        self,
        session: Session,
        batch_size: int = 10,
        worker_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> list[MediaTranscodeJob]:
        """Claim a batch of QUEUED jobs eligible for execution.

        Uses SELECT FOR UPDATE SKIP LOCKED on PostgreSQL to prevent worker collision.
        Transitions claimed jobs to PROCESSING status.

        Args:
            session: SQLAlchemy DB session.
            batch_size: Maximum jobs to claim.
            worker_id: Unique worker hostname/pid identifier.
            current_time: Optional timestamp override.

        Returns:
            List of claimed MediaTranscodeJob instances.
        """
        now = current_time or utc_now()
        stmt = (
            select(MediaTranscodeJob)
            .where(
                MediaTranscodeJob.status == TRANSCODE_STATUS_QUEUED,
                MediaTranscodeJob.next_retry_at <= now,
            )
            .order_by(
                MediaTranscodeJob.priority.asc(),
                MediaTranscodeJob.created_at.asc(),
            )
            .limit(max(1, batch_size))
        )

        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        jobs = list(session.execute(stmt).scalars().all())
        for job in jobs:
            job.status = TRANSCODE_STATUS_PROCESSING
            job.locked_at = now
            job.locked_by = worker_id
            if job.started_at is None:
                job.started_at = now
        session.flush()
        return jobs

    def mark_completed(
        self,
        session: Session,
        job_id: Union[uuid.UUID, str],
        job_metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[MediaTranscodeJob]:
        """Mark a job as successfully completed."""
        job = self.get_by_id(session, job_id, for_update=True)
        if not job:
            return None

        now = utc_now()
        job.status = TRANSCODE_STATUS_COMPLETED
        job.completed_at = now
        job.locked_at = None
        job.locked_by = None
        job.error_message = None
        job.error_details = None

        if job_metadata:
            merged = dict(job.job_metadata or {})
            merged.update(job_metadata)
            job.job_metadata = merged

        session.flush()
        return job

    def mark_failed(
        self,
        session: Session,
        job_id: Union[uuid.UUID, str],
        error_message: str,
        error_details: Optional[dict[str, Any]] = None,
        is_retryable: bool = True,
        base_backoff_seconds: int = 30,
    ) -> Optional[MediaTranscodeJob]:
        """Record job failure and schedule exponential retry or permanent failure.

        Args:
            session: SQLAlchemy DB session.
            job_id: Transcode job ID.
            error_message: Summary error message.
            error_details: Structured diagnostic error details.
            is_retryable: Whether error is transient and eligible for retry.
            base_backoff_seconds: Base multiplier for exponential backoff.

        Returns:
            Updated MediaTranscodeJob or None if not found.
        """
        job = self.get_by_id(session, job_id, for_update=True)
        if not job:
            return None

        now = utc_now()
        job.retry_count += 1
        job.error_message = error_message[:2000] if error_message else "Unknown error"
        job.error_details = error_details or {}
        job.locked_at = None
        job.locked_by = None

        if is_retryable and job.retry_count < job.max_retries:
            backoff_secs = base_backoff_seconds * (2 ** (job.retry_count - 1))
            job.status = TRANSCODE_STATUS_QUEUED
            job.next_retry_at = now + timedelta(seconds=backoff_secs)
            logger.warning(
                "TranscodeJob %s failed (%s); scheduled retry #%d for %s",
                job.id,
                error_message,
                job.retry_count,
                job.next_retry_at.isoformat(),
            )
        else:
            job.status = TRANSCODE_STATUS_FAILED
            job.completed_at = now
            logger.error(
                "TranscodeJob %s permanently failed after %d retries: %s",
                job.id,
                job.retry_count,
                error_message,
            )

        session.flush()
        return job

    def recover_stale_processing_jobs(
        self,
        session: Session,
        stale_threshold_seconds: int = 600,
        current_time: Optional[datetime] = None,
    ) -> int:
        """Reset stale PROCESSING jobs abandoned by worker crashes or timeouts.

        Args:
            session: SQLAlchemy DB session.
            stale_threshold_seconds: Duration after which locked job is deemed dead.
            current_time: Optional reference time override.

        Returns:
            Number of recovered jobs.
        """
        now = current_time or utc_now()
        cutoff = now - timedelta(seconds=stale_threshold_seconds)

        stmt = (
            select(MediaTranscodeJob)
            .where(
                MediaTranscodeJob.status == TRANSCODE_STATUS_PROCESSING,
                MediaTranscodeJob.locked_at <= cutoff,
            )
        )

        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        stale_jobs = list(session.execute(stmt).scalars().all())
        recovered_count = 0

        for job in stale_jobs:
            job.retry_count += 1
            job.locked_at = None
            job.locked_by = None
            if job.retry_count < job.max_retries:
                job.status = TRANSCODE_STATUS_QUEUED
                job.next_retry_at = now
                job.error_message = f"Recovered from stale lock after {stale_threshold_seconds}s"
            else:
                job.status = TRANSCODE_STATUS_FAILED
                job.completed_at = now
                job.error_message = f"Permanently failed after exceeding retries due to stale worker crashes"
            recovered_count += 1

        if recovered_count > 0:
            session.flush()
            logger.warning("Recovered %d stale transcode jobs.", recovered_count)

        return recovered_count

    def list_jobs(
        self,
        session: Session,
        media_id: Optional[Union[uuid.UUID, str]] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[MediaTranscodeJob], int]:
        """List transcoding jobs with pagination and filters."""
        base_query = select(MediaTranscodeJob)
        count_query = select(func.count()).select_from(MediaTranscodeJob)

        if media_id is not None:
            parsed_media_id = uuid.UUID(str(media_id)) if not isinstance(media_id, uuid.UUID) else media_id
            base_query = base_query.where(MediaTranscodeJob.media_id == parsed_media_id)
            count_query = count_query.where(MediaTranscodeJob.media_id == parsed_media_id)

        if status is not None:
            base_query = base_query.where(MediaTranscodeJob.status == status)
            count_query = count_query.where(MediaTranscodeJob.status == status)

        total = session.scalar(count_query) or 0
        offset = max(0, (page - 1) * per_page)
        items = list(
            session.execute(
                base_query.order_by(MediaTranscodeJob.created_at.desc()).offset(offset).limit(per_page)
            )
            .scalars()
            .all()
        )
        return items, total
