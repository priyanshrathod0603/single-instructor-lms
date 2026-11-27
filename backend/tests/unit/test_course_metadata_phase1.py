"""Comprehensive unit and API tests for Phase 1: Course Creation & Metadata Management.

Covers:
1. Full course metadata creation, persistence, and initial draft revision creation.
2. Title, slug, headline, description, category, difficulty, language, outcomes, requirements validation.
3. Auto-slug generation, suffix deduplication, explicit slug validation, and availability checks.
4. Partial updates (PATCH) preserving existing fields + explicit clearing + snapshot immutability.
5. Pricing & discount percentage invariants (free vs paid, compare_at_price >= price).
6. Tag normalization, deduplication, and XSS/dangerous URL rejection.
7. RBAC enforcement (401 unauthenticated, 403 insufficient permissions).
8. Thumbnail upload content verification (PNG/JPEG/WebP binary dimensions) & fail-closed public serving.
"""

import struct
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import hash_password
from app.core.storage import _shared_in_memory_storage
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.media import MEDIA_STATUS_READY, MediaAsset
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
from tests.conftest import create_test_auth_headers


def _make_valid_png(width: int = 800, height: int = 450) -> bytes:
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"


def _make_valid_jpeg(width: int = 640, height: int = 360) -> bytes:
    sof0_payload = struct.pack(">BHHBBBB", 8, height, width, 3, 1, 0x11, 0)
    seg_len = struct.pack(">H", len(sof0_payload) + 2)
    return b"\xff\xd8\xff\xc0" + seg_len + sof0_payload + b"\xff\xd9"


def _make_valid_webp(width: int = 1280, height: int = 720) -> bytes:
    dims = struct.pack("<I", (width - 1) | ((height - 1) << 14))
    vp8l_chunk = b"VP8L" + struct.pack("<I", 5) + b"\x2f" + dims
    return b"RIFF" + struct.pack("<I", 4 + len(vp8l_chunk)) + b"WEBP" + vp8l_chunk


@pytest.fixture
def phase1_env():
    """Isolated SQLite DB with seeded RBAC roles, permissions, admin, staff, and student users."""
    _shared_in_memory_storage.clear()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db: Session = SessionLocal()

    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Assistant"),
        Role(id=ROLE_ADMIN, name="Admin", description="Instructor/Admin"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform Owner"),
    ]
    db.add_all(roles)

    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        db.add(Permission(id=p_id, module=p_mod, description=p_desc))
    for role_id, perms in DEFAULT_ROLE_PERMISSIONS.items():
        for perm in perms:
            db.add(RolePermission(role_id=role_id, permission_id=perm))

    def _create_user(email: str, name: str, role_id: str) -> User:
        u = User(
            email=email,
            password_hash=hash_password("StrongPass123!"),
            full_name=name,
            is_active=True,
            is_verified=True,
        )
        db.add(u)
        db.flush()
        db.add(UserRole(user_id=u.id, role_id=role_id))
        return u

    admin = _create_user("instructor@lms.local", "Lead Instructor", ROLE_ADMIN)
    super_admin = _create_user("owner@lms.local", "Owner", ROLE_SUPER_ADMIN)
    staff = _create_user("staff@lms.local", "Staff Member", ROLE_STAFF)
    student = _create_user("student@lms.local", "Student User", ROLE_STUDENT)
    db.commit()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client:
        yield {
            "client": client,
            "db": db,
            "admin_headers": create_test_auth_headers(admin, db),
            "super_admin_headers": create_test_auth_headers(super_admin, db),
            "staff_headers": create_test_auth_headers(staff, db),
            "student_headers": create_test_auth_headers(student, db),
            "admin": admin,
        }

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()
    _shared_in_memory_storage.clear()


