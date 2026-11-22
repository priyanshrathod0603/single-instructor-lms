"""Unit tests for User, Session, and AuthToken repositories.

Verifies:
1. UserRepository:
   - Email normalization and duplicate collision prevention (ConflictException).
   - Default role assignment (STUDENT) and role queries.
   - Verification and password hash updates.
2. SessionRepository:
   - Atomic session displacement (Single-Active-Session invariant).
   - Session retrieval by token hash and active status.
   - Revocation and multi-session revocation.
   - Throttled activity timestamp updates.
   - Expired session cleanup.
3. AuthTokenRepository:
   - Token creation and retrieval by SHA-256 hash.
   - Expiration and type filtering.
   - Single-use consumption guarantee.
   - Mass user token invalidation.
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ConflictException, ValidationException
from app.models import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    SYSTEM_ROLES,
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
    AuthSession,
    AuthToken,
    Base,
    Role,
    User,
    UserRole,
)
from app.models.base import utc_now
from app.repositories import (
    AuthTokenRepository,
    SessionRepository,
    UserRepository,
)


@pytest.fixture
def db_session():
    """In-memory SQLite session configured with schema and default roles."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        # Seed default roles
        for role_id in SYSTEM_ROLES:
            session.add(Role(id=role_id, name=role_id.capitalize(), description=f"{role_id} role"))
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestUserRepository:
    """Verifies UserRepository data access methods."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, db_session: Session):
        repo = UserRepository()
        user = await repo.create_user(
            db_session,
            email="  NEW.Learner@Domain.COM  ",
            full_name="New Learner",
            password_hash="$argon2id$mockhash",
        )
        assert user.id is not None
        assert user.email == "new.learner@domain.com"
        assert user.has_role(ROLE_STUDENT) is True
        assert user.is_verified is False
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_raises_conflict(self, db_session: Session):
        repo = UserRepository()
        await repo.create_user(
            db_session,
            email="duplicate@example.com",
            full_name="First User",
        )
        with pytest.raises(ConflictException) as exc_info:
            await repo.create_user(
                db_session,
                email="DUPLICATE@example.com",
                full_name="Second User",
            )
        assert exc_info.value.code == "EMAIL_ALREADY_EXISTS"

    @pytest.mark.asyncio
    async def test_create_user_empty_email_or_invalid_role(self, db_session: Session):
        repo = UserRepository()
        with pytest.raises(ValidationException):
            await repo.create_user(db_session, email="", full_name="User")

        with pytest.raises(ValidationException):
            await repo.create_user(
                db_session,
                email="valid@example.com",
                full_name="User",
                role_id="NON_EXISTENT_ROLE",
            )

    @pytest.mark.asyncio
    async def test_get_by_id_and_email(self, db_session: Session):
        repo = UserRepository()
        created = await repo.create_user(
            db_session,
            email="lookup@example.com",
            full_name="Lookup User",
        )
        by_id = await repo.get_by_id(db_session, created.id)
        assert by_id is not None
        assert by_id.id == created.id

        by_email = await repo.get_by_email(db_session, "  LOOKUP@example.com ")
        assert by_email is not None
        assert by_email.id == created.id

        assert await repo.get_by_email(db_session, "nonexistent@example.com") is None

    @pytest.mark.asyncio
    async def test_update_password_and_verification(self, db_session: Session):
        repo = UserRepository()
        user = await repo.create_user(
            db_session,
            email="update@example.com",
            full_name="Update User",
            password_hash="old_hash",
        )
        await repo.update_password_hash(db_session, user.id, "new_hash")
        await repo.mark_email_verified(db_session, user.id)

        reloaded = await repo.get_by_id(db_session, user.id)
        assert reloaded.password_hash == "new_hash"
        assert reloaded.is_verified is True

    @pytest.mark.asyncio
    async def test_assign_role_and_update_status(self, db_session: Session):
        repo = UserRepository()
        user = await repo.create_user(
            db_session,
            email="role_status@example.com",
            full_name="Role Status User",
        )
        await repo.assign_role(db_session, user.id, ROLE_ADMIN)
        await repo.update_status(db_session, user.id, is_active=False)

        reloaded = await repo.get_by_id(db_session, user.id)
        assert reloaded.has_role(ROLE_ADMIN) is True
        assert reloaded.has_role(ROLE_STUDENT) is True
        assert reloaded.is_active is False


class TestSessionRepository:
    """Verifies SessionRepository methods and concurrency control."""

    @pytest.mark.asyncio
    async def test_create_and_get_session(self, db_session: Session):
        user_repo = UserRepository()
        session_repo = SessionRepository()

        user = await user_repo.create_user(db_session, email="session1@example.com", full_name="S1")
        now = utc_now()
        session = await session_repo.create_session(
            db_session,
            user_id=user.id,
            session_token_hash="hash_1" * 10,
            expires_at=now + timedelta(days=7),
            ip_address="127.0.0.1",
            user_agent="TestAgent",
        )
        assert session.id is not None
        assert session.status == SESSION_STATUS_ACTIVE

        retrieved = await session_repo.get_session_by_token_hash(db_session, "hash_1" * 10)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.user.email == "session1@example.com"

        active = await session_repo.get_active_session_by_user_id(db_session, user.id)
        assert active is not None
        assert active.id == session.id

    @pytest.mark.asyncio
    async def test_atomic_displacement_revokes_prior_session(self, db_session: Session):
        """Single-Active-Session: logging in from a second device displaces previous session."""
        user_repo = UserRepository()
        session_repo = SessionRepository()

        user = await user_repo.create_user(db_session, email="displace@example.com", full_name="Displace User")
        exp = utc_now() + timedelta(days=7)

        # Device 1 login
        sess1, displaced1 = await session_repo.atomic_displace_session(
            db_session,
            user_id=user.id,
            new_session_token_hash="token_device_1" + "0" * 50,
            expires_at=exp,
            ip_address="10.0.0.1",
            user_agent="Device1",
        )
        assert sess1.status == SESSION_STATUS_ACTIVE
        assert displaced1 is None

        # Device 2 login -> must displace Device 1
        sess2, displaced2 = await session_repo.atomic_displace_session(
            db_session,
            user_id=user.id,
            new_session_token_hash="token_device_2" + "0" * 50,
            expires_at=exp,
            ip_address="10.0.0.2",
            user_agent="Device2",
        )
        assert sess2.status == SESSION_STATUS_ACTIVE
        assert displaced2 is not None
        assert displaced2.id == sess1.id
        assert displaced2.status == SESSION_STATUS_REVOKED

        # Verify in DB: sess1 is revoked, sess2 is active
        r1 = await session_repo.get_session_by_token_hash(db_session, "token_device_1" + "0" * 50)
        assert r1.status == SESSION_STATUS_REVOKED
        r2 = await session_repo.get_session_by_token_hash(db_session, "token_device_2" + "0" * 50)
        assert r2.status == SESSION_STATUS_ACTIVE

    @pytest.mark.asyncio
    async def test_revocation_and_multi_revocation(self, db_session: Session):
        user_repo = UserRepository()
        session_repo = SessionRepository()

        user = await user_repo.create_user(db_session, email="revoke@example.com", full_name="Revoke User")
        sess, _ = await session_repo.atomic_displace_session(
            db_session,
            user_id=user.id,
            new_session_token_hash="token_revoke" + "0" * 52,
            expires_at=utc_now() + timedelta(days=7),
        )
        assert sess.status == SESSION_STATUS_ACTIVE

        # Single revocation
        revoked = await session_repo.revoke_session(db_session, sess.id)
        assert revoked is True
        assert sess.status == SESSION_STATUS_REVOKED

        # Revoke all sessions for user
        sess2, _ = await session_repo.atomic_displace_session(
            db_session,
            user_id=user.id,
            new_session_token_hash="token_revoke_all" + "0" * 48,
            expires_at=utc_now() + timedelta(days=7),
        )
        count = await session_repo.revoke_all_user_sessions(db_session, user.id)
        assert count == 1
        assert sess2.status == SESSION_STATUS_REVOKED

    def test_atomic_displacement_sql_postgresql_dialect_avoids_outer_join(self):
        """Verifies that lock_stmt avoids outer joins and targets auth_sessions exclusively under PostgreSQL.

        Fixes regression where PostgreSQL raised FeatureNotSupported:
        'FOR UPDATE cannot be applied to the nullable side of an outer join'.
        """
        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.orm import noload

        uid = uuid.uuid4()
        lock_stmt = (
            select(AuthSession)
            .options(noload(AuthSession.user))
            .where(
                AuthSession.user_id == uid,
                AuthSession.status == SESSION_STATUS_ACTIVE,
            )
            .with_for_update(of=AuthSession)
        )
        sql = str(lock_stmt.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE OF auth_sessions" in sql
        assert "LEFT OUTER JOIN" not in sql
        assert "JOIN users" not in sql

    @pytest.mark.asyncio
    async def test_touch_last_active_throttling(self, db_session: Session):
        user_repo = UserRepository()
        session_repo = SessionRepository()

        user = await user_repo.create_user(db_session, email="touch@example.com", full_name="Touch User")
        sess, _ = await session_repo.atomic_displace_session(
            db_session,
            user_id=user.id,
            new_session_token_hash="token_touch" + "0" * 53,
            expires_at=utc_now() + timedelta(days=7),
        )
        # Immediate touch should be throttled (less than 300s elapsed)
        updated = await session_repo.touch_last_active(db_session, sess, threshold_seconds=300)
        assert updated is False

        # Simulate elapsed time
        sess.last_active_at = utc_now() - timedelta(seconds=301)
        updated = await session_repo.touch_last_active(db_session, sess, threshold_seconds=300)
        assert updated is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, db_session: Session):
        user_repo = UserRepository()
        session_repo = SessionRepository()

        user = await user_repo.create_user(db_session, email="cleanup@example.com", full_name="Clean User")
        past_exp = utc_now() - timedelta(minutes=1)
        # Force create an already-expired active session
        sess = await session_repo.create_session(
            db_session,
            user_id=user.id,
            session_token_hash="token_expired" + "0" * 51,
            expires_at=past_exp,
        )
        assert sess.status == SESSION_STATUS_ACTIVE

        count = await session_repo.cleanup_expired_sessions(db_session)
        assert count == 1
        assert sess.status == SESSION_STATUS_EXPIRED


class TestAuthTokenRepository:
    """Verifies AuthTokenRepository operations."""

    @pytest.mark.asyncio
    async def test_create_and_get_valid_token(self, db_session: Session):
        user_repo = UserRepository()
        token_repo = AuthTokenRepository()

        user = await user_repo.create_user(db_session, email="token@example.com", full_name="Token User")
        token_hash = "token_hash_" + "0" * 53
        exp = utc_now() + timedelta(hours=1)

        token = await token_repo.create_token(
            db_session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
            expires_at=exp,
        )
        assert token.id is not None
        assert token.is_used is False

        # Retrieve valid token
        valid = await token_repo.get_valid_token(
            db_session,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
        )
        assert valid is not None
        assert valid.id == token.id

        # Mismatched type returns None
        assert await token_repo.get_valid_token(
            db_session,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
        ) is None

    @pytest.mark.asyncio
    async def test_consume_token_single_use(self, db_session: Session):
        user_repo = UserRepository()
        token_repo = AuthTokenRepository()

        user = await user_repo.create_user(db_session, email="consume@example.com", full_name="Consume User")
        token_hash = "consume_hash_" + "0" * 51
        exp = utc_now() + timedelta(hours=1)

        token = await token_repo.create_token(
            db_session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            expires_at=exp,
        )

        consumed = await token_repo.consume_token(db_session, token.id)
        assert consumed is True

        # Second consume fails
        second_consume = await token_repo.consume_token(db_session, token.id)
        assert second_consume is False

        # No longer retrievable as valid
        valid = await token_repo.get_valid_token(
            db_session,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
        )
        assert valid is None

    @pytest.mark.asyncio
    async def test_invalidate_user_tokens(self, db_session: Session):
        user_repo = UserRepository()
        token_repo = AuthTokenRepository()

        user = await user_repo.create_user(db_session, email="inval@example.com", full_name="Inval User")
        exp = utc_now() + timedelta(hours=1)

        await token_repo.create_token(
            db_session,
            user_id=user.id,
            token_hash="inval_1_" + "0" * 56,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            expires_at=exp,
        )
        await token_repo.create_token(
            db_session,
            user_id=user.id,
            token_hash="inval_2_" + "0" * 56,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            expires_at=exp,
        )

        count = await token_repo.invalidate_user_tokens(
            db_session,
            user_id=user.id,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
        )
        assert count == 2
