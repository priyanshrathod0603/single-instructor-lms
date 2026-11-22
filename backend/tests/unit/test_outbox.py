"""Unit tests for Transactional Outbox model, repository, service, and worker.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import ValidationException
from app.core.logging import set_request_id
from app.main import create_app
from app.models.base import Base, utc_now
from app.models.notification import (
    OUTBOX_CHANNEL_EMAIL,
    OUTBOX_CHANNEL_IN_APP,
    OUTBOX_CHANNEL_WEBHOOK,
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSING,
    OUTBOX_STATUS_SENT,
    NotificationOutbox,
    OutboxEvent,
)
from app.repositories.notification_repo import (
    NotificationOutboxRepository,
    OutboxRepository,
)
from app.services.outbox_service import NotificationService, OutboxService
from app.workers.outbox_worker import OutboxWorker


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Provides a fresh, isolated SQLite in-memory database and session for outbox unit tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        class_=Session,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def session_factory():
    """Provides a fresh SQLite in-memory engine and sessionmaker factory."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        class_=Session,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    yield TestingSessionLocal
    Base.metadata.drop_all(engine)
    engine.dispose()


# =============================================================================
# 1. Outbox Model Tests
# =============================================================================

class TestNotificationOutboxModel:
    """Verifies Outbox model instantiation, defaults, and invariants."""

    def test_instantiation_defaults(self):
        """Model must initialize with proper client defaults."""
        event = NotificationOutbox(event_type="AUTH_VERIFY_EMAIL")

        assert isinstance(event.id, uuid.UUID)
        assert event.event_type == "AUTH_VERIFY_EMAIL"
        assert event.channel == OUTBOX_CHANNEL_EMAIL
        assert event.recipient == ""
        assert event.subject is None
        assert event.payload == {}
        assert event.dedupe_key is None
        assert event.status == OUTBOX_STATUS_PENDING
        assert event.retry_count == 0
        assert event.max_retries == 5
        assert isinstance(event.created_at, datetime)
        assert event.created_at.tzinfo == timezone.utc
        assert isinstance(event.next_retry_at, datetime)
        assert event.next_retry_at.tzinfo == timezone.utc
        assert event.processed_at is None
        assert event.last_error is None

    def test_instantiation_with_all_fields(self):
        """Model must accept all defined fields and normalize timezones."""
        custom_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        payload = {"first_name": "Alice", "token": "abc123xyz"}

        event = NotificationOutbox(
            id=custom_id,
            event_type="ENROLLMENT_RECEIPT",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient="alice@example.com",
            subject="Welcome to Course",
            payload=payload,
            dedupe_key="RECEIPT_ORD_001",
            status=OUTBOX_STATUS_PROCESSING,
            retry_count=1,
            max_retries=3,
            next_retry_at=now,
            processed_at=now,
            last_error="Temporary gateway error",
            created_at=now,
        )

        assert event.id == custom_id
        assert event.event_type == "ENROLLMENT_RECEIPT"
        assert event.channel == OUTBOX_CHANNEL_EMAIL
        assert event.recipient == "alice@example.com"
        assert event.subject == "Welcome to Course"
        assert event.payload == payload
        assert event.dedupe_key == "RECEIPT_ORD_001"
        assert event.status == OUTBOX_STATUS_PROCESSING
        assert event.retry_count == 1
        assert event.max_retries == 3
        assert event.next_retry_at == now
        assert event.processed_at == now
        assert event.last_error == "Temporary gateway error"

    def test_canonical_alias(self):
        """OutboxEvent must be an alias for NotificationOutbox."""
        assert OutboxEvent is NotificationOutbox
        event = OutboxEvent(event_type="TEST_EVENT")
        assert isinstance(event, NotificationOutbox)

    def test_safe_representation(self):
        """__repr__ must not expose payload dictionary."""
        event = NotificationOutbox(
            event_type="AUTH_PASSWORD_RESET",
            payload={"secret_token": "super_secret_value"},
        )
        rep = repr(event)
        assert "super_secret_value" not in rep
        assert "AUTH_PASSWORD_RESET" in rep
        assert "PENDING" in rep


# =============================================================================
# 2. Outbox Repository Tests
# =============================================================================

