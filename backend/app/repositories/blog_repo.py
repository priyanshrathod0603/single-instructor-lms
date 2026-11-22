"""Repository for Blog Posts persistence and querying (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 4)
- docs/backend/04-DATABASE-ARCHITECTURE.md
"""

from datetime import datetime
import logging
from typing import List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.models.base import utc_now
from app.models.blog import (
    BLOG_STATUS_ARCHIVED,
    BLOG_STATUS_DRAFT,
    BLOG_STATUS_PUBLISHED,
    BlogPost,
)
from app.schemas.blog import slugify

logger = logging.getLogger(__name__)


class BlogRepository:
    """Data access repository for Blog Posts."""

    def get_by_id(self, db: Session, post_id: uuid.UUID) -> Optional[BlogPost]:
        """Fetch blog post by UUID primary key."""
        stmt = (
            select(BlogPost)
            .options(joinedload(BlogPost.author), joinedload(BlogPost.thumbnail_media))
            .where(BlogPost.id == post_id)
        )
        return db.scalar(stmt)

    def get_by_slug(self, db: Session, slug: str) -> Optional[BlogPost]:
        """Fetch blog post by unique slug."""
        stmt = (
            select(BlogPost)
            .options(joinedload(BlogPost.author), joinedload(BlogPost.thumbnail_media))
            .where(func.lower(BlogPost.slug) == slug.strip().lower())
        )
        return db.scalar(stmt)

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
    ) -> Tuple[List[BlogPost], int]:
        """Paginated list of blog posts with multi-attribute filtering."""
        query = select(BlogPost).options(
            joinedload(BlogPost.author), joinedload(BlogPost.thumbnail_media)
        )
        base_count_query = select(BlogPost.id)

        if status and status.upper() != "ALL":
            query = query.where(BlogPost.status == status.upper())
            base_count_query = base_count_query.where(BlogPost.status == status.upper())

        if category and category.upper() != "ALL":
            cat_clause = func.lower(BlogPost.category) == category.strip().lower()
            query = query.where(cat_clause)
            base_count_query = base_count_query.where(cat_clause)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            search_clause = or_(
                func.lower(BlogPost.title).like(term),
                func.lower(BlogPost.slug).like(term),
                func.lower(BlogPost.content).like(term),
                func.lower(BlogPost.excerpt).like(term),
            )
            query = query.where(search_clause)
            base_count_query = base_count_query.where(search_clause)

        # Count total matching records
        count_stmt = select(func.count()).select_from(base_count_query.subquery())
        total = db.scalar(count_stmt) or 0

        # Sorting
        sort_col = getattr(BlogPost, sort_by, BlogPost.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        query = query.offset(offset).limit(per_page)

        items = list(db.scalars(query).unique().all())
        return items, total

    def create_post(
        self,
        db: Session,
        *,
        title: str,
        content: str,
        slug: Optional[str] = None,
        excerpt: Optional[str] = None,
        category: str = "General",
        thumbnail_url: Optional[str] = None,
        thumbnail_media_id: Optional[uuid.UUID] = None,
        status: str = BLOG_STATUS_DRAFT,
        author_id: uuid.UUID,
    ) -> BlogPost:
        """Create a new blog post entity."""
        if not slug:
            base_slug = slugify(title)
            slug = base_slug
            counter = 1
            while self.get_by_slug(db, slug) is not None:
                slug = f"{base_slug}-{counter}"
                counter += 1
        else:
            slug = slugify(slug)
            if self.get_by_slug(db, slug) is not None:
                raise ConflictException(f"Blog post with slug '{slug}' already exists.")

        post = BlogPost(
            title=title,
            slug=slug,
            excerpt=excerpt,
            content=content,
            category=category,
            thumbnail_url=thumbnail_url,
            thumbnail_media_id=thumbnail_media_id,
            status=status,
            author_id=author_id,
            published_at=utc_now() if status == BLOG_STATUS_PUBLISHED else None,
        )
        db.add(post)
        db.flush()
        return post

    def update_post(
        self,
        db: Session,
        post: BlogPost,
        *,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        excerpt: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        thumbnail_media_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> BlogPost:
        """Update existing blog post fields."""
        if title is not None:
            post.title = title
        if slug is not None:
            clean_slug = slugify(slug)
            if clean_slug != post.slug:
                existing = self.get_by_slug(db, clean_slug)
                if existing and existing.id != post.id:
                    raise ConflictException(f"Blog post with slug '{clean_slug}' already exists.")
                post.slug = clean_slug
        if excerpt is not None:
            post.excerpt = excerpt
        if content is not None:
            post.content = content
        if category is not None:
            post.category = category
        if thumbnail_url is not None:
            post.thumbnail_url = thumbnail_url
        if thumbnail_media_id is not None:
            post.thumbnail_media_id = thumbnail_media_id
        if status is not None:
            if status == BLOG_STATUS_PUBLISHED and post.status != BLOG_STATUS_PUBLISHED:
                post.publish()
            elif status == BLOG_STATUS_DRAFT and post.status != BLOG_STATUS_DRAFT:
                post.unpublish()
            elif status == BLOG_STATUS_ARCHIVED and post.status != BLOG_STATUS_ARCHIVED:
                post.archive()
            else:
                post.status = status

        post.updated_at = utc_now()
        db.flush()
        return post

    def delete_post(self, db: Session, post: BlogPost) -> None:
        """Delete blog post entity."""
        db.delete(post)
        db.flush()

    def get_categories(self, db: Session) -> List[str]:
        """Fetch distinct categories used across blog posts."""
        stmt = select(BlogPost.category).distinct().order_by(BlogPost.category)
        return list(db.scalars(stmt).all())
