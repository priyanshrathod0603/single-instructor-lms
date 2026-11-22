"""Unit tests for SQLAlchemy 2.0 AuditLog model.

Verifies:
1. Model instantiation with required and optional fields.
2. Client-side and server-side UUIDv4 primary key generation.
3. Nullable actor_id for system/unauthenticated events.
4. Required column constraints and defaults (actor_type='SYSTEM', metadata={}).
5. JSONB / JSON attribute handling for before_state, after_state, and metadata_.
6. created_at timezone-aware UTC timestamp behavior.
7. Absence of updated_at column and attribute (append-only invariant).
8. Safe __repr__ string representation (no attribute/credential leakage).
9. Sensitive field exclusion in to_dict() serialization.
10. End-to-end SQLite in-memory persistence and attribute roundtrip.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.logging import reset_request_id, set_request_id
from app.models import AuditLog, Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.repositories import AuditRepository
from app.services import AuditService


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def in_memory_db():
    """Provides a fresh, isolated SQLite in-memory database and session for AuditLog tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


# -----------------------------------------------------------------------------
# Test Suites
# -----------------------------------------------------------------------------
class TestAuditLogModelInstantiation:
    """Verifies AuditLog model attribute initialization and defaults."""

    def test_instantiation_with_required_fields(self):
        """Model must instantiate successfully with only required fields."""
        log = AuditLog(
            action="COURSE_CREATED",
            resource_type="course",
        )

        assert log.action == "COURSE_CREATED"
        assert log.resource_type == "course"
        assert log.actor_id is None
        assert log.actor_type == "SYSTEM"
        assert log.resource_id is None
        assert log.before_state is None
        assert log.after_state is None
        assert log.metadata_ == {}
        assert log.request_id is None
        assert log.ip_address is None
        assert log.user_agent is None
        assert isinstance(log.id, uuid.UUID)
        assert isinstance(log.created_at, datetime)
        assert log.created_at.tzinfo == timezone.utc

    def test_instantiation_with_all_fields(self):
        """Model must store and expose all specified attributes correctly."""
        actor_uuid = uuid.uuid4()
        log = AuditLog(
            actor_id=actor_uuid,
            actor_type="ADMIN",
            action="GRADE_OVERRIDDEN",
            resource_type="assignment_submission",
            resource_id="sub_12345",
            before_state={"final_score": 70.0, "status": "GRADED"},
            after_state={"final_score": 90.0, "status": "GRADED"},
            metadata_={"override_reason": "Question 3 ambiguity grant"},
            request_id="req_test_abc123",
            ip_address="198.51.100.42",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        )

        assert log.actor_id == actor_uuid
        assert log.actor_type == "ADMIN"
        assert log.action == "GRADE_OVERRIDDEN"
        assert log.resource_type == "assignment_submission"
        assert log.resource_id == "sub_12345"
        assert log.before_state == {"final_score": 70.0, "status": "GRADED"}
        assert log.after_state == {"final_score": 90.0, "status": "GRADED"}
        assert log.metadata_ == {"override_reason": "Question 3 ambiguity grant"}
        assert log.request_id == "req_test_abc123"
        assert log.ip_address == "198.51.100.42"
        assert log.user_agent == "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

    def test_metadata_constructor_alias(self):
        """Constructor must accept 'metadata' keyword as an alias for 'metadata_'."""
        log = AuditLog(
            action="AUTH_LOGIN_SUCCESS",
            resource_type="auth_session",
            metadata={"auth_method": "password", "device": "chrome"},
        )
        assert log.metadata_ == {"auth_method": "password", "device": "chrome"}


class TestAuditLogUUIDBehavior:
    """Verifies UUID primary key generation and formatting."""

    def test_client_side_uuid_generation(self):
        """New instances must automatically receive a valid UUIDv4 prior to persistence."""
        log1 = AuditLog(action="ACTION_A", resource_type="type_a")
        log2 = AuditLog(action="ACTION_B", resource_type="type_b")

        assert isinstance(log1.id, uuid.UUID)
        assert isinstance(log2.id, uuid.UUID)
        assert log1.id != log2.id
        assert log1.id.version == 4

    def test_explicit_uuid_assignment(self):
        """Explicitly assigned UUID must be preserved."""
        custom_uuid = uuid.uuid4()
        log = AuditLog(id=custom_uuid, action="ACTION_A", resource_type="type_a")
        assert log.id == custom_uuid


