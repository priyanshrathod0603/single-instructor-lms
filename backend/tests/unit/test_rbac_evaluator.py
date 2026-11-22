"""Unit tests for Centralized RBAC Dependency Evaluator.

Architecture Specifications:
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK202)

Verifies:
1. require_permissions evaluates granular keys with deny-overrides-allow.
2. require_permissions hard-denies suspended accounts (is_active=False).
3. Super Admin bypasses individual permission key requirements.
4. require_permissions detects missing keys and reports them in details.
5. require_role validates role membership with Super Admin bypass.
6. require_role rejects suspended accounts.
7. require_verified_student allows verified learners and elevated staff/admin, but rejects unverified learners.
"""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    require_permissions,
    require_role,
    require_verified_student,
)
from app.core.exceptions import ForbiddenException
from app.core.permissions import (
    ASSIGNMENT_GRADE,
    ASSIGNMENT_SUBMIT,
    CANONICAL_PERMISSIONS,
    COURSE_CREATE,
    COURSE_PUBLISH,
    DEFAULT_ROLE_PERMISSIONS,
    MEDIA_VIEW_PROTECTED,
    ORDERS_CREATE,
    STAFF_INVITE,
)
from app.models.base import Base
from app.models.permission import Permission, RolePermission
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    ROLE_VISITOR,
    Role,
    User,
    UserRole,
)


