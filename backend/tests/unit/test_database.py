"""Unit and integration tests for SQLAlchemy 2.0 database engine, pooling, and session lifecycle.

Verifies:
1. Engine creation with configurable QueuePool connection pooling.
2. Dialect-specific engine options (PostgreSQL QueuePool vs SQLite StaticPool).
3. SessionLocal sessionmaker configuration (autocommit, autoflush, expire_on_commit).
4. get_db generator lifecycle: session yield, exception rollback, and deterministic close.
5. Database connectivity health-check pings (check_db_connectivity, ping_db).
6. Engine disposal and connection pool cleanup.
7. Reset database engine utility for isolated test environments.
8. Async engine and sessionmaker factories.
9. End-to-end transactional persistence and rollback integration.
"""

from collections.abc import Generator
from unittest.mock import MagicMock
import uuid

import pytest
from sqlalchemy import Engine, Integer, String, create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import Settings
from app.core.database import (
    check_db_connectivity,
    create_async_db_engine,
    create_async_session_factory,
    create_db_engine,
    create_session_factory,
    dispose_async_engine,
    dispose_engine,
    get_db,
    ping_db,
    reset_database_engine,
)
import app.core.database as db_module
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# -----------------------------------------------------------------------------
# Test Model for Database Integration
# -----------------------------------------------------------------------------
class DummyRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Test model for verifying transaction commits and rollbacks."""

    __tablename__ = "test_dummy_records"

    content: Mapped[str] = mapped_column(String(100), nullable=False)
    counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# -----------------------------------------------------------------------------
# Test Suites
# -----------------------------------------------------------------------------
class TestEngineConfiguration:
    """Verifies engine creation and connection pool options."""

    def test_default_engine_pool_parameters(self):
        """PostgreSQL engine must configure QueuePool with settings values."""
        custom_settings = Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/test_db",
            DB_POOL_SIZE=15,
            DB_MAX_OVERFLOW=5,
            DB_POOL_TIMEOUT=20,
            DB_POOL_PRE_PING=True,
            DB_ECHO=False,
        )
        engine = create_db_engine(settings=custom_settings)

        assert isinstance(engine, Engine)
        assert engine.pool.size() == 15
        assert engine.pool._max_overflow == 5
        assert engine.pool._timeout == 20
        assert engine.pool._pre_ping is True
        assert engine.echo is False
        dispose_engine(engine)

    def test_sqlite_in_memory_uses_static_pool(self):
        """SQLite in-memory URL must use StaticPool and omit QueuePool options."""
        custom_settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            DB_POOL_SIZE=20,
            DB_MAX_OVERFLOW=10,
        )
        engine = create_db_engine(settings=custom_settings)

        assert isinstance(engine, Engine)
        assert isinstance(engine.pool, StaticPool)
        dispose_engine(engine)

    def test_custom_database_url_override(self):
        """Passing an explicit database_url must override settings.DATABASE_URL."""
        custom_settings = Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/ignored_db",
        )
        engine = create_db_engine(
            settings=custom_settings,
            database_url="sqlite:///:memory:",
        )
        assert "sqlite" in str(engine.url)
        dispose_engine(engine)

    def test_custom_engine_kwargs_pass_through(self):
        """Arbitrary kwargs must pass directly to create_engine."""
        engine = create_db_engine(
            database_url="sqlite:///:memory:",
            echo=True,
        )
        assert engine.echo is True
        dispose_engine(engine)

    def test_create_db_engine_positional_url_handling(self):
        """Passing a URL string as the first positional parameter must succeed."""
        engine = create_db_engine("sqlite:///:memory:")
        assert isinstance(engine, Engine)
        assert "sqlite" in str(engine.url)
        dispose_engine(engine)

    def test_create_async_db_engine_positional_url_handling(self):
        """Passing an async URL string as the first positional parameter must succeed."""
        async_eng = create_async_db_engine("postgresql+psycopg://user:pass@localhost:5432/test_pos")
        assert isinstance(async_eng, AsyncEngine)


class TestSessionFactory:
    """Verifies session factory creation and configuration flags."""

    def test_session_factory_configuration(self):
        """sessionmaker must enforce autocommit=False, autoflush=False, expire_on_commit=False."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine_instance=engine)

        assert isinstance(factory, sessionmaker)
        assert factory.kw.get("autocommit") is False
        assert factory.kw.get("autoflush") is False
        assert factory.kw.get("expire_on_commit") is False

        session = factory()
        assert isinstance(session, Session)
        session.close()
        engine.dispose()


