"""Unit tests for SA-03.1 AuthSession schema evolution and revocation metadata.

Architecture Specifications:
- docs/SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md (SA-03.1, Sections 4.3, 11.1, 14.1, 14.2)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Blueprint v2.0, Pages 1-16]

Verifies:
1. AuthSession model instantiation with new revocation metadata fields (revoked_at, revoked_by, revocation_reason).
2. AuthSession.revoke() sets status to REVOKED, records revoked_at, reason, and actor.
3. Preservation of the single-active-session partial unique index (idx_auth_sessions_unique_active_user).
4. Multiple revoked sessions with revocation reasons allowed for the same user without conflict.
5. System-triggered revocations support nullable revoked_by.
6. Schema and relationship consistency between User and AuthSession.
"""

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base, utc_now
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.user import (
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)


@pytest.fixture
def sa03_db():
    """Isolated SQLite in-memory database with full metadata."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


class TestAuthSessionSchemaEvolution:
    """Verifies SA-03.1 database schema evolution on AuthSession model."""

    def test_auth_session_creation_with_default_revocation_metadata(self, sa03_db: Session):
        """Newly established active sessions should have NULL revocation metadata."""
        user = User(
            id=uuid.uuid4(),
            email="learner@example.com",
            full_name="Learner One",
            is_verified=True,
            is_active=True,
        )
        sa03_db.add(user)
        sa03_db.commit()

        session = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="hash_token_abc_123",
            ip_address="192.168.1.50",
            user_agent="Mozilla/5.0 Test Agent",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add(session)
        sa03_db.commit()

        refreshed = sa03_db.scalar(select(AuthSession).where(AuthSession.id == session.id))
        assert refreshed is not None
        assert refreshed.status == SESSION_STATUS_ACTIVE
        assert refreshed.revoked_at is None
        assert refreshed.revoked_by is None
        assert refreshed.revocation_reason is None

    def test_auth_session_revoke_method_populates_metadata(self, sa03_db: Session):
        """AuthSession.revoke() should update status, timestamp, actor, and reason."""
        admin_id = uuid.uuid4()
        admin = User(
            id=admin_id,
            email="admin@example.com",
            full_name="Admin One",
            is_verified=True,
            is_active=True,
        )
        user = User(
            id=uuid.uuid4(),
            email="student@example.com",
            full_name="Student One",
            is_verified=True,
            is_active=True,
        )
        sa03_db.add_all([admin, user])
        sa03_db.commit()

        session = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="hash_token_xyz_456",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add(session)
        sa03_db.commit()

        # Revoke with reason and admin actor
        session.revoke(
            reason="Suspected credential leak reported by user.",
            revoked_by=admin.id,
        )
        sa03_db.commit()

        refreshed = sa03_db.scalar(select(AuthSession).where(AuthSession.id == session.id))
        assert refreshed is not None
        assert refreshed.status == SESSION_STATUS_REVOKED
        assert isinstance(refreshed.revoked_at, datetime)
        assert refreshed.revoked_by == admin.id
        assert refreshed.revocation_reason == "Suspected credential leak reported by user."

    def test_system_triggered_revocation_supports_null_revoked_by(self, sa03_db: Session):
        """Automated or system displacement revocations should support revoked_by=None."""
        user = User(
            id=uuid.uuid4(),
            email="auto@example.com",
            full_name="Auto User",
            is_verified=True,
            is_active=True,
        )
        sa03_db.add(user)
        sa03_db.commit()

        session = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="hash_system_token_789",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add(session)
        sa03_db.commit()

        session.revoke(reason="LOGIN_DISPLACEMENT", revoked_by=None)
        sa03_db.commit()

        refreshed = sa03_db.scalar(select(AuthSession).where(AuthSession.id == session.id))
        assert refreshed.status == SESSION_STATUS_REVOKED
        assert refreshed.revoked_by is None
        assert refreshed.revocation_reason == "LOGIN_DISPLACEMENT"
        assert refreshed.revoked_at is not None

    def test_multiple_revoked_sessions_allowed_with_metadata(self, sa03_db: Session):
        """Single-active-session invariant permits multiple historical revoked sessions."""
        user = User(
            id=uuid.uuid4(),
            email="multi@example.com",
            full_name="Multi User",
            is_verified=True,
            is_active=True,
        )
        sa03_db.add(user)
        sa03_db.commit()

        s1 = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="token_rev_1",
            status=SESSION_STATUS_REVOKED,
            revoked_at=utc_now(),
            revocation_reason="USER_LOGOUT",
            expires_at=utc_now(),
        )
        s2 = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="token_rev_2",
            status=SESSION_STATUS_REVOKED,
            revoked_at=utc_now(),
            revocation_reason="LOGIN_DISPLACEMENT",
            expires_at=utc_now(),
        )
        s3 = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="token_active_3",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add_all([s1, s2, s3])
        sa03_db.commit()

        user_sessions = sa03_db.scalars(
            select(AuthSession).where(AuthSession.user_id == user.id)
        ).all()
        assert len(user_sessions) == 3
        active_count = sum(1 for s in user_sessions if s.status == SESSION_STATUS_ACTIVE)
        assert active_count == 1

    def test_single_active_session_rejection_on_duplicate_active(self, sa03_db: Session):
        """Second active session for same user violates partial unique index."""
        user = User(
            id=uuid.uuid4(),
            email="single_active@example.com",
            full_name="Single Active User",
            is_verified=True,
            is_active=True,
        )
        sa03_db.add(user)
        sa03_db.commit()

        s1 = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="active_token_1",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add(s1)
        sa03_db.commit()

        s2 = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            session_token_hash="active_token_2",
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now(),
        )
        sa03_db.add(s2)
        with pytest.raises(IntegrityError):
            sa03_db.commit()
        sa03_db.rollback()
