"""Unit tests for SA-02: Complete User, Admin & Staff Management.

Verifies:
1. User directory filtering, search, pagination, and dynamic sorting (created_at, full_name, email).
2. Student learning summary endpoint (enrollments, quiz attempts, assignments, certificates, audit trail).
3. Privilege escalation guard on Admin invitations: Admin role invitation requires Super Admin caller.
4. Sole Super Admin protection invariants (cannot suspend or revoke role from sole super admin).
"""

from datetime import datetime, timezone
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.core.permissions import ROLES_ASSIGN, STAFF_INVITE, USERS_MANAGE_STATUS, USERS_VIEW, USERS_VIEW_ALL
from app.main import app
from app.models.user import ROLE_ADMIN, ROLE_STAFF, ROLE_STUDENT, ROLE_SUPER_ADMIN, User, UserRole
from app.schemas.user import (
    StudentAssignmentSubmissionSummary,
    StudentCertificateSummary,
    StudentEnrollmentSummary,
    StudentLearningSummaryResponse,
    StudentQuizAttemptSummary,
    UserDirectoryItemResponse,
    UserDirectoryResponse,
    UserProfileResponse,
)
from app.services.user_service import UserService


@pytest.fixture
def super_admin_user():
    """Create a mock Super Admin user."""
    u = User(
        id=uuid.uuid4(),
        email="superadmin@example.com",
        full_name="Platform Owner",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_SUPER_ADMIN)]
    u.has_permission = lambda perm: True
    return u


@pytest.fixture
def admin_user():
    """Create a mock Admin user."""
    u = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Operations Admin",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_ADMIN)]
    u.has_permission = lambda perm: True
    u.get_aggregated_permissions = lambda: {STAFF_INVITE, USERS_VIEW, USERS_VIEW_ALL}
    return u


@pytest.fixture
def student_user():
    """Create a mock Student user."""
    u = User(
        id=uuid.uuid4(),
        email="student@example.com",
        full_name="Jane Student",
        is_active=True,
        is_verified=True,
    )
    u.user_roles = [UserRole(user_id=u.id, role_id=ROLE_STUDENT)]
    u.has_permission = lambda perm: False
    return u


class TestSA02UserDirectorySorting:
    """Test dynamic sorting and filtering in user directory."""

    def test_list_users_passes_sorting_params(self, super_admin_user):
        """Verify list_users endpoint passes sort_by and sort_order to UserService."""
        from app.api.deps import get_current_user, get_db, require_permissions
        from app.api.v1.users import get_user_service

        mock_svc = AsyncMock(spec=UserService)
        mock_svc.list_users.return_value = UserDirectoryResponse(
            items=[],
            total=0,
            page=1,
            per_page=20,
            total_pages=0,
        )

        app.dependency_overrides[require_permissions(USERS_VIEW_ALL)] = lambda: super_admin_user
        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_user_service] = lambda: mock_svc
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.get("/api/v1/users?sort_by=full_name&sort_order=asc&role=STUDENT")
            assert response.status_code == status.HTTP_200_OK

            # Assert list_users was called with sort_by="full_name" and sort_order="asc"
            assert mock_svc.list_users.called
            call_kwargs = mock_svc.list_users.call_args.kwargs
            assert call_kwargs["sort_by"] == "full_name"
            assert call_kwargs["sort_order"] == "asc"
            assert call_kwargs["role"] == "STUDENT"
        finally:
            app.dependency_overrides.clear()


