"""PlatformSetting SQLAlchemy 2.0 model for Commercial Governance (SA-05.3).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 5)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf

Strict Invariants:
1. Public & Safe Settings Only: Never store or return master secrets
   (SECRET_KEY, database, Redis, gateway keys, SMTP passwords).
2. Key Uniqueness: Each setting domain is mapped to a unique key (e.g. 'general', 'branding').
3. Structured Value: Typed JSON/JSONB dictionary.
4. Audit Trail: All updates require actor attribution via updated_by_id.
"""

from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    ForeignKey,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.models.user import User

SETTING_KEY_GENERAL = "general"
SETTING_KEY_BRANDING = "branding"


class PlatformSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Platform-level configuration and branding setting managed by Super Admin."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="Setting namespace key (e.g. 'general', 'branding')",
    )
    value: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=False,
        default=dict,
        doc="JSON document containing safe, validated setting values",
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Super Admin who last modified this setting group",
    )

    # Relationship
    updater: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<PlatformSetting key={self.key!r}>"
