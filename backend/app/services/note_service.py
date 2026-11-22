"""Service handling Study Notes CMS business logic and audit logging (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 5)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
"""

from datetime import datetime
import logging
from typing import List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, ResourceNotFoundException
from app.models.audit_log import AuditLog
from app.models.media import MediaAsset
from app.models.note import (
    NOTE_STATUS_ARCHIVED,
    NOTE_STATUS_DRAFT,
    NOTE_STATUS_PUBLISHED,
    Note,
)
from app.models.user import User
from app.repositories.note_repo import NoteRepository
from app.schemas.note import (
    NoteAuthorSummary,
    NoteCreateRequest,
    NoteListResponse,
    NoteReplacePdfRequest,
    NoteResponse,
    NoteUpdateRequest,
)

logger = logging.getLogger(__name__)


class NoteService:
    """Domain service for Super Admin Notes CMS operations."""

    def __init__(self, repo: Optional[NoteRepository] = None) -> None:
        self.repo = repo or NoteRepository()

    def _to_response(self, note: Note) -> NoteResponse:
        """Serialize Note entity into Pydantic response envelope."""
        author_summary = None
        if note.author:
            author_summary = NoteAuthorSummary(
                id=note.author.id,
                email=note.author.email,
                full_name=note.author.full_name,
            )

        return NoteResponse(
            id=note.id,
            title=note.title,
            slug=note.slug,
            description=note.description,
            category=note.category,
            pdf_media_id=note.pdf_media_id,
            pdf_url=note.pdf_url,
            file_size_bytes=note.file_size_bytes,
            status=note.status,
            published_at=note.published_at,
            author_id=note.author_id,
            author=author_summary,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

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
    ) -> NoteListResponse:
        """Paginated search and retrieval of study notes."""
        items, total = self.repo.list_notes(
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
        return NoteListResponse(
            items=[self._to_response(n) for n in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    def get_note(self, db: Session, note_id: uuid.UUID) -> NoteResponse:
        """Fetch single note by UUID."""
        note = self.repo.get_by_id(db, note_id)
        if not note:
            raise ResourceNotFoundException("Note", str(note_id))
        return self._to_response(note)

    def create_note(
        self,
        db: Session,
        current_user: User,
        data: NoteCreateRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> NoteResponse:
        """Create new study note with immutable audit logging."""
        file_size = data.file_size_bytes
        pdf_url = data.pdf_url

        # If a MediaAsset ID is linked, verify and extract file size if needed
        if data.pdf_media_id:
            media = db.get(MediaAsset, data.pdf_media_id)
            if media:
                if not file_size and media.file_size_bytes:
                    file_size = media.file_size_bytes
                if not pdf_url:
                    pdf_url = media.storage_key

        note = self.repo.create_note(
            db,
            title=data.title,
            slug=data.slug,
            description=data.description,
            category=data.category,
            pdf_media_id=data.pdf_media_id,
            pdf_url=pdf_url,
            file_size_bytes=file_size,
            status=data.status,
            author_id=current_user.id,
        )

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="NOTE_CREATED",
                resource_type="note",
                resource_id=str(note.id),
                before_state=None,
                after_state={
                    "title": note.title,
                    "slug": note.slug,
                    "status": note.status,
                    "category": note.category,
                    "pdf_media_id": str(note.pdf_media_id) if note.pdf_media_id else None,
                },
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(note)
        return self._to_response(note)

    def update_note(
        self,
        db: Session,
        current_user: User,
        note_id: uuid.UUID,
        data: NoteUpdateRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> NoteResponse:
        """Update existing study note."""
        note = self.repo.get_by_id(db, note_id)
        if not note:
            raise ResourceNotFoundException("Note", str(note_id))

        before_state = {
            "title": note.title,
            "slug": note.slug,
            "status": note.status,
            "category": note.category,
        }

        updated = self.repo.update_note(
            db,
            note,
            title=data.title,
            slug=data.slug,
            description=data.description,
            category=data.category,
            pdf_media_id=data.pdf_media_id,
            pdf_url=data.pdf_url,
            file_size_bytes=data.file_size_bytes,
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
                action="NOTE_UPDATED",
                resource_type="note",
                resource_id=str(updated.id),
                before_state=before_state,
                after_state=after_state,
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(updated)
        return self._to_response(updated)

    def replace_pdf(
        self,
        db: Session,
        current_user: User,
        note_id: uuid.UUID,
        data: NoteReplacePdfRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> NoteResponse:
        """Replace PDF document attachment for a note."""
        note = self.repo.get_by_id(db, note_id)
        if not note:
            raise ResourceNotFoundException("Note", str(note_id))

        old_pdf_url = note.pdf_url
        old_media_id = str(note.pdf_media_id) if note.pdf_media_id else None

        file_size = data.file_size_bytes
        if data.pdf_media_id:
            media = db.get(MediaAsset, data.pdf_media_id)
            if media and not file_size and media.file_size_bytes:
                file_size = media.file_size_bytes

        note.pdf_media_id = data.pdf_media_id
        note.pdf_url = data.pdf_url
        note.file_size_bytes = file_size

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="NOTE_PDF_REPLACED",
                resource_type="note",
                resource_id=str(note.id),
                before_state={"pdf_url": old_pdf_url, "pdf_media_id": old_media_id},
                after_state={"pdf_url": note.pdf_url, "pdf_media_id": str(note.pdf_media_id) if note.pdf_media_id else None},
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(note)
        return self._to_response(note)

    def change_status(
        self,
        db: Session,
        current_user: User,
        note_id: uuid.UUID,
        target_status: str,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> NoteResponse:
        """Publish, unpublish, or archive a note."""
        note = self.repo.get_by_id(db, note_id)
        if not note:
            raise ResourceNotFoundException("Note", str(note_id))

        target_status = target_status.upper()
        old_status = note.status

        if target_status == NOTE_STATUS_PUBLISHED:
            note.publish()
            action = "NOTE_PUBLISHED"
        elif target_status == NOTE_STATUS_DRAFT:
            note.unpublish()
            action = "NOTE_UNPUBLISHED"
        elif target_status == NOTE_STATUS_ARCHIVED:
            note.archive()
            action = "NOTE_UPDATED"
        else:
            raise BadRequestException(f"Unsupported note status '{target_status}'.")

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action=action,
                resource_type="note",
                resource_id=str(note.id),
                before_state={"status": old_status},
                after_state={"status": note.status, "published_at": str(note.published_at)},
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(note)
        return self._to_response(note)

    def delete_note(
        self,
        db: Session,
        current_user: User,
        note_id: uuid.UUID,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Delete note permanently with audit tracking."""
        note = self.repo.get_by_id(db, note_id)
        if not note:
            raise ResourceNotFoundException("Note", str(note_id))

        before_state = {
            "title": note.title,
            "slug": note.slug,
            "status": note.status,
            "category": note.category,
            "pdf_media_id": str(note.pdf_media_id) if note.pdf_media_id else None,
        }

        self.repo.delete_note(db, note)

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="NOTE_DELETED",
                resource_type="note",
                resource_id=str(note_id),
                before_state=before_state,
                after_state=None,
                ip_address=ip_address,
            )
        )
        db.commit()

    def get_categories(self, db: Session) -> List[str]:
        """Fetch all unique categories."""
        return self.repo.get_categories(db)