def test_create_course_with_complete_metadata(phase1_env):
    client = phase1_env["client"]
    db: Session = phase1_env["db"]
    headers = phase1_env["admin_headers"]

    payload = {
        "title": "  System Design & Distributed Backend  ",
        "slug": "system-design-backend",
        "headline": "Master scalable systems in production",
        "description": "Deep architectural breakdown.\nIncludes real projects.",
        "thumbnail_url": "https://cdn.example.com/courses/sys-design.png",
        "category": "System Design",
        "difficulty_level": "Intermediate",
        "language": "Hinglish",
        "learning_outcomes": [
            "Design high-throughput APIs",
            "Architect distributed consensus",
        ],
        "requirements": [
            "Basic Python or Go proficiency",
            "HTTP fundamentals",
        ],
        "tags": ["Python", "python", " Distributed-Systems "],
        "is_free": False,
        "price_inr": 299900,
        "compare_at_price_inr": 799900,
        "currency": "inr",
    }

    resp = client.post("/api/v1/courses", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["title"] == "System Design & Distributed Backend"
    assert body["slug"] == "system-design-backend"
    assert body["category"] == "System Design"
    assert body["difficulty_level"] == "INTERMEDIATE"
    assert body["language"] == "Hinglish"
    assert body["learning_outcomes"] == [
        "Design high-throughput APIs",
        "Architect distributed consensus",
    ]
    assert body["requirements"] == [
        "Basic Python or Go proficiency",
        "HTTP fundamentals",
    ]
    assert sorted(body["tags"]) == ["distributed-systems", "python"]
    assert len(body["tags"]) == 2
    assert body["price_inr"] == 299900
    assert body["compare_at_price_inr"] == 799900
    assert body["currency"] == "INR"
    assert body["discount_percentage"] == 63
    assert body["is_free"] is False
    assert body["status"] == COURSE_STATUS_DRAFT
    assert body["draft_revision_id"] is not None

    audit = db.query(AuditLog).filter_by(resource_id=body["id"], action="COURSE_CREATED").first()
    assert audit is not None


def test_create_course_rejects_empty_and_short_titles(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    for bad_title in ["", "   ", "Go", "A "]:
        resp = client.post(
            "/api/v1/courses",
            json={"title": bad_title, "is_free": True},
            headers=headers,
        )
        assert resp.status_code == 422


def test_create_course_rejects_invalid_and_duplicate_slugs(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    for bad_slug in ["Bad Slug!", "--leading-dash", "double--dash", "slash/slug"]:
        resp = client.post(
            "/api/v1/courses",
            json={"title": "Valid Course Title", "slug": bad_slug, "is_free": True},
            headers=headers,
        )
        assert resp.status_code == 422

    first = client.post(
        "/api/v1/courses",
        json={"title": "First Course", "slug": "clean-slug", "is_free": True},
        headers=headers,
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    dup = client.post(
        "/api/v1/courses",
        json={"title": "Second Course", "slug": "Clean-Slug", "is_free": True},
        headers=headers,
    )
    assert dup.status_code == 409

    # Slug availability endpoint reports unavailable globally, available for same course
    check_new = client.get("/api/v1/courses/slug-available?slug=clean-slug", headers=headers)
    assert check_new.status_code == 200
    assert check_new.json()["available"] is False

    check_self = client.get(
        f"/api/v1/courses/slug-available?slug=clean-slug&exclude_course_id={first_id}",
        headers=headers,
    )
    assert check_self.status_code == 200
    assert check_self.json()["available"] is True


def test_auto_slug_generation_and_deduplication(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    r1 = client.post("/api/v1/courses", json={"title": "FastAPI Mastery", "is_free": True}, headers=headers)
    r2 = client.post("/api/v1/courses", json={"title": "FastAPI Mastery", "is_free": True}, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["slug"] == "fastapi-mastery"
    assert r2.json()["slug"] == "fastapi-mastery-1"


def test_pricing_and_discount_invariants(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    # Free course with non-zero price rejected
    r_free_paid = client.post(
        "/api/v1/courses",
        json={"title": "Invalid Free Course", "is_free": True, "price_inr": 19900},
        headers=headers,
    )
    assert r_free_paid.status_code == 422

    # Free course with compare_at_price rejected
    r_free_cmp = client.post(
        "/api/v1/courses",
        json={"title": "Invalid Free Compare", "is_free": True, "price_inr": 0, "compare_at_price_inr": 50000},
        headers=headers,
    )
    assert r_free_cmp.status_code == 422

    # Paid course with zero price or negative price rejected
    r_paid_zero = client.post(
        "/api/v1/courses",
        json={"title": "Paid Zero Course", "is_free": False, "price_inr": 0},
        headers=headers,
    )
    assert r_paid_zero.status_code == 422

    # Discounted selling price exceeding regular price rejected
    r_bad_discount = client.post(
        "/api/v1/courses",
        json={
            "title": "Bad Discount Course",
            "is_free": False,
            "price_inr": 600000,
            "compare_at_price_inr": 500000,
        },
        headers=headers,
    )
    assert r_bad_discount.status_code == 422

    # Valid free course creation succeeds
    r_valid_free = client.post(
        "/api/v1/courses",
        json={"title": "Free Starter Bootcamp", "is_free": True, "price_inr": 0},
        headers=headers,
    )
    assert r_valid_free.status_code == 201
    assert r_valid_free.json()["is_free"] is True
    assert r_valid_free.json()["price_inr"] == 0
    assert r_valid_free.json()["discount_percentage"] is None

    # Paid course with equal regular and selling price normalizes compare_at_price_inr to None
    r_equal = client.post(
        "/api/v1/courses",
        json={
            "title": "No Discount Course",
            "is_free": False,
            "price_inr": 499900,
            "compare_at_price_inr": 499900,
        },
        headers=headers,
    )
    assert r_equal.status_code == 201
    assert r_equal.json()["compare_at_price_inr"] is None
    assert r_equal.json()["discount_percentage"] is None


def test_outcomes_requirements_and_xss_sanitization(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    # Reject empty entries inside learning_outcomes or requirements
    r_empty_outcome = client.post(
        "/api/v1/courses",
        json={"title": "Outcome Validation", "is_free": True, "learning_outcomes": ["Valid", "   "]},
        headers=headers,
    )
    assert r_empty_outcome.status_code == 422

    r_empty_req = client.post(
        "/api/v1/courses",
        json={"title": "Req Validation", "is_free": True, "requirements": ["  "]},
        headers=headers,
    )
    assert r_empty_req.status_code == 422

    # Reject unsafe javascript: thumbnail URL
    r_xss_url = client.post(
        "/api/v1/courses",
        json={"title": "XSS Thumb", "is_free": True, "thumbnail_url": "javascript:alert(1)"},
        headers=headers,
    )
    assert r_xss_url.status_code == 422

    # Sanitize HTML script tags while preserving clean text & deduplicating case-insensitively
    r_clean = client.post(
        "/api/v1/courses",
        json={
            "title": "<script>alert(1)</script>Clean Architecture",
            "headline": "<b>Build maintainable apps</b>",
            "description": "Learn C++ & clean patterns.<script>steal()</script>",
            "learning_outcomes": ["Write modular code", "write modular code", "Test APIs"],
            "requirements": ["Laptop with 8GB RAM", "LAPTOP WITH 8GB RAM"],
            "tags": ["Python", "python", "Backend"],
            "is_free": True,
        },
        headers=headers,
    )
    assert r_clean.status_code == 201, r_clean.text
    data = r_clean.json()
    assert data["title"] == "Clean Architecture"
    assert data["headline"] == "Build maintainable apps"
    assert data["description"] == "Learn C++ & clean patterns."
    assert data["learning_outcomes"] == ["Write modular code", "Test APIs"]
    assert data["requirements"] == ["Laptop with 8GB RAM"]
    assert sorted(data["tags"]) == ["backend", "python"]
    assert len(data["tags"]) == 2


def test_partial_update_preserving_fields_and_published_snapshot_immutability(phase1_env):
    client = phase1_env["client"]
    db: Session = phase1_env["db"]
    headers = phase1_env["admin_headers"]

    created = client.post(
        "/api/v1/courses",
        json={
            "title": "PostgreSQL Internals",
            "slug": "postgres-internals",
            "headline": "MVCC, WAL, and Query Planner",
            "category": "Backend Engineering",
            "difficulty_level": "Advanced",
            "language": "English",
            "learning_outcomes": ["Understand MVCC"],
            "requirements": ["SQL basics"],
            "tags": ["postgres", "databases"],
            "is_free": False,
            "price_inr": 399900,
            "compare_at_price_inr": 599900,
        },
        headers=headers,
    )
    assert created.status_code == 201
    cid = created.json()["id"]

    # Partial update changing ONLY headline preserves price, discount, outcomes, tags
    patch1 = client.patch(
        f"/api/v1/courses/{cid}",
        json={"headline": "Deep dive into MVCC & indexing"},
        headers=headers,
    )
    assert patch1.status_code == 200
    d1 = patch1.json()
    assert d1["headline"] == "Deep dive into MVCC & indexing"
    assert d1["price_inr"] == 399900
    assert d1["compare_at_price_inr"] == 599900
    assert d1["learning_outcomes"] == ["Understand MVCC"]
    assert sorted(d1["tags"]) == ["databases", "postgres"]
    assert len(d1["tags"]) == 2

    # Explicit null clears compare_at_price_inr cleanly
    patch2 = client.patch(
        f"/api/v1/courses/{cid}",
        json={"compare_at_price_inr": None},
        headers=headers,
    )
    assert patch2.status_code == 200
    assert patch2.json()["compare_at_price_inr"] is None
    assert patch2.json()["discount_percentage"] is None

    # Cross-field check on partial PATCH: setting selling price > compare_at must fail
    client.patch(
        f"/api/v1/courses/{cid}",
        json={"price_inr": 250000, "compare_at_price_inr": 400000},
        headers=headers,
    )
    bad_partial = client.patch(
        f"/api/v1/courses/{cid}",
        json={"price_inr": 450000},
        headers=headers,
    )
    assert bad_partial.status_code == 422

    # Verify frozen snapshot immutability on published revision
    course_row = db.get(Course, uuid.UUID(cid))
    rev1 = db.query(CourseRevision).filter_by(course_id=course_row.id, revision_no=1).first()
    rev1.status = "PUBLISHED"
    rev1.snapshot = {"title": "PostgreSQL Internals", "price_inr": 250000}
    course_row.status = COURSE_STATUS_PUBLISHED
    course_row.live_revision_id = rev1.id
    db.commit()

    patch_live = client.patch(
        f"/api/v1/courses/{cid}",
        json={"title": "PostgreSQL Internals 2026"},
        headers=headers,
    )
    assert patch_live.status_code == 200
    assert patch_live.json()["title"] == "PostgreSQL Internals 2026"

    db.refresh(rev1)
    assert rev1.snapshot == {"title": "PostgreSQL Internals", "price_inr": 250000}


def test_listing_filters_and_metadata_options(phase1_env):
    client = phase1_env["client"]
    headers = phase1_env["admin_headers"]

    client.post(
        "/api/v1/courses",
        json={
            "title": "React Server Components",
            "category": "Web Development",
            "difficulty_level": "Intermediate",
            "language": "English",
            "is_free": False,
            "price_inr": 199900,
        },
        headers=headers,
    )
    client.post(
        "/api/v1/courses",
        json={
            "title": "Python Data Structures",
            "category": "Programming Languages",
            "difficulty_level": "Beginner",
            "language": "Hinglish",
            "is_free": True,
        },
        headers=headers,
    )

    opts = client.get("/api/v1/courses/metadata-options")
    assert opts.status_code == 200
    assert "Web Development" in opts.json()["categories"]
    assert any(d["value"] == "BEGINNER" and d["label"] == "Beginner" for d in opts.json()["difficulty_levels"])

    filtered = client.get(
        "/api/v1/courses/manage?category=Programming+Languages&difficulty_level=BEGINNER&language=Hinglish",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["title"] == "Python Data Structures"


def test_rbac_unauthorized_and_forbidden_course_mutations(phase1_env):
    client = phase1_env["client"]
    student_headers = phase1_env["student_headers"]
    staff_headers = phase1_env["staff_headers"]
    admin_headers = phase1_env["admin_headers"]

    assert client.post("/api/v1/courses", json={"title": "No Auth Course", "is_free": True}).status_code == 401
    assert client.get("/api/v1/courses/slug-available?slug=no-auth").status_code == 401

    assert (
        client.post("/api/v1/courses", json={"title": "Student Try", "is_free": True}, headers=student_headers).status_code
        == 403
    )
    assert (
        client.post("/api/v1/courses", json={"title": "Staff Try", "is_free": True}, headers=staff_headers).status_code
        == 403
    )
    assert client.get("/api/v1/courses/slug-available?slug=x", headers=student_headers).status_code == 403

    created = client.post("/api/v1/courses", json={"title": "Admin Owned", "is_free": True}, headers=admin_headers)
    cid = created.json()["id"]
    assert client.patch(f"/api/v1/courses/{cid}", json={"title": "Hijacked"}, headers=student_headers).status_code == 403
    assert client.delete(f"/api/v1/courses/{cid}", headers=student_headers).status_code == 403


def test_thumbnail_upload_validation_and_public_image_serving(phase1_env):
    client = phase1_env["client"]
    db: Session = phase1_env["db"]
    headers = phase1_env["admin_headers"]

    # 1. Upload valid PNG, JPEG, and WebP thumbnails and verify public URL + dimensions
    for filename, mime_type, content in [
        ("cover.png", "image/png", _make_valid_png(800, 450)),
        ("cover.jpg", "image/jpeg", _make_valid_jpeg(640, 360)),
        ("cover.webp", "image/webp", _make_valid_webp(1280, 720)),
    ]:
        intent = client.post(
            "/api/v1/media/upload-intent",
            json={
                "filename": filename,
                "mime_type": mime_type,
                "file_size_bytes": len(content),
            },
            headers=headers,
        )
        assert intent.status_code == 201, intent.text
        intent_data = intent.json()

        put_resp = client.put(
            f"/api/v1/media/storage/upload/{intent_data['file_key']}",
            content=content,
            headers={"Content-Type": mime_type},
        )
        assert put_resp.status_code == 200

        confirm = client.post(
            f"/api/v1/media/{intent_data['media_id']}/confirm",
            json={},
            headers=headers,
        )
        assert confirm.status_code == 200, confirm.text
        confirmed_asset = confirm.json()
        assert confirmed_asset["status"] == MEDIA_STATUS_READY
        assert confirmed_asset["public_url"] == f"/api/v1/media/public/{intent_data['media_id']}"

        # Public thumbnail endpoint serves verified image with nosniff
        pub_img = client.get(confirmed_asset["public_url"])
        assert pub_img.status_code == 200
        assert pub_img.headers["content-type"] == mime_type
        assert pub_img.headers["x-content-type-options"] == "nosniff"
        assert pub_img.content == content

    # 2. Reject forged/corrupted PNG missing valid image IHDR structure
    corrupt_png = b"\x89PNG\r\n\x1a\nCORRUPTED_BYTES_NO_IHDR"
    corrupt_intent = client.post(
        "/api/v1/media/upload-intent",
        json={"filename": "bad.png", "mime_type": "image/png", "file_size_bytes": len(corrupt_png)},
        headers=headers,
    ).json()
    client.put(
        f"/api/v1/media/storage/upload/{corrupt_intent['file_key']}",
        content=corrupt_png,
        headers={"Content-Type": "image/png"},
    )
    corrupt_confirm = client.post(f"/api/v1/media/{corrupt_intent['media_id']}/confirm", json={}, headers=headers)
    assert corrupt_confirm.status_code == 400
    assert corrupt_confirm.json()["error"]["code"] == "INVALID_IMAGE_CONTENT"

    # 3. Verify course creation links valid thumbnail_media_id and rejects non-image media_id
    valid_img = db.query(MediaAsset).filter_by(mime_type="image/png", status=MEDIA_STATUS_READY).first()
    course_res = client.post(
        "/api/v1/courses",
        json={
            "title": "Course With Uploaded Thumb",
            "is_free": True,
            "thumbnail_media_id": str(valid_img.id),
        },
        headers=headers,
    )
    assert course_res.status_code == 201
    assert course_res.json()["thumbnail_media_id"] == str(valid_img.id)
    assert course_res.json()["thumbnail_url"] == f"/api/v1/media/public/{valid_img.id}"

    # Create raw video asset and confirm /public/{id} denies access (fail-closed)
    video_asset = MediaAsset(
        uploader_id=phase1_env["admin"].id,
        filename="secret.mp4",
        file_key=f"videos/{uuid.uuid4()}/secret.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=2048,
        status=MEDIA_STATUS_READY,
    )
    db.add(video_asset)
    db.commit()

    assert client.get(f"/api/v1/media/public/{video_asset.id}").status_code == 403
    bad_thumb_course = client.post(
        "/api/v1/courses",
        json={
            "title": "Video As Thumb",
            "is_free": True,
            "thumbnail_media_id": str(video_asset.id),
        },
        headers=headers,
    )
    assert bad_thumb_course.status_code == 422