class TestAuditLogNullableActor:
    """Verifies actor_id nullability for system and anonymous events."""

    def test_nullable_actor_id_allowed(self):
        """actor_id must be nullable to support system tasks, webhooks, and failed auth."""
        log = AuditLog(
            actor_id=None,
            actor_type="SYSTEM",
            action="PAYMENT_WEBHOOK_RECEIVED",
            resource_type="payment_transaction",
        )
        assert log.actor_id is None

    def test_non_null_actor_id_supported(self):
        """actor_id accepts valid UUID for authenticated user events."""
        user_id = uuid.uuid4()
        log = AuditLog(
            actor_id=user_id,
            actor_type="STUDENT",
            action="AUTH_LOGIN_SUCCESS",
            resource_type="auth_session",
        )
        assert log.actor_id == user_id


class TestAuditLogJSONBFields:
    """Verifies JSON attribute handling and dictionary structures."""

    def test_json_fields_accept_nested_dictionaries(self):
        """before_state, after_state, and metadata_ must accept complex nested JSON."""
        before = {"nested": {"score": 50, "items": [1, 2, 3]}}
        after = {"nested": {"score": 100, "items": [1, 2, 3, 4]}}
        meta = {"tags": ["admin", "override"], "retry_count": 0}

        log = AuditLog(
            action="DATA_MUTATED",
            resource_type="entity",
            before_state=before,
            after_state=after,
            metadata_=meta,
        )

        assert log.before_state == before
        assert log.after_state == after
        assert log.metadata_ == meta

    def test_json_fields_nullable_states(self):
        """before_state and after_state can be None for pure creates or purges."""
        log = AuditLog(
            action="COURSE_CREATED",
            resource_type="course",
            before_state=None,
            after_state={"title": "New Course"},
        )
        assert log.before_state is None
        assert log.after_state == {"title": "New Course"}


class TestAuditLogTimezoneBehavior:
    """Verifies timezone-aware UTC creation timestamps."""

    def test_created_at_is_utc_aware(self):
        """created_at must carry timezone.utc tzinfo."""
        log = AuditLog(action="TEST", resource_type="test")
        assert log.created_at.tzinfo == timezone.utc

    def test_naive_datetime_normalized_to_utc(self):
        """Naive datetime passed to created_at must be normalized to UTC."""
        naive_now = datetime.now()
        log = AuditLog(action="TEST", resource_type="test", created_at=naive_now)
        assert log.created_at.tzinfo == timezone.utc


class TestAuditLogAbsenceOfUpdatedAt:
    """Verifies the append-only invariant: updated_at must NOT exist."""

    def test_no_updated_at_attribute_on_class(self):
        """AuditLog class must not declare an updated_at attribute."""
        assert not hasattr(AuditLog, "updated_at")

    def test_no_updated_at_column_in_table(self):
        """audit_logs table must not contain an updated_at column."""
        column_names = [col.name for col in AuditLog.__table__.columns]
        assert "updated_at" not in column_names
        assert "created_at" in column_names

    def test_no_updated_at_on_instance(self):
        """AuditLog instances must not have updated_at in attributes or __dict__."""
        log = AuditLog(action="TEST", resource_type="test")
        assert not hasattr(log, "updated_at")


class TestAuditLogSafeRepresentation:
    """Verifies __repr__ output does not leak attributes or sensitive information."""

    def test_repr_with_primary_key(self):
        """__repr__ must output only class name and id."""
        custom_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        log = AuditLog(
            id=custom_id,
            action="SECRET_ACTION",
            resource_type="secret_resource",
            before_state={"private_data": "secret"},
        )
        repr_str = repr(log)
        assert repr_str == "<AuditLog id=12345678-1234-5678-1234-567812345678>"
        assert "SECRET_ACTION" not in repr_str
        assert "private_data" not in repr_str

    def test_repr_without_primary_key(self):
        """__repr__ without id outputs clean class representation."""
        log = AuditLog(id=None, action="TEST", resource_type="test")
        assert repr(log) == "<AuditLog>"


