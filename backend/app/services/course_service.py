"""CourseService orchestrating course lifecycle, revision spawning, publishing, and curriculum trees.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 8-13)
- docs/backend/06-API-ARCHITECTURE.md (Sections 2.3, 2.4, 3.1)
- docs/backend/11-COURSE-MANAGEMENT.md (Sections 1-5)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301, TASK302, TASK303, TASK304, TASK305)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-005)

Strict Invariants:
1. Immutability: Published revisions are permanently frozen with complete JSONB snapshot.
2. Single Draft Lifecycle: Only one DRAFT revision per course may be in-flight at any time.
3. Pre-Flight Checklist Guard: Publication strictly blocked unless CHK-01 through CHK-07 pass.
4. Single-Active Live Revision: Publishing revision N sets status=PUBLISHED, supersedes prior live revision to ARCHIVED, and updates courses.live_revision_id.
5. Optimistic Concurrency: Section and lesson reordering guarded by version_timestamp.
"""

from datetime import datetime
import logging
from typing import Any, List, Optional, Tuple, Union
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    ResourceNotFoundException,
    ValidationException,
)
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
)
from app.models.curriculum import (
    CurriculumLesson,
    CurriculumSection,
    LessonResource,
)
from app.repositories.course_repo import CourseRepository
from app.schemas.course import (
    CourseCreateRequest,
    CourseDetailResponse,
    CourseListResponse,
    CourseRevisionResponse,
    CourseSummaryResponse,
    CourseUpdateRequest,
    CurriculumLessonResponse,
    CurriculumSectionResponse,
    LessonCreateRequest,
    LessonReorderRequest,
    LessonResourceResponse,
    LessonUpdateRequest,
    PublishChecklistBlocker,
    PublishChecklistResponse,
    PublishChecklistWarning,
    ResourceCreateRequest,
    SectionCreateRequest,
    SectionReorderRequest,
    SectionUpdateRequest,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class CourseService:
    """Service layer coordinating course lifecycle, curriculum hierarchy, and revision publishing."""

    def __init__(
        self,
        repository: Optional[CourseRepository] = None,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self.repo = repository or CourseRepository()
        self.audit_service = audit_service or AuditService()

    # =========================================================================
    # Course Lifecycle Operations
    # =========================================================================

    async def create_course(
        self,
        session: Session,
        data: CourseCreateRequest,
        *,
        actor_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[Course, CourseRevision]:
        """Create new course container and initial Draft Revision 1 atomically."""
        course, initial_revision = self.repo.create_course(
            session,
            title=data.title,
            slug=data.slug,
            headline=data.headline,
            description=data.description,
            thumbnail_url=data.thumbnail_url,
            price_inr=data.price_inr,
            is_free=data.is_free,
            tags=data.tags,
            created_by=actor_id,
        )

        # Audit record
        await self.audit_service.record_event(
            session,
            action="COURSE_CREATED",
            resource_type="course",
            resource_id=str(course.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            after_state={
                "id": str(course.id),
                "slug": course.slug,
                "title": course.title,
                "price_inr": course.price_inr,
                "is_free": course.is_free,
                "status": course.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return course, initial_revision

    async def get_course_detail(
        self,
        session: Session,
        id_or_slug: str,
        *,
        is_staff_view: bool = False,
    ) -> CourseDetailResponse:
        """Fetch course details.

        If public/student view: returns live published revision hierarchy (from snapshot or live revision).
        If staff view: returns latest revision hierarchy.
        """
        course: Optional[Course] = None
        try:
            course_uuid = uuid.UUID(id_or_slug)
            course = self.repo.get_by_id(session, course_uuid)
        except ValueError:
            course = self.repo.get_by_slug(session, id_or_slug)

        if course is None:
            raise ResourceNotFoundException("Course", id_or_slug)

        # If not staff view and course is archived or draft without live revision, return 404
        if not is_staff_view and course.status != COURSE_STATUS_PUBLISHED:
            raise ResourceNotFoundException("Course", id_or_slug)

        # Build curriculum tree
        curriculum: List[CurriculumSectionResponse] = []
        target_revision: Optional[CourseRevision] = None

        if is_staff_view:
            target_revision = self.repo.get_latest_revision(session, course.id)
        else:
            target_revision = course.live_revision or self.repo.get_live_revision(session, course.id)

        if target_revision:
            curriculum = self._format_revision_sections(target_revision)

        return CourseDetailResponse(
            id=course.id,
            slug=course.slug,
            title=course.title,
            headline=course.headline,
            description=course.description,
            thumbnail_url=course.thumbnail_url,
            status=course.status,
            price_inr=course.price_inr,
            is_free=course.is_free,
            tags=[t.tag for t in course.tags],
            live_revision_id=course.live_revision_id,
            created_at=course.created_at,
            updated_at=course.updated_at,
            curriculum=curriculum,
        )

    async def list_courses(
        self,
        session: Session,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> CourseListResponse:
        """List paginated courses for public catalog or admin directory."""
        items, total = self.repo.list_courses(
            session,
            status=status,
            search=search,
            tag=tag,
            page=page,
            per_page=per_page,
        )

        summaries = [
            CourseSummaryResponse(
                id=c.id,
                slug=c.slug,
                title=c.title,
                headline=c.headline,
                thumbnail_url=c.thumbnail_url,
                status=c.status,
                price_inr=c.price_inr,
                is_free=c.is_free,
                tags=[t.tag for t in c.tags],
                live_revision_id=c.live_revision_id,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in items
        ]

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        return CourseListResponse(
            items=summaries,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    async def update_course(
        self,
        session: Session,
        course_id: uuid.UUID,
        data: CourseUpdateRequest,
        *,
        actor_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CourseSummaryResponse:
        """Update top-level course metadata and record audit event."""
        course = self.repo.get_by_id(session, course_id)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        before_state = {
            "title": course.title,
            "slug": course.slug,
            "headline": course.headline,
            "price_inr": course.price_inr,
            "is_free": course.is_free,
        }

        updated = self.repo.update_course(
            session,
            course,
            title=data.title,
            slug=data.slug,
            headline=data.headline,
            description=data.description,
            thumbnail_url=data.thumbnail_url,
            price_inr=data.price_inr,
            is_free=data.is_free,
            tags=data.tags,
        )

        after_state = {
            "title": updated.title,
            "slug": updated.slug,
            "headline": updated.headline,
            "price_inr": updated.price_inr,
            "is_free": updated.is_free,
        }

        await self.audit_service.record_event(
            session,
            action="COURSE_UPDATED",
            resource_type="course",
            resource_id=str(updated.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return CourseSummaryResponse(
            id=updated.id,
            slug=updated.slug,
            title=updated.title,
            headline=updated.headline,
            thumbnail_url=updated.thumbnail_url,
            status=updated.status,
            price_inr=updated.price_inr,
            is_free=updated.is_free,
            tags=[t.tag for t in updated.tags],
            live_revision_id=updated.live_revision_id,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )

    async def archive_course(
        self,
        session: Session,
        course_id: uuid.UUID,
        *,
        actor_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CourseSummaryResponse:
        """Archive course, removing it from active sales and enrollments."""
        course = self.repo.get_by_id(session, course_id)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        archived = self.repo.archive_course(session, course)

        await self.audit_service.record_event(
            session,
            action="COURSE_ARCHIVED",
            resource_type="course",
            resource_id=str(archived.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            before_state={"status": course.status},
            after_state={"status": archived.status},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return CourseSummaryResponse(
            id=archived.id,
            slug=archived.slug,
            title=archived.title,
            headline=archived.headline,
            thumbnail_url=archived.thumbnail_url,
            status=archived.status,
            price_inr=archived.price_inr,
            is_free=archived.is_free,
            tags=[t.tag for t in archived.tags],
            live_revision_id=archived.live_revision_id,
            created_at=archived.created_at,
            updated_at=archived.updated_at,
        )

    # =========================================================================
    # Revision Spawning & Management
    # =========================================================================

    async def spawn_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
        changelog: Optional[str] = None,
        *,
        actor_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CourseRevisionResponse:
        """Spawn a new working draft revision from the published course revision.

        Deep clones the complete curriculum hierarchy (sections, lessons, resources)
        into the new draft revision.
        """
        course = self.repo.get_by_id(session, course_id, for_update=True)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        # Check if draft revision already exists
        existing_draft = self.repo.get_draft_revision(session, course.id)
        if existing_draft is not None:
            raise ConflictException(
                message=f"Course already has an active draft revision (Revision {existing_draft.revision_no}).",
                code="DRAFT_REVISION_EXISTS",
                details={"revision_id": str(existing_draft.id), "revision_no": existing_draft.revision_no},
            )

        # Source revision to clone from: live revision or latest revision
        source_rev = course.live_revision or self.repo.get_latest_revision(session, course.id)
        latest_rev = self.repo.get_latest_revision(session, course.id)
        new_revision_no = (latest_rev.revision_no if latest_rev else 0) + 1

        if source_rev is not None:
            new_rev = self.repo.deep_clone_revision(
                session,
                source_revision=source_rev,
                new_revision_no=new_revision_no,
                changelog=changelog,
                created_by=actor_id,
            )
        else:
            new_rev = self.repo.create_revision(
                session,
                course_id=course.id,
                revision_no=new_revision_no,
                title=f"{course.title} (Draft {new_revision_no})",
                changelog=changelog,
                created_by=actor_id,
            )

        await self.audit_service.record_event(
            session,
            action="COURSE_REVISION_SPAWNED",
            resource_type="course_revision",
            resource_id=str(new_rev.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            after_state={
                "id": str(new_rev.id),
                "course_id": str(course.id),
                "revision_no": new_rev.revision_no,
                "status": new_rev.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return self._format_revision_response(new_rev)

    async def get_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> CourseRevisionResponse:
        """Retrieve specific revision details and curriculum tree."""
        rev = self.repo.get_revision_by_id(session, revision_id)
        if rev is None or rev.course_id != course_id:
            raise ResourceNotFoundException("CourseRevision", str(revision_id))

        return self._format_revision_response(rev)

    # =========================================================================
    # Pre-Flight Publishing Checklist & Atomic Publication
    # =========================================================================

    def evaluate_publish_checklist(
        self,
        session: Session,
        course_id: uuid.UUID,
        revision_id: uuid.UUID,
    ) -> PublishChecklistResponse:
        """Evaluate pre-flight checklist rules (CHK-01 through CHK-08)."""
        course = self.repo.get_by_id(session, course_id)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        revision = self.repo.get_revision_by_id(session, revision_id)
        if revision is None or revision.course_id != course_id:
            raise ResourceNotFoundException("CourseRevision", str(revision_id))

        blockers: List[PublishChecklistBlocker] = []
        warnings: List[PublishChecklistWarning] = []

        # CHK-01: Course Metadata
        if not course.title or not course.title.strip():
            blockers.append(PublishChecklistBlocker(code="EMPTY_TITLE", message="Course title cannot be empty."))
        if not course.slug or not course.slug.strip():
            blockers.append(PublishChecklistBlocker(code="EMPTY_SLUG", message="Course slug cannot be empty."))
        if not course.headline or not course.headline.strip():
            blockers.append(PublishChecklistBlocker(code="EMPTY_HEADLINE", message="Course headline cannot be empty."))

        # CHK-02: Commercial Pricing
        if not course.is_free and course.price_inr <= 0:
            blockers.append(
                PublishChecklistBlocker(
                    code="INVALID_PRICING",
                    message="Paid courses must have price_inr greater than 0.",
                )
            )

        # CHK-03: Non-Empty Sections
        if not revision.sections:
            blockers.append(
                PublishChecklistBlocker(
                    code="NO_SECTIONS",
                    message="Course revision must contain at least one curriculum section.",
                )
            )

        # CHK-04 through CHK-07: Lesson level validation
        for sec in revision.sections:
            if not sec.lessons:
                blockers.append(
                    PublishChecklistBlocker(
                        code="EMPTY_SECTION",
                        section_id=sec.id,
                        message=f"Section '{sec.title}' contains 0 lessons.",
                    )
                )
                continue

            for les in sec.lessons:
                # CHK-05: Media readiness check
                if les.lesson_type == "VIDEO":
                    media_id_val = les.content.get("media_asset_id") if les.content else None
                    if media_id_val:
                        try:
                            ma_uuid = uuid.UUID(str(media_id_val))
                            from app.models.media import MEDIA_STATUS_READY, MediaAsset
                            ma = session.get(MediaAsset, ma_uuid)
                            if ma and ma.status != MEDIA_STATUS_READY:
                                blockers.append(
                                    PublishChecklistBlocker(
                                        code="MEDIA_NOT_READY",
                                        lesson_id=les.id,
                                        section_id=sec.id,
                                        message=f"Video asset for lesson '{les.title}' is not ready (status: {ma.status}).",
                                    )
                                )
                        except (ValueError, TypeError):
                            pass
                    elif les.content and les.content.get("status") == "PROCESSING":
                        blockers.append(
                            PublishChecklistBlocker(
                                code="MEDIA_NOT_READY",
                                lesson_id=les.id,
                                section_id=sec.id,
                                message=f"Video asset for lesson '{les.title}' is still processing.",
                            )
                        )

                # CHK-06: Quiz validity (BUG-007: Relational Assessment Validation)
                elif les.lesson_type == "QUIZ":
                    from app.models.quiz import Quiz
                    quiz = session.query(Quiz).filter(Quiz.lesson_id == les.id).first()
                    if not quiz or not quiz.questions:
                        blockers.append(
                            PublishChecklistBlocker(
                                code="EMPTY_QUIZ",
                                lesson_id=les.id,
                                section_id=sec.id,
                                message=f"Quiz lesson '{les.title}' must contain at least one question.",
                            )
                        )
                    else:
                        for q in quiz.questions:
                            if not q.options:
                                blockers.append(
                                    PublishChecklistBlocker(
                                        code="EMPTY_QUIZ_OPTIONS",
                                        lesson_id=les.id,
                                        section_id=sec.id,
                                        message=f"Question in quiz lesson '{les.title}' must contain options.",
                                    )
                                )
                                break
                            if not any(opt.is_correct for opt in q.options):
                                blockers.append(
                                    PublishChecklistBlocker(
                                        code="NO_CORRECT_OPTION",
                                        lesson_id=les.id,
                                        section_id=sec.id,
                                        message=f"Question in quiz lesson '{les.title}' must have at least one correct answer option.",
                                    )
                                )
                                break

                # CHK-07: Assignment validity (BUG-007: Relational Assessment Validation)
                elif les.lesson_type == "ASSIGNMENT":
                    from app.models.assignment import Assignment, Rubric
                    assignment = session.query(Assignment).filter(Assignment.lesson_id == les.id).first()
                    if not assignment:
                        blockers.append(
                            PublishChecklistBlocker(
                                code="MISSING_ASSIGNMENT_RUBRIC",
                                lesson_id=les.id,
                                section_id=sec.id,
                                message=f"Assignment lesson '{les.title}' must have an evaluation rubric.",
                            )
                        )
                    else:
                        if assignment.max_score <= 0:
                            blockers.append(
                                PublishChecklistBlocker(
                                    code="INVALID_ASSIGNMENT_SCORE",
                                    lesson_id=les.id,
                                    section_id=sec.id,
                                    message=f"Assignment lesson '{les.title}' must have max_score > 0.",
                                )
                            )
                        rubric = (
                            session.query(Rubric)
                            .filter(Rubric.assignment_id == assignment.id)
                            .order_by(Rubric.version.desc())
                            .first()
                        )
                        if not rubric or not rubric.criteria:
                            blockers.append(
                                PublishChecklistBlocker(
                                    code="MISSING_ASSIGNMENT_RUBRIC",
                                    lesson_id=les.id,
                                    section_id=sec.id,
                                    message=f"Assignment lesson '{les.title}' must have an evaluation rubric.",
                                )
                            )

        # CHK-08: Thumbnail Asset (Warning)
        if not course.thumbnail_url or not course.thumbnail_url.strip():
            warnings.append(
                PublishChecklistWarning(
                    code="MISSING_THUMBNAIL",
                    message="Course thumbnail image is not set; default fallback image will be displayed.",
                )
            )

        can_publish = len(blockers) == 0

        return PublishChecklistResponse(
            can_publish=can_publish,
            revision_id=revision.id,
            revision_no=revision.revision_no,
            blockers=blockers,
            warnings=warnings,
        )

    async def publish_revision(
        self,
        session: Session,
        course_id: uuid.UUID,
        revision_id: uuid.UUID,
        *,
        actor_id: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CourseRevisionResponse:
        """Atomically validate checklist, freeze snapshot, and publish revision.

        Single Atomic Transaction:
        1. Lock course and revision FOR UPDATE.
        2. Validate pre-flight publishing checklist.
        3. Serialize full frozen curriculum tree into JSONB snapshot.
        4. Mark revision status = PUBLISHED, published_at = NOW().
        5. Mark prior published revisions as ARCHIVED.
        6. Set courses.live_revision_id = rev_id, status = PUBLISHED.
        7. Record audit log COURSE_PUBLISHED.
        """
        course = self.repo.get_by_id(session, course_id, for_update=True)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        prior_course_status = course.status
        prior_live_revision_id = course.live_revision_id

        revision = self.repo.get_revision_by_id(session, revision_id, for_update=True)
        if revision is None or revision.course_id != course_id:
            raise ResourceNotFoundException("CourseRevision", str(revision_id))

        if revision.status != REVISION_STATUS_DRAFT:
            raise ForbiddenException(
                message=f"Only draft revisions can be published. Revision is already '{revision.status}'.",
                code="REVISION_NOT_DRAFT",
            )

        # 2. Pre-flight checklist verification
        checklist = self.evaluate_publish_checklist(session, course_id, revision_id)
        if not checklist.can_publish:
            raise ValidationException(
                message="Cannot publish revision; pre-flight checklist conditions failed.",
                code="PUBLISH_CHECKLIST_FAILED",
                details={
                    "blockers": [b.model_dump() for b in checklist.blockers],
                    "warnings": [w.model_dump() for w in checklist.warnings],
                },
            )

        # 3. Serialize JSONB snapshot
        snapshot_data = {
            "course_id": str(course.id),
            "revision_id": str(revision.id),
            "revision_no": revision.revision_no,
            "title": course.title,
            "slug": course.slug,
            "headline": course.headline,
            "description": course.description,
            "price_inr": course.price_inr,
            "is_free": course.is_free,
            "sections": [
                {
                    "id": str(sec.id),
                    "title": sec.title,
                    "description": sec.description,
                    "sort_order": sec.sort_order,
                    "lessons": [
                        {
                            "id": str(les.id),
                            "title": les.title,
                            "lesson_type": les.lesson_type,
                            "sort_order": les.sort_order,
                            "duration_seconds": les.duration_seconds,
                            "is_preview": les.is_preview,
                            "content": les.content or {},
                            "resources": [
                                {
                                    "id": str(res.id),
                                    "title": res.title,
                                    "resource_type": res.resource_type,
                                    "file_url": res.file_url,
                                    "file_size_bytes": res.file_size_bytes,
                                }
                                for res in les.resources
                            ],
                        }
                        for les in sorted(sec.lessons, key=lambda l: l.sort_order)
                    ],
                }
                for sec in sorted(revision.sections, key=lambda s: s.sort_order)
            ],
        }

        # 4. Mark revision published
        now = utc_now()
        revision.status = REVISION_STATUS_PUBLISHED
        revision.published_at = now
        revision.snapshot = snapshot_data
        revision.updated_at = now

        # 5. Archive prior published revisions
        for other_rev in course.revisions:
            if other_rev.id != revision.id and other_rev.status == REVISION_STATUS_PUBLISHED:
                other_rev.status = REVISION_STATUS_ARCHIVED
                other_rev.updated_at = now

        # 6. Update course container
        course.live_revision_id = revision.id
        course.status = COURSE_STATUS_PUBLISHED
        course.updated_at = now
        session.flush()

        # 7. Audit log
        after_state_dict: dict[str, Any] = {
            "revision_id": str(revision.id),
            "revision_no": revision.revision_no,
            "status": course.status,
        }
        if reason:
            after_state_dict["reason"] = reason

        await self.audit_service.record_event(
            session,
            action="COURSE_PUBLISHED",
            resource_type="course",
            resource_id=str(course.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            before_state={
                "status": prior_course_status,
                "live_revision_id": str(prior_live_revision_id) if prior_live_revision_id else None,
            },
            after_state=after_state_dict,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return self._format_revision_response(revision)

    # =========================================================================
    # Curriculum Section & Lesson Operations
    # =========================================================================

    def add_section(
        self,
        session: Session,
        course_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: SectionCreateRequest,
    ) -> CurriculumSectionResponse:
        """Add section to draft revision."""
        rev = self.repo.get_revision_by_id(session, revision_id)
        if rev is None or rev.course_id != course_id:
            raise ResourceNotFoundException("CourseRevision", str(revision_id))

        sec = self.repo.create_section(
            session,
            revision=rev,
            title=data.title,
            description=data.description,
            sort_order=data.sort_order,
        )
        return self._format_section_response(sec)

    def update_section(
        self,
        session: Session,
        section_id: uuid.UUID,
        data: SectionUpdateRequest,
    ) -> CurriculumSectionResponse:
        """Update section metadata."""
        sec = self.repo.get_section_by_id(session, section_id)
        if sec is None:
            raise ResourceNotFoundException("CurriculumSection", str(section_id))

        updated = self.repo.update_section(
            session,
            sec,
            title=data.title,
            description=data.description,
        )
        return self._format_section_response(updated)

    def delete_section(
        self,
        session: Session,
        section_id: uuid.UUID,
    ) -> None:
        """Delete section and children."""
        sec = self.repo.get_section_by_id(session, section_id)
        if sec is None:
            raise ResourceNotFoundException("CurriculumSection", str(section_id))

        self.repo.delete_section(session, sec)

    def reorder_sections(
        self,
        session: Session,
        course_id: uuid.UUID,
        revision_id: uuid.UUID,
        data: SectionReorderRequest,
    ) -> List[CurriculumSectionResponse]:
        """Reorder sections with optimistic concurrency guard."""
        rev = self.repo.get_revision_by_id(session, revision_id)
        if rev is None or rev.course_id != course_id:
            raise ResourceNotFoundException("CourseRevision", str(revision_id))

        reordered = self.repo.reorder_sections(
            session,
            revision=rev,
            section_ids=data.section_ids,
            version_timestamp=data.version_timestamp,
        )
        return [self._format_section_response(s) for s in reordered]

    def add_lesson(
        self,
        session: Session,
        section_id: uuid.UUID,
        data: LessonCreateRequest,
    ) -> CurriculumLessonResponse:
        """Add lesson to a section."""
        sec = self.repo.get_section_by_id(session, section_id)
        if sec is None:
            raise ResourceNotFoundException("CurriculumSection", str(section_id))

        les = self.repo.create_lesson(
            session,
            section=sec,
            title=data.title,
            lesson_type=data.lesson_type,
            duration_seconds=data.duration_seconds or 0,
            is_preview=data.is_preview or False,
            sort_order=data.sort_order,
            content=data.content,
        )
        return self._format_lesson_response(les)

    def get_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> CurriculumLessonResponse:
        """Fetch lesson details."""
        les = self.repo.get_lesson_by_id(session, lesson_id)
        if les is None:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        return self._format_lesson_response(les)

    def update_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        data: LessonUpdateRequest,
    ) -> CurriculumLessonResponse:
        """Update lesson properties."""
        les = self.repo.get_lesson_by_id(session, lesson_id)
        if les is None:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        updated = self.repo.update_lesson(
            session,
            les,
            title=data.title,
            lesson_type=data.lesson_type,
            duration_seconds=data.duration_seconds,
            is_preview=data.is_preview,
            content=data.content,
        )
        return self._format_lesson_response(updated)

    def delete_lesson(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> None:
        """Delete lesson and children."""
        les = self.repo.get_lesson_by_id(session, lesson_id)
        if les is None:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        self.repo.delete_lesson(session, les)

    def reorder_lessons(
        self,
        session: Session,
        section_id: uuid.UUID,
        data: LessonReorderRequest,
    ) -> List[CurriculumLessonResponse]:
        """Reorder lessons within a section with optimistic concurrency guard."""
        sec = self.repo.get_section_by_id(session, section_id)
        if sec is None:
            raise ResourceNotFoundException("CurriculumSection", str(section_id))

        reordered = self.repo.reorder_lessons(
            session,
            section=sec,
            lesson_ids=data.lesson_ids,
            version_timestamp=data.version_timestamp,
        )
        return [self._format_lesson_response(l) for l in reordered]

    def add_resource(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        data: ResourceCreateRequest,
    ) -> LessonResourceResponse:
        """Add resource to a lesson."""
        les = self.repo.get_lesson_by_id(session, lesson_id)
        if les is None:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        res = self.repo.create_resource(
            session,
            lesson=les,
            title=data.title,
            resource_type=data.resource_type,
            file_url=data.file_url,
            file_size_bytes=data.file_size_bytes or 0,
        )
        return LessonResourceResponse.model_validate(res)

    def delete_resource(
        self,
        session: Session,
        resource_id: uuid.UUID,
    ) -> None:
        """Delete resource."""
        res = session.get(LessonResource, resource_id)
        if res is None:
            raise ResourceNotFoundException("LessonResource", str(resource_id))

        self.repo.delete_resource(session, res)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _format_revision_response(self, rev: CourseRevision) -> CourseRevisionResponse:
        sections = self._format_revision_sections(rev)
        return CourseRevisionResponse(
            id=rev.id,
            course_id=rev.course_id,
            revision_no=rev.revision_no,
            status=rev.status,
            title=rev.title,
            changelog=rev.changelog,
            snapshot=rev.snapshot,
            published_at=rev.published_at,
            created_by=rev.created_by,
            created_at=rev.created_at,
            updated_at=rev.updated_at,
            sections=sections,
        )

    def _format_revision_sections(self, rev: CourseRevision) -> List[CurriculumSectionResponse]:
        return [self._format_section_response(s) for s in sorted(rev.sections, key=lambda s: s.sort_order)]

    def _format_section_response(self, sec: CurriculumSection) -> CurriculumSectionResponse:
        lessons = [self._format_lesson_response(l) for l in sorted(sec.lessons, key=lambda l: l.sort_order)]
        return CurriculumSectionResponse(
            id=sec.id,
            course_revision_id=sec.course_revision_id,
            title=sec.title,
            description=sec.description,
            sort_order=sec.sort_order,
            lessons=lessons,
            created_at=sec.created_at,
            updated_at=sec.updated_at,
        )

    def _format_lesson_response(self, les: CurriculumLesson) -> CurriculumLessonResponse:
        resources = [LessonResourceResponse.model_validate(r) for r in les.resources]
        return CurriculumLessonResponse(
            id=les.id,
            section_id=les.section_id,
            title=les.title,
            lesson_type=les.lesson_type,
            sort_order=les.sort_order,
            duration_seconds=les.duration_seconds,
            is_preview=les.is_preview,
            content=les.content,
            resources=resources,
            created_at=les.created_at,
            updated_at=les.updated_at,
        )
