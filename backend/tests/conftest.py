"""Pytest configuration and global fixtures for backend test suites."""

import sys
from pathlib import Path
import pytest

# Ensure backend root is on Python sys.path so 'app.*' imports resolve cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import get_settings


def create_test_auth_headers(user, session=None, extra_claims=None):
    """Generate Authorization Bearer headers for a test user with an active AuthSession."""
    from datetime import timedelta
    from sqlalchemy import inspect
    from app.models.base import utc_now
    from app.models.auth_session import AuthSession, SESSION_STATUS_ACTIVE
    from app.core.security import create_access_token, generate_secure_token, hash_token
    import uuid

    db = session
    if db is None:
        try:
            db = inspect(user).session
        except Exception:
            db = None

    session_id = uuid.uuid4()
    if db is not None:
        existing = db.query(AuthSession).filter(
            AuthSession.user_id == user.id,
            AuthSession.status == SESSION_STATUS_ACTIVE,
        ).first()
        if existing:
            session_id = existing.id
        else:
            auth_session = AuthSession(
                id=session_id,
                user_id=user.id,
                session_token_hash=hash_token(generate_secure_token(32)),
                status=SESSION_STATUS_ACTIVE,
                expires_at=utc_now() + timedelta(days=7),
            )
            db.add(auth_session)
            db.commit()

    claims = {"roles": user.roles, "session_id": str(session_id)}
    if extra_claims:
        claims.update(extra_claims)
    token = create_access_token(subject=str(user.id), extra_claims=claims)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Automatically clears the get_settings LRU cache before and after every test
    to guarantee test isolation when monkeypatching environment variables.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    """Configures AnyIO to run async tests using the standard asyncio backend."""
    return "asyncio"


def pytest_collection_modifyitems(items):
    """Enables AnyIO runner for tests marked with @pytest.mark.asyncio."""
    for item in items:
        if "asyncio" in item.keywords and "anyio" not in item.keywords:
            item.add_marker(pytest.mark.anyio)
