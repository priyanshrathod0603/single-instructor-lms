"""Pydantic schemas for Super Admin Audit Trail API.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 35)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK206)
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Immutable audit trail event record representation."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    actor_type: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    before_state: Optional[dict[str, Any]] = None
    after_state: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated list of immutable audit log records."""
    items: list[AuditLogResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
