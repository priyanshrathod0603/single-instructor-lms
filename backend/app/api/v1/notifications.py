"""In-App Notification Feed REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK205)

Strict Invariants:
1. Recipient Isolation: Users can only view and mutate their own notifications.
2. Unread Filtering: Dedicated flag to view pending/unread notices.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationReadAllResponse,
    NotificationResponse,
)
from app.services.in_app_notification_service import InAppNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_notification_service() -> InAppNotificationService:
    """Dependency providing InAppNotificationService instance."""
    return InAppNotificationService()


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List in-app notifications for authenticated user",
)
async def list_notifications_endpoint(
    unread_only: bool = Query(False, description="Filter to only unread notifications"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service: InAppNotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """Retrieve authenticated user's notification feed with unread count."""
    return await notification_service.list_notifications(
        db,
        user_id=current_user.id,
        unread_only=unread_only,
        page=page,
        per_page=per_page,
    )


@router.patch(
    "/{id}/read",
    response_model=NotificationResponse,
    summary="Mark an individual notification as read",
)
async def mark_notification_read_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service: InAppNotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Mark notification as read. Enforces owner verification."""
    result = await notification_service.mark_as_read(
        db,
        notification_id=id,
        user_id=current_user.id,
    )
    db.commit()
    return result


@router.post(
    "/read-all",
    response_model=NotificationReadAllResponse,
    summary="Mark all unread notifications as read",
)
async def mark_all_notifications_read_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service: InAppNotificationService = Depends(get_notification_service),
) -> NotificationReadAllResponse:
    """Mark all unread notifications as read for current authenticated user."""
    result = await notification_service.mark_all_as_read(
        db,
        user_id=current_user.id,
    )
    db.commit()
    return result
