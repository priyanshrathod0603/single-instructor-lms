"""Unit tests for Curriculum Drag-and-Drop Reordering with Optimistic Concurrency (TASK303).

Verifies:
1. Section reordering updates sort_order cleanly when version_timestamp matches.
2. Section reordering raises HTTP 409 CONCURRENT_EDIT_CONFLICT when version_timestamp is older than revision.updated_at.
3. Lesson reordering updates sort_order cleanly when version_timestamp matches.
4. Lesson reordering raises HTTP 409 CONCURRENT_EDIT_CONFLICT when version_timestamp is stale.
5. Immutability guard: attempting to reorder sections or lessons in a PUBLISHED revision raises HTTP 403 REVISION_IMMUTABLE.
6. Validation guard: submitting invalid or foreign UUIDs raises HTTP 409 INVALID_REORDER_PAYLOAD.
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ConflictException, ForbiddenException
from app.models.base import Base, utc_now
from app.models.course import REVISION_STATUS_DRAFT, REVISION_STATUS_PUBLISHED
from app.models.curriculum import LESSON_TYPE_ARTICLE, LESSON_TYPE_VIDEO
from app.schemas.course import (
    CourseCreateRequest,
    LessonReorderRequest,
    SectionReorderRequest,
)
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


@pytest.mark.asyncio
async def test_section_reorder_happy_path(db_session: Session, course_service: CourseService):
    """Reordering sections with valid timestamp updates sort_order accurately."""
    req = CourseCreateRequest(title="Reorder Test Course", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Sec A", sort_order=0)
    s2 = repo.create_section(db_session, revision=rev, title="Sec B", sort_order=1)
    s3 = repo.create_section(db_session, revision=rev, title="Sec C", sort_order=2)
    db_session.commit()

    # Capture valid version timestamp
    client_version_ts = rev.updated_at

    # Reverse order: [s3, s2, s1]
    reorder_req = SectionReorderRequest(
        section_ids=[s3.id, s2.id, s1.id],
        version_timestamp=client_version_ts + timedelta(seconds=1),
    )

    reordered = course_service.reorder_sections(db_session, course.id, rev.id, reorder_req)
    db_session.commit()

    assert len(reordered) == 3
    assert reordered[0].id == s3.id
    assert reordered[0].sort_order == 0
    assert reordered[1].id == s2.id
    assert reordered[1].sort_order == 1
    assert reordered[2].id == s1.id
    assert reordered[2].sort_order == 2


@pytest.mark.asyncio
async def test_section_reorder_concurrent_edit_conflict(db_session: Session, course_service: CourseService):
    """Reordering sections with a stale version_timestamp must raise ConflictException."""
    req = CourseCreateRequest(title="Conflict Test Course", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Sec 1", sort_order=0)
    s2 = repo.create_section(db_session, revision=rev, title="Sec 2", sort_order=1)
    db_session.commit()

    # Stale timestamp from the past
    stale_ts = rev.updated_at - timedelta(minutes=5)

    reorder_req = SectionReorderRequest(
        section_ids=[s2.id, s1.id],
        version_timestamp=stale_ts,
    )

    with pytest.raises(ConflictException) as exc_info:
        course_service.reorder_sections(db_session, course.id, rev.id, reorder_req)

    assert exc_info.value.code == "CONCURRENT_EDIT_CONFLICT"


@pytest.mark.asyncio
async def test_lesson_reorder_happy_path(db_session: Session, course_service: CourseService):
    """Reordering lessons within a section updates sort_order accurately."""
    req = CourseCreateRequest(title="Lesson Reorder Course", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Module 1", sort_order=0)
    l1 = repo.create_lesson(db_session, section=s1, title="L1", lesson_type=LESSON_TYPE_VIDEO, sort_order=0)
    l2 = repo.create_lesson(db_session, section=s1, title="L2", lesson_type=LESSON_TYPE_ARTICLE, sort_order=1)
    l3 = repo.create_lesson(db_session, section=s1, title="L3", lesson_type=LESSON_TYPE_VIDEO, sort_order=2)
    db_session.commit()

    client_ts = rev.updated_at

    reorder_req = LessonReorderRequest(
        lesson_ids=[l3.id, l1.id, l2.id],
        version_timestamp=client_ts + timedelta(seconds=1),
    )

    reordered = course_service.reorder_lessons(db_session, s1.id, reorder_req)
    db_session.commit()

    assert len(reordered) == 3
    assert reordered[0].id == l3.id
    assert reordered[0].sort_order == 0
    assert reordered[1].id == l1.id
    assert reordered[1].sort_order == 1
    assert reordered[2].id == l2.id
    assert reordered[2].sort_order == 2


@pytest.mark.asyncio
async def test_lesson_reorder_concurrent_conflict(db_session: Session, course_service: CourseService):
    """Reordering lessons with a stale timestamp raises ConflictException."""
    req = CourseCreateRequest(title="Lesson Conflict Course", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Module 1", sort_order=0)
    l1 = repo.create_lesson(db_session, section=s1, title="L1", lesson_type=LESSON_TYPE_VIDEO, sort_order=0)
    l2 = repo.create_lesson(db_session, section=s1, title="L2", lesson_type=LESSON_TYPE_ARTICLE, sort_order=1)
    db_session.commit()

    stale_ts = rev.updated_at - timedelta(hours=1)

    reorder_req = LessonReorderRequest(
        lesson_ids=[l2.id, l1.id],
        version_timestamp=stale_ts,
    )

    with pytest.raises(ConflictException) as exc_info:
        course_service.reorder_lessons(db_session, s1.id, reorder_req)

    assert exc_info.value.code == "CONCURRENT_EDIT_CONFLICT"


@pytest.mark.asyncio
async def test_immutability_guard_blocks_reordering_published_revision(db_session: Session, course_service: CourseService):
    """Published revisions are immutable: reordering sections or lessons must be rejected with 403."""
    req = CourseCreateRequest(
        title="Immutable Publishing Course",
        headline="Testing frozen revisions",
        is_free=True,
    )
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Sec 1", sort_order=0)
    l1 = repo.create_lesson(db_session, section=s1, title="Les 1", lesson_type=LESSON_TYPE_VIDEO, sort_order=0)
    s2 = repo.create_section(db_session, revision=rev, title="Sec 2", sort_order=1)
    l2 = repo.create_lesson(db_session, section=s2, title="Les 2", lesson_type=LESSON_TYPE_ARTICLE, sort_order=0)
    db_session.commit()

    # Publish revision
    await course_service.publish_revision(db_session, course.id, rev.id)
    db_session.commit()

    # Attempting to reorder sections on published revision must fail
    with pytest.raises(ForbiddenException) as exc_info:
        course_service.reorder_sections(
            db_session,
            course.id,
            rev.id,
            SectionReorderRequest(
                section_ids=[s2.id, s1.id],
                version_timestamp=utc_now() + timedelta(minutes=1),
            ),
        )
    assert exc_info.value.code == "REVISION_IMMUTABLE"

    # Attempting to reorder lessons on published revision must fail
    with pytest.raises(ForbiddenException) as exc_info:
        course_service.reorder_lessons(
            db_session,
            s1.id,
            LessonReorderRequest(
                lesson_ids=[l1.id],
                version_timestamp=utc_now() + timedelta(minutes=1),
            ),
        )
    assert exc_info.value.code == "REVISION_IMMUTABLE"


@pytest.mark.asyncio
async def test_invalid_reorder_payload_fails(db_session: Session, course_service: CourseService):
    """Passing invalid or foreign IDs during reordering must fail with INVALID_REORDER_PAYLOAD."""
    req = CourseCreateRequest(title="Validation Course", is_free=True)
    course, rev = await course_service.create_course(db_session, req)
    repo = course_service.repo

    s1 = repo.create_section(db_session, revision=rev, title="Sec 1", sort_order=0)
    db_session.commit()

    foreign_uuid = uuid.uuid4()
    with pytest.raises(ConflictException) as exc_info:
        course_service.reorder_sections(
            db_session,
            course.id,
            rev.id,
            SectionReorderRequest(
                section_ids=[foreign_uuid],
                version_timestamp=utc_now() + timedelta(minutes=1),
            ),
        )
    assert exc_info.value.code == "INVALID_REORDER_PAYLOAD"
