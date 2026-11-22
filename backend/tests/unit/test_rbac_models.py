"""Unit tests for RBAC Permission, RolePermission, and Notification models.

Verifies:
1. Canonical permissions registry integrity (35 permissions across 8 functional modules).
2. Permission and RolePermission model instantiation and string representation.
3. Notification model defaults, unread state, and serialization safety.
4. User role aggregation: get_aggregated_permissions() and has_permission().
5. Multi-role permission union (e.g. Student + Staff inherits permissions from both).
6. Super Admin permission inheritance (all permissions possessed automatically).
7. AuthToken TOKEN_TYPE_STAFF_ONBOARDING presence in AUTH_TOKEN_TYPES.
"""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.permissions import (
    ALL_PERMISSION_KEYS,
    ASSIGNMENT_GRADE,
    ASSIGNMENT_SUBMIT,
    ASSIGNMENT_VIEW_ALL,
    AUDIT_VIEW,
    CANONICAL_PERMISSIONS,
    COURSE_CREATE,
    COURSE_PUBLISH,
    COURSE_VIEW_ALL,
    COURSE_VIEW_PUBLIC,
    DEFAULT_ROLE_PERMISSIONS,
    MEDIA_VIEW_PROTECTED,
    ORDERS_CREATE,
    STAFF_INVITE,
    USERS_VIEW,
)
from app.models.auth_token import AUTH_TOKEN_TYPES, TOKEN_TYPE_STAFF_ONBOARDING
from app.models.base import Base
from app.models.notification import (
    NOTIFICATION_TYPE_ANNOUNCEMENT,
    NOTIFICATION_TYPE_ENROLLMENT,
    Notification,
)
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
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed roles
    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant / grader"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)

    # Seed permissions
    now = datetime.now(timezone.utc)
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc, created_at=now))

    # Seed role permissions
    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for p_key in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=p_key, assigned_at=now))

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestCanonicalPermissionsRegistry:
    """Verifies the static canonical permissions registry and defaults."""

    def test_canonical_permissions_count_and_uniqueness(self):
        """Should have 45 unique canonical permissions (35 baseline + 4 SA-03 + 3 SA-04 + 3 SA-05)."""
        assert len(CANONICAL_PERMISSIONS) == 45
        keys = [p[0] for p in CANONICAL_PERMISSIONS]
        assert len(keys) == len(set(keys))
        assert len(ALL_PERMISSION_KEYS) == 45

    def test_default_role_permission_mappings_conform_to_blueprint(self):
        """Roles must possess their blueprint-mandated permissions."""
        assert COURSE_VIEW_PUBLIC in DEFAULT_ROLE_PERMISSIONS[ROLE_VISITOR]
        assert len(DEFAULT_ROLE_PERMISSIONS[ROLE_VISITOR]) == 1

        student_perms = DEFAULT_ROLE_PERMISSIONS[ROLE_STUDENT]
        assert ASSIGNMENT_SUBMIT in student_perms
        assert MEDIA_VIEW_PROTECTED in student_perms
        assert ORDERS_CREATE in student_perms
        assert COURSE_CREATE not in student_perms
        assert COURSE_PUBLISH not in student_perms

        staff_perms = DEFAULT_ROLE_PERMISSIONS[ROLE_STAFF]
        assert ASSIGNMENT_VIEW_ALL in staff_perms
        assert ASSIGNMENT_GRADE in staff_perms
        assert COURSE_CREATE not in staff_perms
        assert ORDERS_CREATE not in staff_perms

        admin_perms = DEFAULT_ROLE_PERMISSIONS[ROLE_ADMIN]
        assert COURSE_CREATE in admin_perms
        assert COURSE_VIEW_ALL in admin_perms
        assert STAFF_INVITE in admin_perms
        assert COURSE_PUBLISH not in admin_perms  # Super Admin only
        assert "sessions:view_all" not in admin_perms  # Super Admin only (SA-03)
        assert "sessions:revoke" not in admin_perms  # Super Admin only (SA-03)
        assert "courses:govern" not in admin_perms  # Super Admin only (SA-04)
        assert "blog:manage" not in admin_perms  # Super Admin only (SA-04)
        assert "notes:manage" not in admin_perms  # Super Admin only (SA-04)
        assert "offers:manage" not in admin_perms  # Super Admin only (SA-05)
        assert "payments:view_all" not in admin_perms  # Super Admin only (SA-05)
        assert "settings:manage" not in admin_perms  # Super Admin only (SA-05)

        super_admin_perms = DEFAULT_ROLE_PERMISSIONS[ROLE_SUPER_ADMIN]
        assert COURSE_PUBLISH in super_admin_perms
        assert AUDIT_VIEW in super_admin_perms
        assert "sessions:view_all" in super_admin_perms
        assert "sessions:revoke" in super_admin_perms
        assert "security:metrics_view" in super_admin_perms
        assert "control:revoke_others" in super_admin_perms
        assert "courses:govern" in super_admin_perms
        assert "blog:manage" in super_admin_perms
        assert "notes:manage" in super_admin_perms
        assert "offers:manage" in super_admin_perms
        assert "payments:view_all" in super_admin_perms
        assert "settings:manage" in super_admin_perms
        assert len(super_admin_perms) == 45

    def test_auth_token_type_includes_staff_onboarding(self):
        """AUTH_TOKEN_TYPES must include TOKEN_TYPE_STAFF_ONBOARDING."""
        assert TOKEN_TYPE_STAFF_ONBOARDING == "STAFF_ONBOARDING"
        assert TOKEN_TYPE_STAFF_ONBOARDING in AUTH_TOKEN_TYPES


