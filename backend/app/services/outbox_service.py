"""OutboxService orchestrating transactional outbox event publishing.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Features:
1. Transactional staging: Events are inserted into notification_outbox within the caller's
   active database transaction and flushed without committing.
2. Idempotent dispatch: If an event with the supplied dedupe_key already exists,
   returns the existing event without re-inserting or raising a duplicate key error.
3. Strict payload validation: Ensures event payloads are valid, JSON-serializable dictionaries.
4. Channel validation: Enforces approved delivery channels (EMAIL, IN_APP, WEBHOOK).
5. Automated correlation: Enriches outgoing event metadata with the active request_id.
"""

import json
import logging
from typing import Any, Optional, Union
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationException
from app.core.logging import get_request_id
from app.models.notification import (
    OUTBOX_CHANNEL_EMAIL,
    VALID_OUTBOX_CHANNELS,
    NotificationOutbox,
    OutboxEvent,
)
from app.repositories.notification_repo import (
    NotificationOutboxRepository,
    OutboxRepository,
)

logger = logging.getLogger(__name__)


class OutboxService:
    """Service managing transactional event creation and idempotency enforcement."""

    def __init__(self, repository: Optional[NotificationOutboxRepository] = None) -> None:
        """Initialize OutboxService with an outbox repository."""
        self.repository = repository or NotificationOutboxRepository()

    @staticmethod
    def validate_payload(payload: Any) -> dict[str, Any]:
        """Validate that the event payload is a valid, JSON-serializable dictionary.

        Args:
            payload: Input payload data.

        Returns:
            Validated payload dictionary.

        Raises:
            ValidationException: If payload is not a dict or cannot be serialized to JSON.
        """
        if not isinstance(payload, dict):
            raise ValidationException(
                message="Outbox event payload must be a JSON dictionary.",
                details={"provided_type": type(payload).__name__},
            )

        try:
            # Verify JSON serializability
            json.dumps(payload, default=str)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValidationException(
                message="Outbox event payload contains non-JSON-serializable data.",
                details={"error": str(exc)},
            ) from exc

        return payload

    async def publish_event(
        self,
        session: Union[AsyncSession, Session],
        *,
        event_type: str,
        payload: dict[str, Any],
        channel: str = OUTBOX_CHANNEL_EMAIL,
        recipient: str = "",
        subject: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        max_retries: int = 5,
        request_id: Optional[str] = None,
    ) -> NotificationOutbox:
        """Stage an outbox event within the caller's active database transaction.

        Transactional guarantee: The outbox event commits or rolls back atomically
        with the surrounding business operation.

        Idempotency guarantee: If dedupe_key is provided and an event with that key
        already exists in the database, the existing event is returned without
        duplication or unique constraint violation.

        Args:
            session: Active database session (AsyncSession or Session).
            event_type: Canonical event name (e.g. 'AUTH_VERIFY_EMAIL', 'ORDER_CREATED').
            payload: Structured event payload containing template variables.
            channel: Target delivery channel ('EMAIL', 'IN_APP', 'WEBHOOK').
            recipient: Recipient email address, user ID string, or endpoint URL.
            subject: Optional subject line or message title.
            dedupe_key: Optional deterministic key to prevent duplicate event dispatch.
            max_retries: Maximum number of delivery attempts before dead-lettering.
            request_id: Optional explicit correlation ID (defaults to active contextvar).

        Returns:
            The staged NotificationOutbox instance.

        Raises:
            ValidationException: On invalid event_type, channel, or payload.
        """
        # 1. Validate event_type
        if not event_type or not isinstance(event_type, str) or not event_type.strip():
            raise ValidationException(
                message="event_type must be a non-empty string.",
                details={"provided_event_type": event_type},
            )
        clean_event_type = event_type.strip().upper()

        # 2. Validate channel
        clean_channel = (channel or OUTBOX_CHANNEL_EMAIL).strip().upper()
        if clean_channel not in VALID_OUTBOX_CHANNELS:
            raise ValidationException(
                message=f"Invalid delivery channel '{channel}'. Allowed channels: {sorted(VALID_OUTBOX_CHANNELS)}",
                details={"provided_channel": channel, "allowed_channels": list(VALID_OUTBOX_CHANNELS)},
            )

        # 3. Validate payload
        clean_payload = self.validate_payload(payload)

        # 4. Check idempotency if dedupe_key provided
        clean_dedupe_key: Optional[str] = None
        if dedupe_key:
            clean_dedupe_key = str(dedupe_key).strip()
            if clean_dedupe_key:
                existing_event = await self.repository.get_by_dedupe_key(session, clean_dedupe_key)
                if existing_event:
                    logger.info(
                        "Outbox event with dedupe_key=%r already exists (id=%s). Returning existing event.",
                        clean_dedupe_key,
                        existing_event.id,
                    )
                    return existing_event

        # 5. Enrich payload with correlation ID if not present
        resolved_req_id = request_id or get_request_id()
        if resolved_req_id and "_request_id" not in clean_payload:
            clean_payload = {**clean_payload, "_request_id": resolved_req_id}

        # 6. Instantiate and stage event
        event = NotificationOutbox(
            event_type=clean_event_type,
            channel=clean_channel,
            recipient=str(recipient).strip() if recipient else "",
            subject=str(subject).strip() if subject else None,
            payload=clean_payload,
            dedupe_key=clean_dedupe_key,
            max_retries=max(1, max_retries),
        )

        staged_event = await self.repository.add(session, event)
        logger.debug(
            "Staged outbox event %s [%s] for recipient %r in active transaction.",
            staged_event.id,
            staged_event.event_type,
            staged_event.recipient,
        )
        return staged_event


# Canonical aliases
NotificationService = OutboxService
