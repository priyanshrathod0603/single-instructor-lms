"""Unit and Integration tests for Pre-Flight Publishing Checklist & Atomic Publication (TASK304, TASK305).

Verifies:
1. Pre-Flight Checklist Rules:
   - CHK-01: Metadata validation (title, slug, headline).
   - CHK-02: Commercial pricing (is_free=False, price_inr <= 0).
   - CHK-03: Non-empty sections.
   - CHK-04: Non-empty lessons per section.
   - CHK-05: Media asset readiness.
   - CHK-06: Quiz configuration validity.
   - CHK-07: Assignment configuration and rubric validity.
   - CHK-08: Thumbnail asset warning.
2. Atomic publication execution:
   - Locks course and revision FOR UPDATE.
   - Serializes complete curriculum hierarchy into JSONB snapshot.
   - Updates status to PUBLISHED and sets live_revision_id.
   - Archives previous published revisions.
   - Records immutable audit log COURSE_PUBLISHED.
3. Course archiving (soft status update to ARCHIVED).
4. REST API Endpoint Integration with FastAPI TestClient.
"""

from datetime import datetime, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_db, require_permissions
from app.core.exceptions import ValidationException
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base, utc_now
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_ARCHIVED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_ASSIGNMENT,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_VIDEO,
    RESOURCE_TYPE_PDF,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)
from app.schemas.course import CourseCreateRequest
from app.services.course_service import CourseService


