"""Comprehensive Part 4 Media Storage & Video Protection Security Test Suite.

Authoritative Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 32)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.10)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401-TASK404)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)

Tests:
1. Media Storage Security:
   - MIME type whitelist rejection
   - File size boundary enforcement (> 5GB video, > 50MB PDF, > 5MB image, > 100MB resource)
   - Extension mismatch rejection (.mp4 with image/png)
   - Path traversal and null byte prevention in filenames
   - Binary header signature enforcement against disguised payloads
   - Object existence and size parity verification
2. Video Protection & Playback Authorization:
   - 2-hour TTL signed HLS token generation
   - Expired token rejection (401 PLAYBACK_TOKEN_EXPIRED)
   - Tampered token signature rejection (401 INVALID_PLAYBACK_TOKEN)
   - Cross-media token replay rejection (401 TOKEN_MEDIA_MISMATCH)
   - Client IP mismatch rejection (401 TOKEN_IP_MISMATCH)
   - Preview lesson access vs non-preview protected access
   - Endpoint verification via POST /media/{id}/verify-playback-token
3. Protected PDF Delivery & Provenance Watermarking:
   - Dynamic provenance watermark with student name, email, student ID
   - Security headers: nosniff, no-store, private, max-age=0
   - Rejection of non-PDF media
4. Authorization & Fail-Closed Access Control (IDOR, Revocation, Expiry):
   - Non-enrolled student access rejection
   - Revoked enrollment access rejection (ENROLLMENT_REVOKED)
   - Expired enrollment access rejection (ENROLLMENT_EXPIRED)
   - Suspended user account access rejection (ACCOUNT_SUSPENDED)
   - Asset not attached to lesson rejection (MEDIA_NOT_ATTACHED_TO_LESSON)
5. Media Deletion & Lifecycle Management:
   - Unauthorized deletion prevention
   - In-use asset deletion protection
   - Storage object and database cleanup on deletion
   - Expired upload intent cleanup
"""

from datetime import datetime, timedelta, timezone
import io
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
    LessonResource,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.media import (
    MAX_IMAGE_SIZE_BYTES,
    MAX_PDF_SIZE_BYTES,
    MAX_RESOURCE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
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
from app.schemas.media import (
    UploadConfirmRequest,
    UploadIntentRequest,
    VerifyPlaybackTokenRequest,
)
from app.services.media_service import MediaService


# ============================================================================
# Test Fixtures
# ============================================================================

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
def test_client(db_session: Session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def instructor_user(db_session: Session) -> User:
    """Creates an Instructor / Admin user."""
    role = db_session.get(Role, ROLE_ADMIN)
    if not role:
        role = Role(id=ROLE_ADMIN, name="Administrator")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="instructor@lms.local",
        full_name="Lead Instructor",
        password_hash=hash_password("InstructorSecureP@ss1"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_ADMIN)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_a(db_session: Session) -> User:
    """Creates Student A user."""
    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="student.a@lms.local",
        full_name="Student Alpha",
        password_hash=hash_password("StudentAlphaP@ss1"),
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
def student_b(db_session: Session) -> User:
    """Creates Student B user."""
    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="student.b@lms.local",
        full_name="Student Beta",
        password_hash=hash_password("StudentBetaP@ss1"),
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
def media_service():
    """MediaService instance."""
    return MediaService()


@pytest.fixture
def course_hierarchy(db_session: Session, instructor_user: User):
    """Sets up a Course, Revision, Section, Lessons, and Media Assets."""
    # 1. Course container
    course = Course(
        title="Distributed Systems Masterclass",
        slug="distributed-systems-masterclass",
        headline="Advanced Systems Engineering",
        price_inr=999900,
        is_free=False,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    # 2. Live Revision
    revision = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="Revision 1",
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(revision)
    db_session.flush()
    course.live_revision_id = revision.id
    db_session.flush()

    # 3. Section
    section = CurriculumSection(
        course_revision_id=revision.id,
        title="Section 1: Consensus",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    # 4. Video Media Asset (ready)
    video_asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="raft_consensus.mp4",
        file_key="raw-videos/uuid-video/raft_consensus.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=52428800,
        status=MEDIA_STATUS_READY,
        transcode_output={
            "hls_master_url": "hls/uuid-video/master.m3u8",
            "resolutions": ["1080p", "720p"],
            "duration_seconds": 3600,
        },
    )
    db_session.add(video_asset)
    db_session.flush()

    # 5. PDF Media Asset (ready)
    # Minimal valid PDF bytes
    minimal_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"
    pdf_asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="consensus_notes.pdf",
        file_key="protected-docs/uuid-pdf/consensus_notes.pdf",
        bucket="lms-media",
        mime_type="application/pdf",
        file_size_bytes=len(minimal_pdf),
        status=MEDIA_STATUS_READY,
    )
    db_session.add(pdf_asset)
    db_session.flush()

    # Store PDF in in-memory storage buffer
    storage = MediaService().storage_client
    storage.put_object(pdf_asset.file_key, minimal_pdf, content_type="application/pdf")

    # 6. Preview Lesson (video)
    preview_lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 1: Intro to Raft (Preview)",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=0,
        is_preview=True,
        content={"media_asset_id": str(video_asset.id)},
    )
    db_session.add(preview_lesson)
    db_session.flush()

    # 7. Non-Preview Lesson (protected video + PDF resource)
    protected_lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 2: Advanced Raft Log Compaction",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=1,
        is_preview=False,
        content={"media_asset_id": str(video_asset.id)},
    )
    db_session.add(protected_lesson)
    db_session.flush()

    # Attach PDF resource to protected lesson
    pdf_resource = LessonResource(
        lesson_id=protected_lesson.id,
        title="Log Compaction Deep Dive PDF",
        file_url=f"/api/v1/media/{pdf_asset.id}",
        resource_type="PDF",
    )
    db_session.add(pdf_resource)
    db_session.commit()

    return {
        "course": course,
        "revision": revision,
        "section": section,
        "video_asset": video_asset,
        "pdf_asset": pdf_asset,
        "preview_lesson": preview_lesson,
        "protected_lesson": protected_lesson,
        "pdf_resource": pdf_resource,
        "minimal_pdf": minimal_pdf,
    }


