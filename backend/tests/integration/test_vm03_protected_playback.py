"""Comprehensive integration tests for VM-03: Protected Video Playback.

Strictly verifies all 17 backend requirements specified in VM-03 PART E:
1. Authorized enrolled student playback.
2. Non-enrolled student denied.
3. Unauthenticated user denied.
4. Wrong course access denied.
5. Wrong lesson access denied.
6. Lesson/media association validation.
7. Media not READY denied.
8. Invalid token denied.
9. Expired token denied.
10. Token bound to the wrong media denied.
11. Token/session reuse restrictions as applicable (IP binding).
12. Master playlist authorization.
13. Variant playlist authorization.
14. Segment authorization.
15. Missing HLS output handling.
16. Media processing failure handling.
17. Storage/CDN error handling & path traversal prevention.
"""

from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.core.security import hash_password
from app.core.storage import StorageClient
from app.main import create_app
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.media import (
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
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

    # Pre-populate roles
    for r_id, r_name in [
        (ROLE_SUPER_ADMIN, "Super Admin"),
        (ROLE_ADMIN, "Admin"),
        (ROLE_STUDENT, "Student"),
    ]:
        if not session.get(Role, r_id):
            session.add(Role(id=r_id, name=r_name))
    session.commit()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def storage():
    """Storage client configured for test environment."""
    return StorageClient()


@pytest.fixture
def instructor_user(db_session: Session) -> User:
    """Creates a verified instructor (Admin)."""
    user = User(
        email="instructor@lms.local",
        full_name="Lead Instructor",
        password_hash=hash_password("InstructorSecureP@ss1"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=ROLE_ADMIN))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def enrolled_student(db_session: Session) -> User:
    """Creates an enrolled, active student user."""
    user = User(
        email="enrolled@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentSecureP@ss1"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=ROLE_STUDENT))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def non_enrolled_student(db_session: Session) -> User:
    """Creates a student without course enrollment."""
    user = User(
        email="outsider@lms.local",
        full_name="Outsider Student",
        password_hash=hash_password("StudentSecureP@ss1"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=ROLE_STUDENT))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def published_course(db_session: Session, instructor_user: User):
    """Creates a published course with revision and sections."""
    course = Course(
        title="Production System Design",
        slug="production-system-design",
        description="Masterclass on distributed architecture.",
        status=COURSE_STATUS_PUBLISHED,
        price_inr=199,
    )
    db_session.add(course)
    db_session.flush()

    revision = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="Production System Design v1",
        status=REVISION_STATUS_PUBLISHED,
    )
    db_session.add(revision)
    db_session.flush()

    course.live_revision_id = revision.id

    section = CurriculumSection(
        course_revision_id=revision.id,
        title="Module 1: Video Storage & CDN",
        sort_order=1,
    )
    db_session.add(section)
    db_session.flush()

    db_session.commit()
    return course, revision, section


