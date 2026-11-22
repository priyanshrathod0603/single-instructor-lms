"""AuditRepository for persistent append-only audit trail.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 35)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK007)

Features:
1. Pure async SQLAlchemy 2.0 query execution (supporting both AsyncSession and Session).
2. add() adds and flushes audit records without committing, allowing caller to control transaction boundary.
3. get_by_id() retrieves single audit log by UUID.
4. list_logs() provides comprehensive filtering by actor_id, actor_type, action, resource_type,
   resource_id, request_id, date ranges, and pagination with total count.
"""

from datetime import datetime
from typing import Optional, Union
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditRepository:
    """Repository handling database operations for AuditLog entities."""

    async def add(
        self,
        session: Union[AsyncSession, Session],
        log_entry: AuditLog,
    ) -> AuditLog:
        """Add an AuditLog record to the active session and flush.

        Does not commit the session, preserving caller transaction boundaries.

        Args:
            session: Active database session (AsyncSession or Session).
            log_entry: AuditLog instance to persist.

        Returns:
            The flushed AuditLog instance.
        """
        session.add(log_entry)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return log_entry

    def add_sync(
        self,
        session: Session,
        log_entry: AuditLog,
    ) -> AuditLog:
        """Add an AuditLog record synchronously to the active session and flush."""
        session.add(log_entry)
        session.flush()
        return log_entry

    async def get_by_id(
        self,
        session: Union[AsyncSession, Session],
        log_id: Union[uuid.UUID, str],
    ) -> Optional[AuditLog]:
        """Retrieve an audit log entry by its primary key ID.

        Args:
            session: Active database session.
            log_id: UUID or UUID string.

        Returns:
            Matching AuditLog instance or None if not found.
        """
        parsed_id = uuid.UUID(str(log_id)) if not isinstance(log_id, uuid.UUID) else log_id
        stmt = select(AuditLog).where(AuditLog.id == parsed_id)
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            return session.scalar(stmt)

    async def list_logs(
        self,
        session: Union[AsyncSession, Session],
        *,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        actor_type: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Query audit log records with filtering, sorting, and pagination.

        Args:
            session: Active database session.
            actor_id: Optional actor UUID filter.
            actor_type: Optional actor persona filter (e.g. 'ADMIN', 'STUDENT').
            action: Optional action verb filter.
            resource_type: Optional entity type filter (e.g. 'course', 'enrollment').
            resource_id: Optional entity ID filter.
            request_id: Optional correlation request ID filter.
            start_date: Optional earliest creation timestamp (inclusive).
            end_date: Optional latest creation timestamp (inclusive).
            limit: Maximum records to return (default 50).
            offset: Number of records to skip (default 0).

        Returns:
            Tuple of (list of AuditLog entries, total matching count).
        """
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        # Apply filters
        if actor_id is not None:
            parsed_actor = uuid.UUID(str(actor_id)) if not isinstance(actor_id, uuid.UUID) else actor_id
            stmt = stmt.where(AuditLog.actor_id == parsed_actor)
            count_stmt = count_stmt.where(AuditLog.actor_id == parsed_actor)

        if actor_type is not None:
            stmt = stmt.where(AuditLog.actor_type == actor_type)
            count_stmt = count_stmt.where(AuditLog.actor_type == actor_type)

        if action is not None:
            clean_action = action.strip().upper()
            stmt = stmt.where(func.upper(AuditLog.action) == clean_action)
            count_stmt = count_stmt.where(func.upper(AuditLog.action) == clean_action)

        if resource_type is not None:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
            count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)

        if resource_id is not None:
            stmt = stmt.where(AuditLog.resource_id == str(resource_id))
            count_stmt = count_stmt.where(AuditLog.resource_id == str(resource_id))

        if request_id is not None:
            stmt = stmt.where(AuditLog.request_id == request_id)
            count_stmt = count_stmt.where(AuditLog.request_id == request_id)

        if ip_address is not None:
            clean_ip = ip_address.strip()
            stmt = stmt.where(AuditLog.ip_address == clean_ip)
            count_stmt = count_stmt.where(AuditLog.ip_address == clean_ip)

        if start_date is not None:
            stmt = stmt.where(AuditLog.created_at >= start_date)
            count_stmt = count_stmt.where(AuditLog.created_at >= start_date)

        if end_date is not None:
            stmt = stmt.where(AuditLog.created_at <= end_date)
            count_stmt = count_stmt.where(AuditLog.created_at <= end_date)

        # Ordering & pagination
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

        if isinstance(session, AsyncSession):
            total_count = (await session.execute(count_stmt)).scalar_one()
            results = (await session.execute(stmt)).scalars().all()
            return list(results), int(total_count)
        else:
            total_count = session.scalar(count_stmt) or 0
            results = session.scalars(stmt).all()
            return list(results), int(total_count)