class TestNotificationOutboxRepository:
    """Verifies repository query operations and lifecycle transitions."""

    @pytest.mark.asyncio
    async def test_add_and_get_by_id(self, db_session: Session):
        """add() flushes event; get_by_id() retrieves it."""
        repo = NotificationOutboxRepository()
        event = NotificationOutbox(
            event_type="TEST_ADD",
            recipient="test@example.com",
            payload={"key": "val"},
        )

        staged = await repo.add(db_session, event)
        assert staged.id is not None

        retrieved = await repo.get_by_id(db_session, staged.id)
        assert retrieved is not None
        assert retrieved.id == staged.id
        assert retrieved.event_type == "TEST_ADD"
        assert retrieved.recipient == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_by_dedupe_key(self, db_session: Session):
        """get_by_dedupe_key() returns matching event."""
        repo = NotificationOutboxRepository()
        event = NotificationOutbox(
            event_type="TEST_DEDUPE",
            dedupe_key="UNIQUE_KEY_001",
        )
        await repo.add(db_session, event)

        retrieved = await repo.get_by_dedupe_key(db_session, "UNIQUE_KEY_001")
        assert retrieved is not None
        assert retrieved.dedupe_key == "UNIQUE_KEY_001"

        missing = await repo.get_by_dedupe_key(db_session, "NON_EXISTENT")
        assert missing is None

    @pytest.mark.asyncio
    async def test_claim_pending_events(self, db_session: Session):
        """claim_pending_events() claims eligible events and transitions them to PROCESSING."""
        repo = NotificationOutboxRepository()
        now = utc_now()

        # Event 1: eligible (PENDING, next_retry_at <= now)
        ev1 = NotificationOutbox(event_type="EVENT_1", next_retry_at=now - timedelta(seconds=10))
        # Event 2: future (PENDING, next_retry_at > now)
        ev2 = NotificationOutbox(event_type="EVENT_2", next_retry_at=now + timedelta(seconds=100))
        # Event 3: already SENT
        ev3 = NotificationOutbox(event_type="EVENT_3", status=OUTBOX_STATUS_SENT)

        await repo.add(db_session, ev1)
        await repo.add(db_session, ev2)
        await repo.add(db_session, ev3)

        claimed = await repo.claim_pending_events(db_session, batch_size=10, now=now, lock=False)
        assert len(claimed) == 1
        assert claimed[0].id == ev1.id
        assert claimed[0].status == OUTBOX_STATUS_PROCESSING

    @pytest.mark.asyncio
    async def test_mark_as_sent(self, db_session: Session):
        """mark_as_sent() transitions event to SENT with processed_at."""
        repo = NotificationOutboxRepository()
        event = NotificationOutbox(event_type="TEST_SENT")
        await repo.add(db_session, event)

        updated = await repo.mark_as_sent(db_session, event.id)
        assert updated is not None
        assert updated.status == OUTBOX_STATUS_SENT
        assert updated.processed_at is not None
        assert updated.last_error is None

    @pytest.mark.asyncio
    async def test_record_failure_exponential_backoff(self, db_session: Session):
        """record_failure() computes exponential backoff 30 * 2^retry_count."""
        repo = NotificationOutboxRepository()
        now = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = NotificationOutbox(event_type="TEST_RETRY", next_retry_at=now)
        await repo.add(db_session, event)

        # Attempt 1: retry_count becomes 1 -> delay = 30 * 2^1 = 60s
        ev1 = await repo.record_failure(
            db_session,
            event.id,
            error_message="Connection timeout",
            base_backoff_seconds=30,
            max_retries=5,
            now=now,
        )
        assert ev1.retry_count == 1
        assert ev1.status == OUTBOX_STATUS_PENDING
        assert ev1.next_retry_at == now + timedelta(seconds=60)
        assert "Connection timeout" in ev1.last_error

        # Attempt 2: retry_count becomes 2 -> delay = 30 * 2^2 = 120s
        ev2 = await repo.record_failure(
            db_session,
            event.id,
            error_message="Connection timeout 2",
            base_backoff_seconds=30,
            max_retries=5,
            now=now,
        )
        assert ev2.retry_count == 2
        assert ev2.status == OUTBOX_STATUS_PENDING
        assert ev2.next_retry_at == now + timedelta(seconds=120)

    @pytest.mark.asyncio
    async def test_record_failure_dead_letter_queue(self, db_session: Session):
        """record_failure() transitions to FAILED when retry_count reaches max_retries."""
        repo = NotificationOutboxRepository()
        event = NotificationOutbox(
            event_type="TEST_DEAD_LETTER",
            retry_count=4,
            max_retries=5,
        )
        await repo.add(db_session, event)

        # 5th failure -> reaches max_retries
        ev = await repo.record_failure(
            db_session,
            event.id,
            error_message="Permanent 500 fatal failure",
            base_backoff_seconds=30,
            max_retries=5,
        )
        assert ev.retry_count == 5
        assert ev.status == OUTBOX_STATUS_FAILED
        assert ev.processed_at is not None

    @pytest.mark.asyncio
    async def test_recover_stale_processing_events(self, db_session: Session):
        """recover_stale_processing_events() resets crashed worker events to PENDING."""
        repo = NotificationOutboxRepository()
        now = utc_now()

        stale_event = NotificationOutbox(
            event_type="STALE_EVENT",
            status=OUTBOX_STATUS_PROCESSING,
            next_retry_at=now - timedelta(seconds=600),
        )
        fresh_event = NotificationOutbox(
            event_type="FRESH_EVENT",
            status=OUTBOX_STATUS_PROCESSING,
            next_retry_at=now - timedelta(seconds=10),
        )

        await repo.add(db_session, stale_event)
        await repo.add(db_session, fresh_event)

        recovered = await repo.recover_stale_processing_events(
            db_session,
            stale_threshold_seconds=300,
            now=now,
        )
        assert recovered == 1

        refreshed_stale = await repo.get_by_id(db_session, stale_event.id)
        assert refreshed_stale.status == OUTBOX_STATUS_PENDING

        refreshed_fresh = await repo.get_by_id(db_session, fresh_event.id)
        assert refreshed_fresh.status == OUTBOX_STATUS_PROCESSING

    @pytest.mark.asyncio
    async def test_list_events_with_filters(self, db_session: Session):
        """list_events() filters by status, channel, and pagination."""
        repo = NotificationOutboxRepository()
        await repo.add(db_session, NotificationOutbox(event_type="T1", channel="EMAIL", status="PENDING"))
        await repo.add(db_session, NotificationOutbox(event_type="T2", channel="IN_APP", status="SENT"))
        await repo.add(db_session, NotificationOutbox(event_type="T3", channel="EMAIL", status="SENT"))

        all_events, total = await repo.list_events(db_session)
        assert total == 3

        sent_events, sent_count = await repo.list_events(db_session, status="SENT")
        assert sent_count == 2

        email_events, email_count = await repo.list_events(db_session, channel="EMAIL")
        assert email_count == 2