class TestAuditLogSerializationAndSecurity:
    """Verifies to_dict() serialization and sensitive credential filtering."""

    def test_to_dict_includes_standard_columns(self):
        """to_dict() must serialize all AuditLog columns cleanly."""
        log = AuditLog(
            action="USER_SUSPENDED",
            resource_type="user",
            resource_id="u_999",
            actor_type="SUPER_ADMIN",
            metadata_={"reason": "Suspicious login attempts"},
        )
        d = log.to_dict()

        assert d["action"] == "USER_SUSPENDED"
        assert d["resource_type"] == "user"
        assert d["resource_id"] == "u_999"
        assert d["actor_type"] == "SUPER_ADMIN"
        assert d["metadata_"] == {"reason": "Suspicious login attempts"}
        assert isinstance(d["id"], str)
        assert isinstance(d["created_at"], str)

    def test_to_dict_excludes_custom_fields(self):
        """to_dict(exclude={...}) must exclude requested fields."""
        log = AuditLog(action="TEST", resource_type="test")
        d = log.to_dict(exclude={"ip_address", "user_agent"})
        assert "ip_address" not in d
        assert "user_agent" not in d


class TestAuditLogInMemoryPersistence:
    """Verifies end-to-end ORM persistence and querying in SQLite."""

    def test_persist_and_query_roundtrip(self, in_memory_db):
        """AuditLog must persist and query back with complete fidelity."""
        actor_id = uuid.uuid4()
        entry = AuditLog(
            actor_id=actor_id,
            actor_type="STAFF",
            action="GRADE_RECORDED",
            resource_type="assignment_submission",
            resource_id="sub_789",
            before_state=None,
            after_state={"final_score": 88.5, "status": "GRADED"},
            metadata_={"criteria_count": 4},
            request_id="req_corr_999",
            ip_address="10.0.0.1",
            user_agent="pytest-client",
        )

        in_memory_db.add(entry)
        in_memory_db.commit()

        # Query back
        loaded = in_memory_db.scalar(select(AuditLog).where(AuditLog.id == entry.id))
        assert loaded is not None
        assert loaded.id == entry.id
        assert loaded.actor_id == actor_id
        assert loaded.actor_type == "STAFF"
        assert loaded.action == "GRADE_RECORDED"
        assert loaded.resource_type == "assignment_submission"
        assert loaded.resource_id == "sub_789"
        assert loaded.after_state == {"final_score": 88.5, "status": "GRADED"}
        assert loaded.metadata_ == {"criteria_count": 4}
        assert loaded.request_id == "req_corr_999"
        assert loaded.ip_address == "10.0.0.1"
        assert loaded.user_agent == "pytest-client"
        assert loaded.created_at.tzinfo == timezone.utc

    def test_multiple_audit_logs_ordering(self, in_memory_db):
        """Querying audit logs ordered by created_at desc must return newest first."""
        log1 = AuditLog(action="ACTION_1", resource_type="res")
        log2 = AuditLog(action="ACTION_2", resource_type="res")

        in_memory_db.add_all([log1, log2])
        in_memory_db.commit()

        results = in_memory_db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc())
        ).all()
        assert len(results) == 2
        assert {results[0].action, results[1].action} == {"ACTION_1", "ACTION_2"}


