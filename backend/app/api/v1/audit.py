"""Super Admin Audit Trail Query REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK206)

Strict Invariants:
1. Gated Access: Restricted strictly to callers with audit:view permission (Super Admin).
2. Append-Only Read Trail: Pure read-only query endpoint; zero mutations or deletions.
3. Sensitive Data Redaction: Passwords and private credentials scrubbed at entry and serialization.
"""

from datetime import datetime
import logging
import math
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permissions
from app.core.exceptions import NotFoundException
from app.core.permissions import AUDIT_VIEW
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit import AuditLogListResponse, AuditLogResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["Audit Trail"])


def get_audit_repository() -> AuditRepository:
    """Dependency providing AuditRepository instance."""
    return AuditRepository()


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="Filter and inspect immutable security audit trail",
)
async def query_audit_logs_endpoint(
    actor_id: Optional[uuid.UUID] = Query(None, description="Filter by actor UUID"),
    actor_type: Optional[str] = Query(None, description="Filter by persona (e.g. STUDENT, ADMIN)"),
    action: Optional[str] = Query(None, description="Filter by action verb"),
    resource_type: Optional[str] = Query(None, description="Filter by entity type (e.g. user, course)"),
    resource_id: Optional[str] = Query(None, description="Filter by entity ID"),
    request_id: Optional[str] = Query(None, description="Filter by correlation request ID"),
    ip_address: Optional[str] = Query(None, description="Filter by client IP address"),
    start_date: Optional[datetime] = Query(None, description="Earliest UTC creation timestamp"),
    end_date: Optional[datetime] = Query(None, description="Latest UTC creation timestamp"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(AUDIT_VIEW)),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditLogListResponse:
    """Query immutable audit logs with multi-attribute filtering and pagination. Requires audit:view."""
    offset = (page - 1) * per_page
    logs, total = await audit_repo.list_logs(
        db,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        ip_address=ip_address,
        start_date=start_date,
        end_date=end_date,
        limit=per_page,
        offset=offset,
    )
    total_pages = math.ceil(total / per_page) if per_page > 0 else 0
    items = [AuditLogResponse.model_validate(log) for log in logs]
    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get(
    "/{id}",
    response_model=AuditLogResponse,
    summary="Retrieve single audit log entry by UUID",
)
async def get_audit_log_by_id_endpoint(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(AUDIT_VIEW)),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> AuditLogResponse:
    """Retrieve full audit log entry by UUID, including state diffs and metadata. Requires audit:view."""
    log = await audit_repo.get_by_id(db, id)
    if log is None:
        raise NotFoundException(
            message="Audit log entry not found.",
            code="AUDIT_LOG_NOT_FOUND",
        )
    return AuditLogResponse.model_validate(log)
