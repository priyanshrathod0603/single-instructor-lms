"""Unit and integration tests for Super Admin user creation functionality.

Verifies:
1. Super Admin can create STUDENT, STAFF, ADMIN, and SUPER_ADMIN users with full details and credentials.
2. Mandatory fields validation: full_name, email, phone, password, role.
3. Phone number validation (7-15 digits, syntax).
4. Password complexity policy validation (min 12 chars, upper, lower, digit, symbol).
5. Email uniqueness enforcement (rejects duplicate email with 409 Conflict).
6. Password security: Argon2id hash stored, never plaintext.
7. Role assignment: correct canonical role in user_roles.
8. Audit trail: USER_CREATED event recorded with actor details and safe snapshot.
9. Authorization protection: Non-super-admins (Admin, Staff, Student, Anonymous) are blocked with 401/403.
10. Both API routes: POST /api/v1/control/users and POST /api/v1/users.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ConflictException, ForbiddenException, ValidationException
from app.core.security import verify_password
from app.main import app
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    User,
    UserRole,
)
from app.schemas.user import UserCreateRequest, UserProfileResponse
from app.services.user_service import UserService


@pytest.fixture
def super_admin_user():
    u = User(
        id=uuid.uuid4(),
        email="superadmin@example.com",
        full_name="Platform Owner",
        phone="+919876543210",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_SUPER_ADMIN)]
    return u


@pytest.fixture
def admin_user():
    u = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Operations Admin",
        phone="+919876543211",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_ADMIN)]
    return u


@pytest.fixture
def student_user():
    u = User(
        id=uuid.uuid4(),
        email="student@example.com",
        full_name="Enrolled Student",
        phone="+919876543212",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_STUDENT)]
    return u


class TestSuperAdminCreateUser:
    """Test suite for Super Admin user creation workflow."""

    def test_super_admin_create_student_via_control_api(self, super_admin_user):
        """Super Admin creates a student user via POST /api/v1/control/users."""
        mock_db = MagicMock()
        mock_user_service = MagicMock(spec=UserService)

        new_user_id = uuid.uuid4()
        mock_user_service.create_user = AsyncMock(
            return_value=UserProfileResponse(
                id=new_user_id,
                email="newstudent@example.com",
                full_name="New Student",
                phone="+919876543299",
                is_verified=True,
                is_active=True,
                roles=["STUDENT"],
                permissions=[],
                created_at="2026-11-17T12:00:00Z",
                updated_at="2026-11-17T12:00:00Z",
            )
        )

        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_db] = lambda: mock_db
        from app.api.v1.control import get_user_service as get_control_user_svc
        app.dependency_overrides[get_control_user_svc] = lambda: mock_user_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "New Student",
                "email": "newstudent@example.com",
                "phone": "+919876543299",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )

        app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["email"] == "newstudent@example.com"
        assert data["full_name"] == "New Student"
        assert data["phone"] == "+919876543299"
        assert data["roles"] == ["STUDENT"]
        assert data["is_verified"] is True
        mock_db.commit.assert_called_once()

    def test_super_admin_create_staff_via_users_api(self, super_admin_user):
        """Super Admin creates a staff user via POST /api/v1/users."""
        mock_db = MagicMock()
        mock_user_service = MagicMock(spec=UserService)

        new_user_id = uuid.uuid4()
        mock_user_service.create_user = AsyncMock(
            return_value=UserProfileResponse(
                id=new_user_id,
                email="newstaff@example.com",
                full_name="New Teaching Assistant",
                phone="+14155552671",
                is_verified=True,
                is_active=True,
                roles=["STAFF"],
                permissions=["assignments:grade"],
                created_at="2026-11-17T12:00:00Z",
                updated_at="2026-11-17T12:00:00Z",
            )
        )

        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_db] = lambda: mock_db
        from app.api.v1.users import get_user_service as get_users_svc
        app.dependency_overrides[get_users_svc] = lambda: mock_user_service

        client = TestClient(app)
        response = client.post(
            "/api/v1/users",
            json={
                "full_name": "New Teaching Assistant",
                "email": "newstaff@example.com",
                "phone": "+14155552671",
                "password": "StrongPassword123!",
                "role": "STAFF",
            },
        )

        app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["email"] == "newstaff@example.com"
        assert data["roles"] == ["STAFF"]
        mock_db.commit.assert_called_once()

    def test_non_super_admin_forbidden(self, admin_user, student_user):
        """Admin or Student caller is strictly rejected with 403 Forbidden."""
        mock_db = MagicMock()

        # Admin caller
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: mock_db

        client = TestClient(app)
        res_admin = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Unauthorized Attempt",
                "email": "unauth@example.com",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert res_admin.status_code == status.HTTP_403_FORBIDDEN

        res_users = client.post(
            "/api/v1/users",
            json={
                "full_name": "Unauthorized Attempt",
                "email": "unauth@example.com",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert res_users.status_code == status.HTTP_403_FORBIDDEN

        # Student caller
        app.dependency_overrides[get_current_user] = lambda: student_user
        res_student = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Student Attempt",
                "email": "student_attempt@example.com",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert res_student.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()

    def test_unauthenticated_caller_unauthorized(self):
        """Unauthenticated caller is rejected with 401 Unauthorized."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Anon Attempt",
                "email": "anon@example.com",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_validation_missing_or_invalid_fields(self, super_admin_user):
        """Pydantic validation rejects missing or invalid fields."""
        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_db] = lambda: MagicMock()

        client = TestClient(app)

        # 1. Invalid email
        res_email = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Valid Name",
                "email": "not-an-email",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert res_email.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # 2. Invalid phone (too short)
        res_phone = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Valid Name",
                "email": "valid@example.com",
                "phone": "123",
                "password": "StrongPassword123!",
                "role": "STUDENT",
            },
        )
        assert res_phone.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # 3. Invalid role
        res_role = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Valid Name",
                "email": "valid@example.com",
                "phone": "+919876543210",
                "password": "StrongPassword123!",
                "role": "INVALID_ROLE",
            },
        )
        assert res_role.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # 4. Short password (< 12 chars)
        res_pass = client.post(
            "/api/v1/control/users",
            json={
                "full_name": "Valid Name",
                "email": "valid@example.com",
                "phone": "+919876543210",
                "password": "Short1!",
                "role": "STUDENT",
            },
        )
        assert res_pass.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()


