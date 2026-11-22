"""InAppNotificationService orchestrating user in-app notification feed.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 33)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK205)
"""

import math
from typing import Any, Optional, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.notification import NOTIFICATION_TYPE_ANNOUNCEMENT, Notification
from app.repositories.in_app_notification_repo import InAppNotificationRepository
from app.schemas.notification import (
    NotificationListResponse,
    NotificationReadAllResponse,
    NotificationResponse,
)


class InAppNotificationService:
    """Service handling in-app user notifications and read receipt management."""

    def __init__(self, repository: Optional[InAppNotificationRepository] = None) -> None:
        self.repository = repository or InAppNotificationRepository()

    async def list_notifications(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> NotificationListResponse:
        """Fetch paginated notifications for authenticated user."""
        items, total, unread_count = await self.repository.list_user_notifications(
            session,
            user_id=user_id,
            unread_only=unread_only,
            page=page,
            per_page=per_page,
        )
        total_pages = math.ceil(total / per_page) if per_page > 0 else 0
        resp_items = [NotificationResponse.model_validate(n) for n in items]
        return NotificationListResponse(
            items=resp_items,
            total=total,
            unread_count=unread_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    async def mark_as_read(
        self,
        session: Union[AsyncSession, Session],
        *,
        notification_id: Union[uuid.UUID, str],
        user_id: Union[uuid.UUID, str],
    ) -> NotificationResponse:
        """Mark individual notification as read enforcing user ownership."""
        notification = await self.repository.mark_as_read(
            session,
            notification_id=notification_id,
            user_id=user_id,
        )
        if notification is None:
            raise NotFoundException(
                message="Notification not found.",
                code="NOTIFICATION_NOT_FOUND",
            )
        return NotificationResponse.model_validate(notification)

    async def mark_all_as_read(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
    ) -> NotificationReadAllResponse:
        """Mark all unread notifications for a user as read."""
        count = await self.repository.mark_all_as_read(session, user_id=user_id)
        return NotificationReadAllResponse(
            updated_count=count,
            message=f"Marked {count} notification(s) as read.",
        )

    async def send_notification(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        title: str,
        message: str,
        notification_type: str = NOTIFICATION_TYPE_ANNOUNCEMENT,
        data: Optional[dict[str, Any]] = None,
    ) -> NotificationResponse:
        """Create and flush an in-app notification."""
        notif = await self.repository.create_notification(
            session,
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            data=data,
        )
        return NotificationResponse.model_validate(notif)
