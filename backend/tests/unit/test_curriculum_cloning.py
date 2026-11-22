"""Unit tests for Course Revision Spawning & Deep Hierarchy Cloning (TASK302).

Verifies:
1. Initial course creation with draft revision 1.
2. Multi-tier curriculum construction (sections, lessons, resources).
3. Spawning new draft revision (deep hierarchy cloning):
   - Generates new UUIDs for cloned entities.
   - Preserves sort ordering, content, preview flags, and resource associations.
   - Sets revision_no = N + 1 and status = DRAFT.
4. Draft isolation: changes to cloned draft revision do NOT mutate source revision.
5. Concurrency protection: prevents spawning a new draft when an uncommitted draft already exists.
"""

from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ConflictException
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_ARCHIVED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
)
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_VIDEO,
    RESOURCE_TYPE_PDF,
    RESOURCE_TYPE_SOURCE_CODE,
)
from app.repositories.course_repo import CourseRepository
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


@pytest.mark.asyncio
async def test_initial_course_creation_spawns_draft_rev_1(db_session: Session, course_service: CourseService):
    """Creating a course must atomically create the course container and initial draft revision 1."""
    req = CourseCreateRequest(
        title="Distributed Systems with Python",
        slug="distributed-systems-python",
        headline="Build fault-tolerant distributed backends",
        description="Comprehensive course on distributed architectures.",
        price_inr=799900,
        is_free=False,
        tags=["python", "distributed-systems", "backend"],
    )

    course, rev1 = await course_service.create_course(db_session, req)
    db_session.commit()

    assert course.id is not None
    assert course.slug == "distributed-systems-python"
    assert course.status == COURSE_STATUS_DRAFT
    assert course.price_inr == 799900
    assert course.is_free is False
    assert len(course.tags) == 3

    assert rev1.id is not None
    assert rev1.course_id == course.id
    assert rev1.revision_no == 1
    assert rev1.status == REVISION_STATUS_DRAFT
    assert "Draft 1" in rev1.title


@pytest.mark.asyncio
async def test_deep_clone_hierarchy_preserves_tree_structure(db_session: Session, course_service: CourseService):
    """Spawning a new revision must deep clone all sections, lessons, and resources with new UUIDs."""
    req = CourseCreateRequest(
        title="Microservices Masterclass",
        slug="microservices-masterclass",
        headline="Architecting enterprise microservices",
        price_inr=0,
        is_free=True,
    )
    course, rev1 = await course_service.create_course(db_session, req)
    db_session.commit()

    # Populate Revision 1 Curriculum Tree
    repo = course_service.repo

    # Section 1
    s1 = repo.create_section(db_session, revision=rev1, title="Section 1: Service Design", sort_order=0)
    l1 = repo.create_lesson(
        db_session,
        section=s1,
        title="1.1 Service Boundaries",
        lesson_type=LESSON_TYPE_VIDEO,
        duration_seconds=1500,
        is_preview=True,
        sort_order=0,
        content={"video_id": "vid-101"},
    )
    l2 = repo.create_lesson(
        db_session,
        section=s1,
        title="1.2 Domain Driven Design Principles",
        lesson_type=LESSON_TYPE_ARTICLE,
        duration_seconds=800,
        is_preview=False,
        sort_order=1,
    )
    r1 = repo.create_resource(
        db_session,
        lesson=l1,
        title="Architecture Cheat Sheet",
        resource_type=RESOURCE_TYPE_PDF,
        file_url="https://cdn.example.com/sheet.pdf",
        file_size_bytes=204800,
    )

    # Section 2
    s2 = repo.create_section(db_session, revision=rev1, title="Section 2: Communication Patterns", sort_order=1)
    l3 = repo.create_lesson(
        db_session,
        section=s2,
        title="2.1 Synchronous vs Asynchronous",
        lesson_type=LESSON_TYPE_VIDEO,
        duration_seconds=1200,
        sort_order=0,
    )
    db_session.commit()

    # Publish revision 1 so we can spawn revision 2
    pub_rev = await course_service.publish_revision(db_session, course.id, rev1.id)
    db_session.commit()
    assert pub_rev.status == REVISION_STATUS_PUBLISHED
    assert course.status == COURSE_STATUS_PUBLISHED
    assert course.live_revision_id == rev1.id

    # Now spawn Revision 2
    rev2_resp = await course_service.spawn_revision(
        db_session,
        course.id,
        changelog="Adding event-driven architecture modules",
    )
    db_session.commit()

    assert rev2_resp.revision_no == 2
    assert rev2_resp.status == REVISION_STATUS_DRAFT
    assert rev2_resp.id != rev1.id
    assert len(rev2_resp.sections) == 2

    # Verify Section 1 Cloned Correctly
    sec1_clone = rev2_resp.sections[0]
    assert sec1_clone.id != s1.id
    assert sec1_clone.title == "Section 1: Service Design"
    assert sec1_clone.sort_order == 0
    assert len(sec1_clone.lessons) == 2

    les1_clone = sec1_clone.lessons[0]
    assert les1_clone.id != l1.id
    assert les1_clone.title == "1.1 Service Boundaries"
    assert les1_clone.lesson_type == LESSON_TYPE_VIDEO
    assert les1_clone.duration_seconds == 1500
    assert les1_clone.is_preview is True
    assert les1_clone.content == {"video_id": "vid-101"}
    assert len(les1_clone.resources) == 1

    res1_clone = les1_clone.resources[0]
    assert res1_clone.id != r1.id
    assert res1_clone.title == "Architecture Cheat Sheet"
    assert res1_clone.resource_type == RESOURCE_TYPE_PDF
    assert res1_clone.file_url == "https://cdn.example.com/sheet.pdf"

    # Verify Section 2 Cloned Correctly
    sec2_clone = rev2_resp.sections[1]
    assert sec2_clone.id != s2.id
    assert sec2_clone.title == "Section 2: Communication Patterns"
    assert sec2_clone.sort_order == 1
    assert len(sec2_clone.lessons) == 1