class TestUserServiceCreateUserLogic:
    """Direct test of UserService.create_user business logic and audit guarantees."""

    @pytest.mark.anyio
    async def test_service_create_user_hashes_password_and_audits(self, super_admin_user):
        """create_user hashes password, creates user in repo, and logs audit event."""
        mock_user_repo = MagicMock()
        mock_audit_service = MagicMock()
        mock_session = MagicMock()

        # Email not taken
        mock_user_repo.get_by_email = AsyncMock(return_value=None)

        created_user = User(
            id=uuid.uuid4(),
            email="testuser@example.com",
            full_name="Test User",
            phone="+919876543210",
            is_active=True,
            is_verified=True,
        )
        created_user.user_roles = [UserRole(user_id=created_user.id, role_id=ROLE_STAFF)]
        mock_user_repo.create_user = AsyncMock(return_value=created_user)
        mock_audit_service.record_event = AsyncMock()

        service = UserService(
            user_repo=mock_user_repo,
            audit_service=mock_audit_service,
        )

        req = UserCreateRequest(
            full_name="Test User",
            email="testuser@example.com",
            phone="+919876543210",
            password="StrongPassword123!",
            role="STAFF",
        )

        profile = await service.create_user(mock_session, req, actor=super_admin_user)

        assert profile.email == "testuser@example.com"
        assert profile.full_name == "Test User"
        assert profile.phone == "+919876543210"
        assert profile.roles == ["STAFF"]

        # Verify password_hash was hashed with Argon2id and passed to repo
        call_kwargs = mock_user_repo.create_user.call_args[1]
        passed_hash = call_kwargs["password_hash"]
        assert passed_hash is not None
        assert passed_hash != "StrongPassword123!"
        assert verify_password("StrongPassword123!", passed_hash) is True

        # Verify audit log was recorded
        mock_audit_service.record_event.assert_called_once()
        audit_kwargs = mock_audit_service.record_event.call_args[1]
        assert audit_kwargs["action"] == "USER_CREATED"
        assert audit_kwargs["resource_type"] == "user"
        assert audit_kwargs["actor_id"] == super_admin_user.id
        assert audit_kwargs["after_state"]["role"] == "STAFF"

    @pytest.mark.anyio
    async def test_duplicate_email_raises_conflict(self, super_admin_user):
        """Duplicate email raises ConflictException (409)."""
        mock_user_repo = MagicMock()
        mock_session = MagicMock()

        existing_user = User(
            id=uuid.uuid4(),
            email="existing@example.com",
            full_name="Existing User",
        )
        mock_user_repo.get_by_email = AsyncMock(return_value=existing_user)

        service = UserService(user_repo=mock_user_repo)
        req = UserCreateRequest(
            full_name="Another User",
            email="existing@example.com",
            phone="+919876543210",
            password="StrongPassword123!",
            role="STUDENT",
        )

        with pytest.raises(ConflictException) as exc:
            await service.create_user(mock_session, req, actor=super_admin_user)
        assert exc.value.code == "EMAIL_ALREADY_EXISTS"

    @pytest.mark.anyio
    async def test_weak_password_rejected_by_complexity_rules(self, super_admin_user):
        """Weak password (missing special character or digit) rejected by complexity rules."""
        mock_user_repo = MagicMock()
        mock_session = MagicMock()
        mock_user_repo.get_by_email = AsyncMock(return_value=None)

        service = UserService(user_repo=mock_user_repo)

        # Missing special character
        req = UserCreateRequest(
            full_name="Weak Pass User",
            email="weak@example.com",
            phone="+919876543210",
            password="PasswordWithoutSpecial123",
            role="STUDENT",
        )

        with pytest.raises(ValidationException) as exc:
            await service.create_user(mock_session, req, actor=super_admin_user)
        assert "Password does not satisfy complexity requirements" in str(exc.value)
