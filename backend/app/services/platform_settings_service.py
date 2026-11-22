"""Domain service for Platform Information & Settings Management (SA-05.3).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 5)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md

Strict Invariants:
1. Master Secret Isolation: SECRET_KEY, DB passwords, Redis credentials,
   Razorpay secrets, and cloud storage keys are strictly never returned.
2. Changes to settings emit immutable audit logs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.audit_log import AuditLog
from app.models.platform_setting import (
    SETTING_KEY_BRANDING,
    SETTING_KEY_GENERAL,
    PlatformSetting,
)
from app.models.user import User
from app.repositories.platform_settings_repo import PlatformSettingsRepository
from app.schemas.settings import (
    PlatformSettingsUpdateRequest,
    PublicPlatformInfoResponse,
)

logger = logging.getLogger(__name__)


class PlatformSettingsService:
    """Domain service for Super Admin platform and branding configuration."""

    def __init__(
        self,
        repo: Optional[PlatformSettingsRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.repo = repo or PlatformSettingsRepository()
        self.settings = settings or get_settings()

    def get_public_platform_info(self, db: Session) -> PublicPlatformInfoResponse:
        """Retrieve safe public platform information and brand settings."""
        persisted = self.repo.get_all_settings(db)
        branding_data = persisted.get(SETTING_KEY_BRANDING, {})
        general_data = persisted.get(SETTING_KEY_GENERAL, {})

        # Merge environment defaults with persisted overrides
        platform_name = (
            general_data.get("platform_name")
            or branding_data.get("platform_name")
            or self.settings.PROJECT_NAME
        )
        brand_name = (
            branding_data.get("brand_name")
            or self.settings.EMAIL_FROM_NAME
            or "Single-Instructor LMS"
        )
        brand_description = (
            branding_data.get("brand_description")
            or self.settings.DESCRIPTION
        )
        support_email = general_data.get("support_email") or self.settings.EMAIL_FROM
        support_phone = general_data.get("support_phone") or None
        logo_url = branding_data.get("logo_url") or "/brand/logo.svg"

        # Timestamp of last update
        branding_row = self.repo.get_setting(db, SETTING_KEY_BRANDING)
        general_row = self.repo.get_setting(db, SETTING_KEY_GENERAL)
        last_updated = None
        if branding_row and general_row:
            last_updated = max(branding_row.updated_at, general_row.updated_at)
        elif branding_row:
            last_updated = branding_row.updated_at
        elif general_row:
            last_updated = general_row.updated_at

        return PublicPlatformInfoResponse(
            platform_name=platform_name,
            brand_name=brand_name,
            brand_description=brand_description,
            support_email=support_email,
            support_phone=support_phone,
            logo_url=logo_url,
            frontend_url=self.settings.FRONTEND_URL,
            cdn_stream_base_url=self.settings.CDN_STREAM_BASE_URL,
            version=self.settings.VERSION,
            environment=self.settings.ENVIRONMENT,
            currency="INR",
            email_provider=self.settings.EMAIL_PROVIDER,
            storage_provider=self.settings.STORAGE_PROVIDER,
            updated_at=last_updated,
        )

    def update_platform_settings(
        self,
        db: Session,
        current_user: User,
        data: PlatformSettingsUpdateRequest,
        *,
        ip_address: Optional[str] = None,
    ) -> PublicPlatformInfoResponse:
        """Update authorized platform and branding configuration with audit logging."""
        persisted = self.repo.get_all_settings(db)
        branding_data = dict(persisted.get(SETTING_KEY_BRANDING, {}))
        general_data = dict(persisted.get(SETTING_KEY_GENERAL, {}))

        before_state = {
            "platform_name": general_data.get("platform_name") or self.settings.PROJECT_NAME,
            "brand_name": branding_data.get("brand_name") or self.settings.EMAIL_FROM_NAME,
            "brand_description": branding_data.get("brand_description") or self.settings.DESCRIPTION,
            "support_email": general_data.get("support_email") or self.settings.EMAIL_FROM,
            "support_phone": general_data.get("support_phone"),
            "logo_url": branding_data.get("logo_url") or "/brand/logo.svg",
        }

        # Apply updates
        if data.platform_name is not None:
            general_data["platform_name"] = data.platform_name.strip()
            branding_data["platform_name"] = data.platform_name.strip()
        if data.brand_name is not None:
            branding_data["brand_name"] = data.brand_name.strip()
        if data.brand_description is not None:
            branding_data["brand_description"] = data.brand_description.strip()
        if data.support_email is not None:
            general_data["support_email"] = data.support_email.strip()
        if data.support_phone is not None:
            general_data["support_phone"] = data.support_phone.strip()
        if data.logo_url is not None:
            branding_data["logo_url"] = data.logo_url.strip()

        # Save settings groups
        self.repo.set_setting(db, SETTING_KEY_BRANDING, branding_data, current_user.id)
        self.repo.set_setting(db, SETTING_KEY_GENERAL, general_data, current_user.id)

        after_state = {
            "platform_name": general_data.get("platform_name"),
            "brand_name": branding_data.get("brand_name"),
            "brand_description": branding_data.get("brand_description"),
            "support_email": general_data.get("support_email"),
            "support_phone": general_data.get("support_phone"),
            "logo_url": branding_data.get("logo_url"),
        }

        # Audit Event
        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="PLATFORM_SETTINGS_UPDATED",
                resource_type="platform_settings",
                resource_id="platform",
                before_state=before_state,
                after_state=after_state,
                ip_address=ip_address,
            )
        )
        db.commit()

        return self.get_public_platform_info(db)