@pytest.mark.asyncio
async def test_draft_isolation_does_not_mutate_published_revision(db_session: Session, course_service: CourseService):
    """Mutating the cloned draft revision must not alter published revision data or snapshot."""
    req = CourseCreateRequest(
        title="Isolation Test Course",
        headline="Testing draft isolation invariant",
        is_free=True,
    )
    course, rev1 = await course_service.create_course(db_session, req)
    s1 = course_service.repo.create_section(db_session, revision=rev1, title="Original Section", sort_order=0)
    l1 = course_service.repo.create_lesson(
        db_session, section=s1, title="Original Lesson", lesson_type=LESSON_TYPE_VIDEO, sort_order=0
    )
    db_session.commit()

    # Publish revision 1
    await course_service.publish_revision(db_session, course.id, rev1.id)
    db_session.commit()

    # Spawn Revision 2
    rev2_resp = await course_service.spawn_revision(db_session, course.id, changelog="Rev 2 edits")
    db_session.commit()

    # Mutate Section in Revision 2
    sec2_id = rev2_resp.sections[0].id
    sec2 = course_service.repo.get_section_by_id(db_session, sec2_id)
    course_service.repo.update_section(db_session, sec2, title="Altered Section in Draft 2")
    db_session.commit()

    # Refresh Revision 1 and verify untouched
    rev1_refreshed = course_service.repo.get_revision_by_id(db_session, rev1.id)
    assert rev1_refreshed.sections[0].title == "Original Section"
    assert rev1_refreshed.snapshot["sections"][0]["title"] == "Original Section"


@pytest.mark.asyncio
async def test_prevent_concurrent_draft_spawning(db_session: Session, course_service: CourseService):
    """Attempting to spawn a new draft when an uncommitted draft already exists must raise ConflictException."""
    req = CourseCreateRequest(title="Concurrency Test Course", is_free=True)
    course, rev1 = await course_service.create_course(db_session, req)
    db_session.commit()

    # rev1 is currently in DRAFT status. Spawning another draft must fail.
    with pytest.raises(ConflictException) as exc_info:
        await course_service.spawn_revision(db_session, course.id)

    assert exc_info.value.code == "DRAFT_REVISION_EXISTS"