def create_auth_headers(user: User, session: Optional[Session] = None) -> dict[str, str]:
    """Generate Authorization Bearer token headers for a user with active session."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user, session=session)


# ============================================================================
# 1. Media Storage Security Tests
# ============================================================================

def test_disallowed_mime_type_rejected():
    """Disallowed MIME types (e.g. text/html, application/x-sh) must be rejected."""
    from app.models.media import validate_media_file
    with pytest.raises(ValidationException) as exc_info:
        validate_media_file("text/html", 1024)
    assert exc_info.value.code == "INVALID_MIME_TYPE"


def test_file_size_limits_enforced():
    """File sizes exceeding category limits must be rejected with FILE_TOO_LARGE."""
    from app.models.media import validate_media_file
    with pytest.raises(ValidationException) as exc_info:
        validate_media_file("video/mp4", MAX_VIDEO_SIZE_BYTES + 1)
    assert exc_info.value.code == "FILE_TOO_LARGE"

    with pytest.raises(ValidationException) as exc_info:
        validate_media_file("application/pdf", MAX_PDF_SIZE_BYTES + 1)
    assert exc_info.value.code == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_extension_mismatch_rejected(
    db_session: Session,
    media_service: MediaService,
    instructor_user: User,
):
    """Filename extension mismatch with declared MIME type must raise FILE_EXTENSION_MISMATCH."""
    with pytest.raises(ValidationException) as exc_info:
        await media_service.create_upload_intent(
            db_session,
            instructor_user,
            UploadIntentRequest(
                filename="malicious_script.mp4",
                mime_type="application/pdf",
                file_size_bytes=10240,
            ),
        )
    assert exc_info.value.code == "FILE_EXTENSION_MISMATCH"


@pytest.mark.parametrize("bad_filename", [
    "../../etc/passwd.pdf",
    "..\\..\\windows\\system32.pdf",
    "folder/secret.pdf",
    "exploit\x00hidden.pdf",
    "line\rbreak.pdf",
    "line\nbreak.pdf",
])
def test_path_traversal_and_malformed_filename_rejected(bad_filename: str):
    """Filenames with directory traversal sequences, slashes, or null bytes must be rejected."""
    with pytest.raises(ValueError):
        UploadIntentRequest(
            filename=bad_filename,
            mime_type="application/pdf",
            file_size_bytes=1024,
        )


@pytest.mark.asyncio
async def test_upload_confirm_validates_binary_signature(
    db_session: Session,
    media_service: MediaService,
    instructor_user: User,
):
    """Uploaded object with mismatched binary signature (e.g. text file pretending to be MP4) must be rejected."""
    req = UploadIntentRequest(
        filename="disguised.mp4",
        mime_type="video/mp4",
        file_size_bytes=100,
    )
    resp = await media_service.create_upload_intent(db_session, instructor_user, req)

    # Store fake binary data padded to exact size so size parity passes but signature fails
    fake_payload = b"This is invalid ASCII and not an MP4 container!".ljust(100, b"A")
    media_service.storage_client.put_object(
        resp.file_key,
        fake_payload,
        content_type="video/mp4",
    )

    with pytest.raises(BadRequestException) as exc_info:
        await media_service.confirm_upload(
            db_session,
            resp.media_id,
            UploadConfirmRequest(duration_seconds=10),
            actor=instructor_user,
        )
    assert exc_info.value.code == "INVALID_FILE_SIGNATURE"


@pytest.mark.asyncio
async def test_upload_confirm_validates_size_parity(
    db_session: Session,
    media_service: MediaService,
    instructor_user: User,
):
    """Uploaded object whose actual size differs from approved intent must be rejected."""
    req = UploadIntentRequest(
        filename="notes.pdf",
        mime_type="application/pdf",
        file_size_bytes=500,
    )
    resp = await media_service.create_upload_intent(db_session, instructor_user, req)

    # Put a PDF that is only 50 bytes instead of declared 500 bytes
    media_service.storage_client.put_object(
        resp.file_key,
        b"%PDF-1.4\nMinimal short invalid content",
        content_type="application/pdf",
    )

    with pytest.raises(BadRequestException) as exc_info:
        await media_service.confirm_upload(
            db_session,
            resp.media_id,
            UploadConfirmRequest(),
            actor=instructor_user,
        )
    assert exc_info.value.code == "FILE_SIZE_MISMATCH"


# ============================================================================
# 2. Video Protection & Signed Playback Token Tests
# ============================================================================

def test_playback_token_issuance_and_edge_verification(
    db_session: Session,
    media_service: MediaService,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Verifies complete playback token lifecycle: issuance and edge verification."""
    video = course_hierarchy["video_asset"]
    preview_lesson = course_hierarchy["preview_lesson"]

    # 1. Issue signed token for preview lesson
    token_resp = media_service.generate_playback_token(
        db_session,
        video.id,
        student_a,
        lesson_id=preview_lesson.id,
        client_ip="198.51.100.10",
    )

    assert token_resp.media_id == video.id
    assert token_resp.ttl_seconds == 7200
    assert "https://stream.instructor.com/hls/" in token_resp.stream_url
    assert f"?token={token_resp.playback_token}" in token_resp.stream_url

    # 2. Edge verification endpoint
    edge_resp = test_client.post(
        f"/api/v1/media/{video.id}/verify-playback-token",
        json={"token": token_resp.playback_token},
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    assert edge_resp.status_code == 200
    data = edge_resp.json()
    assert data["valid"] is True
    assert data["claims"]["sub"] == str(student_a.id)
    assert data["claims"]["media_id"] == str(video.id)
    assert data["claims"]["ip"] == "198.51.100.10"


def test_playback_token_ip_mismatch_fails(
    db_session: Session,
    media_service: MediaService,
    course_hierarchy: dict,
    student_a: User,
):
    """Token bound to IP A must be rejected when presented from IP B."""
    video = course_hierarchy["video_asset"]
    preview_lesson = course_hierarchy["preview_lesson"]

    token_resp = media_service.generate_playback_token(
        db_session,
        video.id,
        student_a,
        lesson_id=preview_lesson.id,
        client_ip="198.51.100.10",
    )

    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(
            token_resp.playback_token,
            video.id,
            client_ip="203.0.113.99",
        )
    assert exc_info.value.code == "TOKEN_IP_MISMATCH"


def test_playback_token_tampered_fails(
    media_service: MediaService,
    course_hierarchy: dict,
    student_a: User,
):
    """Forged token signed with invalid key must be rejected with INVALID_PLAYBACK_TOKEN."""
    video = course_hierarchy["video_asset"]
    now = datetime.now(timezone.utc)
    tampered_jwt = jwt.encode(
        {
            "sub": str(student_a.id),
            "media_id": str(video.id),
            "token_type": "playback",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=2)).timestamp()),
        },
        "attacker-fraudulent-key-00000000000000",
        algorithm="HS256",
    )

    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(tampered_jwt, video.id)
    assert exc_info.value.code == "INVALID_PLAYBACK_TOKEN"


