"""Platform Settings repository for database-backed settings (SA-05.3).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 5)
- docs/backend/04-DATABASE-ARCHITECTURE.md
"""

from typing import Any, Dict, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.base import utc_now
from app.models.platform_setting import PlatformSetting


class PlatformSettingsRepository:
    """Persistence operations for platform-level and branding settings."""

    def get_setting(self, session: Session, key: str) -> Optional[PlatformSetting]:
        """Fetch setting record by key."""
        stmt = (
            select(PlatformSetting)
            .where(PlatformSetting.key == key)
            .options(joinedload(PlatformSetting.updater))
        )
        return session.execute(stmt).scalars().first()

    def set_setting(
        self,
        session: Session,
        key: str,
        value: dict[str, Any],
        updated_by_id: Optional[uuid.UUID] = None,
    ) -> PlatformSetting:
        """Insert or update setting group."""
        setting = self.get_setting(session, key)
        if setting:
            setting.value = value
            setting.updated_by_id = updated_by_id
            setting.updated_at = utc_now()
        else:
            setting = PlatformSetting(
                key=key,
                value=value,
                updated_by_id=updated_by_id,
            )
            session.add(setting)
        session.flush()
        return setting

    def get_all_settings(self, session: Session) -> Dict[str, dict[str, Any]]:
        """Return all persisted settings mapped by key."""
        stmt = select(PlatformSetting)
        records = session.execute(stmt).scalars().all()
        return {r.key: r.value for r in records}
