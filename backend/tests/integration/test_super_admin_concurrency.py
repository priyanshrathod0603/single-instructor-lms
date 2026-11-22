"""Real PostgreSQL concurrency integration tests for Sole Super Admin protection (BUG-006).

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 1, 3)
- docs/backend/09-RBAC-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK202)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003)

Invariants Verified:
1. Row-level serialization lock on `roles WHERE id = 'SUPER_ADMIN'` prevents race condition.
2. Concurrent deactivation of two Super Admins preserves at least one active Super Admin.
3. Concurrent role revocation of two Super Admins preserves at least one Super Admin.
4. Concurrent mixed deactivation and role revocation preserves at least one active Super Admin.
5. Sole Super Admin cannot be deactivated or demoted under concurrent load.
"""

import concurrent.futures
import os
import uuid
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ConflictException
from app.models.base import Base
from app.models.user import ROLE_SUPER_ADMIN, Role, User, UserRole
from app.services.user_service import UserService

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:1234@localhost:5432/lms_test_db",
)

try:
    _test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    with _test_engine.connect() as _conn:
        _conn.execute(text("SELECT 1"))
    has_postgres_test_db = True
except Exception:
    has_postgres_test_db = False

pytestmark = pytest.mark.skipif(
    not has_postgres_test_db,
    reason="Isolated PostgreSQL test database (lms_test_db) not reachable.",
)