class TestRBACModels:
    """Verifies Permission, RolePermission, and Notification model instantiation."""

    def test_permission_model_instantiation(self, db_session: Session):
        """Permission model stores id, module, description, and created_at."""
        perm = db_session.get(Permission, COURSE_CREATE)
        assert perm is not None
        assert perm.id == "course:create"
        assert perm.module == "courses"
        assert "create" in perm.description.lower()
        assert repr(perm) == "<Permission id='course:create' module='courses'>"

    def test_role_permission_model_instantiation(self, db_session: Session):
        """RolePermission connects a role to a permission."""
        rp = db_session.get(RolePermission, (ROLE_ADMIN, COURSE_CREATE))
        assert rp is not None
        assert rp.role_id == ROLE_ADMIN
        assert rp.permission_id == COURSE_CREATE
        assert repr(rp) == "<RolePermission role_id='ADMIN' permission_id='course:create'>"

    def test_notification_model_instantiation_and_defaults(self, db_session: Session):
        """Notification model initializes with unread state and UUID PK."""
        user = User(email="learner@example.com", full_name="Learner")
        db_session.add(user)
        db_session.flush()

        notif = Notification(
            user_id=user.id,
            title="Enrollment Confirmed",
            message="Welcome to Full-Stack Architecture!",
            notification_type=NOTIFICATION_TYPE_ENROLLMENT,
            data={"course_id": "c1f7a28e-5b1b-4d4b-9c3f-7e8e12345678"},
        )
        db_session.add(notif)
        db_session.commit()

        loaded = db_session.get(Notification, notif.id)
        assert loaded is not None
        assert loaded.is_read is False
        assert loaded.notification_type == NOTIFICATION_TYPE_ENROLLMENT
        assert loaded.data["course_id"] == "c1f7a28e-5b1b-4d4b-9c3f-7e8e12345678"
        assert "Notification" in repr(loaded)


class TestUserPermissionAggregation:
    """Verifies User.get_aggregated_permissions() and User.has_permission()."""

    def test_student_aggregated_permissions(self, db_session: Session):
        """Student has student permissions, but not staff or admin permissions."""
        student_role = db_session.get(Role, ROLE_STUDENT)
        user = User(email="student@example.com", full_name="Student Test")
        user.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=student_role))
        db_session.add(user)
        db_session.commit()

        perms = user.get_aggregated_permissions()
        assert ASSIGNMENT_SUBMIT in perms
        assert MEDIA_VIEW_PROTECTED in perms
        assert ORDERS_CREATE in perms
        assert COURSE_CREATE not in perms
        assert user.has_permission(ASSIGNMENT_SUBMIT) is True
        assert user.has_permission(COURSE_CREATE) is False

    def test_multi_role_union_aggregation(self, db_session: Session):
        """User with multiple roles receives the union of permissions from both roles."""
        student_role = db_session.get(Role, ROLE_STUDENT)
        staff_role = db_session.get(Role, ROLE_STAFF)

        user = User(email="ta@example.com", full_name="Teaching Assistant")
        user.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=student_role))
        user.user_roles.append(UserRole(role_id=ROLE_STAFF, role=staff_role))
        db_session.add(user)
        db_session.commit()

        perms = user.get_aggregated_permissions()
        # Student permission
        assert ASSIGNMENT_SUBMIT in perms
        # Staff permission
        assert ASSIGNMENT_GRADE in perms
        assert ASSIGNMENT_VIEW_ALL in perms
        # Still not an admin
        assert COURSE_CREATE not in perms
        assert user.has_permission(ASSIGNMENT_SUBMIT) is True
        assert user.has_permission(ASSIGNMENT_GRADE) is True
        assert user.has_permission(COURSE_CREATE) is False

    def test_super_admin_receives_all_permissions_automatically(self, db_session: Session):
        """Super Admin receives all platform permissions and has_permission always returns True."""
        super_admin_role = db_session.get(Role, ROLE_SUPER_ADMIN)
        user = User(email="instructor@example.com", full_name="Chief Instructor")
        user.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, role=super_admin_role))
        db_session.add(user)
        db_session.commit()

        perms = user.get_aggregated_permissions()
        assert len(perms) == 45
        assert user.has_permission(COURSE_PUBLISH) is True
        assert user.has_permission(AUDIT_VIEW) is True
        assert user.has_permission("non_existent:permission") is True  # Super admin bypass
