"""FastAPI REST API integration tests for Progress Tracking & Certification.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30, 31)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1-3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901-TASK904)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)
"""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.certificate import Certificate
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.permission import Permission, RolePermission
from app.models.progress import CourseProgressSummary, LessonProgress
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)


@pytest.fixture
def db_session():
    """Provides isolated in-memory SQLite database session seeded with RBAC roles and permissions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()

    # Seed canonical permissions
    for key, module, desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=key, module=module, description=desc))

    # Seed canonical roles and permission mappings
    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(id=r_id, name=r_id.title())
        session.add(role)
        for pk in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=pk))

    session.flush()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def super_admin_user(db_session: Session) -> User:
    """Creates a Super Admin user."""
    user = User(
        email="superadmin@lms.local",
        full_name="Platform Owner",
        password_hash=hash_password("SuperSecure123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_SUPER_ADMIN)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Creates an active, verified Student user."""
    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STUDENT)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_student_user(db_session: Session) -> User:
    """Creates an un-enrolled Student user."""
    user = User(
        email="unenrolled@lms.local",
        full_name="Unenrolled Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STUDENT)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def course_with_lessons(db_session: Session, super_admin_user: User, student_user: User):
    """Creates course with 2 published lessons and student enrollment."""
    course = Course(
        title="Modern Cloud Architecture",
        slug="modern-cloud-architecture",
        headline="Learn microservices and distributed databases",
        price_inr=799900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="v1",
        created_by=super_admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()

    section = CurriculumSection(
        course_revision_id=rev.id,
        title="Module 1: Infrastructure",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    # Lesson 1: Video (600s duration, 90% = 540s)
    lesson1 = CurriculumLesson(
        section_id=section.id,
        title="Cloud Basics Video",
        lesson_type=LESSON_TYPE_VIDEO,
        duration_seconds=600,
        sort_order=0,
    )
    # Lesson 2: Article
    lesson2 = CurriculumLesson(
        section_id=section.id,
        title="Architecture Blueprint Article",
        lesson_type=LESSON_TYPE_ARTICLE,
        sort_order=1,
    )
    db_session.add_all([lesson1, lesson2])
    db_session.flush()

    # Active student enrollment
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(enrollment)
    db_session.commit()
    db_session.refresh(course)
    db_session.refresh(lesson1)
    db_session.refresh(lesson2)
    return course, lesson1, lesson2


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """TestClient overriding get_db dependency."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    """Generates valid Authorization Bearer header for user."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


class TestProgressAndCertificatesAPI:
    """Integration tests for progress heartbeat, summaries, certificate issuance, and verification."""

    def test_record_lesson_progress_video_heartbeat_and_summary(
        self,
        client: TestClient,
        student_user: User,
        course_with_lessons,
    ):
        """Posting watch heartbeats updates lesson progress and course summary metrics."""
        course, lesson1, _ = course_with_lessons
        headers = auth_headers(student_user)

        # 1. Below 90% watch threshold (e.g. 300s of 600s) -> is_completed = False
        res1 = client.post(
            f"/api/v1/progress/lessons/{lesson1.id}",
            json={"watch_position_seconds": 300},
            headers=headers,
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["lesson_id"] == str(lesson1.id)
        assert data1["is_completed"] is False
        assert data1["watch_position_seconds"] == 300
        assert data1["course_progress"]["completed_lessons_count"] == 0
        assert data1["course_progress"]["total_lessons_count"] == 2
        assert float(data1["course_progress"]["progress_percentage"]) == 0.0

        # 2. Reaching 90% watch threshold (540s of 600s) -> is_completed = True
        res2 = client.post(
            f"/api/v1/progress/lessons/{lesson1.id}",
            json={"watch_position_seconds": 540},
            headers=headers,
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["is_completed"] is True
        assert data2["completed_at"] is not None
        assert data2["course_progress"]["completed_lessons_count"] == 1
        assert float(data2["course_progress"]["progress_percentage"]) == 50.0

    def test_progress_denied_without_active_enrollment(
        self,
        client: TestClient,
        other_student_user: User,
        course_with_lessons,
    ):
        """Un-enrolled students are denied access to record progress."""
        course, lesson1, _ = course_with_lessons
        headers = auth_headers(other_student_user)

        res = client.post(
            f"/api/v1/progress/lessons/{lesson1.id}",
            json={"watch_position_seconds": 300},
            headers=headers,
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "ENROLLMENT_REQUIRED"

    def test_get_course_progress_endpoint(
        self,
        client: TestClient,
        student_user: User,
        course_with_lessons,
    ):
        """GET /api/v1/progress/courses/{course_id} retrieves accurate summary metrics."""
        course, lesson1, _ = course_with_lessons
        headers = auth_headers(student_user)

        # Complete lesson 1 first
        client.post(
            f"/api/v1/progress/lessons/{lesson1.id}",
            json={"watch_position_seconds": 600},
            headers=headers,
        )

        res = client.get(
            f"/api/v1/progress/courses/{course.id}",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["course_id"] == str(course.id)
        assert data["completed_lessons_count"] == 1
        assert data["total_lessons_count"] == 2
        assert float(data["progress_percentage"]) == 50.0
        assert str(lesson1.id) in data["completed_lesson_ids"]

    def test_certificate_issuance_and_public_verification_workflow(
        self,
        client: TestClient,
        student_user: User,
        super_admin_user: User,
        course_with_lessons,
    ):
        """Full end-to-end workflow: complete 100%, claim certificate, download PDF, publicly verify QR code, and admin revoke."""
        course, lesson1, lesson2 = course_with_lessons
        headers = auth_headers(student_user)

        # 1. Before 100%, requesting certificate returns 400 CERTIFICATE_NOT_ELIGIBLE
        not_ready_res = client.get(f"/api/v1/certificates/{course.id}", headers=headers)
        assert not_ready_res.status_code == 400
        assert not_ready_res.json()["error"]["code"] == "CERTIFICATE_NOT_ELIGIBLE"

        # 2. Complete Lesson 1 (Video)
        client.post(
            f"/api/v1/progress/lessons/{lesson1.id}",
            json={"watch_position_seconds": 600},
            headers=headers,
        )

        # 3. Complete Lesson 2 (Article) -> hits 100%
        res_comp2 = client.post(
            f"/api/v1/progress/lessons/{lesson2.id}",
            json={"is_completed": True},
            headers=headers,
        )
        assert res_comp2.status_code == 200
        assert float(res_comp2.json()["course_progress"]["progress_percentage"]) == 100.0

        # 4. GET /api/v1/certificates/{course_id} automatically retrieves issued certificate
        cert_res = client.get(f"/api/v1/certificates/{course.id}", headers=headers)
        assert cert_res.status_code == 200
        cert_data = cert_res.json()
        assert cert_data["certificate_no"].startswith("CERT-")
        assert cert_data["verification_hash"] is not None
        assert cert_data["student_name"] == student_user.full_name
        assert cert_data["course_title"] == course.title
        assert cert_data["is_revoked"] is False

        verification_hash = cert_data["verification_hash"]
        certificate_id = cert_data["id"]

        # 5. Public verification endpoint (No Auth Required)
        pub_verify_res = client.get(f"/api/v1/certificates/verify/{verification_hash}")
        assert pub_verify_res.status_code == 200
        verify_data = pub_verify_res.json()
        assert verify_data["verified"] is True
        assert verify_data["status"] == "VALID"
        assert verify_data["certificate_no"] == cert_data["certificate_no"]
        assert verify_data["student_name"] == student_user.full_name
        assert verify_data["course_title"] == course.title

        # 6. Download certificate PDF
        download_res = client.get(f"/api/v1/certificates/{course.id}/download", headers=headers)
        assert download_res.status_code == 200
        assert download_res.headers["content-type"] == "application/pdf"
        assert download_res.content.startswith(b"%PDF")

        # 7. Super Admin revokes certificate
        admin_headers = auth_headers(super_admin_user)
        revoke_res = client.post(
            f"/api/v1/certificates/{certificate_id}/revoke",
            json={"reason": "Revoked due to commercial policy violation"},
            headers=admin_headers,
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["is_revoked"] is True

        # 8. Public verification now reflects revoked status
        pub_revoked_res = client.get(f"/api/v1/certificates/verify/{verification_hash}")
        assert pub_revoked_res.status_code == 200
        revoked_verify_data = pub_revoked_res.json()
        assert revoked_verify_data["verified"] is False
        assert revoked_verify_data["status"] == "REVOKED"
        assert revoked_verify_data["revoked_reason"] == "Revoked due to commercial policy violation"