class TestSessionLifecycle:
    """Verifies get_db session acquisition, rollback, and deterministic close."""

    def test_get_db_yields_active_session(self, monkeypatch):
        """get_db must yield an active database session and close it afterwards."""
        test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        test_session_factory = create_session_factory(test_engine)

        monkeypatch.setattr(db_module, "SessionLocal", test_session_factory)

        generator = get_db()
        session = next(generator)

        assert isinstance(session, Session)
        session.execute(text("SELECT 1"))
        assert session.in_transaction()

        close_called = False
        original_close = session.close

        def tracked_close():
            nonlocal close_called
            close_called = True
            original_close()

        session.close = tracked_close

        # Closing generator triggers finally block
        with pytest.raises(StopIteration):
            generator.send(None)

        assert close_called is True
        assert not session.in_transaction()
        test_engine.dispose()

    def test_get_db_rollback_on_exception(self, monkeypatch):
        """get_db must call db.rollback() and db.close() when an exception occurs."""
        mock_session = MagicMock(spec=Session)
        mock_factory = MagicMock(return_value=mock_session)

        monkeypatch.setattr(db_module, "SessionLocal", mock_factory)

        generator = get_db()
        session = next(generator)
        assert session is mock_session

        # Simulate exception raised within the route context
        test_exception = RuntimeError("Simulated service error")
        with pytest.raises(RuntimeError, match="Simulated service error"):
            generator.throw(test_exception)

        # Assert rollback and close were both invoked
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    def test_get_db_handles_base_exception_and_exit(self, monkeypatch):
        """get_db must roll back and close even on BaseException / GeneratorExit."""
        mock_session = MagicMock(spec=Session)
        mock_factory = MagicMock(return_value=mock_session)

        monkeypatch.setattr(db_module, "SessionLocal", mock_factory)

        generator = get_db()
        session = next(generator)
        assert session is mock_session

        # Simulate GeneratorExit (triggered during early stream termination or client disconnect)
        with pytest.raises(GeneratorExit):
            generator.throw(GeneratorExit)

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestConnectivityChecks:
    """Verifies check_db_connectivity and ping_db functionality."""

    def test_check_db_connectivity_success(self):
        """check_db_connectivity must return True when connection is healthy."""
        test_engine = create_engine("sqlite:///:memory:")
        result = check_db_connectivity(target_engine=test_engine)
        assert result is True
        test_engine.dispose()

    def test_check_db_connectivity_failure(self):
        """check_db_connectivity must catch errors and return False for unreachable DB."""
        # Unreachable host:port
        unreachable_engine = create_engine(
            "postgresql+psycopg://invalid:invalid@127.0.0.1:54329/nonexistent",
        )
        result = check_db_connectivity(target_engine=unreachable_engine)
        assert result is False
        dispose_engine(unreachable_engine)

    def test_ping_db_success(self):
        """ping_db must succeed silently when connection is healthy."""
        test_engine = create_engine("sqlite:///:memory:")
        ping_db(target_engine=test_engine)
        test_engine.dispose()

    def test_ping_db_failure_raises(self):
        """ping_db must raise SQLAlchemyError when connection is broken."""
        unreachable_engine = create_engine(
            "postgresql+psycopg://invalid:invalid@127.0.0.1:54329/nonexistent",
        )
        with pytest.raises(SQLAlchemyError):
            ping_db(target_engine=unreachable_engine)
        dispose_engine(unreachable_engine)


class TestEngineDisposal:
    """Verifies connection pool disposal."""

    def test_dispose_engine(self):
        """dispose_engine must clear checked-in connections cleanly."""
        test_engine = create_engine("sqlite:///:memory:")
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # Verify pool disposal executes without error
        dispose_engine(target_engine=test_engine)

    def test_dispose_engine_default(self):
        """dispose_engine without arguments must dispose module default engine."""
        dispose_engine()


class TestResetDatabaseEngine:
    """Verifies module-level engine re-initialization utility."""

    def test_reset_engine_updates_singletons(self):
        """reset_database_engine must reassign engine and SessionLocal."""
        orig_engine = db_module.engine
        orig_factory = db_module.SessionLocal

        new_eng, new_factory = reset_database_engine(
            new_database_url="sqlite:///:memory:",
        )

        assert db_module.engine is new_eng
        assert db_module.SessionLocal is new_factory
        assert "sqlite" in str(db_module.engine.url)

        # Restore default engine
        reset_database_engine()
        assert "postgresql" in str(db_module.engine.url)