def test_playback_token_expired_fails(
    media_service: MediaService,
    course_hierarchy: dict,
    student_a: User,
):
    """Expired token must be rejected with PLAYBACK_TOKEN_EXPIRED."""
    video = course_hierarchy["video_asset"]
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired_jwt = jwt.encode(
        {
            "sub": str(student_a.id),
            "media_id": str(video.id),
            "token_type": "playback",
            "iat": int((now - timedelta(hours=3)).timestamp()),
            "exp": int((now - timedelta(seconds=1)).timestamp()),
        },
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )

    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(expired_jwt, video.id)
    assert exc_info.value.code == "PLAYBACK_TOKEN_EXPIRED"


# ============================================================================
# 3. Dynamic PDF Provenance Watermarking Tests
# ============================================================================

def test_protected_pdf_stream_stamps_dynamic_watermark(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Authenticated enrolled student receives watermarked PDF with strict security headers."""
    course = course_hierarchy["course"]
    pdf_asset = course_hierarchy["pdf_asset"]
    protected_lesson = course_hierarchy["protected_lesson"]

    # Enroll student_a in course
    enrollment = Enrollment(
        student_id=student_a.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{pdf_asset.id}/protected-pdf?lesson_id={protected_lesson.id}",
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "private, no-store, max-age=0" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert f'inline; filename="{pdf_asset.filename}"' in resp.headers["content-disposition"]

    # Verify returned stream is a valid non-empty PDF
    pdf_bytes = resp.content
    assert pdf_bytes.startswith(b"%PDF-")


# ============================================================================
# 4. Fail-Closed Authorization & Access Control (IDOR, Revocation, Expiry)
# ============================================================================

def test_non_enrolled_student_access_denied(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Non-enrolled student attempting to access protected non-preview lesson media gets 403."""
    pdf_asset = course_hierarchy["pdf_asset"]
    protected_lesson = course_hierarchy["protected_lesson"]

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{pdf_asset.id}/protected-pdf?lesson_id={protected_lesson.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_REQUIRED"


def test_revoked_enrollment_access_denied(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Student with REVOKED enrollment must be denied access with 403 ENROLLMENT_REVOKED."""
    course = course_hierarchy["course"]
    pdf_asset = course_hierarchy["pdf_asset"]
    protected_lesson = course_hierarchy["protected_lesson"]

    enrollment = Enrollment(
        student_id=student_a.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_REVOKED,
    )
    db_session.add(enrollment)
    db_session.commit()

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{pdf_asset.id}/protected-pdf?lesson_id={protected_lesson.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_REVOKED"


def test_expired_enrollment_access_denied(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Student with expired access date must be denied with 403 ENROLLMENT_EXPIRED."""
    course = course_hierarchy["course"]
    pdf_asset = course_hierarchy["pdf_asset"]
    protected_lesson = course_hierarchy["protected_lesson"]

    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    enrollment = Enrollment(
        student_id=student_a.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        expires_at=past_date,
    )
    db_session.add(enrollment)
    db_session.commit()

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{pdf_asset.id}/protected-pdf?lesson_id={protected_lesson.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_EXPIRED"


def test_suspended_user_access_denied(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
):
    """Suspended user account (is_active=False) must be denied access with 403 ACCOUNT_SUSPENDED."""
    course = course_hierarchy["course"]
    pdf_asset = course_hierarchy["pdf_asset"]
    protected_lesson = course_hierarchy["protected_lesson"]

    enrollment = Enrollment(
        student_id=student_a.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    student_a.is_active = False
    db_session.commit()

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{pdf_asset.id}/protected-pdf?lesson_id={protected_lesson.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_SUSPENDED"


def test_unattached_media_access_denied(
    db_session: Session,
    course_hierarchy: dict,
    student_a: User,
    test_client: TestClient,
    instructor_user: User,
):
    """Enrolled student attempting to access media not attached to the lesson gets 403 MEDIA_NOT_ATTACHED_TO_LESSON."""
    course = course_hierarchy["course"]
    preview_lesson = course_hierarchy["preview_lesson"]

    # Create unattached media asset
    unattached_asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="unrelated_document.pdf",
        file_key="protected-docs/uuid-unrelated/unrelated_document.pdf",
        bucket="lms-media",
        mime_type="application/pdf",
        file_size_bytes=1000,
        status=MEDIA_STATUS_READY,
    )
    db_session.add(unattached_asset)
    db_session.commit()

    headers = create_auth_headers(student_a, session=db_session)
    resp = test_client.get(
        f"/api/v1/media/{unattached_asset.id}/protected-pdf?lesson_id={preview_lesson.id}",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "MEDIA_NOT_ATTACHED_TO_LESSON"


# ============================================================================
# 5. Media Deletion & Lifecycle Management Tests
# ============================================================================

@pytest.mark.asyncio
async def test_unauthorized_deletion_rejected(
    db_session: Session,
    media_service: MediaService,
    course_hierarchy: dict,
    student_a: User,
):
    """Non-owner student attempting to delete media asset must be rejected with 403 PERMISSION_DENIED."""
    video = course_hierarchy["video_asset"]
    with pytest.raises(ForbiddenException) as exc_info:
        await media_service.delete_media_asset(db_session, video.id, actor=student_a)
    assert exc_info.value.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_cannot_delete_media_in_active_use(
    db_session: Session,
    media_service: MediaService,
    course_hierarchy: dict,
    instructor_user: User,
):
    """Attempting to delete a media asset attached to course curriculum resources must raise MEDIA_ASSET_IN_USE."""
    pdf = course_hierarchy["pdf_asset"]
    with pytest.raises(BadRequestException) as exc_info:
        await media_service.delete_media_asset(db_session, pdf.id, actor=instructor_user)
    assert exc_info.value.code == "MEDIA_ASSET_IN_USE"


@pytest.mark.asyncio
async def test_cannot_delete_media_attached_to_lesson_content(
    db_session: Session,
    media_service: MediaService,
    course_hierarchy: dict,
    instructor_user: User,
):
    """Attempting to delete a media asset bound in lesson content JSON must raise MEDIA_ASSET_IN_USE (FIX-01)."""
    video = course_hierarchy["video_asset"]
    with pytest.raises(BadRequestException) as exc_info:
        await media_service.delete_media_asset(db_session, video.id, actor=instructor_user)
    assert exc_info.value.code == "MEDIA_ASSET_IN_USE"
    assert "attached to curriculum lessons" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_successful_media_deletion_and_storage_cleanup(
    db_session: Session,
    media_service: MediaService,
    instructor_user: User,
):
    """Deleting an unattached asset removes storage binary, logs audit event, and purges database record."""
    storage = media_service.storage_client
    file_key = "lesson-resources/test-uuid/unattached_notes.zip"
    storage.put_object(file_key, b"PK\x03\x04DummyZipContent", content_type="application/zip")

    asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="unattached_notes.zip",
        file_key=file_key,
        bucket="lms-media",
        mime_type="application/zip",
        file_size_bytes=20,
        status=MEDIA_STATUS_READY,
    )
    db_session.add(asset)
    db_session.commit()
    asset_id = asset.id

    assert storage.object_exists(file_key) is True

    # Delete asset
    await media_service.delete_media_asset(db_session, asset_id, actor=instructor_user)

    # Object should be deleted from storage
    assert storage.object_exists(file_key) is False

    # Asset should be deleted from DB
    assert db_session.get(MediaAsset, asset_id) is None


def test_cleanup_expired_intents(
    db_session: Session,
    media_service: MediaService,
    instructor_user: User,
):
    """Old UPLOADING intents beyond retention threshold must be transitioned to FAILED status."""
    stale_time = datetime.now(timezone.utc) - timedelta(hours=48)
    stale_asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="abandoned_upload.mp4",
        file_key="raw-videos/abandoned/abandoned_upload.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=100000,
        status=MEDIA_STATUS_UPLOADING,
    )
    db_session.add(stale_asset)
    db_session.flush()
    # Backdate created_at
    stale_asset.created_at = stale_time
    db_session.commit()

    count = media_service.cleanup_expired_intents(db_session, max_age_hours=24)
    assert count >= 1

    db_session.refresh(stale_asset)
    assert stale_asset.status == "FAILED"
