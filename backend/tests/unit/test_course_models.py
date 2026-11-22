"""Unit tests for Course and Curriculum SQLAlchemy models.

Verifies:
1. Model field definitions, data types, constraints, and defaults.
2. Relationships: Course <-> CourseRevision, CourseRevision <-> CurriculumSection,
   CurriculumSection <-> CurriculumLesson, CurriculumLesson <-> LessonResource,
   Course <-> CourseTag.
3. Circular reference: Course.live_revision <-> CourseRevision.
4. Constants and valid statuses: DRAFT, PUBLISHED, ARCHIVED.
5. Minor currency invariant: price_inr as integer paise.
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_ARCHIVED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    VALID_COURSE_STATUSES,
    VALID_REVISION_STATUSES,
    Course,
    CourseRevision,
    CourseTag,
)
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_ASSIGNMENT,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_VIDEO,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_LINK,
    RESOURCE_TYPE_PDF,
    RESOURCE_TYPE_SOURCE_CODE,
    VALID_LESSON_TYPES,
    VALID_RESOURCE_TYPES,
    CurriculumLesson,
    CurriculumSection,
    LessonResource,
)
from app.models.user import User


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database session with all models created."""
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


class TestCourseConstants:
    """Verifies domain constants and status enums."""

    def test_course_statuses(self):
        assert COURSE_STATUS_DRAFT == "DRAFT"
        assert COURSE_STATUS_PUBLISHED == "PUBLISHED"
        assert COURSE_STATUS_ARCHIVED == "ARCHIVED"
        assert VALID_COURSE_STATUSES == {"DRAFT", "PUBLISHED", "ARCHIVED"}

    def test_revision_statuses(self):
        assert REVISION_STATUS_DRAFT == "DRAFT"
        assert REVISION_STATUS_PUBLISHED == "PUBLISHED"
        assert REVISION_STATUS_ARCHIVED == "ARCHIVED"
        assert VALID_REVISION_STATUSES == {"DRAFT", "PUBLISHED", "ARCHIVED"}

    def test_lesson_types(self):
        assert VALID_LESSON_TYPES == {"VIDEO", "ARTICLE", "QUIZ", "ASSIGNMENT"}
        assert LESSON_TYPE_VIDEO == "VIDEO"
        assert LESSON_TYPE_ARTICLE == "ARTICLE"
        assert LESSON_TYPE_QUIZ == "QUIZ"
        assert LESSON_TYPE_ASSIGNMENT == "ASSIGNMENT"

    def test_resource_types(self):
        assert VALID_RESOURCE_TYPES == {"PDF", "SOURCE_CODE", "LINK", "ASSET"}
        assert RESOURCE_TYPE_PDF == "PDF"
        assert RESOURCE_TYPE_SOURCE_CODE == "SOURCE_CODE"
        assert RESOURCE_TYPE_LINK == "LINK"
        assert RESOURCE_TYPE_ASSET == "ASSET"


class TestCourseAndRevisionModels:
    """Verifies Course and CourseRevision persistence and relationships."""

    def test_create_course_with_revisions(self, db_session: Session):
        # Create a course
        course = Course(
            title="Mastering Modern Systems",
            slug="mastering-modern-systems",
            headline="Comprehensive guide to high-scale architecture",
            description="In-depth, end-to-end distributed systems curriculum.",
            price_inr=999900,  # ₹9,999.00 in paise
            is_free=False,
            status=COURSE_STATUS_DRAFT,
        )
        db_session.add(course)
        db_session.commit()

        assert course.id is not None
        assert course.status == COURSE_STATUS_DRAFT
        assert course.price_inr == 999900
        assert course.is_free is False
        assert course.live_revision_id is None

        # Create initial revision
        rev1 = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Mastering Modern Systems - Draft 1",
            status=REVISION_STATUS_DRAFT,
            changelog="Initial draft creation",
        )
        db_session.add(rev1)
        db_session.commit()

        assert rev1.id is not None
        assert rev1.course_id == course.id
        assert rev1.revision_no == 1
        assert rev1.status == REVISION_STATUS_DRAFT

        # Verify relationship from course to revisions
        db_session.refresh(course)
        assert len(course.revisions) == 1
        assert course.revisions[0].id == rev1.id

    def test_circular_reference_live_revision(self, db_session: Session):
        """Course live_revision_id references CourseRevision.id with post_update."""
        course = Course(
            title="FastAPI Microservices",
            slug="fastapi-microservices",
            price_inr=0,
            is_free=True,
            status=COURSE_STATUS_DRAFT,
        )
        db_session.add(course)
        db_session.commit()

        rev = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="FastAPI Microservices v1",
            status=REVISION_STATUS_PUBLISHED,
        )
        db_session.add(rev)
        db_session.commit()

        # Link live revision
        course.live_revision_id = rev.id
        course.status = COURSE_STATUS_PUBLISHED
        db_session.commit()

        db_session.refresh(course)
        assert course.live_revision is not None
        assert course.live_revision.id == rev.id
        assert course.live_revision.title == "FastAPI Microservices v1"

    def test_course_tags(self, db_session: Session):
        """Course can have multiple associated tags."""
        course = Course(
            title="Cloud Architecture",
            slug="cloud-architecture",
            price_inr=499900,
            is_free=False,
        )
        db_session.add(course)
        db_session.commit()

        tag1 = CourseTag(course_id=course.id, tag="cloud")
        tag2 = CourseTag(course_id=course.id, tag="aws")
        db_session.add_all([tag1, tag2])
        db_session.commit()

        db_session.refresh(course)
        assert len(course.tags) == 2
        tag_names = {t.tag for t in course.tags}
        assert tag_names == {"cloud", "aws"}