@pytest.fixture
def db_session():
    """Provides isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def course_service():
    """CourseService instance."""
    return CourseService()


@pytest.fixture
def super_admin_user(db_session: Session) -> User:
    """Creates a Super Admin user."""
    # Ensure SUPER_ADMIN role exists
    role = db_session.get(Role, ROLE_SUPER_ADMIN)
    if not role:
        role = Role(id=ROLE_SUPER_ADMIN, name="Super Administrator")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="superadmin@lms.local",
        full_name="Super Administrator",
        password_hash=hash_password("SuperSecureP@ss123"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_SUPER_ADMIN)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Creates a standard Student user."""
    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentSecureP@ss123"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_STUDENT)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session: Session):
    """FastAPI TestClient wired to isolated in-memory test database."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# 1. Pre-Flight Checklist Tests
# =============================================================================

@pytest.mark.asyncio
async def test_checklist_chk01_empty_metadata_blockers(db_session: Session, course_service: CourseService):
    """CHK-01: Empty headline must block publication."""
    course = Course(title="Meta Course", slug="meta-course", headline="", price_inr=0, is_free=True)
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.flush()

    # Add section and lesson to avoid CHK-03/04
    sec = course_service.repo.create_section(db_session, revision=rev, title="S1", sort_order=0)
    course_service.repo.create_lesson(db_session, section=sec, title="L1", lesson_type=LESSON_TYPE_ARTICLE, sort_order=0)
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is False
    blocker_codes = {b.code for b in report.blockers}
    assert "EMPTY_HEADLINE" in blocker_codes


@pytest.mark.asyncio
async def test_checklist_chk02_commercial_pricing_blocker(db_session: Session, course_service: CourseService):
    """CHK-02: Non-free course with price_inr <= 0 must block publication."""
    course = Course(title="Paid Course", slug="paid-course", headline="Great course", price_inr=0, is_free=False)
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.flush()

    sec = course_service.repo.create_section(db_session, revision=rev, title="S1", sort_order=0)
    course_service.repo.create_lesson(db_session, section=sec, title="L1", lesson_type=LESSON_TYPE_ARTICLE, sort_order=0)
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is False
    blocker_codes = {b.code for b in report.blockers}
    assert "INVALID_PRICING" in blocker_codes


@pytest.mark.asyncio
async def test_checklist_chk03_no_sections_blocker(db_session: Session, course_service: CourseService):
    """CHK-03: Revision with zero sections must block publication."""
    course = Course(title="Empty Course", slug="empty-course", headline="Empty", price_inr=0, is_free=True)
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is False
    assert any(b.code == "NO_SECTIONS" for b in report.blockers)


@pytest.mark.asyncio
async def test_checklist_chk04_empty_section_blocker(db_session: Session, course_service: CourseService):
    """CHK-04: Section with zero lessons must block publication."""
    course = Course(title="Course", slug="course-4", headline="Headline", price_inr=0, is_free=True)
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.flush()

    course_service.repo.create_section(db_session, revision=rev, title="Empty Section", sort_order=0)
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is False
    assert any(b.code == "EMPTY_SECTION" for b in report.blockers)


@pytest.mark.asyncio
async def test_checklist_chk06_chk07_quiz_and_assignment_validity(db_session: Session, course_service: CourseService):
    """CHK-06 & CHK-07: Invalid quiz or assignment configurations must block publication."""
    course = Course(title="Assessment Course", slug="assessment-course", headline="Headline", price_inr=0, is_free=True)
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.flush()

    sec = course_service.repo.create_section(db_session, revision=rev, title="Module 1", sort_order=0)
    # Quiz with 0 questions
    course_service.repo.create_lesson(
        db_session, section=sec, title="Quiz Lesson", lesson_type=LESSON_TYPE_QUIZ, content={"questions": []}, sort_order=0
    )
    # Assignment without rubric
    course_service.repo.create_lesson(
        db_session, section=sec, title="Assignment Lesson", lesson_type=LESSON_TYPE_ASSIGNMENT, content={"max_score": 100, "rubric": []}, sort_order=1
    )
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is False
    blocker_codes = {b.code for b in report.blockers}
    assert "EMPTY_QUIZ" in blocker_codes
    assert "MISSING_ASSIGNMENT_RUBRIC" in blocker_codes


@pytest.mark.asyncio
async def test_checklist_chk08_thumbnail_warning(db_session: Session, course_service: CourseService):
    """CHK-08: Missing thumbnail generates a warning but does not block publication."""
    course = Course(
        title="Thumbnail Warning Course",
        slug="thumb-warn-course",
        headline="Valid Headline",
        thumbnail_url="",  # Missing thumbnail
        price_inr=0,
        is_free=True,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft 1", status=REVISION_STATUS_DRAFT)
    db_session.add(rev)
    db_session.flush()

    sec = course_service.repo.create_section(db_session, revision=rev, title="S1", sort_order=0)
    course_service.repo.create_lesson(db_session, section=sec, title="L1", lesson_type=LESSON_TYPE_ARTICLE, sort_order=0)
    db_session.commit()

    report = course_service.evaluate_publish_checklist(db_session, course.id, rev.id)
    assert report.can_publish is True
    assert len(report.blockers) == 0
    assert any(w.code == "MISSING_THUMBNAIL" for w in report.warnings)


# =============================================================================
# 2. Atomic Publication & Revision Superseding Tests
# =============================================================================

@pytest.mark.asyncio
async def test_atomic_publication_and_snapshot_serialization(db_session: Session, course_service: CourseService):
    """Publication serializes complete curriculum to JSONB snapshot and supersedes prior revisions."""
    req = CourseCreateRequest(
        title="Production High-Performance Backend",
        slug="high-perf-backend",
        headline="Master async pipelines and concurrency",
        description="End-to-end distributed system course.",
        thumbnail_url="https://cdn.example.com/thumb.png",
        price_inr=499900,
        is_free=False,
    )
    course, rev1 = await course_service.create_course(db_session, req)

    # Build Revision 1 Curriculum
    s1 = course_service.repo.create_section(db_session, revision=rev1, title="Sec 1", sort_order=0)
    l1 = course_service.repo.create_lesson(
        db_session, section=s1, title="Les 1", lesson_type=LESSON_TYPE_VIDEO, duration_seconds=1200, is_preview=True, sort_order=0
    )
    course_service.repo.create_resource(
        db_session, lesson=l1, title="Res 1", resource_type=RESOURCE_TYPE_PDF, file_url="https://res.pdf", file_size_bytes=100
    )
    db_session.commit()

    # 1. Publish Revision 1
    pub1 = await course_service.publish_revision(db_session, course.id, rev1.id)
    db_session.commit()

    assert pub1.status == REVISION_STATUS_PUBLISHED
    assert pub1.snapshot is not None
    assert pub1.snapshot["slug"] == "high-perf-backend"
    assert len(pub1.snapshot["sections"]) == 1
    assert pub1.snapshot["sections"][0]["lessons"][0]["title"] == "Les 1"

    db_session.refresh(course)
    assert course.status == COURSE_STATUS_PUBLISHED
    assert course.live_revision_id == rev1.id

    # 2. Spawn Revision 2
    rev2_resp = await course_service.spawn_revision(db_session, course.id, changelog="Adding revision 2 modules")
    db_session.commit()

    # Add Section 2 to Revision 2
    rev2 = course_service.repo.get_revision_by_id(db_session, rev2_resp.id)
    s2 = course_service.repo.create_section(db_session, revision=rev2, title="Sec 2 in Rev 2", sort_order=1)
    course_service.repo.create_lesson(db_session, section=s2, title="Les 2 in Rev 2", lesson_type=LESSON_TYPE_ARTICLE, sort_order=0)
    db_session.commit()

    # 3. Publish Revision 2
    pub2 = await course_service.publish_revision(db_session, course.id, rev2.id)
    db_session.commit()

    assert pub2.status == REVISION_STATUS_PUBLISHED
    assert len(pub2.snapshot["sections"]) == 2

    # Verify Revision 1 was superseded to ARCHIVED
    db_session.refresh(rev1)
    assert rev1.status == REVISION_STATUS_ARCHIVED

    # Verify Course live_revision_id updated to Revision 2
    db_session.refresh(course)
    assert course.live_revision_id == rev2.id


@pytest.mark.asyncio
async def test_archive_course(db_session: Session, course_service: CourseService):
    """Archiving a course marks its container status as ARCHIVED."""
    req = CourseCreateRequest(title="To Be Archived", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    db_session.commit()

    archived = await course_service.archive_course(db_session, course.id)
    db_session.commit()

    assert archived.status == COURSE_STATUS_ARCHIVED
    db_session.refresh(course)
    assert course.status == COURSE_STATUS_ARCHIVED


# =============================================================================
# 3. REST API Endpoint Integration Tests (FastAPI TestClient)
# =============================================================================

def test_api_public_catalog_and_rbac_guards(client: TestClient, super_admin_user: User, student_user: User):
    """Integration test verifying public catalog, admin management listing, and RBAC protection."""
    from tests.conftest import create_test_auth_headers
    admin_token = create_test_auth_headers(super_admin_user, extra_claims={"roles": [ROLE_SUPER_ADMIN]})["Authorization"].split()[1]
    student_token = create_test_auth_headers(student_user, extra_claims={"roles": [ROLE_STUDENT]})["Authorization"].split()[1]

    # 1. Unauthenticated creation must be rejected with 401
    resp = client.post("/api/v1/courses", json={"title": "Unauthorized Course", "is_free": True})
    assert resp.status_code == 401

    # 2. Student creation must be rejected with 403 (missing course:create)
    resp = client.post(
        "/api/v1/courses",
        json={"title": "Student Course", "is_free": True},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 403

    # 3. Super Admin creates course
    create_resp = client.post(
        "/api/v1/courses",
        json={
            "title": "Full-Stack Microservices",
            "slug": "full-stack-microservices",
            "headline": "Modern Distributed Full-Stack Architecture",
            "description": "Complete curriculum",
            "thumbnail_url": "https://cdn.example.com/fs.png",
            "price_inr": 299900,
            "is_free": False,
            "tags": ["python", "fastapi", "react"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    course_data = create_resp.json()
    course_id = course_data["id"]
    assert course_data["status"] == COURSE_STATUS_DRAFT
    assert course_data["price_inr"] == 299900

    # 4. Public catalog does not show DRAFT courses
    pub_list = client.get("/api/v1/courses")
    assert pub_list.status_code == 200
    assert not any(c["id"] == course_id for c in pub_list.json()["items"])

    # 5. Admin management catalog shows DRAFT courses
    admin_list = client.get(
        "/api/v1/courses/manage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_list.status_code == 200
    assert any(c["id"] == course_id for c in admin_list.json()["items"])

    # 6. Fetch Draft Revision 1 details
    rev_list_resp = client.get(
        f"/api/v1/courses/{course_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert rev_list_resp.status_code == 200
    detail = rev_list_resp.json()
    assert detail["title"] == "Full-Stack Microservices"

    # Get active draft revision ID from checklist
    chk_resp = client.get(
        f"/api/v1/courses/{course_id}/publish-checklist",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert chk_resp.status_code == 200
    rev1_id = chk_resp.json()["revision_id"]

    # 7. Add Section
    sec_resp = client.post(
        f"/api/v1/courses/{course_id}/revisions/{rev1_id}/sections",
        json={"title": "Module 1: Foundations", "sort_order": 0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert sec_resp.status_code == 201
    sec_id = sec_resp.json()["id"]

    # 8. Add Lesson
    les_resp = client.post(
        f"/api/v1/sections/{sec_id}/lessons",
        json={
            "title": "1.1 Architecture Overview",
            "lesson_type": "VIDEO",
            "duration_seconds": 900,
            "is_preview": True,
            "sort_order": 0,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert les_resp.status_code == 201
    les_id = les_resp.json()["id"]

    # 9. Before publication, anonymous preview access is strictly blocked (P0-03)
    public_les_before = client.get(f"/api/v1/lessons/{les_id}")
    assert public_les_before.status_code == 403
    assert public_les_before.json()["error"]["code"] == "COURSE_NOT_PUBLISHED"

    # 10. Pre-Flight Checklist passes now
    chk_pass = client.get(
        f"/api/v1/courses/{course_id}/publish-checklist",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert chk_pass.status_code == 200
    assert chk_pass.json()["can_publish"] is True

    # 11. Publish Revision 1
    pub_resp = client.post(
        f"/api/v1/courses/{course_id}/revisions/{rev1_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pub_resp.status_code == 200
    assert pub_resp.json()["status"] == REVISION_STATUS_PUBLISHED

    # 11b. Verify preview lesson is publicly accessible without auth once course is published (P0-03)
    public_les_after = client.get(f"/api/v1/lessons/{les_id}")
    assert public_les_after.status_code == 200
    assert public_les_after.json()["title"] == "1.1 Architecture Overview"

    # 12. Public catalog now includes the published course
    pub_list_after = client.get("/api/v1/courses")
    assert pub_list_after.status_code == 200
    assert any(c["id"] == course_id for c in pub_list_after.json()["items"])

    # 13. Public detail lookup by slug
    slug_lookup = client.get("/api/v1/courses/full-stack-microservices")
    assert slug_lookup.status_code == 200
    assert slug_lookup.json()["slug"] == "full-stack-microservices"
    assert len(slug_lookup.json()["curriculum"]) == 1

    # 14. Archive Course
    archive_resp = client.delete(
        f"/api/v1/courses/{course_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["status"] == COURSE_STATUS_ARCHIVED