@pytest.fixture(scope="module")
def pg_test_engine():
    """Provides isolated PostgreSQL engine on lms_test_db."""
    engine = create_engine(TEST_DB_URL, pool_size=10, max_overflow=5)
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE IF EXISTS audit_logs DISABLE TRIGGER ALL;
            DELETE FROM audit_logs;
            ALTER TABLE IF EXISTS audit_logs ENABLE TRIGGER ALL;
            DELETE FROM auth_sessions;
            DELETE FROM user_roles;
            DELETE FROM users;
            DELETE FROM roles;
        """))
        conn.commit()
    engine.dispose()


@pytest.fixture
def session_factory(pg_test_engine):
    """Provides thread-safe sessionmaker for concurrency tests."""
    return sessionmaker(bind=pg_test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_tables(session_factory):
    """Ensures clean state before each concurrency test."""
    with session_factory() as session:
        session.execute(text("ALTER TABLE IF EXISTS audit_logs DISABLE TRIGGER ALL;"))
        session.execute(text("DELETE FROM audit_logs;"))
        session.execute(text("ALTER TABLE IF EXISTS audit_logs ENABLE TRIGGER ALL;"))
        session.execute(text("DELETE FROM auth_sessions;"))
        session.query(UserRole).delete()
        session.query(User).delete()
        session.query(Role).delete()

        # Seed SUPER_ADMIN role
        super_role = Role(
            id=ROLE_SUPER_ADMIN,
            name="Super Administrator",
            description="Full system authority",
        )
        session.add(super_role)
        session.commit()
    yield


class TestPostgreSQLSuperAdminConcurrency:

    def _seed_two_super_admins(self, session_factory) -> tuple[uuid.UUID, uuid.UUID]:
        with session_factory() as session:
            admin1 = User(
                email=f"admin1_{uuid.uuid4().hex[:6]}@example.com",
                password_hash="hashed_pw_test",
                full_name="Admin One",
                is_active=True,
                is_verified=True,
            )
            admin2 = User(
                email=f"admin2_{uuid.uuid4().hex[:6]}@example.com",
                password_hash="hashed_pw_test",
                full_name="Admin Two",
                is_active=True,
                is_verified=True,
            )
            session.add_all([admin1, admin2])
            session.flush()

            ur1 = UserRole(user_id=admin1.id, role_id=ROLE_SUPER_ADMIN)
            ur2 = UserRole(user_id=admin2.id, role_id=ROLE_SUPER_ADMIN)
            session.add_all([ur1, ur2])
            session.commit()
            return admin1.id, admin2.id

    def test_concurrent_deactivation_preserves_sole_super_admin(self, session_factory):
        """Two concurrent transactions attempt to deactivate both Super Admins simultaneously.
        
        Row-level serialization lock on roles forces sequential evaluation; exactly one
        must succeed and one must be rejected, preserving at least 1 active Super Admin.
        """
        id1, id2 = self._seed_two_super_admins(session_factory)
        user_svc = UserService()

        def deactive_admin(user_id: uuid.UUID):
            with session_factory() as session:
                try:
                    import asyncio
                    # Run synchronously in thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res = loop.run_until_complete(
                        user_svc.update_user_status(session, user_id=user_id, is_active=False)
                    )
                    loop.close()
                    session.commit()
                    return ("SUCCESS", user_id)
                except ConflictException as ce:
                    session.rollback()
                    return ("CONFLICT", ce.code)
                except Exception as ex:
                    session.rollback()
                    return ("ERROR", str(ex))

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(deactive_admin, id1)
            f2 = executor.submit(deactive_admin, id2)
            results = [f1.result(), f2.result()]

        statuses = [r[0] for r in results]
        assert "SUCCESS" in statuses, f"Expected exactly one success: {results}"
        assert "CONFLICT" in statuses, f"Expected one conflict rejection: {results}"
        conflict_codes = [r[1] for r in results if r[0] == "CONFLICT"]
        assert conflict_codes[0] == "CANNOT_SUSPEND_LAST_SUPER_ADMIN"

        # Verify database state: exactly 1 active Super Admin remains
        with session_factory() as session:
            active_super_admins = (
                session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .filter(UserRole.role_id == ROLE_SUPER_ADMIN, User.is_active.is_(True))
                .count()
            )
            assert active_super_admins == 1, f"Expected 1 active Super Admin, found {active_super_admins}"

    def test_concurrent_role_revocation_preserves_sole_super_admin(self, session_factory):
        """Two concurrent transactions attempt to revoke SUPER_ADMIN role from both users."""
        id1, id2 = self._seed_two_super_admins(session_factory)
        user_svc = UserService()

        def revoke_role(user_id: uuid.UUID):
            with session_factory() as session:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res = loop.run_until_complete(
                        user_svc.manage_user_role(
                            session,
                            user_id=user_id,
                            role_id=ROLE_SUPER_ADMIN,
                            action="REVOKE",
                        )
                    )
                    loop.close()
                    session.commit()
                    return ("SUCCESS", user_id)
                except ConflictException as ce:
                    session.rollback()
                    return ("CONFLICT", ce.code)
                except Exception as ex:
                    session.rollback()
                    return ("ERROR", str(ex))

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(revoke_role, id1)
            f2 = executor.submit(revoke_role, id2)
            results = [f1.result(), f2.result()]

        statuses = [r[0] for r in results]
        assert "SUCCESS" in statuses
        assert "CONFLICT" in statuses
        conflict_codes = [r[1] for r in results if r[0] == "CONFLICT"]
        assert conflict_codes[0] == "CANNOT_DEMOTE_LAST_SUPER_ADMIN"

        with session_factory() as session:
            count = (
                session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .filter(UserRole.role_id == ROLE_SUPER_ADMIN, User.is_active.is_(True))
                .count()
            )
            assert count == 1

    def test_concurrent_mixed_deactivation_and_role_revocation(self, session_factory):
        """Worker 1 attempts deactivation of Admin 1; Worker 2 attempts role revocation of Admin 2.
        
        Row-level serialization on roles ensures atomic serialization; exactly one succeeds,
        preserving at least one active Super Admin.
        """
        id1, id2 = self._seed_two_super_admins(session_factory)
        user_svc = UserService()

        def op_deactivate(user_id: uuid.UUID):
            with session_factory() as session:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res = loop.run_until_complete(
                        user_svc.update_user_status(session, user_id=user_id, is_active=False)
                    )
                    loop.close()
                    session.commit()
                    return ("SUCCESS_DEACTIVATE", user_id)
                except ConflictException as ce:
                    session.rollback()
                    return ("CONFLICT", ce.code)
                except Exception as ex:
                    session.rollback()
                    return ("ERROR", str(ex))

        def op_revoke(user_id: uuid.UUID):
            with session_factory() as session:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    res = loop.run_until_complete(
                        user_svc.manage_user_role(
                            session,
                            user_id=user_id,
                            role_id=ROLE_SUPER_ADMIN,
                            action="REVOKE",
                        )
                    )
                    loop.close()
                    session.commit()
                    return ("SUCCESS_REVOKE", user_id)
                except ConflictException as ce:
                    session.rollback()
                    return ("CONFLICT", ce.code)
                except Exception as ex:
                    session.rollback()
                    return ("ERROR", str(ex))

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(op_deactivate, id1)
            f2 = executor.submit(op_revoke, id2)
            results = [f1.result(), f2.result()]

        statuses = [r[0] for r in results]
        assert "CONFLICT" in statuses, f"Expected one conflict rejection: {results}"

        with session_factory() as session:
            count = (
                session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .filter(UserRole.role_id == ROLE_SUPER_ADMIN, User.is_active.is_(True))
                .count()
            )
            assert count == 1, f"Expected 1 active Super Admin, got {count}"
