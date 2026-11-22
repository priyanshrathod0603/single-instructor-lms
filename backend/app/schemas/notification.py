"""Pydantic schemas for In-App Notification Feed.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 33)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK205)
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    """In-app notification message item representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    message: str
    notification_type: str
    is_read: bool
    data: Optional[dict[str, Any]] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated in-app notification feed response envelope with unread counts."""
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    per_page: int
    total_pages: int


class NotificationReadAllResponse(BaseModel):
    """Response envelope for bulk mark-all-read operation."""
    updated_count: int
    message: str