class TestAsyncDatabaseComponents:
    """Verifies async engine and async sessionmaker construction."""

    def test_create_async_db_engine(self):
        """create_async_db_engine must construct an AsyncEngine instance."""
        async_eng = create_async_db_engine(
            database_url="postgresql+psycopg://user:pass@localhost:5432/test_async",
        )
        assert isinstance(async_eng, AsyncEngine)

    def test_create_async_session_factory(self):
        """create_async_session_factory must return an async_sessionmaker."""
        async_eng = create_async_db_engine(
            database_url="postgresql+psycopg://user:pass@localhost:5432/test_async",
        )
        factory = create_async_session_factory(async_engine_instance=async_eng)
        assert isinstance(factory, async_sessionmaker)
        assert factory.kw.get("expire_on_commit") is False

    @pytest.mark.asyncio
    async def test_dispose_async_engine(self):
        """dispose_async_engine must cleanly dispose async pool."""
        async_eng = create_async_db_engine(
            database_url="postgresql+psycopg://user:pass@localhost:5432/test_async",
        )
        await dispose_async_engine(target_async_engine=async_eng)

    @pytest.mark.asyncio
    async def test_get_async_db_uninitialized_raises(self, monkeypatch):
        """get_async_db must raise RuntimeError if AsyncSessionLocal is None."""
        from app.core.database import get_async_db

        monkeypatch.setattr(db_module, "AsyncSessionLocal", None)
        gen = get_async_db()
        with pytest.raises(RuntimeError, match="AsyncSessionLocal is not initialized"):
            await anext(gen)

    @pytest.mark.asyncio
    async def test_get_async_db_lifecycle_and_rollback(self, monkeypatch):
        """get_async_db must yield session and invoke rollback on async exception."""
        from unittest.mock import AsyncMock
        from app.core.database import get_async_db

        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_session
        mock_context_manager.__aexit__.return_value = None
        mock_factory = MagicMock(return_value=mock_context_manager)

        monkeypatch.setattr(db_module, "AsyncSessionLocal", mock_factory)

        gen = get_async_db()
        session = await anext(gen)
        assert session is mock_session

        # Throw error into async generator
        with pytest.raises(ValueError, match="Simulated async failure"):
            await gen.athrow(ValueError("Simulated async failure"))

        mock_session.rollback.assert_awaited_once()
        mock_context_manager.__aexit__.assert_awaited_once()


class TestDatabaseTransactionIntegration:
    """Integration test verifying transactional persistence, commit, and rollback via get_db."""

    def test_transactional_commit_and_query(self, monkeypatch):
        """Verify committing through get_db persists data into the database."""
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(test_engine)
        test_factory = create_session_factory(test_engine)
        monkeypatch.setattr(db_module, "SessionLocal", test_factory)

        # 1. Insert via get_db dependency
        gen1 = get_db()
        db1 = next(gen1)
        record = DummyRecord(content="Persisted Data", counter=42)
        db1.add(record)
        db1.commit()
        assigned_id = record.id
        try:
            gen1.send(None)
        except StopIteration:
            pass

        # 2. Query in fresh session via get_db dependency
        gen2 = get_db()
        db2 = next(gen2)
        loaded = db2.scalar(select(DummyRecord).where(DummyRecord.id == assigned_id))
        assert loaded is not None
        assert loaded.content == "Persisted Data"
        assert loaded.counter == 42
        assert isinstance(loaded.id, uuid.UUID)
        try:
            gen2.send(None)
        except StopIteration:
            pass

        Base.metadata.drop_all(test_engine)
        test_engine.dispose()

    def test_transactional_rollback_on_failure(self, monkeypatch):
        """Verify uncommitted data is discarded on route failure during get_db."""
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(test_engine)
        test_factory = create_session_factory(test_engine)
        monkeypatch.setattr(db_module, "SessionLocal", test_factory)

        # 1. Attempt insert that fails midway
        gen1 = get_db()
        db1 = next(gen1)
        failed_record = DummyRecord(content="Failed Data", counter=999)
        db1.add(failed_record)
        db1.flush()  # Flushed to transaction, but not committed
        failed_id = failed_record.id

        # Simulate exception during request processing
        with pytest.raises(ValueError, match="Request error before commit"):
            gen1.throw(ValueError("Request error before commit"))

        # 2. Query in fresh session — must NOT exist due to rollback
        gen2 = get_db()
        db2 = next(gen2)
        found = db2.scalar(select(DummyRecord).where(DummyRecord.id == failed_id))
        assert found is None
        try:
            gen2.send(None)
        except StopIteration:
            pass

        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
