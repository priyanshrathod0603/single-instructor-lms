"""Database engine configuration, connection pooling, and session lifecycle management.

Follows the database architecture specification in docs/backend/04-DATABASE-ARCHITECTURE.md
and ADR-001 (FastAPI with SQLAlchemy 2.0 & Pydantic v2).
Configures:
1. SQLAlchemy 2.0 engine with PostgreSQL QueuePool connection pooling.
2. Production pool metrics (pool_size=20, max_overflow=10, pool_timeout=30, pool_pre_ping=True).
3. Thread-safe SessionLocal sessionmaker.
4. FastAPI dependency generator (get_db) with transactional safety and deterministic closing.
5. Async engine and async_sessionmaker support for high-concurrency tasks.
6. Health-check connectivity verification (check_db_connectivity, ping_db).
7. Clean engine and connection pool disposal.
"""

from collections.abc import AsyncGenerator, Generator
import logging
from typing import Any, Optional, Union

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_engine_options(
    settings: Settings,
    database_url: str,
    custom_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Assemble engine options appropriate for the target database driver."""
    options: dict[str, Any] = {
        "echo": settings.DB_ECHO,
    }

    # SQLite-specific handling for tests and local embedded environments
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool
        else:
            options["pool_pre_ping"] = settings.DB_POOL_PRE_PING
    else:
        # PostgreSQL / Production QueuePool connection pooling
        options.update({
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_pre_ping": settings.DB_POOL_PRE_PING,
        })

    options.update(custom_kwargs)

    # If caller specifies a poolclass that does not support QueuePool parameters (e.g. NullPool, StaticPool),
    # strip those parameters to prevent SQLAlchemy create_engine TypeError.
    poolclass = options.get("poolclass")
    if poolclass is not None and getattr(poolclass, "__name__", "") in ("NullPool", "StaticPool"):
        options.pop("pool_size", None)
        options.pop("max_overflow", None)
        options.pop("pool_timeout", None)
        if getattr(poolclass, "__name__", "") == "NullPool":
            options.pop("pool_pre_ping", None)

    return options


def _resolve_engine_args(
    settings: Optional[Union[Settings, str]],
    database_url: Optional[str],
) -> tuple[Settings, str]:
    """Resolve polymorphic (settings, database_url) arguments safely."""
    if isinstance(settings, str):
        # Caller supplied a database URL string as the first positional argument
        return get_settings(), settings
    resolved_settings = settings or get_settings()
    resolved_url = database_url or resolved_settings.DATABASE_URL
    return resolved_settings, resolved_url


def create_db_engine(
    settings: Optional[Union[Settings, str]] = None,
    database_url: Optional[str] = None,
    **kwargs: Any,
) -> Engine:
    """Create a configured SQLAlchemy 2.0 synchronous Engine instance.
    
    Supports polymorphic argument calling:
    - create_db_engine() -> uses default settings
    - create_db_engine(custom_settings) -> uses custom settings
    - create_db_engine("sqlite:///:memory:") -> treats positional string as URL
    - create_db_engine(database_url="...") -> uses keyword URL
    
    Args:
        settings: Optional Settings instance or database URL string.
        database_url: Optional database URL string overriding settings.
        **kwargs: Additional parameters passed directly to create_engine.
        
    Returns:
        Configured SQLAlchemy Engine.
    """
    app_settings, url = _resolve_engine_args(settings, database_url)
    options = _build_engine_options(app_settings, url, kwargs)

    logger.debug("Creating database engine for URL: %s", url.split("@")[-1] if "@" in url else url)
    return create_engine(url, **options)


def create_session_factory(
    engine_instance: Optional[Engine] = None,
) -> sessionmaker[Session]:
    """Create a thread-safe synchronous session factory.
    
    Args:
        engine_instance: SQLAlchemy Engine to bind. Defaults to module engine.
        
    Returns:
        sessionmaker configured with autocommit=False, autoflush=False, expire_on_commit=False.
    """
    bind = engine_instance or engine
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=bind,
        class_=Session,
        expire_on_commit=False,
    )


def create_async_db_engine(
    settings: Optional[Union[Settings, str]] = None,
    database_url: Optional[str] = None,
    **kwargs: Any,
) -> AsyncEngine:
    """Create a configured SQLAlchemy 2.0 asynchronous AsyncEngine instance.
    
    Supports polymorphic argument calling:
    - create_async_db_engine() -> uses default settings
    - create_async_db_engine(custom_settings) -> uses custom settings
    - create_async_db_engine("postgresql+psycopg://...") -> treats positional string as URL
    - create_async_db_engine(database_url="...") -> uses keyword URL
    
    Args:
        settings: Optional Settings instance or database URL string.
        database_url: Optional database URL string overriding settings.
        **kwargs: Additional parameters passed directly to create_async_engine.
        
    Returns:
        Configured SQLAlchemy AsyncEngine.
    """
    app_settings, url = _resolve_engine_args(settings, database_url)
    options = _build_engine_options(app_settings, url, kwargs)

    return create_async_engine(url, **options)


def create_async_session_factory(
    async_engine_instance: Optional[AsyncEngine] = None,
) -> async_sessionmaker[AsyncSession]:
    """Create an asynchronous session factory.
    
    Args:
        async_engine_instance: AsyncEngine to bind. Defaults to module async_engine.
        
    Returns:
        async_sessionmaker configured with expire_on_commit=False.
    """
    bind = async_engine_instance or async_engine
    if bind is None:
        raise RuntimeError("Async engine is not initialized.")
    return async_sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# -----------------------------------------------------------------------------
# Module Singletons
# -----------------------------------------------------------------------------
engine: Engine = create_db_engine()
SessionLocal: sessionmaker[Session] = create_session_factory(engine)

# Async engine is initialized when using an async-compatible driver (e.g. PostgreSQL + psycopg)
async_engine: Optional[AsyncEngine] = None
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

try:
    if not get_settings().DATABASE_URL.startswith("sqlite"):
        async_engine = create_async_db_engine()
        AsyncSessionLocal = create_async_session_factory(async_engine)
except Exception as _exc:  # pragma: no cover
    logger.debug("Async engine not initialized by default: %s", _exc)


def reset_database_engine(
    new_settings: Optional[Union[Settings, str]] = None,
    new_database_url: Optional[str] = None,
    **kwargs: Any,
) -> tuple[Engine, sessionmaker[Session]]:
    """Re-initialize module-level engine and SessionLocal.
    
    Primarily utilized during test suite execution to redirect sessions to
    an isolated test database or in-memory instance without process restart.
    """
    global engine, SessionLocal, async_engine, AsyncSessionLocal

    dispose_engine(engine)
    app_settings, url = _resolve_engine_args(new_settings, new_database_url)

    engine = create_db_engine(app_settings, url, **kwargs)
    SessionLocal = create_session_factory(engine)

    # Re-initialize async engine if applicable
    if not url.startswith("sqlite") or "aiosqlite" in url:
        try:
            async_engine = create_async_db_engine(app_settings, url, **kwargs)
            AsyncSessionLocal = create_async_session_factory(async_engine)
        except Exception:
            async_engine = None
            AsyncSessionLocal = None
    else:
        async_engine = None
        AsyncSessionLocal = None

    return engine, SessionLocal


# -----------------------------------------------------------------------------
# Session Lifecycle & Dependencies
# -----------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a managed database session.
    
    Guarantees:
    1. A dedicated session is opened for the request.
    2. If the request completes successfully without exception, uncommitted changes
       are committed atomically at the request boundary.
    3. Any unhandled exception or abort triggers an automatic transaction rollback.
    4. The session is closed deterministically in all cases upon completion.
    """
    db = SessionLocal()
    try:
        yield db
        if db.in_transaction():
            db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an asynchronous database session.
    
    Guarantees:
    1. A dedicated async session is opened for the request.
    2. If the request completes successfully without exception, uncommitted changes
       are committed atomically at the request boundary.
    3. Any unhandled exception or abort triggers an automatic transaction rollback.
    4. The session is closed deterministically in all cases upon completion.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("AsyncSessionLocal is not initialized. Check your database driver and URL.")
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except BaseException:
            await session.rollback()
            raise


# -----------------------------------------------------------------------------
# Connectivity & Lifecycle Maintenance
# -----------------------------------------------------------------------------
def check_db_connectivity(
    target_engine: Optional[Engine] = None,
) -> bool:
    """Verify database connectivity by executing a lightweight `SELECT 1` ping.
    
    Args:
        target_engine: Optional Engine to verify. Defaults to module engine.
        
    Returns:
        True if the query succeeds; False if connection fails or times out.
    """
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        return False


def ping_db(target_engine: Optional[Engine] = None) -> None:
    """Execute a connectivity ping or raise the underlying database exception.
    
    Used by application startup checks and readiness probes.
    """
    eng = target_engine or engine
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))


def dispose_engine(target_engine: Optional[Engine] = None) -> None:
    """Dispose of the connection pool and close all active connections.
    
    Invoked during graceful application shutdown and lifespan teardown.
    """
    eng = target_engine or engine
    try:
        eng.dispose()
        logger.info("Database engine connection pool disposed successfully.")
    except Exception as exc:
        logger.error("Error disposing database engine: %s", exc)


async def dispose_async_engine(
    target_async_engine: Optional[AsyncEngine] = None,
) -> None:
    """Dispose of the asynchronous connection pool."""
    eng = target_async_engine or async_engine
    if eng is not None:
        try:
            await eng.dispose()
            logger.info("Async database engine connection pool disposed successfully.")
        except Exception as exc:
            logger.error("Error disposing async database engine: %s", exc)
