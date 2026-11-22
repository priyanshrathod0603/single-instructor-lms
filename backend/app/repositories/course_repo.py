"""Course and Curriculum Database Repository.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 8-13)
- docs/backend/11-COURSE-MANAGEMENT.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301, TASK302, TASK303)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-005)

Strict Invariants:
1. Immutability: Revisions with status 'PUBLISHED' cannot be edited or reordered.
2. Optimistic Concurrency: Reordering checks `revision.updated_at <= version_timestamp`.
3. Hierarchy Integrity: Deleting a section cascade-deletes lessons and resources.
4. Minor Currency: price_inr stored in integer paise.
"""

from datetime import datetime
import logging
from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictException, ForbiddenException, ResourceNotFoundException
from app.models.base import utc_now
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_ARCHIVED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
    CourseTag,
)
from app.models.curriculum import (
    CurriculumLesson,
    CurriculumSection,
    LessonResource,
)
from app.schemas.course import slugify

logger = logging.getLogger(__name__)


class CourseRepository:
    """Repository managing course containers, immutable revisions, and curriculum hierarchies."""

    # =========================================================================
    # Course Operations
    # =========================================================================

    def create_course(
        self,
        session: Session,
        *,
        title: str,
        slug: Optional[str] = None,
        headline: Optional[str] = None,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        price_inr: int = 0,
        is_free: bool = False,
        tags: Optional[List[str]] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> Tuple[Course, CourseRevision]:
        """Create top-level course container and initial Draft Revision 1 atomically."""
        if not slug:
            base_slug = slugify(title)
            slug = base_slug
            counter = 1
            while self.get_by_slug(session, slug) is not None:
                slug = f"{base_slug}-{counter}"
                counter += 1
        else:
            if self.get_by_slug(session, slug) is not None:
                raise ConflictException(
                    message=f"Course with slug '{slug}' already exists.",
                    code="COURSE_SLUG_EXISTS",
                    details={"slug": slug},
                )

        course = Course(
            title=title,
            slug=slug,
            headline=headline,
            description=description,
            thumbnail_url=thumbnail_url,
            price_inr=price_inr,
            is_free=is_free,
            status=COURSE_STATUS_DRAFT,
        )
        session.add(course)
        session.flush()

        # Add initial Course Tags
        if tags:
            for tag_str in set(tags):
                cleaned_tag = tag_str.strip().lower()
                if cleaned_tag:
                    session.add(CourseTag(course_id=course.id, tag=cleaned_tag))

        # Spawn Initial Revision 1 (DRAFT)
        initial_revision = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title=f"{title} (Draft 1)",
            status=REVISION_STATUS_DRAFT,
            changelog="Initial draft revision",
            created_by=created_by,
        )
        session.add(initial_revision)
        session.flush()

        return course, initial_revision

    def get_by_id(
        self,
        session: Session,
        course_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Course]:
        """Fetch course container by primary key UUID."""
        stmt = (
            select(Course)
            .options(
                selectinload(Course.tags),
                selectinload(Course.revisions),
                selectinload(Course.live_revision),
            )
            .where(Course.id == course_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.scalar(stmt)

    def get_by_slug(
        self,
        session: Session,
        slug: str,
    ) -> Optional[Course]:
        """Fetch course container by URL slug."""
        stmt = (
            select(Course)
            .options(
                selectinload(Course.tags),
                selectinload(Course.revisions),
                selectinload(Course.live_revision),
            )
            .where(func.lower(Course.slug) == slug.strip().lower())
        )
        return session.scalar(stmt)

    def list_courses(
        self,
        session: Session,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Course], int]:
        """List paginated course entities with optional status, search, and tag filters."""
        query = select(Course).options(
            selectinload(Course.tags),
            selectinload(Course.live_revision),
        )

        if status:
            query = query.where(Course.status == status)
        if search:
            search_term = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(Course.title).like(search_term),
                    func.lower(Course.headline).like(search_term),
                    func.lower(Course.slug).like(search_term),
                )
            )
        if tag:
            query = query.join(Course.tags).where(CourseTag.tag == tag.strip().lower())

        # Count total
        count_stmt = select(func.count()).select_from(query.order_by(None).subquery())
        total = session.scalar(count_stmt) or 0

        # Pagination and order
        offset = (page - 1) * per_page
        query = query.order_by(desc(Course.created_at)).offset(offset).limit(per_page)

        items = list(session.scalars(query).all())
        return items, total

    def update_course(
        self,
        session: Session,
        course: Course,
        **kwargs: Any,
    ) -> Course:
        """Update top-level course metadata and replace tags if provided."""
        if "slug" in kwargs and kwargs["slug"] is not None:
            new_slug = kwargs["slug"].strip().lower()
            if new_slug != course.slug:
                existing = self.get_by_slug(session, new_slug)
                if existing and existing.id != course.id:
                    raise ConflictException(
                        message=f"Course with slug '{new_slug}' already exists.",
                        code="COURSE_SLUG_EXISTS",
                        details={"slug": new_slug},
                    )
                course.slug = new_slug

        for field in ("title", "headline", "description", "thumbnail_url", "price_inr", "is_free"):
            if field in kwargs and kwargs[field] is not None:
                setattr(course, field, kwargs[field])

        if "tags" in kwargs and kwargs["tags"] is not None:
            # Replace tags
            session.query(CourseTag).filter(CourseTag.course_id == course.id).delete()
            for t in set(kwargs["tags"]):
                clean_t = t.strip().lower()
                if clean_t:
                    session.add(CourseTag(course_id=course.id, tag=clean_t))

        course.updated_at = utc_now()
        session.flush()
        return course

    def archive_course(
        self,
        session: Session,
        course: Course,
    ) -> Course:
        """Archive course container, removing it from active sales."""
        course.status = COURSE_STATUS_ARCHIVED
        course.updated_at = utc_now()
        session.flush()
        return course

    # =========================================================================
    # Revision Operations
    # =========================================================================

    def get_revision_by_id(
        self,
        session: Session,
        revision_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[CourseRevision]:
        """Fetch revision by UUID with fully loaded curriculum tree."""
        existing = session.get(CourseRevision, revision_id)
        if existing is not None and for_update:
            session.expire(existing)

        stmt = (
            select(CourseRevision)
            .options(
                selectinload(CourseRevision.sections).selectinload(
                    CurriculumSection.lessons
                ).selectinload(CurriculumLesson.resources),
                selectinload(CourseRevision.course),
            )
            .where(CourseRevision.id == revision_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.scalar(stmt)

    def get_latest_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
    ) -> Optional[CourseRevision]:
        """Fetch latest revision by revision_no for a given course."""
        stmt = (
            select(CourseRevision)
            .options(
                selectinload(CourseRevision.sections).selectinload(
                    CurriculumSection.lessons
                ).selectinload(CurriculumLesson.resources),
            )
            .where(CourseRevision.course_id == course_id)
            .order_by(desc(CourseRevision.revision_no))
            .limit(1)
        )
        return session.scalar(stmt)

    def get_live_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
    ) -> Optional[CourseRevision]:
        """Fetch the currently active published revision for a course."""
        stmt = (
            select(CourseRevision)
            .options(
                selectinload(CourseRevision.sections).selectinload(
                    CurriculumSection.lessons
                ).selectinload(CurriculumLesson.resources),
            )
            .where(
                CourseRevision.course_id == course_id,
                CourseRevision.status == REVISION_STATUS_PUBLISHED,
            )
            .limit(1)
        )
        return session.scalar(stmt)

    def get_draft_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
    ) -> Optional[CourseRevision]:
        """Fetch active working draft revision for a course if one exists."""
        stmt = (
            select(CourseRevision)
            .options(
                selectinload(CourseRevision.sections).selectinload(
                    CurriculumSection.lessons
                ).selectinload(CurriculumLesson.resources),
            )
            .where(
                CourseRevision.course_id == course_id,
                CourseRevision.status == REVISION_STATUS_DRAFT,
            )
            .limit(1)
        )
        return session.scalar(stmt)

    def create_revision(
        self,
        session: Session,
        *,
        course_id: uuid.UUID,
        revision_no: int,
        title: str,
        changelog: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> CourseRevision:
        """Create new empty CourseRevision."""
        revision = CourseRevision(
            course_id=course_id,
            revision_no=revision_no,
            title=title,
            status=REVISION_STATUS_DRAFT,
            changelog=changelog,
            created_by=created_by,
        )
        session.add(revision)
        session.flush()
        return revision

    def deep_clone_revision(
        self,
        session: Session,
        *,
        source_revision: CourseRevision,
        new_revision_no: int,
        changelog: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> CourseRevision:
        """Deep clone curriculum hierarchy into a newly spawned working draft revision.

        Copies:
        - sections (preserving sort_order, title, description)
        - lessons (preserving sort_order, lesson_type, title, duration_seconds, is_preview, content)
        - resources (preserving resource_type, title, file_url, file_size_bytes)
        """
        new_rev = CourseRevision(
            course_id=source_revision.course_id,
            revision_no=new_revision_no,
            title=f"{source_revision.course.title if source_revision.course else 'Course'} (Draft {new_revision_no})",
            status=REVISION_STATUS_DRAFT,
            changelog=changelog,
            created_by=created_by,
        )
        session.add(new_rev)
        session.flush()

        # Clone all sections in order
        for sec in sorted(source_revision.sections, key=lambda s: s.sort_order):
            new_sec = CurriculumSection(
                course_revision_id=new_rev.id,
                title=sec.title,
                description=sec.description,
                sort_order=sec.sort_order,
            )
            session.add(new_sec)
            session.flush()

            # Clone all lessons in section
            for les in sorted(sec.lessons, key=lambda l: l.sort_order):
                new_les = CurriculumLesson(
                    section_id=new_sec.id,
                    title=les.title,
                    lesson_type=les.lesson_type,
                    sort_order=les.sort_order,
                    duration_seconds=les.duration_seconds,
                    is_preview=les.is_preview,
                    content=dict(les.content) if les.content else {},
                )
                session.add(new_les)
                session.flush()

                # Clone all resources in lesson
                for res in les.resources:
                    new_res = LessonResource(
                        lesson_id=new_les.id,
                        title=res.title,
                        resource_type=res.resource_type,
                        file_url=res.file_url,
                        file_size_bytes=res.file_size_bytes,
                    )
                    session.add(new_res)

                # Clone assessments associated with lesson (BUG-008)
                if les.lesson_type == "QUIZ":
                    from app.models.quiz import Quiz, QuizQuestion, QuizQuestionOption
                    old_quiz = session.query(Quiz).filter(Quiz.lesson_id == les.id).first()
                    if old_quiz:
                        new_quiz = Quiz(
                            lesson_id=new_les.id,
                            title=old_quiz.title,
                            description=old_quiz.description,
                            pass_percentage=old_quiz.pass_percentage,
                            time_limit_minutes=old_quiz.time_limit_minutes,
                            shuffle_questions=old_quiz.shuffle_questions,
                            max_attempts=old_quiz.max_attempts,
                        )
                        session.add(new_quiz)
                        session.flush()

                        for q in sorted(old_quiz.questions, key=lambda x: x.sort_order):
                            new_q = QuizQuestion(
                                quiz_id=new_quiz.id,
                                question_type=q.question_type,
                                prompt=q.prompt,
                                points=q.points,
                                explanation=q.explanation,
                                sort_order=q.sort_order,
                            )
                            session.add(new_q)
                            session.flush()

                            for opt in sorted(q.options, key=lambda x: x.sort_order):
                                new_opt = QuizQuestionOption(
                                    question_id=new_q.id,
                                    option_text=opt.option_text,
                                    is_correct=opt.is_correct,
                                    sort_order=opt.sort_order,
                                )
                                session.add(new_opt)

                elif les.lesson_type == "ASSIGNMENT":
                    from app.models.assignment import Assignment, Rubric, RubricCriteria
                    old_assignment = session.query(Assignment).filter(Assignment.lesson_id == les.id).first()
                    if old_assignment:
                        new_assignment = Assignment(
                            lesson_id=new_les.id,
                            title=old_assignment.title,
                            instructions=old_assignment.instructions,
                            max_score=old_assignment.max_score,
                            pass_score=old_assignment.pass_score,
                            allow_late=old_assignment.allow_late,
                            due_date=old_assignment.due_date,
                        )
                        session.add(new_assignment)
                        session.flush()

                        for rubric in old_assignment.rubrics:
                            new_rubric = Rubric(
                                assignment_id=new_assignment.id,
                                title=rubric.title,
                                version=rubric.version,
                                is_active=rubric.is_active,
                            )
                            session.add(new_rubric)
                            session.flush()

                            for crit in sorted(rubric.criteria, key=lambda x: x.sort_order):
                                new_crit = RubricCriteria(
                                    rubric_id=new_rubric.id,
                                    title=crit.title,
                                    description=crit.description,
                                    max_points=crit.max_points,
                                    weight=crit.weight,
                                    sort_order=crit.sort_order,
                                )
                                session.add(new_crit)

        session.flush()
        return self.get_revision_by_id(session, new_rev.id) or new_rev

    # =========================================================================
    # Section Operations
    # =========================================================================

    def create_section(
        self,
        session: Session,
        *,
        revision: CourseRevision,
        title: str,
        description: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> CurriculumSection:
        """Create new section within draft revision."""
        if revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot add sections to an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        if sort_order is None:
            max_order_stmt = select(func.coalesce(func.max(CurriculumSection.sort_order), -1)).where(
                CurriculumSection.course_revision_id == revision.id
            )
            max_order = session.scalar(max_order_stmt)
            sort_order = max_order + 1

        section = CurriculumSection(
            course_revision_id=revision.id,
            title=title,
            description=description,
            sort_order=sort_order,
        )
        session.add(section)
        revision.updated_at = utc_now()
        session.flush()
        session.expire(revision)
        return section

    def get_section_by_id(
        self,
        session: Session,
        section_id: uuid.UUID,
    ) -> Optional[CurriculumSection]:
        """Fetch section by UUID with lessons and parent revision."""
        stmt = (
            select(CurriculumSection)
            .options(
                selectinload(CurriculumSection.lessons).selectinload(CurriculumLesson.resources),
                selectinload(CurriculumSection.revision),
            )
            .where(CurriculumSection.id == section_id)
        )
        return session.scalar(stmt)

    def update_section(
        self,
        session: Session,
        section: CurriculumSection,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> CurriculumSection:
        """Update section metadata."""
        if section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot edit sections in an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )
        if title is not None:
            section.title = title
        if description is not None:
            section.description = description
        section.updated_at = utc_now()
        section.revision.updated_at = utc_now()
        session.flush()
        return section

    def delete_section(
        self,
        session: Session,
        section: CurriculumSection,
    ) -> None:
        """Delete section and all child lessons/resources."""
        if section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot delete sections from an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )
        section.revision.updated_at = utc_now()
        session.delete(section)
        session.flush()

    def reorder_sections(
        self,
        session: Session,
        *,
        revision: CourseRevision,
        section_ids: List[uuid.UUID],
        version_timestamp: datetime,
    ) -> List[CurriculumSection]:
        """Atomically reorder sections with optimistic concurrency check."""
        if revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot reorder sections in an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        # Optimistic locking guard
        if revision.updated_at > version_timestamp:
            raise ConflictException(
                message="Curriculum sections were modified by another request. Please refresh.",
                code="CONCURRENT_EDIT_CONFLICT",
                details={
                    "revision_updated_at": revision.updated_at.isoformat(),
                    "client_version_timestamp": version_timestamp.isoformat(),
                },
            )

        existing_sections = {s.id: s for s in revision.sections}
        if set(section_ids) != set(existing_sections.keys()):
            raise ConflictException(
                message="Provided section IDs do not match the sections belonging to this revision.",
                code="INVALID_REORDER_PAYLOAD",
            )

        for new_order, sec_id in enumerate(section_ids):
            existing_sections[sec_id].sort_order = new_order
            existing_sections[sec_id].updated_at = utc_now()

        revision.updated_at = utc_now()
        session.flush()
        return sorted(revision.sections, key=lambda s: s.sort_order)

    # =========================================================================
    # Lesson Operations
    # =========================================================================

    def create_lesson(
        self,
        session: Session,
        *,
        section: CurriculumSection,
        title: str,
        lesson_type: str,
        duration_seconds: int = 0,
        is_preview: bool = False,
        sort_order: Optional[int] = None,
        content: Optional[dict[str, Any]] = None,
    ) -> CurriculumLesson:
        """Create new lesson within a section."""
        if section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot add lessons to an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        if sort_order is None:
            max_order_stmt = select(func.coalesce(func.max(CurriculumLesson.sort_order), -1)).where(
                CurriculumLesson.section_id == section.id
            )
            max_order = session.scalar(max_order_stmt)
            sort_order = max_order + 1

        lesson = CurriculumLesson(
            section_id=section.id,
            title=title,
            lesson_type=lesson_type,
            sort_order=sort_order,
            duration_seconds=duration_seconds,
            is_preview=is_preview,
            content=content or {},
        )
        session.add(lesson)
        section.updated_at = utc_now()
        section.revision.updated_at = utc_now()
        session.flush()
        session.expire(section)
        session.expire(section.revision)
        return lesson

    def get_lesson_by_id(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> Optional[CurriculumLesson]:
        """Fetch lesson by UUID with resources and parent section."""
        stmt = (
            select(CurriculumLesson)
            .options(
                selectinload(CurriculumLesson.resources),
                selectinload(CurriculumLesson.section).selectinload(CurriculumSection.revision),
            )
            .where(CurriculumLesson.id == lesson_id)
        )
        return session.scalar(stmt)

    def update_lesson(
        self,
        session: Session,
        lesson: CurriculumLesson,
        **kwargs: Any,
    ) -> CurriculumLesson:
        """Update lesson properties."""
        if lesson.section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot edit lessons in an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        for field in ("title", "lesson_type", "duration_seconds", "is_preview", "content"):
            if field in kwargs and kwargs[field] is not None:
                setattr(lesson, field, kwargs[field])

        lesson.updated_at = utc_now()
        lesson.section.updated_at = utc_now()
        lesson.section.revision.updated_at = utc_now()
        session.flush()
        return lesson

    def delete_lesson(
        self,
        session: Session,
        lesson: CurriculumLesson,
    ) -> None:
        """Delete lesson and all child resources."""
        if lesson.section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot delete lessons from an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )
        lesson.section.revision.updated_at = utc_now()
        session.delete(lesson)
        session.flush()

    def reorder_lessons(
        self,
        session: Session,
        *,
        section: CurriculumSection,
        lesson_ids: List[uuid.UUID],
        version_timestamp: datetime,
    ) -> List[CurriculumLesson]:
        """Atomically reorder lessons within a section with optimistic concurrency check."""
        if section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot reorder lessons in an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        if section.revision.updated_at > version_timestamp:
            raise ConflictException(
                message="Curriculum lessons were modified by another request. Please refresh.",
                code="CONCURRENT_EDIT_CONFLICT",
                details={
                    "revision_updated_at": section.revision.updated_at.isoformat(),
                    "client_version_timestamp": version_timestamp.isoformat(),
                },
            )

        existing_lessons = {l.id: l for l in section.lessons}
        if set(lesson_ids) != set(existing_lessons.keys()):
            raise ConflictException(
                message="Provided lesson IDs do not match the lessons belonging to this section.",
                code="INVALID_REORDER_PAYLOAD",
            )

        for new_order, les_id in enumerate(lesson_ids):
            existing_lessons[les_id].sort_order = new_order
            existing_lessons[les_id].updated_at = utc_now()

        section.updated_at = utc_now()
        section.revision.updated_at = utc_now()
        session.flush()
        return sorted(section.lessons, key=lambda l: l.sort_order)

    # =========================================================================
    # Resource Operations
    # =========================================================================

    def create_resource(
        self,
        session: Session,
        *,
        lesson: CurriculumLesson,
        title: str,
        resource_type: str,
        file_url: str,
        file_size_bytes: int = 0,
    ) -> LessonResource:
        """Create new downloadable/external resource attached to lesson."""
        if lesson.section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot add resources to an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )

        resource = LessonResource(
            lesson_id=lesson.id,
            title=title,
            resource_type=resource_type,
            file_url=file_url,
            file_size_bytes=file_size_bytes,
        )
        session.add(resource)
        lesson.updated_at = utc_now()
        lesson.section.revision.updated_at = utc_now()
        session.flush()
        return resource

    def delete_resource(
        self,
        session: Session,
        resource: LessonResource,
    ) -> None:
        """Delete lesson resource."""
        if resource.lesson.section.revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message="Cannot delete resources from an immutable published or archived revision.",
                code="REVISION_IMMUTABLE",
            )
        resource.lesson.section.revision.updated_at = utc_now()
        session.delete(resource)
        session.flush()