# =============================================================================
# 3. Outbox Service Tests
# =============================================================================

class TestOutboxService:
    """Verifies service event validation, idempotency, and transactional atomicity."""

    @pytest.mark.asyncio
    async def test_publish_event_success(self, db_session: Session):
        """publish_event stages valid event with defaults."""
        service = OutboxService()
        event = await service.publish_event(
            db_session,
            event_type="AUTH_VERIFY_EMAIL",
            payload={"token": "123"},
            recipient="test@example.com",
            subject="Verify your email",
        )

        assert event.id is not None
        assert event.event_type == "AUTH_VERIFY_EMAIL"
        assert event.recipient == "test@example.com"
        assert event.subject == "Verify your email"
        assert event.payload["token"] == "123"

    @pytest.mark.asyncio
    async def test_publish_event_validates_payload(self, db_session: Session):
        """Non-dict or non-serializable payloads raise ValidationException."""
        service = OutboxService()

        with pytest.raises(ValidationException, match="must be a JSON dictionary"):
            await service.publish_event(
                db_session,
                event_type="TEST",
                payload="not_a_dict",  # type: ignore
            )

    @pytest.mark.asyncio
    async def test_publish_event_validates_channel(self, db_session: Session):
        """Invalid channel raises ValidationException."""
        service = OutboxService()

        with pytest.raises(ValidationException, match="Invalid delivery channel"):
            await service.publish_event(
                db_session,
                event_type="TEST",
                payload={},
                channel="SMS",  # Not supported
            )

    @pytest.mark.asyncio
    async def test_publish_event_validates_event_type(self, db_session: Session):
        """Empty event_type raises ValidationException."""
        service = OutboxService()

        with pytest.raises(ValidationException, match="must be a non-empty string"):
            await service.publish_event(
                db_session,
                event_type="",
                payload={},
            )

    @pytest.mark.asyncio
    async def test_idempotency_via_dedupe_key(self, db_session: Session):
        """Subsequent publish calls with same dedupe_key return existing event without duplicates."""
        service = OutboxService()
        key = "IDEMPOTENT_KEY_123"

        ev1 = await service.publish_event(
            db_session,
            event_type="TEST_IDEMPOTENCY",
            payload={"attempt": 1},
            dedupe_key=key,
        )

        ev2 = await service.publish_event(
            db_session,
            event_type="TEST_IDEMPOTENCY",
            payload={"attempt": 2},
            dedupe_key=key,
        )

        assert ev1.id == ev2.id

    @pytest.mark.asyncio
    async def test_request_id_correlation(self, db_session: Session):
        """Active request_id is automatically attached to event payload."""
        service = OutboxService()
        test_req_id = "req-test-uuid-12345"
        token = set_request_id(test_req_id)

        try:
            event = await service.publish_event(
                db_session,
                event_type="TEST_REQ_ID",
                payload={"data": 1},
            )
            assert event.payload["_request_id"] == test_req_id
        finally:
            from app.core.logging import reset_request_id
            reset_request_id(token)

    @pytest.mark.asyncio
    async def test_transactional_rollback_discards_outbox_event(self, session_factory):
        """Caller transaction rollback must discard staged outbox event."""
        service = OutboxService()
        event_id = None

        with session_factory() as session:
            with session.begin():
                event = await service.publish_event(
                    session,
                    event_type="TEST_ROLLBACK",
                    payload={"msg": "should not persist"},
                )
                event_id = event.id
                # Force rollback by raising an exception
                session.rollback()

        # Verify event was NOT persisted
        with session_factory() as check_session:
            repo = NotificationOutboxRepository()
            persisted = await repo.get_by_id(check_session, event_id)
            assert persisted is None


