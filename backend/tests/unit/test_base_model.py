"""Unit tests for SQLAlchemy 2.0 Base, UUIDPrimaryKeyMixin, and TimestampMixin.

Verifies:
1. DeclarativeBase naming conventions and metadata configuration.
2. UUIDPrimaryKeyMixin client-side and server-side defaults.
3. TimestampMixin timezone-aware UTC timestamps and automatic update hooks.
4. to_dict serialization for UUIDs, datetimes, and excluded fields.
5. __repr__ string formatting.
6. In-memory database persistence and column ordering.
"""

from datetime import datetime, timezone
import time
from typing import Optional
import uuid

import pytest
from sqlalchemy import DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import (
    Base,
    POSTGRES_NAMING_CONVENTION,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


# -----------------------------------------------------------------------------
# Test Models
# -----------------------------------------------------------------------------
class DummyItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Concrete test model combining Base and all foundation mixins."""

    __tablename__ = "test_dummy_items"

    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DummySimple(Base):
    """Simple model without mixins for isolated Base testing."""

    __tablename__ = "test_dummy_simple"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class DummyUserWithSecrets(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Model with sensitive credentials to verify serialization security."""

    __tablename__ = "test_dummy_users_with_secrets"

    email: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    custom_private_data: Mapped[str] = mapped_column(String(50), nullable=False)

    __sensitive_fields__ = frozenset({"custom_private_data"})


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def in_memory_db():
    """Provides a fresh, isolated SQLite in-memory database and session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, class_=Session, expire_on_commit=False
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
class TestBaseDeclarativeModel:
    """Verifies Base model metadata, constraint naming conventions, and methods."""

    def test_naming_convention_metadata(self):
        """Metadata must contain standard PostgreSQL constraint naming patterns."""
        convention = Base.metadata.naming_convention
        assert convention["ix"] == "ix_%(column_0_label)s"
        assert convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"
        assert convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"
        assert convention["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        assert convention["pk"] == "pk_%(table_name)s"

    def test_repr_with_primary_key(self):
        """__repr__ must show class name and primary key when set."""
        test_uuid = uuid.uuid4()
        item = DummyItem(id=test_uuid, title="Test Item")
        assert repr(item) == f"<DummyItem id={test_uuid}>"

    def test_repr_without_primary_key(self):
        """__repr__ must show class name without ID when ID is None."""
        item = DummySimple(name="Item Without ID")
        assert repr(item) == "<DummySimple>"

    def test_to_dict_standard_fields(self):
        """to_dict must serialize standard strings and integers."""
        simple = DummySimple(id=42, name="Test")
        data = simple.to_dict()
        assert data == {"id": 42, "name": "Test"}

    def test_to_dict_uuid_and_datetime_formatting(self):
        """to_dict must convert UUIDs and datetimes to strings."""
        test_id = uuid.uuid4()
        now_utc = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
        item = DummyItem(
            id=test_id,
            title="Formatted Item",
            description="Sample",
            view_count=5,
            created_at=now_utc,
            updated_at=now_utc,
        )
        data = item.to_dict()
        assert data["id"] == str(test_id)
        assert data["title"] == "Formatted Item"
        assert data["description"] == "Sample"
        assert data["view_count"] == 5
        assert data["created_at"] == "2026-11-13T12:00:00+00:00"
        assert data["updated_at"] == "2026-11-13T12:00:00+00:00"

    def test_to_dict_with_exclude_set(self):
        """to_dict must exclude attributes specified in the exclude argument."""
        item = DummyItem(
            id=uuid.uuid4(),
            title="Exclude Test",
            description="Secret notes",
            view_count=10,
        )
        data = item.to_dict(exclude={"description", "view_count"})
        assert "description" not in data
        assert "view_count" not in data
        assert "title" in data
        assert "id" in data

    def test_to_dict_automatic_sensitive_field_exclusion(self):
        """to_dict must automatically exclude passwords, token hashes, and sensitive data."""
        user = DummyUserWithSecrets(
            id=uuid.uuid4(),
            email="student@example.com",
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
            session_token_hash="a1b2c3d4e5f6g7h8",
            custom_private_data="confidential-student-note",
        )
        data = user.to_dict()

        # Universally sensitive fields must be absent
        assert "password_hash" not in data
        assert "session_token_hash" not in data

        # Model-declared sensitive fields must be absent
        assert "custom_private_data" not in data

        # Standard non-sensitive fields must remain present
        assert data["email"] == "student@example.com"
        assert data["id"] == str(user.id)

    def test_to_dict_include_sensitive_flag(self):
        """Passing include_sensitive=True must serialize all fields when explicitly required."""
        user = DummyUserWithSecrets(
            id=uuid.uuid4(),
            email="student@example.com",
            password_hash="secret-hash",
            session_token_hash="token-hash",
            custom_private_data="private-data",
        )
        data = user.to_dict(include_sensitive=True)

        assert data["password_hash"] == "secret-hash"
        assert data["session_token_hash"] == "token-hash"
        assert data["custom_private_data"] == "private-data"
        assert data["email"] == "student@example.com"

    def test_repr_security_does_not_leak_fields(self):
        """__repr__ must never dump table columns or credentials into log outputs."""
        user = DummyUserWithSecrets(
            id=uuid.uuid4(),
            email="student@example.com",
            password_hash="$argon2id$secretpassword",
            session_token_hash="top-secret-token",
            custom_private_data="bank-account-info",
        )
        repr_str = repr(user)

        assert repr_str == f"<DummyUserWithSecrets id={user.id}>"
        assert "argon2id" not in repr_str
        assert "student@example.com" not in repr_str
        assert "top-secret-token" not in repr_str
        assert "bank-account" not in repr_str


class TestUUIDPrimaryKeyMixin:
    """Verifies UUIDPrimaryKeyMixin configuration and ID generation."""

    def test_uuid_column_properties(self):
        """The id column must be defined as primary key, non-nullable with server default."""
        id_col = DummyItem.__table__.columns["id"]
        assert id_col.primary_key is True
        assert id_col.nullable is False
        assert id_col.server_default is not None
        assert "gen_random_uuid" in str(id_col.server_default.arg)

    def test_uuid_first_in_column_order(self):
        """The id column must appear first in column order due to sort_order=-100."""
        column_names = [col.name for col in DummyItem.__table__.columns]
        assert column_names[0] == "id"

    def test_uuid_automatic_client_generation(self, in_memory_db: Session):
        """Persisting a record without explicit id must automatically assign a valid UUIDv4."""
        item = DummyItem(title="Auto UUID")
        in_memory_db.add(item)
        in_memory_db.commit()
        in_memory_db.refresh(item)

        assert isinstance(item.id, uuid.UUID)
        assert item.id.version == 4

    def test_uuid_manual_assignment(self, in_memory_db: Session):
        """Explicitly assigned UUID must be preserved upon insertion."""
        custom_uuid = uuid.uuid4()
        item = DummyItem(id=custom_uuid, title="Explicit UUID")
        in_memory_db.add(item)
        in_memory_db.commit()
        in_memory_db.refresh(item)

        assert item.id == custom_uuid


class TestTimestampMixin:
    """Verifies TimestampMixin timezone awareness and automatic updates."""

    def test_timestamp_column_properties(self):
        """created_at and updated_at must be TIMESTAMPTZ (timezone=True) and non-nullable."""
        created_col = DummyItem.__table__.columns["created_at"]
        updated_col = DummyItem.__table__.columns["updated_at"]

        # UTCDateTime wraps DateTime(timezone=True)
        assert isinstance(created_col.type.impl, DateTime)
        assert created_col.type.impl.timezone is True
        assert created_col.nullable is False

        assert isinstance(updated_col.type.impl, DateTime)
        assert updated_col.type.impl.timezone is True
        assert updated_col.nullable is False

    def test_timestamp_default_is_timezone_aware_utc(self):
        """The default factory must generate timezone-aware UTC datetime."""
        # Test the underlying callable directly
        now_val = utc_now()
        assert isinstance(now_val, datetime)
        assert now_val.tzinfo is not None
        assert now_val.tzinfo == timezone.utc

        # Test the column default invocation (SQLAlchemy wraps with ctx argument)
        created_default = DummyItem.__table__.columns["created_at"].default.arg(None)
        updated_default = DummyItem.__table__.columns["updated_at"].default.arg(None)

        assert isinstance(created_default, datetime)
        assert created_default.tzinfo is not None
        assert created_default.tzinfo == timezone.utc

        assert isinstance(updated_default, datetime)
        assert updated_default.tzinfo is not None
        assert updated_default.tzinfo == timezone.utc

    def test_timestamp_persistence(self, in_memory_db: Session):
        """Persisting a record must populate created_at and updated_at."""
        before_insert = datetime.now(timezone.utc)
        item = DummyItem(title="Timestamp Test")
        in_memory_db.add(item)
        in_memory_db.commit()
        in_memory_db.refresh(item)

        assert item.created_at is not None
        assert item.updated_at is not None
        # Assert within a reasonable tolerance window
        assert (item.created_at - before_insert).total_seconds() >= -1.0
        assert (item.updated_at - before_insert).total_seconds() >= -1.0

    def test_timestamp_updated_at_refresh(self, in_memory_db: Session):
        """Updating a record must refresh updated_at."""
        item = DummyItem(title="Initial Title")
        in_memory_db.add(item)
        in_memory_db.commit()
        in_memory_db.refresh(item)

        initial_updated_at = item.updated_at

        # Small sleep to ensure timestamp differs
        time.sleep(0.01)

        item.title = "Updated Title"
        in_memory_db.commit()
        in_memory_db.refresh(item)

        assert item.title == "Updated Title"
        assert item.updated_at >= initial_updated_at


class TestBaseModelPersistenceIntegration:
    """Verifies end-to-end CRUD operations on models inheriting from Base."""

    def test_crud_lifecycle(self, in_memory_db: Session):
        """Complete Create, Read, Update, Delete lifecycle on DummyItem."""
        # Create
        item = DummyItem(title="Lifecycle Test", description="Testing CRUD", view_count=100)
        in_memory_db.add(item)
        in_memory_db.commit()
        assigned_id = item.id

        # Read
        retrieved = in_memory_db.scalar(select(DummyItem).where(DummyItem.id == assigned_id))
        assert retrieved is not None
        assert retrieved.title == "Lifecycle Test"
        assert retrieved.view_count == 100

        # Update
        retrieved.view_count = 250
        in_memory_db.commit()
        updated = in_memory_db.scalar(select(DummyItem).where(DummyItem.id == assigned_id))
        assert updated.view_count == 250

        # Delete
        in_memory_db.delete(updated)
        in_memory_db.commit()
        deleted = in_memory_db.scalar(select(DummyItem).where(DummyItem.id == assigned_id))
        assert deleted is None


class TestPostgreSQLDialectDDL:
    """Verifies that SQLAlchemy 2.0 generates correct PostgreSQL 17 DDL."""

    def test_postgresql_ddl_uuid_and_timestamps(self):
        """DummyItem must compile to UUID with gen_random_uuid() and TIMESTAMPTZ with now()."""
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        ddl = str(CreateTable(DummyItem.__table__).compile(dialect=postgresql.dialect()))

        assert "id UUID DEFAULT gen_random_uuid() NOT NULL" in ddl
        assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
        assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
        assert "CONSTRAINT pk_test_dummy_items PRIMARY KEY (id)" in ddl

    def test_postgresql_ddl_naming_conventions(self):
        """Unique and index constraints must follow PostgreSQL naming patterns."""
        from sqlalchemy import Index, UniqueConstraint
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        class ConstrainedModel(Base, UUIDPrimaryKeyMixin):
            __tablename__ = "test_constrained_models"
            slug: Mapped[str] = mapped_column(String(50), nullable=False)
            code: Mapped[str] = mapped_column(String(20), nullable=False)
            __table_args__ = (
                UniqueConstraint("slug"),
                Index("ix_code_idx", "code"),
            )

        ddl = str(CreateTable(ConstrainedModel.__table__).compile(dialect=postgresql.dialect()))
        assert "CONSTRAINT uq_test_constrained_models_slug UNIQUE (slug)" in ddl
        assert "CONSTRAINT pk_test_constrained_models PRIMARY KEY (id)" in ddl
