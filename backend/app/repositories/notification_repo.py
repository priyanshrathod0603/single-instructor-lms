"""NotificationOutboxRepository managing transactional outbox event lifecycle.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Features:
1. Pure async/sync SQLAlchemy 2.0 query execution.
2. add() adds and flushes without committing, preserving caller transaction boundary.
3. claim_pending_events() leverages PostgreSQL row-level locking (FOR UPDATE SKIP LOCKED)
   to prevent dual-worker race conditions.
4. record_failure() calculates exponential backoff: 30 * 2^retry_count seconds.
5. Transitions events to FAILED (dead-letter queue) when retry_count >= max_retries.
6. recover_stale_processing_events() safely resets events abandoned by crashed workers.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Union
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.notification import (
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSING,
    OUTBOX_STATUS_SENT,
    NotificationOutbox,
)

logger = logging.getLogger(__name__)


class NotificationOutboxRepository:
    """Repository handling database operations for NotificationOutbox entities."""

    async def add(
        self,
        session: Union[AsyncSession, Session],
        event: NotificationOutbox,
    ) -> NotificationOutbox:
        """Add an outbox event to the active database session and flush.

        Does not commit, preserving atomic transaction boundaries with the caller.

        Args:
            session: Active database session.
            event: NotificationOutbox instance to persist.

        Returns:
            The flushed NotificationOutbox instance.
        """
        session.add(event)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return event

    async def get_by_id(
        self,
        session: Union[AsyncSession, Session],
        event_id: Union[uuid.UUID, str],
    ) -> Optional[NotificationOutbox]:
        """Retrieve an outbox event by its primary key UUID.

        Args:
            session: Active database session.
            event_id: UUID or UUID string.

        Returns:
            The NotificationOutbox entity or None if not found.
        """
        parsed_id = uuid.UUID(str(event_id)) if not isinstance(event_id, uuid.UUID) else event_id
        if isinstance(session, AsyncSession):
            result = await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.id == parsed_id)
            )
            return result.scalar_one_or_none()
        return session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == parsed_id)
        ).scalar_one_or_none()

    async def get_by_dedupe_key(
        self,
        session: Union[AsyncSession, Session],
        dedupe_key: str,
    ) -> Optional[NotificationOutbox]:
        """Retrieve an outbox event by its unique deduplication key.

        Args:
            session: Active database session.
            dedupe_key: Deterministic idempotency key string.

        Returns:
            The NotificationOutbox entity or None if not found.
        """
        stmt = select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        return session.execute(stmt).scalar_one_or_none()

    async def claim_pending_events(
        self,
        session: Union[AsyncSession, Session],
        batch_size: int = 50,
        now: Optional[datetime] = None,
        lock: bool = True,
    ) -> list[NotificationOutbox]:
        """Fetch and lock eligible pending outbox events for processing.

        Uses PostgreSQL's `FOR UPDATE SKIP LOCKED` when running against a database
        that supports row-level locking, ensuring multiple worker processes or threads
        never claim the same events simultaneously.

        Transitioned events are marked as 'PROCESSING' and flushed within the session.

        Args:
            session: Active database session.
            batch_size: Maximum number of events to claim in one batch.
            now: Current timestamp (defaults to UTC now).
            lock: Whether to acquire row locks with FOR UPDATE SKIP LOCKED.

        Returns:
            List of claimed NotificationOutbox entities in 'PROCESSING' state.
        """
        current_time = now or utc_now()

        # Build query for eligible pending events
        stmt = (
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status == OUTBOX_STATUS_PENDING,
                NotificationOutbox.next_retry_at <= current_time,
            )
            .order_by(NotificationOutbox.created_at.asc())
            .limit(batch_size)
        )

        # Apply PostgreSQL FOR UPDATE SKIP LOCKED if requested and supported
        bind = session.bind if hasattr(session, "bind") else None
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        if lock and dialect_name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
            events = list(result.scalars().all())
        else:
            events = list(session.execute(stmt).scalars().all())

        # Transition claimed events to PROCESSING state
        for event in events:
            event.status = OUTBOX_STATUS_PROCESSING

        if events:
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()

        return events

    async def mark_as_sent(
        self,
        session: Union[AsyncSession, Session],
        event_id: Union[uuid.UUID, str],
        processed_at: Optional[datetime] = None,
    ) -> Optional[NotificationOutbox]:
        """Mark an outbox event as successfully sent.

        Args:
            session: Active database session.
            event_id: Target event UUID or string.
            processed_at: Optional completion timestamp.

        Returns:
            The updated NotificationOutbox or None if not found.
        """
        event = await self.get_by_id(session, event_id)
        if not event:
            return None

        event.status = OUTBOX_STATUS_SENT
        event.processed_at = processed_at or utc_now()
        event.last_error = None

        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return event

    async def record_failure(
        self,
        session: Union[AsyncSession, Session],
        event_id: Union[uuid.UUID, str],
        error_message: str,
        base_backoff_seconds: int = 30,
        max_retries: int = 5,
        now: Optional[datetime] = None,
    ) -> Optional[NotificationOutbox]:
        """Record an event failure, increment retry count, and schedule next retry.

        Applies exponential backoff:
            next_retry_at = NOW() + (base_backoff_seconds * 2^retry_count)

        If retry_count reaches max_retries, transitions the event to FAILED (dead-letter).

        Args:
            session: Active database session.
            event_id: Target event UUID or string.
            error_message: Sanitized error description.
            base_backoff_seconds: Base backoff multiplier in seconds (default 30s).
            max_retries: Retry threshold for dead-letter transition (default 5).
            now: Current timestamp (defaults to UTC now).

        Returns:
            The updated NotificationOutbox or None if not found.
        """
        event = await self.get_by_id(session, event_id)
        if not event:
            return None

        current_time = now or utc_now()
        event.retry_count += 1
        event.last_error = error_message[:2048] if error_message else "Unknown delivery error"

        effective_max = event.max_retries or max_retries

        if event.retry_count >= effective_max:
            event.status = OUTBOX_STATUS_FAILED
            event.processed_at = current_time
            logger.error(
                "Outbox event %s reached maximum retries (%d/%d). Transitioned to FAILED (dead-letter queue).",
                event.id,
                event.retry_count,
                effective_max,
            )
        else:
            event.status = OUTBOX_STATUS_PENDING
            # Exponential backoff formula: base * 2^retry_count
            backoff_delay = base_backoff_seconds * (2 ** event.retry_count)
            # Cap backoff delay to 24 hours (86400 seconds) to prevent integer overflow
            backoff_delay = min(backoff_delay, 86400)
            event.next_retry_at = current_time + timedelta(seconds=backoff_delay)
            logger.warning(
                "Outbox event %s failed attempt %d/%d. Rescheduled for retry at %s (delay %ds).",
                event.id,
                event.retry_count,
                effective_max,
                event.next_retry_at.isoformat(),
                backoff_delay,
            )

        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return event

    async def recover_stale_processing_events(
        self,
        session: Union[AsyncSession, Session],
        stale_threshold_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> int:
        """Reset stale events stuck in PROCESSING state due to crashed workers.

        Any event in 'PROCESSING' whose created_at/next_retry_at is older than
        stale_threshold_seconds is returned to 'PENDING' for re-processing.

        Args:
            session: Active database session.
            stale_threshold_seconds: Seconds after which a processing event is deemed stale (default 300s).
            now: Current timestamp (defaults to UTC now).

        Returns:
            Number of recovered stale events.
        """
        current_time = now or utc_now()
        cutoff_time = current_time - timedelta(seconds=stale_threshold_seconds)

        # Select stale events
        stmt = select(NotificationOutbox).where(
            NotificationOutbox.status == OUTBOX_STATUS_PROCESSING,
            NotificationOutbox.next_retry_at <= cutoff_time,
        )

        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
            stale_events = list(result.scalars().all())
        else:
            stale_events = list(session.execute(stmt).scalars().all())

        recovered_count = len(stale_events)
        for ev in stale_events:
            ev.status = OUTBOX_STATUS_PENDING
            ev.next_retry_at = current_time
            logger.info("Recovered stale outbox event %s back to PENDING status.", ev.id)

        if stale_events:
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()

        return recovered_count

    async def list_events(
        self,
        session: Union[AsyncSession, Session],
        *,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NotificationOutbox], int]:
        """List outbox events with filtering and pagination.

        Args:
            session: Active database session.
            status: Optional filter by event status.
            event_type: Optional filter by event type.
            channel: Optional filter by channel.
            limit: Pagination limit.
            offset: Pagination offset.

        Returns:
            Tuple of (list_of_events, total_count).
        """
        base_query = select(NotificationOutbox)
        count_query = select(func.count()).select_from(NotificationOutbox)

        if status:
            base_query = base_query.where(NotificationOutbox.status == status)
            count_query = count_query.where(NotificationOutbox.status == status)
        if event_type:
            base_query = base_query.where(NotificationOutbox.event_type == event_type)
            count_query = count_query.where(NotificationOutbox.event_type == event_type)
        if channel:
            base_query = base_query.where(NotificationOutbox.channel == channel)
            count_query = count_query.where(NotificationOutbox.channel == channel)

        paginated_query = (
            base_query.order_by(NotificationOutbox.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if isinstance(session, AsyncSession):
            total_count = (await session.execute(count_query)).scalar() or 0
            items = list((await session.execute(paginated_query)).scalars().all())
        else:
            total_count = session.execute(count_query).scalar() or 0
            items = list(session.execute(paginated_query).scalars().all())

        return items, total_count


# Canonical aliases
OutboxRepository = NotificationOutboxRepository
