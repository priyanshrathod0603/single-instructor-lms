"""Service handling Blog CMS business logic and audit logging (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 4)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
"""

from datetime import datetime
import logging
from typing import List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, ResourceNotFoundException
from app.models.audit_log import AuditLog
from app.models.blog import (
    BLOG_STATUS_ARCHIVED,
    BLOG_STATUS_DRAFT,
    BLOG_STATUS_PUBLISHED,
    BlogPost,
)
from app.models.user import User
from app.repositories.blog_repo import BlogRepository
from app.schemas.blog import (
    BlogPostAuthorSummary,
    BlogPostCreateRequest,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostUpdateRequest,
)

logger = logging.getLogger(__name__)


class BlogService:
    """Domain service for Super Admin Blog CMS operations."""

    def __init__(self, repo: Optional[BlogRepository] = None) -> None:
        self.repo = repo or BlogRepository()

    def _to_response(self, post: BlogPost) -> BlogPostResponse:
        """Serialize BlogPost entity into Pydantic response envelope."""
        author_summary = None
        if post.author:
            author_summary = BlogPostAuthorSummary(
                id=post.author.id,
                email=post.author.email,
                full_name=post.author.full_name,
            )

        return BlogPostResponse(
            id=post.id,
            title=post.title,
            slug=post.slug,
            excerpt=post.excerpt,
            content=post.content,
            category=post.category,
            thumbnail_url=post.thumbnail_url,
            thumbnail_media_id=post.thumbnail_media_id,
            status=post.status,
            published_at=post.published_at,
            author_id=post.author_id,
            author=author_summary,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    def list_posts(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> BlogPostListResponse:
        """Paginated search and retrieval of blog posts."""
        items, total = self.repo.list_posts(
            db,
            search=search,
            status=status,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return BlogPostListResponse(
            items=[self._to_response(p) for p in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    def get_post(self, db: Session, post_id: uuid.UUID) -> BlogPostResponse:
        """Fetch single blog post by UUID."""
        post = self.repo.get_by_id(db, post_id)
        if not post:
            raise ResourceNotFoundException("BlogPost", str(post_id))
        return self._to_response(post)

    def create_post(
        self,
        db: Session,
        current_user: User,
        data: BlogPostCreateRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> BlogPostResponse:
        """Create new blog post with immutable audit logging."""
        post = self.repo.create_post(
            db,
            title=data.title,
            content=data.content,
            slug=data.slug,
            excerpt=data.excerpt,
            category=data.category,
            thumbnail_url=data.thumbnail_url,
            thumbnail_media_id=data.thumbnail_media_id,
            status=data.status,
            author_id=current_user.id,
        )

        # Audit Event
        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="BLOG_POST_CREATED",
                resource_type="blog_post",
                resource_id=str(post.id),
                before_state=None,
                after_state={
                    "title": post.title,
                    "slug": post.slug,
                    "status": post.status,
                    "category": post.category,
                },
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(post)
        return self._to_response(post)

    def update_post(
        self,
        db: Session,
        current_user: User,
        post_id: uuid.UUID,
        data: BlogPostUpdateRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> BlogPostResponse:
        """Update existing blog post."""
        post = self.repo.get_by_id(db, post_id)
        if not post:
            raise ResourceNotFoundException("BlogPost", str(post_id))

        before_state = {
            "title": post.title,
            "slug": post.slug,
            "status": post.status,
            "category": post.category,
        }

        updated = self.repo.update_post(
            db,
            post,
            title=data.title,
            slug=data.slug,
            excerpt=data.excerpt,
            content=data.content,
            category=data.category,
            thumbnail_url=data.thumbnail_url,
            thumbnail_media_id=data.thumbnail_media_id,
            status=data.status,
        )

        after_state = {
            "title": updated.title,
            "slug": updated.slug,
            "status": updated.status,
            "category": updated.category,
        }

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="BLOG_POST_UPDATED",
                resource_type="blog_post",
                resource_id=str(updated.id),
                before_state=before_state,
                after_state=after_state,
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(updated)
        return self._to_response(updated)

    def change_status(
        self,
        db: Session,
        current_user: User,
        post_id: uuid.UUID,
        target_status: str,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> BlogPostResponse:
        """Publish, unpublish, or archive a blog post."""
        post = self.repo.get_by_id(db, post_id)
        if not post:
            raise ResourceNotFoundException("BlogPost", str(post_id))

        target_status = target_status.upper()
        old_status = post.status

        if target_status == BLOG_STATUS_PUBLISHED:
            post.publish()
            action = "BLOG_POST_PUBLISHED"
        elif target_status == BLOG_STATUS_DRAFT:
            post.unpublish()
            action = "BLOG_POST_UNPUBLISHED"
        elif target_status == BLOG_STATUS_ARCHIVED:
            post.archive()
            action = "BLOG_POST_UPDATED"
        else:
            raise BadRequestException(f"Unsupported blog status '{target_status}'.")

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action=action,
                resource_type="blog_post",
                resource_id=str(post.id),
                before_state={"status": old_status},
                after_state={"status": post.status, "published_at": str(post.published_at)},
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(post)
        return self._to_response(post)

    def delete_post(
        self,
        db: Session,
        current_user: User,
        post_id: uuid.UUID,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Delete blog post permanently with audit tracking."""
        post = self.repo.get_by_id(db, post_id)
        if not post:
            raise ResourceNotFoundException("BlogPost", str(post_id))

        before_state = {
            "title": post.title,
            "slug": post.slug,
            "status": post.status,
            "category": post.category,
        }

        self.repo.delete_post(db, post)

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="BLOG_POST_DELETED",
                resource_type="blog_post",
                resource_id=str(post_id),
                before_state=before_state,
                after_state=None,
                ip_address=ip_address,
            )
        )
        db.commit()

    def get_categories(self, db: Session) -> List[str]:
        """Fetch all unique categories."""
        return self.repo.get_categories(db)