@pytest.fixture
def video_media_asset(db_session: Session, instructor_user: User, storage: StorageClient) -> MediaAsset:
    """Creates a READY video media asset with simulated HLS artifacts in storage."""
    asset = MediaAsset(
        uploader_id=instructor_user.id,
        filename="lecture_01.mp4",
        file_key="raw-videos/lecture_01.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=50_000_000,
        status=MEDIA_STATUS_READY,
        transcode_output={
            "hls_master_url": "https://stream.instructor.com/media/test/hls/master.m3u8",
            "resolutions": ["1080p", "720p"],
            "duration_seconds": 120,
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    # Populate storage with realistic HLS artifacts
    prefix = f"media/{asset.id}/hls"

    master_m3u8 = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=4500000,RESOLUTION=1920x1080
1080p/prog_index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p/prog_index.m3u8
"""
    storage.put_object(f"{prefix}/master.m3u8", master_m3u8.encode("utf-8"), "application/vnd.apple.mpegurl")

    variant_1080p = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.000,
segment_000.ts
#EXTINF:6.000,
segment_001.ts
#EXT-X-ENDLIST
"""
    storage.put_object(f"{prefix}/1080p/prog_index.m3u8", variant_1080p.encode("utf-8"), "application/vnd.apple.mpegurl")

    segment_data = b"\x47\x40\x00\x10" + b"\xFF" * 184 # MPEG-2 Transport Stream packet
    storage.put_object(f"{prefix}/1080p/segment_000.ts", segment_data, "video/MP2T")
    storage.put_object(f"{prefix}/1080p/segment_001.ts", segment_data, "video/MP2T")

    return asset


@pytest.fixture
def video_lesson(db_session: Session, published_course, video_media_asset: MediaAsset) -> CurriculumLesson:
    """Creates a video lesson attached canonically to video_media_asset."""
    course, revision, section = published_course
    lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 1: HLS Architecture",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=1,
        is_preview=False,
        content={"media_asset_id": str(video_media_asset.id), "duration": 120},
    )
    db_session.add(lesson)
    db_session.commit()
    db_session.refresh(lesson)
    return lesson


@pytest.fixture
def student_enrollment(db_session: Session, enrolled_student: User, published_course) -> Enrollment:
    """Enrolls enrolled_student into published_course."""
    course, _, _ = published_course
    enrollment = Enrollment(
        student_id=enrolled_student.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()
    db_session.refresh(enrollment)
    return enrollment


@pytest.fixture
def test_client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden database dependency."""
    from app.api.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app, base_url="http://testserver")
    return client


from tests.conftest import create_test_auth_headers


# =============================================================================
# TESTS IMPLEMENTING VM-03 PART E
# =============================================================================

def test_1_authorized_enrolled_student_playback(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """1. Authorized enrolled student gets playback token and successfully fetches HLS master."""
    course, _, _ = published_course
    auth_header = create_test_auth_headers(enrolled_student, session=db_session)

    # Issue playback token
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id), "course_id": str(course.id)},
        headers=auth_header,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data["playback_token"]
    assert data["media_id"] == str(video_media_asset.id)
    assert "https://stream.instructor.com/hls/" in data["stream_url"]

    # Stream master playlist via protected endpoint with token
    master_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": token},
    )
    assert master_resp.status_code == 200
    assert master_resp.headers["content-type"] == "application/vnd.apple.mpegurl"
    assert "1080p/prog_index.m3u8?token=" in master_resp.text


def test_2_non_enrolled_student_denied(
    test_client: TestClient,
    db_session: Session,
    non_enrolled_student: User,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """2. Non-enrolled student is denied access with 403 ENROLLMENT_REQUIRED."""
    course, _, _ = published_course
    auth_header = create_test_auth_headers(non_enrolled_student, session=db_session)

    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id), "course_id": str(course.id)},
        headers=auth_header,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_REQUIRED"


def test_3_unauthenticated_user_denied(
    test_client: TestClient,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """3. Unauthenticated request to issue token is denied with 401."""
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id)},
    )
    assert resp.status_code == 401


def test_4_wrong_course_access_denied(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """4. Passing a mismatched course_id returns 403 COURSE_LESSON_MISMATCH."""
    auth_header = create_test_auth_headers(enrolled_student, session=db_session)
    random_course_id = str(uuid.uuid4())

    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id), "course_id": random_course_id},
        headers=auth_header,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "COURSE_LESSON_MISMATCH"


def test_5_and_6_wrong_lesson_and_association_denied(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_media_asset: MediaAsset,
):
    """5 & 6. Lesson not attached to requested media returns 403 MEDIA_NOT_ATTACHED_TO_LESSON."""
    course, revision, section = published_course
    other_lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 2: Other Topic",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=2,
        is_preview=False,
        content={"media_asset_id": str(uuid.uuid4())}, # Different media ID
    )
    db_session.add(other_lesson)
    db_session.commit()

    auth_header = create_test_auth_headers(enrolled_student, session=db_session)
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(other_lesson.id), "course_id": str(course.id)},
        headers=auth_header,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "MEDIA_NOT_ATTACHED_TO_LESSON"


def test_7_and_16_media_not_ready_denied(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """7 & 16. Media assets in PROCESSING or FAILED status are rejected with MEDIA_NOT_READY."""
    video_media_asset.status = MEDIA_STATUS_PROCESSING
    db_session.commit()

    auth_header = create_test_auth_headers(enrolled_student, session=db_session)
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id)},
        headers=auth_header,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MEDIA_NOT_READY"

    # FAILED status also rejected
    video_media_asset.status = MEDIA_STATUS_FAILED
    db_session.commit()
    resp2 = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id)},
        headers=auth_header,
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "MEDIA_NOT_READY"


def test_8_invalid_token_denied(
    test_client: TestClient,
    video_media_asset: MediaAsset,
):
    """8. Invalid or tampered playback token is rejected with 401."""
    resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": "invalid.tampered.token"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_PLAYBACK_TOKEN"


def test_9_expired_token_denied(
    test_client: TestClient,
    enrolled_student: User,
    video_media_asset: MediaAsset,
):
    """9. Expired playback token is rejected with 401 PLAYBACK_TOKEN_EXPIRED."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(enrolled_student.id),
        "media_id": str(video_media_asset.id),
        "token_type": "playback",
        "iat": int((now - timedelta(hours=3)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)

    resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": expired_token},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "PLAYBACK_TOKEN_EXPIRED"


def test_10_token_bound_to_wrong_media_denied(
    test_client: TestClient,
    enrolled_student: User,
    video_media_asset: MediaAsset,
):
    """10. Token generated for Media A is rejected when attempting to stream Media B."""
    settings = get_settings()
    other_media_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    token_payload = {
        "sub": str(enrolled_student.id),
        "media_id": str(other_media_id),
        "token_type": "playback",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=2)).timestamp()),
    }
    token = jwt.encode(token_payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)

    resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": token},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_MEDIA_MISMATCH"


