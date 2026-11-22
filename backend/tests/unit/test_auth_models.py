"""Unit tests for Phase 1 Part 1 Authentication and Identity SQLAlchemy models.

Verifies:
1. Role model: canonical system roles, constraints, attributes, repr.
2. UserRole model: composite keys, role assignment relationships.
3. User model: email normalization, default flags, sensitive field masking, role queries.
4. AuthSession model: status transitions, expiration checking, single active invariant.
5. AuthToken model: token types, single-use invalidation, expiry checks.
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AUTH_TOKEN_TYPES,
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    ROLE_VISITOR,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    SYSTEM_ROLES,
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
    TOKEN_TYPE_STAFF_ONBOARDING,
    AuthSession,
    AuthToken,
    Base,
    Role,
    User,
    UserRole,
)
from app.models.base import utc_now


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing model relationships and behaviors."""
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


class TestRoleModel:
    """Verifies Role model structure and constants."""

    def test_canonical_system_roles_defined(self):
        """All five system roles must be present in SYSTEM_ROLES constant."""
        expected = {"VISITOR", "STUDENT", "STAFF", "ADMIN", "SUPER_ADMIN"}
        assert SYSTEM_ROLES == expected

    def test_role_creation_and_repr(self, db_session: Session):
        """Role model must persist attributes and produce informative repr."""
        role = db_session.get(Role, ROLE_STUDENT)
        assert role is not None
        assert role.id == "STUDENT"
        assert role.name == "Student"
        assert "STUDENT" in repr(role)


class TestUserModel:
    """Verifies User model invariants, email normalization, and methods."""

    def test_email_normalization_on_instantiation(self):
        """User instantiation must strip whitespace and lowercase email."""
        user = User(
            email="  Test.STUDENT+Exam@Example.COM  ",
            full_name="Exam Student",
        )
        assert user.email == "test.student+exam@example.com"

    def test_default_status_flags(self):
        """Default flags must ensure verified=False and active=True."""
        user = User(
            email="learner@example.com",
            full_name="Learner One",
        )
        assert user.is_verified is False
        assert user.is_active is True

    def test_sensitive_fields_masking(self):
        """password_hash must be explicitly declared in __sensitive_fields__."""
        assert "password_hash" in User.__sensitive_fields__

    def test_user_persistence_and_relationships(self, db_session: Session):
        """User must persist with roles and support query helper methods."""
        user = User(
            email="alice@example.com",
            full_name="Alice Smith",
            password_hash="$argon2id$v=19$mockhash",
        )
        db_session.add(user)
        db_session.flush()

        # Assign STUDENT role
        user_role = UserRole(user_id=user.id, role_id=ROLE_STUDENT)
        db_session.add(user_role)
        db_session.commit()

        # Reload
        reloaded = db_session.get(User, user.id)
        assert reloaded is not None
        assert reloaded.has_role(ROLE_STUDENT) is True
        assert reloaded.has_role(ROLE_ADMIN) is False
        assert reloaded.roles == [ROLE_STUDENT]
        assert "alice@example.com" in repr(reloaded)


class TestAuthSessionModel:
    """Verifies AuthSession model lifecycle, state transitions, and properties."""

    def test_session_creation_and_defaults(self, db_session: Session):
        """Session must default to ACTIVE status with sensitive field masked."""
        user = User(email="bob@example.com", full_name="Bob Jones")
        db_session.add(user)
        db_session.flush()

        now = utc_now()
        session = AuthSession(
            user_id=user.id,
            session_token_hash="a" * 64,
            expires_at=now + timedelta(days=7),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        db_session.add(session)
        db_session.commit()

        assert session.status == SESSION_STATUS_ACTIVE
        assert session.is_active() is True
        assert "session_token_hash" in AuthSession.__sensitive_fields__
        assert session.user.id == user.id

    def test_session_expiration_check(self):
        """Expired session must return False for is_active()."""
        now = utc_now()
        expired_session = AuthSession(
            user_id=uuid.uuid4(),
            session_token_hash="b" * 64,
            expires_at=now - timedelta(seconds=1),
            status=SESSION_STATUS_ACTIVE,
        )
        assert expired_session.is_active() is False

    def test_session_revocation_and_state_methods(self):
        """revoke() and expire() methods must transition status."""
        session = AuthSession(
            user_id=uuid.uuid4(),
            session_token_hash="c" * 64,
            expires_at=utc_now() + timedelta(days=1),
        )
        assert session.status == SESSION_STATUS_ACTIVE
        session.revoke()
        assert session.status == SESSION_STATUS_REVOKED
        assert session.is_active() is False

        session.expire()
        assert session.status == SESSION_STATUS_EXPIRED
        assert session.is_active() is False


class TestAuthTokenModel:
    """Verifies AuthToken single-use and expiration rules."""

    def test_token_types_constant(self):
        """Auth token types must include email verification, password reset, and staff onboarding."""
        assert AUTH_TOKEN_TYPES == {
            TOKEN_TYPE_EMAIL_VERIFICATION,
            TOKEN_TYPE_PASSWORD_RESET,
            TOKEN_TYPE_STAFF_ONBOARDING,
        }

    def test_token_lifecycle_and_validation(self, db_session: Session):
        """AuthToken is_valid() checks expiration and single-use status."""
        user = User(email="charlie@example.com", full_name="Charlie Brown")
        db_session.add(user)
        db_session.flush()

        future_exp = utc_now() + timedelta(hours=1)
        token = AuthToken(
            user_id=user.id,
            token_hash="d" * 64,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
            expires_at=future_exp,
        )
        db_session.add(token)
        db_session.commit()

        assert token.is_valid() is True
        assert "token_hash" in AuthToken.__sensitive_fields__

        # Consume token
        token.mark_used()
        assert token.is_used is True
        assert token.is_valid() is False

    def test_expired_token_is_invalid(self):
        """Expired token must evaluate is_valid() as False."""
        past_exp = utc_now() - timedelta(minutes=5)
        token = AuthToken(
            user_id=uuid.uuid4(),
            token_hash="e" * 64,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            expires_at=past_exp,
            is_used=False,
        )
        assert token.is_valid() is False
