"""Course Catalog, Revision Control, and Publishing REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Sections 2.3, 2.4, 3.1)
- docs/backend/11-COURSE-MANAGEMENT.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301, TASK302, TASK304, TASK305)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-005)
"""

import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_optional_current_user,
    require_permissions,
)
from app.core.permissions import (
    COURSE_ARCHIVE,
    COURSE_CREATE,
    COURSE_EDIT,
    COURSE_PUBLISH,
    COURSE_REVISION_CREATE,
    COURSE_VIEW_ALL,
)
from app.models.course import COURSE_STATUS_PUBLISHED
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.schemas.course import (
    CourseCreateRequest,
    CourseDetailResponse,
    CourseListResponse,
    CourseRevisionCreateRequest,
    CourseRevisionResponse,
    CourseSummaryResponse,
    CourseUpdateRequest,
    CurriculumSectionResponse,
    PublishChecklistResponse,
    SectionCreateRequest,
    SectionReorderRequest,
)
from app.services.course_service import CourseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["Course Catalog & Curriculum"])


def get_course_service() -> CourseService:
    """Dependency providing CourseService instance."""
    return CourseService()


@router.get(
    "",
    response_model=CourseListResponse,
    summary="Public catalog of published courses",
)
async def list_public_courses_endpoint(
    search: Optional[str] = Query(None, description="Search term for title or headline"),
    tag: Optional[str] = Query(None, description="Filter courses by tag"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    course_service: CourseService = Depends(get_course_service),
) -> CourseListResponse:
    """Public catalog endpoint returning active published courses with pagination."""
    return await course_service.list_courses(
        db,
        status=COURSE_STATUS_PUBLISHED,
        search=search,
        tag=tag,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/manage",
    response_model=CourseListResponse,
    summary="Admin directory of all courses (draft, published, archived)",
)
async def list_all_courses_endpoint(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (DRAFT, PUBLISHED, ARCHIVED)"),
    search: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Tag filter"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_VIEW_ALL)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseListResponse:
    """Instructor/Staff view of all courses across all lifecycle statuses. Requires course:view_all."""
    return await course_service.list_courses(
        db,
        status=status_filter,
        search=search,
        tag=tag,
        page=page,
        per_page=per_page,
    )


@router.post(
    "",
    response_model=CourseSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new course entity and initial draft revision",
)
async def create_course_endpoint(
    data: CourseCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_CREATE)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseSummaryResponse:
    """Create a new course container and initialize Draft Revision 1. Requires course:create."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    course, _ = await course_service.create_course(
        db,
        data,
        actor_id=current_user.id,
        ip_address=ip,
        user_agent=ua,
    )

    return CourseSummaryResponse(
        id=course.id,
        slug=course.slug,
        title=course.title,
        headline=course.headline,
        thumbnail_url=course.thumbnail_url,
        status=course.status,
        price_inr=course.price_inr,
        is_free=course.is_free,
        tags=[t.tag for t in course.tags],
        live_revision_id=course.live_revision_id,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@router.get(
    "/{id_or_slug}",
    response_model=CourseDetailResponse,
    summary="Retrieve course details and live published curriculum",
)
async def get_course_detail_endpoint(
    id_or_slug: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    course_service: CourseService = Depends(get_course_service),
) -> CourseDetailResponse:
    """Public detail view of a published course or instructor view of a draft course."""
    is_staff = False
    if current_user is not None:
        is_staff = (
            any(r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
            or current_user.has_permission(COURSE_EDIT)
        )

    return await course_service.get_course_detail(db, id_or_slug, is_staff_view=is_staff)


@router.patch(
    "/{id}",
    response_model=CourseSummaryResponse,
    summary="Update top-level course metadata",
)
async def update_course_endpoint(
    id: uuid.UUID,
    data: CourseUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseSummaryResponse:
    """Update top-level course container metadata (slug, title, pricing, tags). Requires course:edit."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    return await course_service.update_course(
        db,
        id,
        data,
        actor_id=current_user.id,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/{id}/revisions",
    response_model=CourseRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone live revision into a new working draft revision",
)
async def spawn_revision_endpoint(
    id: uuid.UUID,
    data: CourseRevisionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_REVISION_CREATE)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseRevisionResponse:
    """Spawn a new draft revision, deep cloning the prior published curriculum hierarchy.

    Requires course:revision_create.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    return await course_service.spawn_revision(
        db,
        id,
        changelog=data.changelog,
        actor_id=current_user.id,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/{id}/revisions/{rev_id}",
    response_model=CourseRevisionResponse,
    summary="Fetch specific revision draft tree",
)
async def get_revision_endpoint(
    id: uuid.UUID,
    rev_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseRevisionResponse:
    """Fetch revision tree with sections, lessons, and resources. Requires course:edit."""
    return await course_service.get_revision(db, id, rev_id)


@router.post(
    "/{id}/revisions/{rev_id}/sections",
    response_model=CurriculumSectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add section to draft revision",
)
def add_section_to_revision_endpoint(
    id: uuid.UUID,
    rev_id: uuid.UUID,
    data: SectionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> CurriculumSectionResponse:
    """Add a section to the target draft revision. Requires course:edit."""
    return course_service.add_section(db, id, rev_id, data)


@router.put(
    "/{id}/revisions/{rev_id}/sections/reorder",
    response_model=List[CurriculumSectionResponse],
    summary="Bulk reorder sections with version check",
)
def reorder_sections_endpoint(
    id: uuid.UUID,
    rev_id: uuid.UUID,
    data: SectionReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_EDIT)),
    course_service: CourseService = Depends(get_course_service),
) -> List[CurriculumSectionResponse]:
    """Bulk reorder sections with optimistic concurrency guard. Requires course:edit."""
    return course_service.reorder_sections(db, id, rev_id, data)


@router.get(
    "/{id}/publish-checklist",
    response_model=PublishChecklistResponse,
    summary="Evaluate pre-flight publishing requirements",
)
def publish_checklist_endpoint(
    id: uuid.UUID,
    revision_id: Optional[uuid.UUID] = Query(None, description="Revision UUID (defaults to active draft)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_PUBLISH)),
    course_service: CourseService = Depends(get_course_service),
) -> PublishChecklistResponse:
    """Evaluate publishing checklist rules (CHK-01 to CHK-08). Requires course:publish (Super Admin)."""
    target_rev_id = revision_id
    if target_rev_id is None:
        draft = course_service.repo.get_draft_revision(db, id)
        if draft is None:
            latest = course_service.repo.get_latest_revision(db, id)
            if latest is None:
                raise ResourceNotFoundException("CourseRevision", "draft")
            target_rev_id = latest.id
        else:
            target_rev_id = draft.id

    return course_service.evaluate_publish_checklist(db, id, target_rev_id)


@router.post(
    "/{id}/revisions/{rev_id}/publish",
    response_model=CourseRevisionResponse,
    summary="Atomically publish draft revision as live snapshot",
)
async def publish_revision_endpoint(
    id: uuid.UUID,
    rev_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_PUBLISH)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseRevisionResponse:
    """Atomically validate checklist, freeze snapshot, and publish revision.

    Requires course:publish (Super Admin).
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    return await course_service.publish_revision(
        db,
        id,
        rev_id,
        actor_id=current_user.id,
        ip_address=ip,
        user_agent=ua,
    )


@router.delete(
    "/{id}",
    response_model=CourseSummaryResponse,
    summary="Archive course (soft status update)",
)
async def archive_course_endpoint(
    id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(COURSE_ARCHIVE)),
    course_service: CourseService = Depends(get_course_service),
) -> CourseSummaryResponse:
    """Archive course container, removing it from active catalog. Requires course:archive."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    return await course_service.archive_course(
        db,
        id,
        actor_id=current_user.id,
        ip_address=ip,
        user_agent=ua,
    )
