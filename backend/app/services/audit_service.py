"""AuditService orchestrating secure append-only audit trail operations.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 35)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK007)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-013)

Features:
1. Transactional auditing: Business mutation and audit log participate in the same database transaction.
2. Isolated security auditing: Critical security/auth failure events are committed in an independent transaction.
3. Automated request context extraction: Request ID (contextvar or header), IP address (IPv4/IPv6, X-Forwarded-For), and User-Agent (truncated).
4. Allowlisted entity snapshots: Restricts snapshots to declared domain attributes.
5. Recursive sensitive data scrubbing: Strips passwords, token hashes, credentials, cookies, and payment data.
6. Safe non-intrusive event creation: Explicit domain event recording without unrestricted global ORM hooks.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Set, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.core.logging import get_request_id, redact_sensitive_data
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.repositories.audit_repo import AuditRepository


# Default allowed attribute names per resource domain to prevent unrestricted state dumping
DEFAULT_ALLOWLISTED_SNAPSHOT_FIELDS: dict[str, frozenset[str]] = {
    "user": frozenset({"id", "email", "full_name", "phone", "role", "roles", "is_active", "is_verified", "created_at"}),
    "course": frozenset({"id", "slug", "title", "headline", "status", "price_inr", "is_free", "live_revision_id", "reason"}),
    "course_revision": frozenset({"id", "course_id", "revision_no", "status", "published_at"}),
    "enrollment": frozenset({"id", "student_id", "course_id", "order_id", "status", "granted_at", "expires_at"}),
    "order": frozenset({"id", "order_no", "student_id", "course_id", "amount_inr", "currency", "status"}),
    "payment_transaction": frozenset({"id", "order_id", "gateway", "razorpay_payment_id", "status", "amount_inr"}),
    "refund": frozenset({"id", "order_id", "amount_inr", "reason", "status", "approved_by"}),
    "assignment_submission": frozenset({"id", "assignment_id", "student_id", "attempt_no", "status", "final_score", "graded_by"}),
    "grade_override": frozenset({"id", "submission_id", "original_score", "overridden_score", "reason", "overridden_by"}),
    "quiz_attempt": frozenset({"id", "quiz_id", "student_id", "attempt_no", "score", "is_passed", "status"}),
    "auth_session": frozenset({"id", "user_id", "status", "expires_at", "created_at"}),
    "certificate": frozenset({"id", "certificate_no", "student_id", "course_id", "verification_hash", "issued_at"}),
    "media_asset": frozenset({"id", "uploader_id", "filename", "file_key", "bucket", "mime_type", "file_size_bytes", "status", "created_at"}),
}


class AuditService:
    """Domain service managing secure creation, context enrichment, and persistence of audit logs."""

    def __init__(self, repository: Optional[AuditRepository] = None) -> None:
        """Initialize AuditService with an AuditRepository."""
        self.repository = repository or AuditRepository()

    @staticmethod
    def extract_request_context(
        request: Optional[Any] = None,
        explicit_request_id: Optional[str] = None,
        explicit_ip: Optional[str] = None,
        explicit_ua: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract and sanitize Request ID, client IP, and User-Agent from execution context.

        Args:
            request: Optional Starlette/FastAPI Request object.
            explicit_request_id: Explicitly provided correlation ID overriding auto-detection.
            explicit_ip: Explicit client IP overriding auto-detection.
            explicit_ua: Explicit client User-Agent overriding auto-detection.

        Returns:
            Tuple of (resolved_request_id, resolved_ip_address, resolved_user_agent).
        """
        # 1. Resolve Request ID
        resolved_req_id = explicit_request_id
        if not resolved_req_id and request is not None:
            resolved_req_id = getattr(getattr(request, "state", None), "request_id", None)
            if not resolved_req_id and hasattr(request, "headers"):
                resolved_req_id = request.headers.get("x-request-id")
        if not resolved_req_id:
            resolved_req_id = get_request_id()

        # 2. Resolve Client IP
        resolved_ip = explicit_ip
        if not resolved_ip and request is not None:
            from app.core.network import get_trusted_client_ip
            resolved_ip = get_trusted_client_ip(request)

        if resolved_ip:
            resolved_ip = str(resolved_ip).strip()[:45]

        # 3. Resolve User-Agent
        resolved_ua = explicit_ua
        if not resolved_ua and request is not None and hasattr(request, "headers"):
            resolved_ua = request.headers.get("user-agent")

        if resolved_ua:
            resolved_ua = str(resolved_ua).strip()[:512]

        return resolved_req_id, resolved_ip, resolved_ua

    @staticmethod
    def sanitize_state_snapshot(
        state: Optional[Any],
        resource_type: Optional[str] = None,
        allowed_fields: Optional[Union[Set[str], frozenset[str]]] = None,
    ) -> Optional[dict[str, Any]]:
        """Filter and scrub entity snapshots prior to persistence.

        Guards against:
        - Unrestricted ORM model dumping.
        - Accidental persistence of passwords, tokens, cookies, or secrets.
        - Excess payload storage.

        Args:
            state: Dictionary, ORM model, or primitive snapshot.
            resource_type: Resource category for default allowlist lookup.
            allowed_fields: Explicit field allowlist overriding defaults.

        Returns:
            Sanitized dictionary or None if state is None.
        """
        if state is None:
            return None

        # If state is an ORM model instance, use defense-in-depth to_dict()
        if isinstance(state, Base) and hasattr(state, "to_dict"):
            state_dict = state.to_dict()
        elif isinstance(state, dict):
            state_dict = dict(state)
        else:
            state_dict = {"value": state}

        # Determine effective allowlist
        effective_allowlist = allowed_fields
        if effective_allowlist is None and resource_type:
            effective_allowlist = DEFAULT_ALLOWLISTED_SNAPSHOT_FIELDS.get(resource_type.lower())

        if effective_allowlist is not None:
            state_dict = {k: v for k, v in state_dict.items() if k in effective_allowlist}

        # Apply recursive sensitive-data redaction
        sanitized = redact_sensitive_data(state_dict)
        return sanitized if isinstance(sanitized, dict) else {"value": sanitized}

    async def record_event(
        self,
        session: Union[AsyncSession, Session],
        *,
        action: str,
        resource_type: str,
        resource_id: Optional[Union[str, uuid.UUID]] = None,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        actor_type: str = "SYSTEM",
        before_state: Optional[Any] = None,
        after_state: Optional[Any] = None,
        metadata: Optional[dict[str, Any]] = None,
        request: Optional[Any] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        allowed_snapshot_fields: Optional[Union[Set[str], frozenset[str]]] = None,
    ) -> AuditLog:
        """Record an audit event within the caller's active database transaction.

        Transactional guarantee: The audit log commits or rolls back together with
        the business operation.

        Args:
            session: Active database session (AsyncSession or Session).
            action: Canonical screaming snake_case verb (e.g. 'COURSE_PUBLISHED').
            resource_type: Target entity type (e.g. 'course', 'user').
            resource_id: Optional entity ID string or UUID.
            actor_id: Optional actor UUID or UUID string.
            actor_type: Actor persona (default 'SYSTEM').
            before_state: Entity state prior to mutation.
            after_state: Entity state following mutation.
            metadata: Contextual operational metadata.
            request: Optional Request object for automatic context extraction.
            request_id: Explicit correlation ID.
            ip_address: Explicit client IP address.
            user_agent: Explicit client user-agent string.
            allowed_snapshot_fields: Optional set of allowed snapshot keys.

        Returns:
            The flushed AuditLog instance.
        """
        # Context resolution
        req_id, ip, ua = self.extract_request_context(
            request=request,
            explicit_request_id=request_id,
            explicit_ip=ip_address,
            explicit_ua=user_agent,
        )

        # Actor ID parsing
        parsed_actor: Optional[uuid.UUID] = None
        if actor_id is not None:
            parsed_actor = uuid.UUID(str(actor_id)) if not isinstance(actor_id, uuid.UUID) else actor_id

        # Resource ID string normalization
        res_id_str = str(resource_id) if resource_id is not None else None

        # Sanitize state snapshots
        clean_before = self.sanitize_state_snapshot(
            state=before_state,
            resource_type=resource_type,
            allowed_fields=allowed_snapshot_fields,
        )
        clean_after = self.sanitize_state_snapshot(
            state=after_state,
            resource_type=resource_type,
            allowed_fields=allowed_snapshot_fields,
        )

        # Sanitize metadata
        clean_metadata: dict[str, Any] = {}
        if metadata:
            raw_redacted = redact_sensitive_data(metadata)
            if isinstance(raw_redacted, dict):
                clean_metadata = raw_redacted

        log_entry = AuditLog(
            actor_id=parsed_actor,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=res_id_str,
            before_state=clean_before,
            after_state=clean_after,
            metadata_=clean_metadata,
            request_id=req_id,
            ip_address=ip,
            user_agent=ua,
        )

        return await self.repository.add(session, log_entry)

    def record_sync_event(
        self,
        session: Session,
        *,
        action: str,
        resource_type: str,
        resource_id: Optional[Union[str, uuid.UUID]] = None,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        actor_type: str = "SYSTEM",
        before_state: Optional[Any] = None,
        after_state: Optional[Any] = None,
        metadata: Optional[dict[str, Any]] = None,
        request: Optional[Any] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        allowed_snapshot_fields: Optional[Union[Set[str], frozenset[str]]] = None,
    ) -> AuditLog:
        """Record an audit event synchronously within the caller's active database transaction."""
        req_id, ip, ua = self.extract_request_context(
            request=request,
            explicit_request_id=request_id,
            explicit_ip=ip_address,
            explicit_ua=user_agent,
        )

        parsed_actor: Optional[uuid.UUID] = None
        if actor_id is not None:
            parsed_actor = uuid.UUID(str(actor_id)) if not isinstance(actor_id, uuid.UUID) else actor_id

        res_id_str = str(resource_id) if resource_id is not None else None

        clean_before = self.sanitize_state_snapshot(
            state=before_state,
            resource_type=resource_type,
            allowed_fields=allowed_snapshot_fields,
        )
        clean_after = self.sanitize_state_snapshot(
            state=after_state,
            resource_type=resource_type,
            allowed_fields=allowed_snapshot_fields,
        )

        clean_metadata: dict[str, Any] = {}
        if metadata:
            raw_redacted = redact_sensitive_data(metadata)
            if isinstance(raw_redacted, dict):
                clean_metadata = raw_redacted

        log_entry = AuditLog(
            actor_id=parsed_actor,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=res_id_str,
            before_state=clean_before,
            after_state=clean_after,
            metadata_=clean_metadata,
            request_id=req_id,
            ip_address=ip,
            user_agent=ua,
        )

        return self.repository.add_sync(session, log_entry)

    async def record_isolated_event(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: Optional[Union[str, uuid.UUID]] = None,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        actor_type: str = "SYSTEM",
        before_state: Optional[Any] = None,
        after_state: Optional[Any] = None,
        metadata: Optional[dict[str, Any]] = None,
        request: Optional[Any] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        allowed_snapshot_fields: Optional[Union[Set[str], frozenset[str]]] = None,
        session_factory: Optional[Any] = None,
    ) -> AuditLog:
        """Record a security or operational event in an isolated independent transaction.

        Isolated guarantee: Persists permanently even if the caller's main request
        transaction encounters an exception or rolls back.

        Args:
            action: Canonical screaming snake_case verb (e.g. 'AUTH_LOGIN_FAILED').
            resource_type: Target entity type.
            resource_id: Optional entity ID.
            actor_id: Optional actor UUID.
            actor_type: Actor persona (default 'SYSTEM').
            before_state: Entity state prior to mutation.
            after_state: Entity state following mutation.
            metadata: Contextual operational metadata.
            request: Optional Request object.
            request_id: Explicit correlation ID.
            ip_address: Explicit client IP.
            user_agent: Explicit client user agent.
            allowed_snapshot_fields: Optional set of allowed snapshot keys.
            session_factory: Optional session factory override for testing.

        Returns:
            The committed AuditLog instance.
        """
        factory = session_factory or db_module.AsyncSessionLocal or db_module.SessionLocal
        if factory is None:
            raise RuntimeError("Database session factory is not configured for isolated audit logging.")

        isolated_session = factory()
        try:
            if isinstance(isolated_session, AsyncSession):
                async with isolated_session.begin():
                    log = await self.record_event(
                        session=isolated_session,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        actor_id=actor_id,
                        actor_type=actor_type,
                        before_state=before_state,
                        after_state=after_state,
                        metadata=metadata,
                        request=request,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        allowed_snapshot_fields=allowed_snapshot_fields,
                    )
                return log
            else:
                with isolated_session.begin():
                    log = await self.record_event(
                        session=isolated_session,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        actor_id=actor_id,
                        actor_type=actor_type,
                        before_state=before_state,
                        after_state=after_state,
                        metadata=metadata,
                        request=request,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        allowed_snapshot_fields=allowed_snapshot_fields,
                    )
                return log
        finally:
            if isinstance(isolated_session, AsyncSession):
                await isolated_session.close()
            else:
                isolated_session.close()