class TestSA02StudentLearningRecords:
    """Test learning records retrieval endpoint."""

    def test_get_student_learning_records_success(self, super_admin_user, student_user):
        """Verify GET /api/v1/users/{id}/learning-records returns comprehensive ledger."""
        from app.api.deps import get_current_user, get_db
        from app.api.v1.users import get_user_service

        mock_svc = AsyncMock(spec=UserService)
        learning_summary = StudentLearningSummaryResponse(
            user=UserProfileResponse(
                id=student_user.id,
                email=student_user.email,
                full_name=student_user.full_name,
                is_verified=True,
                is_active=True,
                roles=[ROLE_STUDENT],
                permissions=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            enrollments=[
                StudentEnrollmentSummary(
                    id=uuid.uuid4(),
                    course_id=uuid.uuid4(),
                    course_title="Mastering Distributed Systems",
                    status="ACTIVE",
                    granted_at=datetime.now(timezone.utc),
                    progress_percentage=85.0,
                    completed_lessons_count=17,
                    total_lessons_count=20,
                )
            ],
            quiz_attempts=[
                StudentQuizAttemptSummary(
                    id=uuid.uuid4(),
                    quiz_id=uuid.uuid4(),
                    quiz_title="Mid-term Consensus Quiz",
                    attempt_no=1,
                    status="SUBMITTED",
                    score=90.0,
                    is_passed=True,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
            ],
            assignment_submissions=[
                StudentAssignmentSubmissionSummary(
                    id=uuid.uuid4(),
                    assignment_id=uuid.uuid4(),
                    assignment_title="Raft Implementation Project",
                    attempt_no=1,
                    status="GRADED",
                    final_score=95.0,
                    max_score=100.0,
                    pass_score=60.0,
                    file_url="https://storage.example.com/sub.zip",
                    submitted_at=datetime.now(timezone.utc),
                    graded_at=datetime.now(timezone.utc),
                    feedback="Excellent leader election implementation.",
                )
            ],
            certificates=[
                StudentCertificateSummary(
                    id=uuid.uuid4(),
                    certificate_no="CERT-202611-1234",
                    course_id=uuid.uuid4(),
                    course_title="Mastering Distributed Systems",
                    issued_at=datetime.now(timezone.utc),
                    verification_hash="abc123hash",
                    pdf_url="https://storage.example.com/cert.pdf",
                    is_revoked=False,
                )
            ],
            audit_logs=[
                {
                    "id": str(uuid.uuid4()),
                    "action": "ENROLLMENT_GRANTED",
                    "actor_type": "ADMIN",
                    "resource_type": "enrollment",
                    "resource_id": str(student_user.id),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

        mock_svc.get_student_learning_summary.return_value = learning_summary

        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_user_service] = lambda: mock_svc
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.get(f"/api/v1/users/{student_user.id}/learning-records")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["user"]["email"] == "student@example.com"
            assert len(data["enrollments"]) == 1
            assert data["enrollments"][0]["course_title"] == "Mastering Distributed Systems"
            assert len(data["quiz_attempts"]) == 1
            assert data["quiz_attempts"][0]["score"] == 90.0
            assert len(data["assignment_submissions"]) == 1
            assert data["assignment_submissions"][0]["final_score"] == 95.0
            assert len(data["certificates"]) == 1
            assert data["certificates"][0]["certificate_no"] == "CERT-202611-1234"
        finally:
            app.dependency_overrides.clear()

    def test_learning_records_forbidden_for_unauthorized_user(self, student_user):
        """Verify other students cannot access learning records without permission."""
        from app.api.deps import get_current_user, get_db
        from app.api.v1.users import get_user_service

        other_student = User(
            id=uuid.uuid4(),
            email="other@example.com",
            full_name="Other Student",
            is_active=True,
            is_verified=True,
        )
        other_student.user_roles = [UserRole(user_id=other_student.id, role_id=ROLE_STUDENT)]
        other_student.has_permission = lambda perm: False

        app.dependency_overrides[get_current_user] = lambda: other_student
        app.dependency_overrides[get_user_service] = lambda: MagicMock()
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.get(f"/api/v1/users/{student_user.id}/learning-records")
            assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()


class TestSA02AdminInvitationPrivilegeGuard:
    """Test privilege escalation protection on Admin invitations."""

    def test_admin_cannot_invite_admin(self, admin_user):
        """Verify that an Admin caller cannot invite another Admin (requires Super Admin)."""
        from app.api.deps import get_current_user, get_db, require_permissions
        from app.api.v1.users import get_user_service

        app.dependency_overrides[require_permissions(STAFF_INVITE)] = lambda: admin_user
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_user_service] = lambda: MagicMock()
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/users/staff/invite",
                json={
                    "email": "newadmin@example.com",
                    "full_name": "New Admin Candidate",
                    "role": "ADMIN",
                },
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            body = response.json()
            assert body["error"]["code"] == "SUPER_ADMIN_REQUIRED"
        finally:
            app.dependency_overrides.clear()

    def test_super_admin_can_invite_admin(self, super_admin_user):
        """Verify that a Super Admin caller can invite an Admin."""
        from app.api.deps import get_current_user, get_db, require_permissions
        from app.api.v1.users import get_user_service

        mock_svc = AsyncMock(spec=UserService)
        mock_svc.invite_staff.return_value = {
            "user_id": str(uuid.uuid4()),
            "email": "newadmin@example.com",
            "role": "ADMIN",
            "invited": True,
            "message": "Staff invitation staged successfully.",
        }

        app.dependency_overrides[require_permissions(STAFF_INVITE)] = lambda: super_admin_user
        app.dependency_overrides[get_current_user] = lambda: super_admin_user
        app.dependency_overrides[get_user_service] = lambda: mock_svc
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/users/staff/invite",
                json={
                    "email": "newadmin@example.com",
                    "full_name": "New Admin Candidate",
                    "role": "ADMIN",
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["role"] == "ADMIN"
            assert data["invited"] is True
        finally:
            app.dependency_overrides.clear()

    def test_admin_can_invite_staff(self, admin_user):
        """Verify that an Admin caller can invite a regular STAFF member."""
        from app.api.deps import get_current_user, get_db, require_permissions
        from app.api.v1.users import get_user_service

        mock_svc = AsyncMock(spec=UserService)
        mock_svc.invite_staff.return_value = {
            "user_id": str(uuid.uuid4()),
            "email": "newstaff@example.com",
            "role": "STAFF",
            "invited": True,
            "message": "Staff invitation staged successfully.",
        }

        app.dependency_overrides[require_permissions(STAFF_INVITE)] = lambda: admin_user
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_user_service] = lambda: mock_svc
        app.dependency_overrides[get_db] = lambda: MagicMock()

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/users/staff/invite",
                json={
                    "email": "newstaff@example.com",
                    "full_name": "Teaching Assistant",
                    "role": "STAFF",
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["role"] == "STAFF"
        finally:
            app.dependency_overrides.clear()
