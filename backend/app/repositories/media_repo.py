"""MediaRepository managing MediaAsset persistence and queries.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 32)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401)
"""

import logging
from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.base import utc_now
from app.models.media import (
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)

logger = logging.getLogger(__name__)


class MediaRepository:
    """Repository managing database persistence and status transitions for media assets."""

    def create_asset(
        self,
        session: Session,
        *,
        uploader_id: uuid.UUID,
        filename: str,
        file_key: str,
        bucket: str,
        mime_type: str,
        file_size_bytes: int,
    ) -> MediaAsset:
        """Create new MediaAsset record with initial UPLOADING status."""
        asset = MediaAsset(
            uploader_id=uploader_id,
            filename=filename,
            file_key=file_key,
            bucket=bucket,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            status=MEDIA_STATUS_UPLOADING,
        )
        session.add(asset)
        session.flush()
        return asset

    def get_by_id(
        self,
        session: Session,
        media_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[MediaAsset]:
        """Fetch media asset by UUID."""
        stmt = (
            select(MediaAsset)
            .options(selectinload(MediaAsset.uploader))
            .where(MediaAsset.id == media_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.scalar(stmt)

    def get_by_key(
        self,
        session: Session,
        file_key: str,
    ) -> Optional[MediaAsset]:
        """Fetch media asset by S3/R2 object storage key."""
        stmt = (
            select(MediaAsset)
            .options(selectinload(MediaAsset.uploader))
            .where(MediaAsset.file_key == file_key)
        )
        return session.scalar(stmt)

    def update_status(
        self,
        session: Session,
        asset: MediaAsset,
        *,
        status: str,
        transcode_output: Optional[dict[str, Any]] = None,
    ) -> MediaAsset:
        """Update lifecycle status and optional transcode output metadata."""
        asset.status = status
        if transcode_output is not None:
            asset.transcode_output = transcode_output
        asset.updated_at = utc_now()
        session.flush()
        return asset

    def list_assets(
        self,
        session: Session,
        *,
        uploader_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[MediaAsset], int]:
        """Paginated listing of media assets with optional filters."""
        query = select(MediaAsset).options(selectinload(MediaAsset.uploader))

        if uploader_id:
            query = query.where(MediaAsset.uploader_id == uploader_id)
        if status:
            query = query.where(MediaAsset.status == status)

        count_stmt = select(func.count()).select_from(query.order_by(None).subquery())
        total = session.scalar(count_stmt) or 0

        offset = (page - 1) * per_page
        query = query.order_by(desc(MediaAsset.created_at)).offset(offset).limit(per_page)

        items = list(session.scalars(query).all())
        return items, total

    def delete_asset(
        self,
        session: Session,
        asset: MediaAsset,
    ) -> None:
        """Delete MediaAsset record."""
        session.delete(asset)
        session.flush()
