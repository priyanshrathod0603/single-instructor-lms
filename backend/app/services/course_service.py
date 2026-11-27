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
    DEFAULT_COURSE_CATEGORIES,
    DEFAULT_COURSE_LANGUAGES,
    DEFAULT_CURRENCY_INR,
    DIFFICULTY_LEVEL_LABELS,
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
from app.models.media import MEDIA_STATUS_READY, MediaAsset
from app.repositories.course_repo import CourseRepository
from app.schemas.course import (
    SLUG_REGEX,
    CourseCreateRequest,
    CourseDetailResponse,
    CourseListResponse,
    CourseMetadataOptionItem,
    CourseMetadataOptionsResponse,
    CourseRevisionResponse,
    CourseSlugCheckResponse,
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

    def _resolve_thumbnail_media(
        self,
        session: Session,
        thumbnail_media_id: Optional[uuid.UUID],
        thumbnail_url: Optional[str],
    ) -> Tuple[Optional[uuid.UUID], Optional[str]]:
        """Verify linked thumbnail MediaAsset and derive canonical public image URL."""
        if thumbnail_media_id is None:
            return None, thumbnail_url

        asset = session.get(MediaAsset, thumbnail_media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(thumbnail_media_id))

        if (
            asset.status != MEDIA_STATUS_READY
            or not asset.file_key.startswith("public-images/")
            or asset.mime_type not in {"image/png", "image/jpeg", "image/webp"}
        ):
            raise ValidationException(
                message="Course thumbnail must reference a verified ready public image asset.",
                code="INVALID_THUMBNAIL_MEDIA",
            )

        return asset.id, f"/api/v1/media/public/{asset.id}"

    @staticmethod
    def _extract_revision_ids(course: Course) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID]]:
        """Derive draft and latest revision UUIDs from loaded revisions cleanly."""
        revisions = getattr(course, "revisions", None) or []
        if not revisions:
            return None, course.live_revision_id
        draft_rev = next((rev for rev in revisions if rev.status == REVISION_STATUS_DRAFT), None)
        latest_rev = max(revisions, key=lambda r: r.revision_no)
        return (draft_rev.id if draft_rev else None), latest_rev.id

    def _build_course_summary(
        self,
        course: Course,
        *,
        draft_revision_id: Optional[uuid.UUID] = None,
        latest_revision_id: Optional[uuid.UUID] = None,
    ) -> CourseSummaryResponse:
        if draft_revision_id is None and latest_revision_id is None:
            draft_revision_id, latest_revision_id = self._extract_revision_ids(course)
        return CourseSummaryResponse(
            id=course.id,
            slug=course.slug,
            title=course.title,
            headline=course.headline,
            thumbnail_url=course.thumbnail_url,
            thumbnail_media_id=course.thumbnail_media_id,
            category=course.category,
            difficulty_level=course.difficulty_level,
            language=course.language,
            status=course.status,
            price_inr=course.price_inr,
            compare_at_price_inr=course.compare_at_price_inr,
            currency=course.currency,
            discount_percentage=course.discount_percentage,
            is_free=course.is_free,
            tags=[t.tag for t in course.tags],
            live_revision_id=course.live_revision_id,
            draft_revision_id=draft_revision_id,
            latest_revision_id=latest_revision_id,
            created_at=course.created_at,
            updated_at=course.updated_at,
        )

    def _build_course_detail(
        self,
        course: Course,
        curriculum: List[CurriculumSectionResponse],
        *,
        draft_revision_id: Optional[uuid.UUID] = None,
        latest_revision_id: Optional[uuid.UUID] = None,
    ) -> CourseDetailResponse:
        return CourseDetailResponse(
            id=course.id,
            slug=course.slug,
            title=course.title,
            headline=course.headline,
            description=course.description,
            thumbnail_url=course.thumbnail_url,
            thumbnail_media_id=course.thumbnail_media_id,
            category=course.category,
            difficulty_level=course.difficulty_level,
            language=course.language,
            learning_outcomes=list(course.learning_outcomes or []),
            requirements=list(course.requirements or []),
            status=course.status,
            price_inr=course.price_inr,
            compare_at_price_inr=course.compare_at_price_inr,
            currency=course.currency,
            discount_percentage=course.discount_percentage,
            is_free=course.is_free,
            tags=[t.tag for t in course.tags],
            live_revision_id=course.live_revision_id,
            draft_revision_id=draft_revision_id,
            latest_revision_id=latest_revision_id,
            created_at=course.created_at,
            updated_at=course.updated_at,
            curriculum=curriculum,
        )

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
        resolved_media_id, resolved_thumb_url = self._resolve_thumbnail_media(
            session,
            data.thumbnail_media_id,
            data.thumbnail_url,
        )

        course, initial_revision = self.repo.create_course(
            session,
            title=data.title,
            slug=data.slug,
            headline=data.headline,
            description=data.description,
            thumbnail_url=resolved_thumb_url,
            thumbnail_media_id=resolved_media_id,
            category=data.category,
            difficulty_level=data.difficulty_level,
            language=data.language,
            learning_outcomes=data.learning_outcomes,
            requirements=data.requirements,
            price_inr=data.price_inr,
            compare_at_price_inr=data.compare_at_price_inr,
            currency=data.currency,
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
                "category": course.category,
                "difficulty_level": course.difficulty_level,
                "language": course.language,
                "price_inr": course.price_inr,
                "compare_at_price_inr": course.compare_at_price_inr,
                "currency": course.currency,
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

        draft_rev_id: Optional[uuid.UUID] = None
        latest_rev_id: Optional[uuid.UUID] = None
        if is_staff_view:
            draft_rev = self.repo.get_draft_revision(session, course.id)
            if draft_rev:
                draft_rev_id = draft_rev.id
            if target_revision:
                latest_rev_id = target_revision.id
            else:
                latest_rev = self.repo.get_latest_revision(session, course.id)
                if latest_rev:
                    latest_rev_id = latest_rev.id

        return self._build_course_detail(
            course,
            curriculum,
            draft_revision_id=draft_rev_id,
            latest_revision_id=latest_rev_id,
        )

    async def list_courses(
        self,
        session: Session,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        difficulty_level: Optional[str] = None,
        language: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> CourseListResponse:
        """List paginated courses for public catalog or admin directory."""
        items, total = self.repo.list_courses(
            session,
            status=status,
            search=search,
            tag=tag,
            category=category,
            difficulty_level=difficulty_level,
            language=language,
            page=page,
            per_page=per_page,
        )

        summaries = [self._build_course_summary(c) for c in items]

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        return CourseListResponse(
            items=summaries,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    async def check_slug_availability(
        self,
        session: Session,
        slug: str,
        *,
        exclude_course_id: Optional[uuid.UUID] = None,
    ) -> CourseSlugCheckResponse:
        """Verify slug syntax and database uniqueness for course forms."""
        normalized = slug.strip().lower()
        if not normalized or not SLUG_REGEX.match(normalized):
            return CourseSlugCheckResponse(
                slug=normalized,
                available=False,
                reason="Slug must use lowercase letters, numbers, and hyphens only.",
            )
        existing = self.repo.get_by_slug(session, normalized)
        if existing is not None and existing.id != exclude_course_id:
            return CourseSlugCheckResponse(
                slug=normalized,
                available=False,
                reason="This URL slug is already used by another course.",
            )
        return CourseSlugCheckResponse(slug=normalized, available=True, reason=None)

    def get_metadata_options(self, session: Session) -> CourseMetadataOptionsResponse:
        """Return canonical taxonomy options augmented with any existing custom categories."""
        existing_cats = self.repo.list_distinct_categories(session)
        merged_cats = list(DEFAULT_COURSE_CATEGORIES)
        seen_lower = {c.lower() for c in merged_cats}
        for cat in existing_cats:
            if cat.lower() not in seen_lower:
                seen_lower.add(cat.lower())
                merged_cats.append(cat)

        return CourseMetadataOptionsResponse(
            categories=merged_cats,
            difficulty_levels=[
                CourseMetadataOptionItem(value=code, label=label)
                for code, label in DIFFICULTY_LEVEL_LABELS.items()
            ],
            languages=list(DEFAULT_COURSE_LANGUAGES),
            currencies=[DEFAULT_CURRENCY_INR],
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
    ) -> CourseDetailResponse:
        """Update top-level course metadata with explicit partial-update semantics and audit logging."""
        course = self.repo.get_by_id(session, course_id)
        if course is None:
            raise ResourceNotFoundException("Course", str(course_id))

        fields_set = data.model_fields_set
        update_payload: dict[str, Any] = {
            field: getattr(data, field)
            for field in fields_set
        }

        if "slug" in fields_set and data.slug is None:
            raise ValidationException(
                message="Course slug cannot be cleared or empty.",
                code="INVALID_SLUG",
            )
        if "title" in fields_set and not data.title:
            raise ValidationException(
                message="Course title cannot be cleared or empty.",
                code="INVALID_TITLE",
            )
        if "category" in fields_set and not data.category:
            raise ValidationException(
                message="Category cannot be empty.",
                code="INVALID_CATEGORY",
            )
        if "difficulty_level" in fields_set and not data.difficulty_level:
            raise ValidationException(
                message="Difficulty level cannot be empty.",
                code="INVALID_DIFFICULTY",
            )
        if "language" in fields_set and not data.language:
            raise ValidationException(
                message="Language cannot be empty.",
                code="INVALID_LANGUAGE",
            )

        # Resolve linked thumbnail asset & explicit clearing semantics
        if "thumbnail_media_id" in fields_set:
            if data.thumbnail_media_id is None:
                update_payload["thumbnail_media_id"] = None
                if "thumbnail_url" not in fields_set:
                    update_payload["thumbnail_url"] = None
            else:
                media_id, media_url = self._resolve_thumbnail_media(
                    session,
                    data.thumbnail_media_id,
                    data.thumbnail_url,
                )
                update_payload["thumbnail_media_id"] = media_id
                update_payload["thumbnail_url"] = media_url
        elif "thumbnail_url" in fields_set:
            if not data.thumbnail_url or not data.thumbnail_url.startswith("/api/v1/media/public/"):
                update_payload["thumbnail_media_id"] = None

        # Cross-field pricing invariant check against persisted course state
        effective_is_free = (
            update_payload["is_free"]
            if "is_free" in update_payload
            else course.is_free
        )
        if effective_is_free:
            if "price_inr" in update_payload and update_payload["price_inr"] != 0:
                raise ValidationException(
                    message="Free courses must have price_inr equal to 0.",
                    code="INVALID_FREE_PRICE",
                )
            if (
                "compare_at_price_inr" in update_payload
                and update_payload["compare_at_price_inr"] is not None
            ):
                raise ValidationException(
                    message="Free courses cannot have a regular/compare-at price.",
                    code="INVALID_FREE_PRICE",
                )
            update_payload["price_inr"] = 0
            update_payload["compare_at_price_inr"] = None
        else:
            effective_price = (
                update_payload["price_inr"]
                if "price_inr" in update_payload
                else course.price_inr
            )
            effective_compare = (
                update_payload["compare_at_price_inr"]
                if "compare_at_price_inr" in update_payload
                else course.compare_at_price_inr
            )
            if effective_price is None or effective_price <= 0:
                raise ValidationException(
                    message="Paid courses must have a selling price greater than 0 INR.",
                    code="INVALID_COURSE_PRICE",
                )
            if effective_compare is not None:
                if effective_compare < effective_price:
                    raise ValidationException(
                        message="Discounted selling price cannot exceed regular price.",
                        code="INVALID_DISCOUNT_PRICE",
                    )
                if effective_compare == effective_price:
                    update_payload["compare_at_price_inr"] = None

        before_state = {
            "title": course.title,
            "slug": course.slug,
            "headline": course.headline,
            "category": course.category,
            "difficulty_level": course.difficulty_level,
            "language": course.language,
            "learning_outcomes": list(course.learning_outcomes or []),
            "requirements": list(course.requirements or []),
            "thumbnail_url": course.thumbnail_url,
            "thumbnail_media_id": str(course.thumbnail_media_id) if course.thumbnail_media_id else None,
            "price_inr": course.price_inr,
            "compare_at_price_inr": course.compare_at_price_inr,
            "currency": course.currency,
            "is_free": course.is_free,
            "tags": [t.tag for t in course.tags],
        }

        updated = self.repo.update_course(
            session,
            course,
            update_fields=update_payload,
        )

        after_state = {
            "title": updated.title,
            "slug": updated.slug,
            "headline": updated.headline,
            "category": updated.category,
            "difficulty_level": updated.difficulty_level,
            "language": updated.language,
            "learning_outcomes": list(updated.learning_outcomes or []),
            "requirements": list(updated.requirements or []),
            "thumbnail_url": updated.thumbnail_url,
            "thumbnail_media_id": str(updated.thumbnail_media_id) if updated.thumbnail_media_id else None,
            "price_inr": updated.price_inr,
            "compare_at_price_inr": updated.compare_at_price_inr,
            "currency": updated.currency,
            "is_free": updated.is_free,
            "tags": [t.tag for t in updated.tags],
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

        return await self.get_course_detail(session, str(updated.id), is_staff_view=True)

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

        prior_status = course.status
        archived = self.repo.archive_course(session, course)

        await self.audit_service.record_event(
            session,
            action="COURSE_ARCHIVED",
            resource_type="course",
            resource_id=str(archived.id),
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            before_state={"status": prior_status},
            after_state={"status": archived.status},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return self._build_course_summary(archived)

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
            "thumbnail_url": course.thumbnail_url,
            "thumbnail_media_id": str(course.thumbnail_media_id) if course.thumbnail_media_id else None,
            "category": course.category,
            "difficulty_level": course.difficulty_level,
            "language": course.language,
            "learning_outcomes": list(course.learning_outcomes or []),
            "requirements": list(course.requirements or []),
            "tags": [t.tag for t in course.tags],
            "price_inr": course.price_inr,
            "compare_at_price_inr": course.compare_at_price_inr,
            "currency": course.currency,
            "discount_percentage": course.discount_percentage,
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
