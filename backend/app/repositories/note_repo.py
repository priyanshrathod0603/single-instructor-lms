"""Repository for Study Notes persistence and querying (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 5)
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
from app.models.note import (
    NOTE_STATUS_ARCHIVED,
    NOTE_STATUS_DRAFT,
    NOTE_STATUS_PUBLISHED,
    Note,
)
from app.schemas.note import slugify

logger = logging.getLogger(__name__)


class NoteRepository:
    """Data access repository for Study Notes."""

    def get_by_id(self, db: Session, note_id: uuid.UUID) -> Optional[Note]:
        """Fetch note by UUID primary key."""
        stmt = (
            select(Note)
            .options(joinedload(Note.author), joinedload(Note.pdf_media))
            .where(Note.id == note_id)
        )
        return db.scalar(stmt)

    def get_by_slug(self, db: Session, slug: str) -> Optional[Note]:
        """Fetch note by unique slug."""
        stmt = (
            select(Note)
            .options(joinedload(Note.author), joinedload(Note.pdf_media))
            .where(func.lower(Note.slug) == slug.strip().lower())
        )
        return db.scalar(stmt)

    def list_notes(
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
    ) -> Tuple[List[Note], int]:
        """Paginated list of study notes with multi-attribute filtering."""
        query = select(Note).options(
            joinedload(Note.author), joinedload(Note.pdf_media)
        )
        base_count_query = select(Note.id)

        if status and status.upper() != "ALL":
            query = query.where(Note.status == status.upper())
            base_count_query = base_count_query.where(Note.status == status.upper())

        if category and category.upper() != "ALL":
            cat_clause = func.lower(Note.category) == category.strip().lower()
            query = query.where(cat_clause)
            base_count_query = base_count_query.where(cat_clause)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            search_clause = or_(
                func.lower(Note.title).like(term),
                func.lower(Note.slug).like(term),
                func.lower(Note.description).like(term),
            )
            query = query.where(search_clause)
            base_count_query = base_count_query.where(search_clause)

        # Count total matching records
        count_stmt = select(func.count()).select_from(base_count_query.subquery())
        total = db.scalar(count_stmt) or 0

        # Sorting
        sort_col = getattr(Note, sort_by, Note.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        query = query.offset(offset).limit(per_page)

        items = list(db.scalars(query).unique().all())
        return items, total

    def create_note(
        self,
        db: Session,
        *,
        title: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        category: str = "General",
        pdf_media_id: Optional[uuid.UUID] = None,
        pdf_url: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        status: str = NOTE_STATUS_DRAFT,
        author_id: uuid.UUID,
    ) -> Note:
        """Create a new study note entity."""
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
                raise ConflictException(f"Note with slug '{slug}' already exists.")

        note = Note(
            title=title,
            slug=slug,
            description=description,
            category=category,
            pdf_media_id=pdf_media_id,
            pdf_url=pdf_url,
            file_size_bytes=file_size_bytes,
            status=status,
            author_id=author_id,
            published_at=utc_now() if status == NOTE_STATUS_PUBLISHED else None,
        )
        db.add(note)
        db.flush()
        return note

    def update_note(
        self,
        db: Session,
        note: Note,
        *,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        pdf_media_id: Optional[uuid.UUID] = None,
        pdf_url: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Note:
        """Update existing note fields."""
        if title is not None:
            note.title = title
        if slug is not None:
            clean_slug = slugify(slug)
            if clean_slug != note.slug:
                existing = self.get_by_slug(db, clean_slug)
                if existing and existing.id != note.id:
                    raise ConflictException(f"Note with slug '{clean_slug}' already exists.")
                note.slug = clean_slug
        if description is not None:
            note.description = description
        if category is not None:
            note.category = category
        if pdf_media_id is not None:
            note.pdf_media_id = pdf_media_id
        if pdf_url is not None:
            note.pdf_url = pdf_url
        if file_size_bytes is not None:
            note.file_size_bytes = file_size_bytes
        if status is not None:
            if status == NOTE_STATUS_PUBLISHED and note.status != NOTE_STATUS_PUBLISHED:
                note.publish()
            elif status == NOTE_STATUS_DRAFT and note.status != NOTE_STATUS_DRAFT:
                note.unpublish()
            elif status == NOTE_STATUS_ARCHIVED and note.status != NOTE_STATUS_ARCHIVED:
                note.archive()
            else:
                note.status = status

        note.updated_at = utc_now()
        db.flush()
        return note

    def delete_note(self, db: Session, note: Note) -> None:
        """Delete note entity."""
        db.delete(note)
        db.flush()

    def get_categories(self, db: Session) -> List[str]:
        """Fetch distinct categories used across study notes."""
        stmt = select(Note.category).distinct().order_by(Note.category)
        return list(db.scalars(stmt).all())