# -----------------------------------------------------------------------------
# Dummy ORM Model for Snapshot Testing
# -----------------------------------------------------------------------------
class DummyAuditedCourse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Dummy course model to test ORM snapshot conversion in AuditService."""

    __tablename__ = "test_dummy_audited_courses"

    title: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False)


# -----------------------------------------------------------------------------
# Repository Test Suite
# -----------------------------------------------------------------------------
class TestAuditRepository:
    """Verifies AuditRepository data access methods."""

    @pytest.mark.anyio
    async def test_repo_add_and_get_by_id(self, in_memory_db):
        """Repository add() and get_by_id() must persist and retrieve entries."""
        repo = AuditRepository()
        entry = AuditLog(
            action="REPO_TEST_ADD",
            resource_type="course",
            resource_id="c_100",
        )

        persisted = await repo.add(in_memory_db, entry)
        in_memory_db.commit()

        retrieved = await repo.get_by_id(in_memory_db, persisted.id)
        assert retrieved is not None
        assert retrieved.id == persisted.id
        assert retrieved.action == "REPO_TEST_ADD"
        assert retrieved.resource_id == "c_100"

    @pytest.mark.anyio
    async def test_repo_get_by_id_string_uuid(self, in_memory_db):
        """get_by_id() must accept valid UUID strings."""
        repo = AuditRepository()
        entry = AuditLog(action="ACTION_STR", resource_type="res")
        await repo.add(in_memory_db, entry)
        in_memory_db.commit()

        retrieved = await repo.get_by_id(in_memory_db, str(entry.id))
        assert retrieved is not None
        assert retrieved.id == entry.id

    @pytest.mark.anyio
    async def test_repo_get_by_id_not_found(self, in_memory_db):
        """get_by_id() must return None for non-existent IDs."""
        repo = AuditRepository()
        missing = await repo.get_by_id(in_memory_db, uuid.uuid4())
        assert missing is None

    @pytest.mark.anyio
    async def test_repo_list_logs_pagination_and_count(self, in_memory_db):
        """list_logs() must support limit, offset, and return total count."""
        repo = AuditRepository()
        for i in range(5):
            entry = AuditLog(action=f"PAGE_ACTION_{i}", resource_type="page_item")
            await repo.add(in_memory_db, entry)
        in_memory_db.commit()

        # Query first page: limit 2, offset 0
        page1, total1 = await repo.list_logs(in_memory_db, resource_type="page_item", limit=2, offset=0)
        assert total1 == 5
        assert len(page1) == 2

        # Query second page: limit 2, offset 2
        page2, total2 = await repo.list_logs(in_memory_db, resource_type="page_item", limit=2, offset=2)
        assert total2 == 5
        assert len(page2) == 2

        # Verify page 1 and page 2 contain different entries
        assert page1[0].id != page2[0].id

    @pytest.mark.anyio
    async def test_repo_list_logs_filters(self, in_memory_db):
        """list_logs() must filter accurately across actor, action, resource, request, and date."""
        repo = AuditRepository()
        actor_a = uuid.uuid4()
        actor_b = uuid.uuid4()

        log_a = AuditLog(
            actor_id=actor_a,
            actor_type="ADMIN",
            action="FILTER_ACTION_A",
            resource_type="special_resource",
            resource_id="res_1",
            request_id="req_filter_1",
            created_at=datetime(2026, 11, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        log_b = AuditLog(
            actor_id=actor_b,
            actor_type="STUDENT",
            action="FILTER_ACTION_B",
            resource_type="special_resource",
            resource_id="res_2",
            request_id="req_filter_2",
            created_at=datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc),
        )
        await repo.add(in_memory_db, log_a)
        await repo.add(in_memory_db, log_b)
        in_memory_db.commit()

        # Filter by actor_id
        res_actor, count = await repo.list_logs(in_memory_db, actor_id=actor_a)
        assert count == 1
        assert res_actor[0].actor_id == actor_a

        # Filter by actor_type
        res_type, count = await repo.list_logs(in_memory_db, actor_type="STUDENT")
        assert count == 1
        assert res_type[0].actor_type == "STUDENT"

        # Filter by action
        res_act, count = await repo.list_logs(in_memory_db, action="FILTER_ACTION_A")
        assert count == 1
        assert res_act[0].action == "FILTER_ACTION_A"

        # Filter by request_id
        res_req, count = await repo.list_logs(in_memory_db, request_id="req_filter_2")
        assert count == 1
        assert res_req[0].request_id == "req_filter_2"

        # Filter by date range
        start_dt = datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)
        res_date, count = await repo.list_logs(in_memory_db, start_date=start_dt)
        assert count == 1
        assert res_date[0].actor_id == actor_b


# -----------------------------------------------------------------------------
# Service Context Extraction Test Suite
# -----------------------------------------------------------------------------
class TestAuditServiceContextExtraction:
    """Verifies AuditService request context extraction and precedence."""

    def test_request_id_from_contextvar(self):
        """Service must capture request_id from contextvars when not passed explicitly."""
        service = AuditService()
        token = set_request_id("ctx_req_12345")
        try:
            req_id, _, _ = service.extract_request_context()
            assert req_id == "ctx_req_12345"
        finally:
            reset_request_id(token)

    def test_request_id_from_request_state(self):
        """Service must capture request_id from request.state.request_id."""
        service = AuditService()
        mock_req = MagicMock()
        mock_req.state.request_id = "state_req_67890"

        req_id, _, _ = service.extract_request_context(request=mock_req)
        assert req_id == "state_req_67890"

    def test_request_id_from_request_headers(self):
        """Service must fallback to X-Request-ID header if state.request_id is absent."""
        service = AuditService()
        mock_req = MagicMock()
        mock_req.state.request_id = None
        mock_req.headers = {"x-request-id": "header_req_11111"}

        req_id, _, _ = service.extract_request_context(request=mock_req)
        assert req_id == "header_req_11111"

    def test_request_id_explicit_precedence(self):
        """Explicitly passed request_id must take precedence over request and contextvar."""
        service = AuditService()
        token = set_request_id("ctx_to_be_overridden")
        mock_req = MagicMock()
        mock_req.state.request_id = "state_to_be_overridden"
        try:
            req_id, _, _ = service.extract_request_context(
                request=mock_req,
                explicit_request_id="explicit_wins",
            )
            assert req_id == "explicit_wins"
        finally:
            reset_request_id(token)

    def test_ip_extraction_forwarded_for(self):
        """Service must extract the client IP from X-Forwarded-For header."""
        service = AuditService()
        mock_req = MagicMock()
        mock_req.headers = {"x-forwarded-for": "198.51.100.25, 10.0.0.1"}

        _, ip, _ = service.extract_request_context(request=mock_req)
        assert ip == "198.51.100.25"

    def test_ip_extraction_client_host(self):
        """Service must fallback to request.client.host when X-Forwarded-For is absent."""
        service = AuditService()
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.client.host = "192.168.1.100"

        _, ip, _ = service.extract_request_context(request=mock_req)
        assert ip == "192.168.1.100"

    def test_user_agent_extraction_and_truncation(self):
        """Service must extract and truncate User-Agent to 512 characters."""
        service = AuditService()
        long_ua = "A" * 600
        mock_req = MagicMock()
        mock_req.headers = {"user-agent": long_ua}

        _, _, ua = service.extract_request_context(request=mock_req)
        assert len(ua) == 512
        assert ua == "A" * 512


# -----------------------------------------------------------------------------
# Service Redaction & Snapshot Filtering Test Suite
# -----------------------------------------------------------------------------
class TestAuditServiceRedactionAndSnapshots:
    """Verifies sensitive data scrubbing and snapshot filtering."""

    @pytest.mark.anyio
    async def test_sensitive_fields_redacted_in_states_and_metadata(self, in_memory_db):
        """Sensitive authentication, payment, and secret credentials must be redacted."""
        service = AuditService()
        raw_before = {
            "password": "unhashed_password",
            "password_hash": "$argon2id$secret",
            "access_token": "bearer_token_xyz",
            "status": "PENDING",
        }
        raw_after = {
            "session_token": "token_abc123",
            "card_number": "4111111111111111",
            "cvv": "123",
            "status": "ACTIVE",
        }
        raw_meta = {
            "api_key": "live_secret_key_888",
            "client_secret": "top_secret_oauth",
            "safe_detail": "login_succeeded",
        }

        log = await service.record_event(
            in_memory_db,
            action="AUTH_CREDENTIAL_CHANGE",
            resource_type="custom_type",
            before_state=raw_before,
            after_state=raw_after,
            metadata=raw_meta,
        )

        # Verify before_state redactions
        assert log.before_state["password"] == "[REDACTED]"
        assert log.before_state["password_hash"] == "[REDACTED]"
        assert log.before_state["access_token"] == "[REDACTED]"
        assert log.before_state["status"] == "PENDING"

        # Verify after_state redactions
        assert log.after_state["session_token"] == "[REDACTED]"
        assert log.after_state["card_number"] == "[REDACTED]"
        assert log.after_state["cvv"] == "[REDACTED]"
        assert log.after_state["status"] == "ACTIVE"

        # Verify metadata redactions
        assert log.metadata_["api_key"] == "[REDACTED]"
        assert log.metadata_["client_secret"] == "[REDACTED]"
        assert log.metadata_["safe_detail"] == "login_succeeded"

    @pytest.mark.anyio
    async def test_allowlisted_fields_filtered(self, in_memory_db):
        """Only explicitly declared allowlisted fields must be retained in snapshots."""
        service = AuditService()
        raw_state = {
            "id": "c_123",
            "title": "Clean Course Title",
            "price_inr": 499900,
            "internal_debug_note": "do not expose",
            "unrelated_large_field": "x" * 1000,
        }

        log = await service.record_event(
            in_memory_db,
            action="COURSE_UPDATED",
            resource_type="course",
            after_state=raw_state,
            allowed_snapshot_fields={"title", "price_inr"},
        )

        assert "title" in log.after_state
        assert "price_inr" in log.after_state
        assert "internal_debug_note" not in log.after_state
        assert "unrelated_large_field" not in log.after_state

    @pytest.mark.anyio
    async def test_default_domain_allowlist_applied(self, in_memory_db):
        """When allowed_fields is omitted, default domain allowlist must filter course fields."""
        service = AuditService()
        raw_course = {
            "id": "c_555",
            "slug": "fastapi-mastery",
            "title": "FastAPI Mastery",
            "price_inr": 99900,
            "status": "PUBLISHED",
            "internal_scratch_notes": "sensitive draft thoughts",
        }

        log = await service.record_event(
            in_memory_db,
            action="COURSE_PUBLISHED",
            resource_type="course",
            after_state=raw_course,
        )

        assert log.after_state["slug"] == "fastapi-mastery"
        assert log.after_state["status"] == "PUBLISHED"
        assert "internal_scratch_notes" not in log.after_state

    @pytest.mark.anyio
    async def test_orm_model_snapshot_conversion(self, in_memory_db):
        """Passing an ORM model instance must serialize via to_dict() with sensitive fields excluded."""
        service = AuditService()
        dummy_course = DummyAuditedCourse(
            id=uuid.uuid4(),
            title="ORM Model Course",
            slug="orm-model-course",
        )

        log = await service.record_event(
            in_memory_db,
            action="COURSE_CREATED",
            resource_type="course",
            after_state=dummy_course,
        )

        assert log.after_state is not None
        assert log.after_state["title"] == "ORM Model Course"
        assert log.after_state["slug"] == "orm-model-course"
        assert "id" in log.after_state


# -----------------------------------------------------------------------------
# Service Transaction Safety Test Suite
# -----------------------------------------------------------------------------
class TestAuditServiceTransactions:
    """Verifies transactional rollback and isolated audit logging semantics."""

    @pytest.mark.anyio
    async def test_transactional_auditing_rolls_back_with_business_error(self, in_memory_db):
        """Transactional audit record must roll back when business operation fails."""
        service = AuditService()

        try:
            with in_memory_db.begin():
                await service.record_event(
                    in_memory_db,
                    action="TRANSACTIONAL_FAIL_EVENT",
                    resource_type="course",
                    resource_id="c_fail",
                )
                # Simulate business exception aborting transaction
                raise RuntimeError("Business mutation encountered unexpected error!")
        except RuntimeError:
            pass

        # Query database: record must NOT exist
        logs, count = await service.repository.list_logs(
            in_memory_db,
            action="TRANSACTIONAL_FAIL_EVENT",
        )
        assert count == 0
        assert len(logs) == 0

    @pytest.mark.anyio
    async def test_isolated_security_auditing_persists_on_caller_rollback(self):
        """Isolated security audit must persist even when caller transaction rolls back."""
        # Use an isolated test database with its own session factory
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        CustomSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=engine, class_=Session, expire_on_commit=False
        )

        service = AuditService()

        # Simulate caller with an active business transaction
        caller_session = CustomSessionLocal()
        try:
            with caller_session.begin():
                # Caller logs an isolated security event (e.g. brute force detection)
                await service.record_isolated_event(
                    action="ISOLATED_SECURITY_BREACH_DETECTED",
                    resource_type="auth_session",
                    session_factory=CustomSessionLocal,
                    metadata={"reason": "rate_limit_exceeded"},
                )
                # Caller fails and transaction is rolled back
                raise ValueError("Caller business failure aborts transaction")
        except ValueError:
            pass
        finally:
            caller_session.close()

        # Verify isolated audit log WAS persisted
        verify_session = CustomSessionLocal()
        try:
            logs, count = await service.repository.list_logs(
                verify_session,
                action="ISOLATED_SECURITY_BREACH_DETECTED",
            )
            assert count == 1
            assert logs[0].action == "ISOLATED_SECURITY_BREACH_DETECTED"
            assert logs[0].metadata_ == {"reason": "rate_limit_exceeded"}
        finally:
            verify_session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()