@pytest.fixture
def rbac_session():
    """In-memory SQLite session seeded with roles, permissions, and default mappings."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant / grader"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)

    now = datetime.now(timezone.utc)
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc, created_at=now))

    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for p_key in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=p_key, assigned_at=now))

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_user(
    session: Session,
    email: str,
    role_id: str,
    is_active: bool = True,
    is_verified: bool = True,
) -> User:
    """Helper to create and commit a user with a given role."""
    role = session.get(Role, role_id)
    user = User(
        email=email,
        full_name=f"User {role_id}",
        is_active=is_active,
        is_verified=is_verified,
    )
    user.user_roles.append(UserRole(role_id=role_id, role=role))
    session.add(user)
    session.commit()
    return user


class TestRequirePermissionsDependency:
    """Verifies require_permissions dependency evaluator."""

    @pytest.mark.asyncio
    async def test_student_permitted_for_student_actions(self, rbac_session: Session):
        """Student possesses assignment:submit and orders:create."""
        student = make_user(rbac_session, "alice@example.com", ROLE_STUDENT)
        checker = require_permissions(ASSIGNMENT_SUBMIT)
        result = await checker(current_user=student)
        assert result.id == student.id

    @pytest.mark.asyncio
    async def test_student_denied_for_staff_or_admin_actions(self, rbac_session: Session):
        """Student lacks assignment:grade and course:create."""
        student = make_user(rbac_session, "bob@example.com", ROLE_STUDENT)
        checker = require_permissions(ASSIGNMENT_GRADE)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker(current_user=student)
        assert exc_info.value.code == "PERMISSION_DENIED"
        assert "Missing required permission" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_staff_permitted_for_grading_denied_course_create(self, rbac_session: Session):
        """Staff possesses assignment:grade, but lacks course:create."""
        staff = make_user(rbac_session, "grader@example.com", ROLE_STAFF)
        checker_grade = require_permissions(ASSIGNMENT_GRADE)
        res = await checker_grade(current_user=staff)
        assert res.id == staff.id

        checker_create = require_permissions(COURSE_CREATE)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker_create(current_user=staff)
        assert exc_info.value.code == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_suspended_user_hard_denied_before_permissions(self, rbac_session: Session):
        """Inactive user (is_active=False) is hard-denied with ACCOUNT_SUSPENDED."""
        suspended_student = make_user(rbac_session, "bad@example.com", ROLE_STUDENT, is_active=False)
        checker = require_permissions(ASSIGNMENT_SUBMIT)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker(current_user=suspended_student)
        assert exc_info.value.code == "ACCOUNT_SUSPENDED"

    @pytest.mark.asyncio
    async def test_suspended_super_admin_hard_denied(self, rbac_session: Session):
        """Even Super Admin is denied if their account is marked inactive."""
        suspended_super = make_user(rbac_session, "super_bad@example.com", ROLE_SUPER_ADMIN, is_active=False)
        checker = require_permissions(COURSE_CREATE)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker(current_user=suspended_super)
        assert exc_info.value.code == "ACCOUNT_SUSPENDED"

    @pytest.mark.asyncio
    async def test_active_super_admin_bypasses_all_permission_keys(self, rbac_session: Session):
        """Active Super Admin bypasses individual permission key requirements."""
        super_admin = make_user(rbac_session, "boss@example.com", ROLE_SUPER_ADMIN)
        checker = require_permissions("non_existent:fake_action", COURSE_PUBLISH)
        result = await checker(current_user=super_admin)
        assert result.id == super_admin.id

    @pytest.mark.asyncio
    async def test_multi_permission_evaluation(self, rbac_session: Session):
        """Evaluates multiple permissions; all must be present."""
        admin = make_user(rbac_session, "admin@example.com", ROLE_ADMIN)
        checker_success = require_permissions(COURSE_CREATE, STAFF_INVITE)
        res = await checker_success(current_user=admin)
        assert res.id == admin.id

        # Admin has COURSE_CREATE but not COURSE_PUBLISH
        checker_fail = require_permissions(COURSE_CREATE, COURSE_PUBLISH)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker_fail(current_user=admin)
        assert exc_info.value.code == "PERMISSION_DENIED"
        assert exc_info.value.details["missing_permissions"] == [COURSE_PUBLISH]


class TestRequireRoleDependency:
    """Verifies require_role dependency evaluator."""

    @pytest.mark.asyncio
    async def test_allowed_role_succeeds(self, rbac_session: Session):
        """User with matching role succeeds."""
        admin = make_user(rbac_session, "admin2@example.com", ROLE_ADMIN)
        checker = require_role(ROLE_ADMIN, ROLE_STAFF)
        res = await checker(current_user=admin)
        assert res.id == admin.id

    @pytest.mark.asyncio
    async def test_unauthorized_role_fails(self, rbac_session: Session):
        """Student attempting staff/admin role-gated action is rejected."""
        student = make_user(rbac_session, "student2@example.com", ROLE_STUDENT)
        checker = require_role(ROLE_ADMIN, ROLE_STAFF)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker(current_user=student)
        assert exc_info.value.code == "ROLE_NOT_AUTHORIZED"

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_role_restriction(self, rbac_session: Session):
        """Super Admin passes even if explicit role list only specifies STAFF."""
        super_admin = make_user(rbac_session, "boss2@example.com", ROLE_SUPER_ADMIN)
        checker = require_role(ROLE_STAFF)
        res = await checker(current_user=super_admin)
        assert res.id == super_admin.id

    @pytest.mark.asyncio
    async def test_suspended_user_denied_role_check(self, rbac_session: Session):
        """Suspended user fails with ACCOUNT_SUSPENDED before role check."""
        suspended = make_user(rbac_session, "susp@example.com", ROLE_ADMIN, is_active=False)
        checker = require_role(ROLE_ADMIN)
        with pytest.raises(ForbiddenException) as exc_info:
            await checker(current_user=suspended)
        assert exc_info.value.code == "ACCOUNT_SUSPENDED"


class TestRequireVerifiedStudentDependency:
    """Verifies require_verified_student dependency."""

    @pytest.mark.asyncio
    async def test_verified_student_allowed(self, rbac_session: Session):
        """Active verified student is allowed."""
        student = make_user(rbac_session, "verified@example.com", ROLE_STUDENT, is_verified=True)
        res = await require_verified_student(current_user=student)
        assert res.id == student.id

    @pytest.mark.asyncio
    async def test_unverified_student_rejected(self, rbac_session: Session):
        """Active unverified student is rejected with EMAIL_NOT_VERIFIED."""
        student = make_user(rbac_session, "unverified@example.com", ROLE_STUDENT, is_verified=False)
        with pytest.raises(ForbiddenException) as exc_info:
            await require_verified_student(current_user=student)
        assert exc_info.value.code == "EMAIL_NOT_VERIFIED"

    @pytest.mark.asyncio
    async def test_admin_staff_bypass_email_verification(self, rbac_session: Session):
        """Staff and Admin bypass learner email verification check."""
        staff = make_user(rbac_session, "unverified_staff@example.com", ROLE_STAFF, is_verified=False)
        res = await require_verified_student(current_user=staff)
        assert res.id == staff.id