# =============================================================================
# 4. Outbox Worker Tests
# =============================================================================

class TestOutboxWorker:
    """Verifies worker execution, retry logic, error handling, and lifecycle."""

    @pytest.mark.asyncio
    async def test_run_once_empty_queue(self, session_factory):
        """run_once returns 0 when queue has no pending events."""
        worker = OutboxWorker(session_factory=session_factory)

        count = await worker.run_once()
        assert count == 0

    @pytest.mark.asyncio
    async def test_run_once_successful_dispatch(self, session_factory):
        """run_once claims, dispatches, and marks event as SENT."""
        dispatched_events = []

        async def fake_dispatcher(ev: NotificationOutbox):
            dispatched_events.append(ev.id)

        # Stage an event
        with session_factory() as session:
            with session.begin():
                repo = NotificationOutboxRepository()
                event = NotificationOutbox(event_type="TEST_WORKER_SUCCESS")
                await repo.add(session, event)
                target_id = event.id

        worker = OutboxWorker(
            session_factory=session_factory,
            dispatcher=fake_dispatcher,
        )
        processed = await worker.run_once()
        assert processed == 1
        assert target_id in dispatched_events

        # Verify event status is now SENT
        with session_factory() as session:
            repo = NotificationOutboxRepository()
            refreshed = await repo.get_by_id(session, target_id)
            assert refreshed.status == OUTBOX_STATUS_SENT
            assert refreshed.processed_at is not None

    @pytest.mark.asyncio
    async def test_run_once_handles_dispatcher_failure(self, session_factory):
        """Worker catches dispatcher exceptions, records failure, and scrubs sensitive keys."""
        async def failing_dispatcher(ev: NotificationOutbox):
            raise RuntimeError("External SMTP failed with api_key=secret_api_key_123 and Bearer token_abc_999")

        # Stage an event
        with session_factory() as session:
            with session.begin():
                repo = NotificationOutboxRepository()
                event = NotificationOutbox(event_type="TEST_WORKER_FAILURE")
                await repo.add(session, event)
                target_id = event.id

        worker = OutboxWorker(
            session_factory=session_factory,
            dispatcher=failing_dispatcher,
            base_backoff_seconds=10,
        )

        # Must not raise an exception
        processed = await worker.run_once()
        assert processed == 1

        # Verify failure state recorded
        with session_factory() as session:
            repo = NotificationOutboxRepository()
            refreshed = await repo.get_by_id(session, target_id)
            assert refreshed.status == OUTBOX_STATUS_PENDING
            assert refreshed.retry_count == 1
            # Verify sensitive credentials were scrubbed from error trace
            assert "secret_api_key_123" not in refreshed.last_error
            assert "token_abc_999" not in refreshed.last_error
            assert "[REDACTED]" in refreshed.last_error

    @pytest.mark.asyncio
    async def test_worker_start_and_stop_lifecycle(self, session_factory):
        """Worker starts background task and stops cleanly upon signal."""
        worker = OutboxWorker(
            session_factory=session_factory,
            poll_interval=0.1,
        )

        await worker.start()
        assert worker._running is True
        assert worker._task is not None

        await asyncio.sleep(0.05)

        await worker.stop()
        assert worker._running is False
        assert worker._task is None


# =============================================================================
# 5. Application Lifespan Integration Tests
# =============================================================================

class TestOutboxLifespanIntegration:
    """Verifies worker startup and shutdown within FastAPI ASGI lifespan."""

    def test_worker_disabled_by_default(self, monkeypatch):
        """When OUTBOX_WORKER_ENABLED is False, lifespan does not spawn background task."""
        from fastapi.testclient import TestClient

        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        app = create_app()

        with TestClient(app):
            assert getattr(app.state, "outbox_worker", None) is None

    @pytest.mark.asyncio
    async def test_worker_enabled_in_lifespan(self, monkeypatch):
        """When outbox_worker_enabled is True, lifespan starts and stops worker cleanly."""
        from app.main import lifespan

        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        settings = Settings(OUTBOX_WORKER_ENABLED=True)
        app = create_app(settings=settings, outbox_worker_enabled=True)

        async with lifespan(app):
            worker = getattr(app.state, "outbox_worker", None)
            assert worker is not None
            assert worker._running is True

        # After lifespan exits, worker must be stopped
        assert worker._running is False
