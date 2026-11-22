"""Comprehensive automated unit tests for SA-04 Content & Course Governance.

Verifies:
1. SA-04.1 Course Governance: listing, search, status filtering, curriculum aggregation stats, detail inspection, status transition, and audit logging.
2. SA-04.2 Blog CMS: create, list, filter, get, update, publish/unpublish, delete, categories, and audit logging.
3. SA-04.3 Notes CMS: create, list, filter, get, update, replace PDF, publish/unpublish, delete, categories, and audit logging.
4. RBAC Protection: Super Admin exclusive; Admin (403), Student (403), and unauthenticated (401) access denials.
"""

from datetime import datetime, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token, generate_secure_token, hash_password, hash_token
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.auth_session import SESSION_STATUS_ACTIVE, AuthSession
from app.models.base import Base, utc_now
from app.models.blog import BLOG_STATUS_ARCHIVED, BLOG_STATUS_DRAFT, BLOG_STATUS_PUBLISHED, BlogPost
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.media import MediaAsset
from app.models.note import NOTE_STATUS_ARCHIVED, NOTE_STATUS_DRAFT, NOTE_STATUS_PUBLISHED, Note
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
def sa04_db():
    """In-memory SQLite database session with static pool for multi-threaded TestClient."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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

    # Seed users
    super_admin = User(
        id=uuid.uuid4(),
        email="superadmin@lms.local",
        password_hash=hash_password("SuperSecret123!"),
        full_name="Chief Executive Super Admin",
        is_active=True,
        is_verified=True,
    )
    super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN))

    admin = User(
        id=uuid.uuid4(),
        email="admin@lms.local",
        password_hash=hash_password("AdminSecret123!"),
        full_name="Standard Administrator",
        is_active=True,
        is_verified=True,
    )
    admin.user_roles.append(UserRole(role_id=ROLE_ADMIN))

    student = User(
        id=uuid.uuid4(),
        email="student@lms.local",
        password_hash=hash_password("StudentPass123!"),
        full_name="Jane Student",
        is_active=True,
        is_verified=True,
    )
    student.user_roles.append(UserRole(role_id=ROLE_STUDENT))

    session.add_all([super_admin, admin, student])
    session.commit()

    yield session, engine

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_app_and_client(sa04_db):
    """Configures FastAPI TestClient with overridden database session."""
    session, engine = sa04_db
    app = create_app()

    def override_get_db():
        db = sessionmaker(bind=engine)()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, session

    app.dependency_overrides.clear()


def create_authenticated_session(db: Session, user: User) -> tuple[str, str]:
    """Helper to create an active AuthSession and return (session_id, jwt_token)."""
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    session_id = uuid.uuid4()
    now = utc_now()
    expires_at = now + timedelta(days=7)

    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        session_token_hash=token_hash,
        status=SESSION_STATUS_ACTIVE,
        ip_address="127.0.0.1",
        user_agent="Automated-Test-Client/1.0",
        last_active_at=now,
        expires_at=expires_at,
    )
    db.add(auth_session)
    db.commit()

    roles = [ur.role_id for ur in user.user_roles] if user.user_roles else []
    jwt_token = create_access_token(
        subject=str(user.id),
        extra_claims={"roles": roles, "email": user.email, "session_id": str(session_id)},
    )
    return str(session_id), jwt_token


# =============================================================================
# SA-04.1: Course Governance Tests
# =============================================================================


class TestCourseGovernance:
    """Tests for Course Governance list, detail, status management, and curriculum stats."""

    def test_list_governed_courses_with_curriculum_stats(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        # Seed courses
        course1 = Course(
            title="Advanced Machine Learning",
            slug="advanced-ml",
            status=COURSE_STATUS_PUBLISHED,
            price_inr=499900,
        )
        course2 = Course(
            title="System Design Architecture",
            slug="system-design-arch",
            status=COURSE_STATUS_DRAFT,
            price_inr=299900,
        )
        db.add_all([course1, course2])
        db.commit()

        # Seed revision and curriculum for course1
        rev1 = CourseRevision(
            course_id=course1.id,
            revision_no=1,
            title="ML Rev 1",
            status=REVISION_STATUS_PUBLISHED,
        )
        db.add(rev1)
        db.commit()
        course1.live_revision_id = rev1.id

        sec1 = CurriculumSection(
            course_revision_id=rev1.id,
            title="Section 1: Neural Networks",
            sort_order=1,
        )
        db.add(sec1)
        db.commit()

        les1 = CurriculumLesson(
            section_id=sec1.id,
            title="Backpropagation Deep Dive",
            lesson_type="VIDEO",
            duration_seconds=1200,
            sort_order=1,
        )
        les2 = CurriculumLesson(
            section_id=sec1.id,
            title="PyTorch Gradient Assignment",
            lesson_type="ASSIGNMENT",
            duration_seconds=600,
            sort_order=2,
        )
        les3 = CurriculumLesson(
            section_id=sec1.id,
            title="Knowledge Check Quiz",
            lesson_type="QUIZ",
            duration_seconds=300,
            sort_order=3,
        )
        db.add_all([les1, les2, les3])
        db.commit()

        # Test listing
        res = client.get(
            "/api/v1/control/courses",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Check curriculum stats for course1
        c1_item = next(c for c in data["items"] if c["slug"] == "advanced-ml")
        assert c1_item["total_sections"] == 1
        assert c1_item["total_lessons"] == 3
        assert c1_item["total_duration_seconds"] == 2100
        assert c1_item["has_quiz"] is True
        assert c1_item["has_assignment"] is True

        # Test status filter
        res_draft = client.get(
            "/api/v1/control/courses?status=DRAFT",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_draft.status_code == 200
        assert res_draft.json()["total"] == 1
        assert res_draft.json()["items"][0]["slug"] == "system-design-arch"

        # Test search filter
        res_search = client.get(
            "/api/v1/control/courses?search=Machine",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_search.status_code == 200
        assert res_search.json()["total"] == 1
        assert res_search.json()["items"][0]["slug"] == "advanced-ml"

    def test_update_course_status_and_audit_logging(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        course = Course(
            title="Kubernetes in Production",
            slug="k8s-prod",
            headline="Production Kubernetes architecture",
            price_inr=0,
            is_free=True,
            status=COURSE_STATUS_DRAFT,
        )
        db.add(course)
        db.commit()

        rev = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Draft 1",
            status=REVISION_STATUS_DRAFT,
        )
        db.add(rev)
        db.commit()

        sec = CurriculumSection(
            course_revision_id=rev.id,
            title="Section 1",
            sort_order=1,
        )
        db.add(sec)
        db.flush()

        from app.models.curriculum import CurriculumLesson, LESSON_TYPE_ARTICLE
        les = CurriculumLesson(
            section_id=sec.id,
            title="Lesson 1",
            lesson_type=LESSON_TYPE_ARTICLE,
            sort_order=1,
            content={"text": "Welcome"},
        )
        db.add(les)
        db.commit()

        # Transition to PUBLISHED
        res_pub = client.patch(
            f"/api/v1/control/courses/{course.id}/status",
            json={"status": "PUBLISHED", "reason": "Curriculum review approved"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_pub.status_code == 200
        assert res_pub.json()["status"] == "PUBLISHED"

        # Verify audit log
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.resource_id == str(course.id))
            .filter(AuditLog.action.in_(["COURSE_STATUS_CHANGED", "COURSE_PUBLISHED"]))
            .first()
        )
        assert audit is not None
        assert audit.before_state["status"] == "DRAFT"
        assert audit.after_state["status"] == "PUBLISHED"
        assert audit.after_state["reason"] == "Curriculum review approved"

        # Transition to ARCHIVED
        res_arch = client.patch(
            f"/api/v1/control/courses/{course.id}/status",
            json={"status": "ARCHIVED", "reason": "Course retired for v2 release"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_arch.status_code == 200
        assert res_arch.json()["status"] == "ARCHIVED"

    def test_course_governance_invalid_status_and_not_found(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        fake_id = uuid.uuid4()
        res_404 = client.get(
            f"/api/v1/control/courses/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_404.status_code == 404

        course = Course(
            title="Docker Mastery",
            slug="docker-mastery",
            status=COURSE_STATUS_DRAFT,
        )
        db.add(course)
        db.commit()

        res_invalid = client.patch(
            f"/api/v1/control/courses/{course.id}/status",
            json={"status": "INVALID_STATE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_invalid.status_code == 400


# =============================================================================
# SA-04.2: Blog CMS Tests
# =============================================================================


class TestBlogCMS:
    """Tests for Blog post CRUD, slug uniqueness, publication transitions, and categories."""

    def test_blog_crud_lifecycle_and_audit(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        # 1. Create Blog Post (Draft)
        create_payload = {
            "title": "Demystifying Transformer Attention Mechanisms",
            "content": "# Attention is All You Need\n\nDetailed breakdown of multi-head self-attention.",
            "category": "Deep Learning",
            "excerpt": "A deep dive into attention mathematics and tensor implementations.",
            "status": "DRAFT",
        }
        res_create = client.post(
            "/api/v1/control/blog",
            json=create_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_create.status_code == 201
        post = res_create.json()
        post_id = post["id"]
        assert post["title"] == create_payload["title"]
        assert post["slug"] == "demystifying-transformer-attention-mechanisms"
        assert post["status"] == "DRAFT"
        assert post["published_at"] is None

        # Verify audit log for creation
        audit_create = (
            db.query(AuditLog)
            .filter_by(action="BLOG_POST_CREATED", resource_id=post_id)
            .first()
        )
        assert audit_create is not None
        assert audit_create.after_state["slug"] == post["slug"]

        # 2. Get Post by ID
        res_get = client.get(
            f"/api/v1/control/blog/{post_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_get.status_code == 200
        assert res_get.json()["id"] == post_id

        # 3. Update Blog Post
        update_payload = {
            "title": "Understanding Transformer Attention",
            "category": "Architecture",
        }
        res_update = client.put(
            f"/api/v1/control/blog/{post_id}",
            json=update_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_update.status_code == 200
        assert res_update.json()["title"] == "Understanding Transformer Attention"
        assert res_update.json()["category"] == "Architecture"

        # 4. Publish Post
        res_pub = client.patch(
            f"/api/v1/control/blog/{post_id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_pub.status_code == 200
        assert res_pub.json()["status"] == "PUBLISHED"
        assert res_pub.json()["published_at"] is not None

        # 5. List Posts
        res_list = client.get(
            "/api/v1/control/blog?status=PUBLISHED",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_list.status_code == 200
        assert res_list.json()["total"] == 1
        assert res_list.json()["items"][0]["id"] == post_id

        # 6. Categories
        res_cats = client.get(
            "/api/v1/control/blog/categories",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_cats.status_code == 200
        assert "Architecture" in res_cats.json()

        # 7. Unpublish Post
        res_unpub = client.patch(
            f"/api/v1/control/blog/{post_id}/status",
            json={"status": "DRAFT"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_unpub.status_code == 200
        assert res_unpub.json()["status"] == "DRAFT"

        # 8. Delete Post
        res_del = client.delete(
            f"/api/v1/control/blog/{post_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_del.status_code == 204

        # Confirm post is gone
        res_get_del = client.get(
            f"/api/v1/control/blog/{post_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_get_del.status_code == 404

    def test_blog_duplicate_slug_conflict_and_not_found(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        # 1. Create Post
        res1 = client.post(
            "/api/v1/control/blog",
            json={"title": "Unique Article", "slug": "unique-slug", "content": "Sample"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 201

        # 2. Try creating with same slug -> 409 Conflict
        res2 = client.post(
            "/api/v1/control/blog",
            json={"title": "Another Article", "slug": "unique-slug", "content": "Sample"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 409

        # 3. Not Found
        fake_id = uuid.uuid4()
        res_404 = client.get(
            f"/api/v1/control/blog/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_404.status_code == 404


# =============================================================================
# SA-04.3: Notes CMS Tests
# =============================================================================


class TestNotesCMS:
    """Tests for Notes CMS CRUD, PDF replacement, publication, and categories."""

    def test_notes_crud_and_pdf_replacement(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        # 1. Create Study Note
        create_payload = {
            "title": "System Design Cheatsheet v1",
            "description": "Comprehensive reference for distributed caching and database partitioning.",
            "category": "Cheatsheets",
            "pdf_url": "protected-docs/system-design-v1.pdf",
            "file_size_bytes": 1048576,
            "status": "DRAFT",
        }
        res_create = client.post(
            "/api/v1/control/notes",
            json=create_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_create.status_code == 201
        note = res_create.json()
        note_id = note["id"]
        assert note["title"] == create_payload["title"]
        assert note["slug"] == "system-design-cheatsheet-v1"
        assert note["status"] == "DRAFT"
        assert note["pdf_url"] == "protected-docs/system-design-v1.pdf"

        # 2. Get Note
        res_get = client.get(
            f"/api/v1/control/notes/{note_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_get.status_code == 200
        assert res_get.json()["id"] == note_id

        # 3. Update Note Metadata
        res_update = client.put(
            f"/api/v1/control/notes/{note_id}",
            json={"title": "System Design Handbook", "category": "Reference"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_update.status_code == 200
        assert res_update.json()["title"] == "System Design Handbook"
        assert res_update.json()["category"] == "Reference"

        # 4. Replace Attached PDF
        replace_payload = {
            "pdf_url": "protected-docs/system-design-v2-final.pdf",
            "file_size_bytes": 2097152,
        }
        res_replace = client.post(
            f"/api/v1/control/notes/{note_id}/pdf",
            json=replace_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_replace.status_code == 200
        assert res_replace.json()["pdf_url"] == "protected-docs/system-design-v2-final.pdf"
        assert res_replace.json()["file_size_bytes"] == 2097152

        # Verify audit log for PDF replacement
        audit_pdf = (
            db.query(AuditLog)
            .filter_by(action="NOTE_PDF_REPLACED", resource_id=note_id)
            .first()
        )
        assert audit_pdf is not None
        assert audit_pdf.after_state["pdf_url"] == "protected-docs/system-design-v2-final.pdf"

        # 5. Publish Note
        res_pub = client.patch(
            f"/api/v1/control/notes/{note_id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_pub.status_code == 200
        assert res_pub.json()["status"] == "PUBLISHED"
        assert res_pub.json()["published_at"] is not None

        # 6. Categories
        res_cats = client.get(
            "/api/v1/control/notes/categories",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_cats.status_code == 200
        assert "Reference" in res_cats.json()

        # 7. Delete Note
        res_del = client.delete(
            f"/api/v1/control/notes/{note_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_del.status_code == 204

    def test_notes_duplicate_slug_and_not_found(self, test_app_and_client):
        client, db = test_app_and_client
        super_admin = db.query(User).filter_by(email="superadmin@lms.local").first()
        _, token = create_authenticated_session(db, super_admin)

        # 1. Create Note
        res1 = client.post(
            "/api/v1/control/notes",
            json={"title": "Unique Note", "slug": "unique-note-slug"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 201

        # 2. Duplicate slug -> 409 Conflict
        res2 = client.post(
            "/api/v1/control/notes",
            json={"title": "Another Note", "slug": "unique-note-slug"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res2.status_code == 409

        # 3. Not Found
        fake_id = uuid.uuid4()
        res_404 = client.get(
            f"/api/v1/control/notes/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_404.status_code == 404


# =============================================================================
# SA-04.4: RBAC & Permission Boundary Enforcement
# =============================================================================


class TestContentGovernanceRBAC:
    """Verifies that non-Super-Admin roles (ADMIN, STUDENT) are forbidden from SA-04 APIs."""

    def test_admin_cannot_access_sa04_control_apis(self, test_app_and_client):
        client, db = test_app_and_client
        admin = db.query(User).filter_by(email="admin@lms.local").first()
        _, token = create_authenticated_session(db, admin)

        # 1. Course Governance
        res_courses = client.get(
            "/api/v1/control/courses",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_courses.status_code == 403
        assert res_courses.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"

        # 2. Blog CMS
        res_blog = client.get(
            "/api/v1/control/blog",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_blog.status_code == 403
        assert res_blog.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"

        # 3. Notes CMS
        res_notes = client.get(
            "/api/v1/control/notes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_notes.status_code == 403
        assert res_notes.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"

    def test_student_cannot_access_sa04_control_apis(self, test_app_and_client):
        client, db = test_app_and_client
        student = db.query(User).filter_by(email="student@lms.local").first()
        _, token = create_authenticated_session(db, student)

        res = client.get(
            "/api/v1/control/courses",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"

    def test_unauthenticated_request_rejected(self, test_app_and_client):
        client, _ = test_app_and_client
        res = client.get("/api/v1/control/courses")
        assert res.status_code == 401