class TestCurriculumHierarchyModels:
    """Verifies CurriculumSection, CurriculumLesson, and LessonResource hierarchy."""

    def test_full_curriculum_tree(self, db_session: Session):
        course = Course(title="Complete Backend", slug="complete-backend")
        db_session.add(course)
        db_session.commit()

        rev = CourseRevision(course_id=course.id, revision_no=1, title="v1")
        db_session.add(rev)
        db_session.commit()

        # Add 2 Sections
        sec1 = CurriculumSection(
            course_revision_id=rev.id,
            title="Section 1: Foundations",
            sort_order=1,
        )
        sec2 = CurriculumSection(
            course_revision_id=rev.id,
            title="Section 2: Advanced Topics",
            sort_order=2,
        )
        db_session.add_all([sec1, sec2])
        db_session.commit()

        # Add Lessons to Section 1
        les1 = CurriculumLesson(
            section_id=sec1.id,
            title="Introduction to Concurrency",
            sort_order=1,
            lesson_type=LESSON_TYPE_VIDEO,
            duration_seconds=1200,
            is_preview=True,
        )
        les2 = CurriculumLesson(
            section_id=sec1.id,
            title="AsyncIO Deep Dive",
            sort_order=2,
            lesson_type=LESSON_TYPE_ARTICLE,
            duration_seconds=600,
            is_preview=False,
        )
        db_session.add_all([les1, les2])
        db_session.commit()

        # Add Resources to Lesson 1
        res1 = LessonResource(
            lesson_id=les1.id,
            title="Concurrency Architecture Slides",
            resource_type=RESOURCE_TYPE_PDF,
            file_url="https://assets.example.com/slides/intro.pdf",
            file_size_bytes=4500000,
        )
        res2 = LessonResource(
            lesson_id=les1.id,
            title="Exercise Repository",
            resource_type=RESOURCE_TYPE_SOURCE_CODE,
            file_url="https://github.com/example/concurrency-code",
            file_size_bytes=10240,
        )
        db_session.add_all([res1, res2])
        db_session.commit()

        # Verify tree relationships
        db_session.refresh(rev)
        assert len(rev.sections) == 2
        assert rev.sections[0].title == "Section 1: Foundations"
        assert len(rev.sections[0].lessons) == 2
        assert rev.sections[0].lessons[0].title == "Introduction to Concurrency"
        assert rev.sections[0].lessons[0].is_preview is True
        assert len(rev.sections[0].lessons[0].resources) == 2
        assert rev.sections[0].lessons[0].resources[0].resource_type == RESOURCE_TYPE_PDF

    def test_cascade_delete_section_deletes_lessons_and_resources(self, db_session: Session):
        course = Course(title="Cascade Course", slug="cascade-course")
        db_session.add(course)
        db_session.commit()

        rev = CourseRevision(course_id=course.id, revision_no=1, title="v1")
        db_session.add(rev)
        db_session.commit()

        sec = CurriculumSection(course_revision_id=rev.id, title="Deletable Section", sort_order=1)
        db_session.add(sec)
        db_session.commit()

        les = CurriculumLesson(section_id=sec.id, title="Deletable Lesson", sort_order=1, lesson_type="VIDEO")
        db_session.add(les)
        db_session.commit()

        res = LessonResource(lesson_id=les.id, title="Deletable Resource", resource_type="PDF", file_url="https://res.pdf")
        db_session.add(res)
        db_session.commit()

        # Deleting section should cascade delete lesson and resource
        db_session.delete(sec)
        db_session.commit()

        assert db_session.get(CurriculumSection, sec.id) is None
        assert db_session.get(CurriculumLesson, les.id) is None
        assert db_session.get(LessonResource, res.id) is None