def test_11_token_ip_binding_restrictions(
    db_session: Session,
    enrolled_student: User,
    video_media_asset: MediaAsset,
):
    """11. Token bound to client IP 198.51.100.1 is rejected when accessed from 203.0.113.2."""
    media_service = MediaService()
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(enrolled_student.id),
        "media_id": str(video_media_asset.id),
        "ip": "198.51.100.1",
        "token_type": "playback",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=2)).timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)

    # Verifying from same IP succeeds
    claims = media_service.verify_playback_token(token, video_media_asset.id, client_ip="198.51.100.1")
    assert claims["ip"] == "198.51.100.1"

    # Verifying from different IP fails
    from app.core.exceptions import UnauthorizedException
    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(token, video_media_asset.id, client_ip="203.0.113.2")
    assert exc_info.value.code == "TOKEN_IP_MISMATCH"


def test_12_13_14_end_to_end_playlist_and_segment_authorization(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """12, 13 & 14. Master playlist -> Variant playlist -> Video segment authorization propagation."""
    course, _, _ = published_course
    auth_header = create_test_auth_headers(enrolled_student, session=db_session)

    # Obtain valid playback token
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id), "course_id": str(course.id)},
        headers=auth_header,
    )
    token = resp.json()["playback_token"]

    # Step 1: Master playlist (D12)
    master_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": token},
    )
    assert master_resp.status_code == 200
    assert "1080p/prog_index.m3u8?token=" in master_resp.text

    # Step 2: Variant playlist (D13)
    variant_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/1080p/prog_index.m3u8",
        params={"token": token},
    )
    assert variant_resp.status_code == 200
    assert variant_resp.headers["content-type"] == "application/vnd.apple.mpegurl"
    assert "segment_000.ts?token=" in variant_resp.text
    assert "segment_001.ts?token=" in variant_resp.text

    # Step 3: Video segment (D14)
    segment_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/1080p/segment_000.ts",
        params={"token": token},
    )
    assert segment_resp.status_code == 200
    assert segment_resp.headers["content-type"] == "video/MP2T"
    assert len(segment_resp.content) > 0

    # Step 4: Unauthenticated segment request without token MUST BE REJECTED
    unauth_seg = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/1080p/segment_000.ts"
    )
    assert unauth_seg.status_code == 401
    assert unauth_seg.json()["error"]["code"] == "MISSING_TOKEN"


def test_15_missing_hls_output_handling(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """15. Media asset without transcode_output is rejected with 400 HLS_OUTPUT_MISSING when streaming."""
    video_media_asset.transcode_output = None
    db_session.commit()

    auth_header = create_test_auth_headers(enrolled_student, session=db_session)
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id)},
        headers=auth_header,
    )
    assert resp.status_code == 200
    token = resp.json()["playback_token"]

    stream_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/master.m3u8",
        params={"token": token},
    )
    assert stream_resp.status_code == 400
    assert stream_resp.json()["error"]["code"] == "HLS_OUTPUT_MISSING"


def test_17_storage_error_and_path_traversal_rejection(
    test_client: TestClient,
    db_session: Session,
    enrolled_student: User,
    student_enrollment: Enrollment,
    published_course,
    video_lesson: CurriculumLesson,
    video_media_asset: MediaAsset,
):
    """17. Storage 404 for missing segment & 400 for path traversal attempts."""
    auth_header = create_test_auth_headers(enrolled_student, session=db_session)
    resp = test_client.post(
        f"/api/v1/media/{video_media_asset.id}/playback-token",
        json={"lesson_id": str(video_lesson.id)},
        headers=auth_header,
    )
    token = resp.json()["playback_token"]

    # Missing segment returns 404
    missing_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/1080p/nonexistent_segment.ts",
        params={"token": token},
    )
    assert missing_resp.status_code == 404

    # Path traversal attempts are strictly rejected
    traversal_resp = test_client.get(
        f"/api/v1/media/{video_media_asset.id}/hls/1080p/%2e%2e/%2e%2e/etc/passwd.m3u8",
        params={"token": token},
    )
    assert traversal_resp.status_code == 400
    assert traversal_resp.json()["error"]["code"] == "INVALID_HLS_PATH"

    # Direct service call path traversal prevention
    media_service = MediaService()
    with pytest.raises(BadRequestException) as exc_info:
        media_service.stream_hls_resource(
            db_session,
            video_media_asset.id,
            "../../etc/passwd.m3u8",
            token=token,
        )
    assert exc_info.value.code == "INVALID_HLS_PATH"
