"""InAppNotificationRepository managing user notification records.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 33)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK205)

Strict Invariants:
1. Strict user isolation: Queries always enforce user_id match to eliminate IDOR risks.
2. Read receipt persistence: Individual and bulk read marking.
3. Unread count tracking: Efficient count of unread items per user.
"""

import logging
from typing import Any, Optional, Union
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.notification import NOTIFICATION_TYPE_ANNOUNCEMENT, Notification

logger = logging.getLogger(__name__)


class InAppNotificationRepository:
    """Repository handling database operations for In-App Notification entities."""

    async def list_user_notifications(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[Notification], int, int]:
        """Query paginated user notifications, total count, and unread count.

        Returns:
            Tuple of (items, total_filtered_count, unread_count).
        """
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id

        # Base query restricted strictly to owner
        base_stmt = select(Notification).where(Notification.user_id == uid)
        count_stmt = select(func.count(Notification.id)).where(Notification.user_id == uid)

        if unread_only:
            base_stmt = base_stmt.where(Notification.is_read.is_(False))
            count_stmt = count_stmt.where(Notification.is_read.is_(False))

        # Separate query for total unread items
        unread_stmt = select(func.count(Notification.id)).where(
            Notification.user_id == uid,
            Notification.is_read.is_(False),
        )

        query_stmt = (
            base_stmt
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        if isinstance(session, AsyncSession):
            items = list((await session.execute(query_stmt)).scalars().all())
            total = int((await session.execute(count_stmt)).scalar() or 0)
            unread_count = int((await session.execute(unread_stmt)).scalar() or 0)
        else:
            items = list(session.execute(query_stmt).scalars().all())
            total = int(session.execute(count_stmt).scalar() or 0)
            unread_count = int(session.execute(unread_stmt).scalar() or 0)

        return items, total, unread_count

    async def get_by_id_and_user(
        self,
        session: Union[AsyncSession, Session],
        *,
        notification_id: Union[uuid.UUID, str],
        user_id: Union[uuid.UUID, str],
    ) -> Optional[Notification]:
        """Fetch notification verifying user ownership."""
        nid = uuid.UUID(str(notification_id)) if not isinstance(notification_id, uuid.UUID) else notification_id
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id

        stmt = select(Notification).where(
            Notification.id == nid,
            Notification.user_id == uid,
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

    async def mark_as_read(
        self,
        session: Union[AsyncSession, Session],
        *,
        notification_id: Union[uuid.UUID, str],
        user_id: Union[uuid.UUID, str],
    ) -> Optional[Notification]:
        """Mark an individual notification as read enforcing user ownership."""
        notification = await self.get_by_id_and_user(session, notification_id=notification_id, user_id=user_id)
        if notification is None:
            return None

        if not notification.is_read:
            notification.is_read = True
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()

        return notification

    async def mark_all_as_read(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
    ) -> int:
        """Mark all unread notifications for a user as read."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id

        stmt = (
            update(Notification)
            .where(
                Notification.user_id == uid,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount

    async def create_notification(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        title: str,
        message: str,
        notification_type: str = NOTIFICATION_TYPE_ANNOUNCEMENT,
        data: Optional[dict[str, Any]] = None,
    ) -> Notification:
        """Create and flush an in-app notification record."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        notif = Notification(
            user_id=uid,
            title=title,
            message=message,
            notification_type=notification_type,
            data=data,
            is_read=False,
        )
        session.add(notif)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return notif
