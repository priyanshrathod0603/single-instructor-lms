"""Integration tests for Media Storage REST API Endpoints and CHK-05 Publishing Integration.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.10)
- docs/backend/11-COURSE-MANAGEMENT.md (Section 3)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401-TASK404)
"""

from datetime import datetime, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import LESSON_TYPE_VIDEO, CurriculumLesson, CurriculumSection
from app.models.media import (
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)
from app.services.course_service import CourseService
from app.services.media_service import MediaService


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
def super_admin_user(db_session: Session) -> User:
    """Creates a Super Admin user."""
    role = db_session.get(Role, ROLE_SUPER_ADMIN)
    if not role:
        role = Role(id=ROLE_SUPER_ADMIN, name="Super Administrator")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="superadmin@lms.local",
        full_name="Super Administrator",
        password_hash=hash_password("SuperP@ss12345"),
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
        password_hash=hash_password("StudentP@ss12345"),
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


def test_media_upload_intent_and_confirm_lifecycle(
    client: TestClient, db_session: Session, super_admin_user: User, student_user: User
):
    """Complete REST API upload lifecycle: intent generation, authorization, and confirmation."""
    from tests.conftest import create_test_auth_headers
    admin_token = create_test_auth_headers(super_admin_user, extra_claims={"roles": [ROLE_SUPER_ADMIN]})["Authorization"].split()[1]
    student_token = create_test_auth_headers(student_user, extra_claims={"roles": [ROLE_STUDENT]})["Authorization"].split()[1]
    video_bytes = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"

    # 1. Unauthenticated request rejected with 401
    unauth_resp = client.post("/api/v1/media/upload-intent", json={"filename": "test.mp4", "mime_type": "video/mp4", "file_size_bytes": len(video_bytes)})
    assert unauth_resp.status_code == 401

    # 2. Student without media:upload permission rejected with 403
    student_resp = client.post(
        "/api/v1/media/upload-intent",
        json={"filename": "test.mp4", "mime_type": "video/mp4", "file_size_bytes": len(video_bytes)},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert student_resp.status_code == 403

    # 3. Super Admin creates upload intent
    intent_resp = client.post(
        "/api/v1/media/upload-intent",
        json={
            "filename": "lesson_1_intro.mp4",
            "mime_type": "video/mp4",
            "file_size_bytes": len(video_bytes),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert intent_resp.status_code == 201
    intent_data = intent_resp.json()
    media_id = intent_data["media_id"]
    assert intent_data["bucket"] == "lms-media"
    assert "raw-videos/" in intent_data["file_key"]
    assert "X-Amz-Signature=" in intent_data["presigned_url"]

    # 4. Simulate client binary upload to presigned storage, then confirm upload
    from app.core.storage import StorageClient
    StorageClient().put_object(intent_data["file_key"], video_bytes, content_type="video/mp4")

    confirm_resp = client.post(
        f"/api/v1/media/{media_id}/confirm",
        json={"duration_seconds": 1200},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == MEDIA_STATUS_PROCESSING
    assert confirm_data["transcode_output"]["duration_seconds"] == 1200

    # 5. List media assets
    list_resp = client.get(
        "/api/v1/media",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    assert any(a["id"] == media_id for a in list_resp.json()["items"])

    # 6. Retrieve single asset details
    detail_resp = client.get(
        f"/api/v1/media/{media_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == media_id


def test_video_playback_token_and_pdf_streaming(
    client: TestClient, db_session: Session, super_admin_user: User, student_user: User
):
    """Integration test verifying playback token issuance and protected PDF streaming with watermark."""
    from tests.conftest import create_test_auth_headers
    from app.models.curriculum import LessonResource, RESOURCE_TYPE_PDF
    from app.models.enrollment import Enrollment, ENROLLMENT_STATUS_ACTIVE

    admin_token = create_test_auth_headers(super_admin_user, extra_claims={"roles": [ROLE_SUPER_ADMIN]})["Authorization"].split()[1]
    student_token = create_test_auth_headers(student_user, extra_claims={"roles": [ROLE_STUDENT]})["Authorization"].split()[1]

    # 1. Create a video asset in READY state
    video = MediaAsset(
        uploader_id=super_admin_user.id,
        filename="lecture_video.mp4",
        file_key="raw-videos/lecture_video.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=50000000,
        status=MEDIA_STATUS_READY,
        transcode_output={
            "hls_master_url": "https://stream.instructor.com/media/lecture_video/hls/master.m3u8",
            "resolutions": ["1080p"],
            "duration_seconds": 120,
        },
    )
    # 2. Create a PDF asset in READY state
    pdf = MediaAsset(
        uploader_id=super_admin_user.id,
        filename="course_syllabus.pdf",
        file_key="protected-docs/course_syllabus.pdf",
        bucket="lms-media",
        mime_type="application/pdf",
        file_size_bytes=1000000,
        status=MEDIA_STATUS_READY,
    )
    db_session.add_all([video, pdf])
    db_session.flush()

    # Seed storage client with mock PDF object
    from app.core.storage import StorageClient
    raw_sample_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Sample Course Document) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000206 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n300\n%%EOF\n"
    StorageClient().put_object(pdf.file_key, raw_sample_pdf, content_type="application/pdf")

    # 3. Create course hierarchy and attach assets to lesson
    course = Course(
        title="Streaming Test Course",
        slug="streaming-test-course",
        headline="Streaming test headline",
        status=COURSE_STATUS_PUBLISHED,
        price_inr=0,
        is_free=True,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="Published Revision",
        status=REVISION_STATUS_PUBLISHED,
    )
    db_session.add(rev)
    db_session.flush()
    course.live_revision_id = rev.id

    sec = CurriculumSection(course_revision_id=rev.id, title="Section 1", sort_order=0)
    db_session.add(sec)
    db_session.flush()

    lesson = CurriculumLesson(
        section_id=sec.id,
        title="Lecture 1",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=0,
        content={"media_asset_id": str(video.id)},
    )
    db_session.add(lesson)
    db_session.flush()

    res = LessonResource(
        lesson_id=lesson.id,
        title="course_syllabus.pdf",
        resource_type=RESOURCE_TYPE_PDF,
        file_url=f"/api/v1/media/{pdf.id}",
        file_size_bytes=1000000,
    )
    db_session.add(res)

    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    # 4. Student requests video playback token with lesson_id
    token_resp = client.post(
        f"/api/v1/media/{video.id}/playback-token",
        json={"lesson_id": str(lesson.id)},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert token_data["media_id"] == str(video.id)
    assert token_data["ttl_seconds"] == 7200
    assert f"/hls/{video.id}/master.m3u8?token=" in token_data["stream_url"]

    # 5. Student streams protected watermarked PDF with lesson_id
    pdf_resp = client.get(
        f"/api/v1/media/{pdf.id}/protected-pdf?lesson_id={lesson.id}",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "private, no-store, max-age=0" in pdf_resp.headers["cache-control"]
    assert pdf_resp.headers["x-content-type-options"] == "nosniff"
    assert 'filename="course_syllabus.pdf"' in pdf_resp.headers["content-disposition"]

    # Watermark text in body
    assert b"Enrolled Student" in pdf_resp.content
    assert b"student@lms.local" in pdf_resp.content


def test_chk05_media_readiness_publishing_checklist_integration(
    client: TestClient, db_session: Session, super_admin_user: User
):
    """CHK-05: Publishing is blocked if any video lesson references a media asset that is still PROCESSING."""
    from tests.conftest import create_test_auth_headers
    admin_token = create_test_auth_headers(super_admin_user, extra_claims={"roles": [ROLE_SUPER_ADMIN]})["Authorization"].split()[1]

    # 1. Create a course and draft revision
    course = Course(
        title="Video Readiness Course",
        slug="video-readiness-course",
        headline="Testing CHK-05 media readiness",
        price_inr=0,
        is_free=True,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="Draft 1",
    )
    db_session.add(rev)
    db_session.flush()

    sec = CurriculumSection(course_revision_id=rev.id, title="Module 1", sort_order=0)
    db_session.add(sec)
    db_session.flush()

    # 2. Create media asset in PROCESSING state
    media = MediaAsset(
        uploader_id=super_admin_user.id,
        filename="transcoding_lecture.mp4",
        file_key="raw-videos/transcoding_lecture.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=50000000,
        status=MEDIA_STATUS_PROCESSING,  # Still processing!
    )
    db_session.add(media)
    db_session.flush()

    # 3. Create video lesson linking to media asset
    les = CurriculumLesson(
        section_id=sec.id,
        title="Transcoding Lesson",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=0,
        content={"media_asset_id": str(media.id)},
    )
    db_session.add(les)
    db_session.commit()

    # 4. Check publish checklist via API
    chk_resp = client.get(
        f"/api/v1/courses/{course.id}/publish-checklist?revision_id={rev.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert chk_resp.status_code == 200
    chk_data = chk_resp.json()
    assert chk_data["can_publish"] is False
    assert any(b["code"] == "MEDIA_NOT_READY" for b in chk_data["blockers"])

    # 5. Transition media asset status to READY
    media.status = MEDIA_STATUS_READY
    db_session.commit()

    # 6. Check publish checklist again: now can_publish should be True!
    chk_resp2 = client.get(
        f"/api/v1/courses/{course.id}/publish-checklist?revision_id={rev.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert chk_resp2.status_code == 200
    chk_data2 = chk_resp2.json()
    assert chk_data2["can_publish"] is True
    assert len(chk_data2["blockers"]) == 0


def test_local_storage_upload_and_download_flow(
    client: TestClient, db_session: Session, super_admin_user: User
):
    """Verifies end-to-end local dev storage upload pipeline: intent -> direct PUT -> confirm -> download."""
    from tests.conftest import create_test_auth_headers
    from app.core.storage import StorageClient

    admin_token = create_test_auth_headers(super_admin_user, extra_claims={"roles": [ROLE_SUPER_ADMIN]})["Authorization"].split()[1]

    # 1. Request upload intent
    intent_resp = client.post(
        "/api/v1/media/upload-intent",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "filename": "local_demo_doc.pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": 1024,
        },
    )
    assert intent_resp.status_code == 201
    intent_data = intent_resp.json()
    media_id = intent_data["media_id"]
    presigned_url = intent_data["presigned_url"]
    file_key = intent_data["file_key"]

    assert "/api/v1/media/storage/upload/" in presigned_url

    # Extract relative path from presigned_url
    from urllib.parse import urlparse
    parsed = urlparse(presigned_url)
    upload_path = parsed.path
    if parsed.query:
        upload_path = f"{upload_path}?{parsed.query}"

    # 2. Direct binary PUT
    payload = b"%PDF-1.4 " + b"A" * (1024 - 9)
    put_resp = client.put(
        upload_path,
        content=payload,
        headers={"Content-Type": "application/pdf"},
    )
    assert put_resp.status_code == 200

    # Verify StorageClient holds the bytes
    storage = StorageClient()
    assert storage.object_exists(file_key) is True
    assert storage.get_object(file_key) == payload

    # 3. Confirm upload
    confirm_resp = client.post(
        f"/api/v1/media/{media_id}/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"file_key": file_key},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == MEDIA_STATUS_READY

    # 4. Direct binary download via local download route
    dl_resp = client.get(f"/api/v1/media/storage/download/{file_key}")
    assert dl_resp.status_code == 200
    assert dl_resp.content == payload
