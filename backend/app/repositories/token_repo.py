"""AuthTokenRepository managing single-use cryptographic token persistence.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Table 3)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK103, TASK104, TASK106)

Strict Invariants:
1. Single-use guarantee: consume_token atomically marks is_used=True.
2. Token lookup: Queries by SHA-256 hex digest only; raw tokens never stored.
3. Expiration enforcement: get_valid_token enforces utc_now() < expires_at.
4. Token invalidation: Invalidation before generating new token for same user/purpose.
"""

from datetime import datetime
import logging
from typing import Optional, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.models.auth_token import AuthToken
from app.models.base import utc_now
from app.models.user import User

logger = logging.getLogger(__name__)


class AuthTokenRepository:
    """Repository handling database operations for AuthToken entities."""

    async def create_token(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        token_hash: str,
        token_type: str,
        expires_at: datetime,
    ) -> AuthToken:
        """Create and flush a single-use token record.

        Args:
            session: Active database session.
            user_id: Target user UUID.
            token_hash: SHA-256 hex digest of the raw token.
            token_type: Purpose identifier (e.g. EMAIL_VERIFICATION, PASSWORD_RESET).
            expires_at: UTC expiration timestamp.

        Returns:
            The flushed AuthToken instance.
        """
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        token = AuthToken(
            user_id=uid,
            token_hash=token_hash,
            token_type=token_type,
            expires_at=expires_at,
            is_used=False,
        )
        session.add(token)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        return token

    async def get_valid_token(
        self,
        session: Union[AsyncSession, Session],
        *,
        token_hash: str,
        token_type: str,
    ) -> Optional[AuthToken]:
        """Retrieve a token if it exists, matches type, is unused, and not expired."""
        now = utc_now()
        stmt = (
            select(AuthToken)
            .options(selectinload(AuthToken.user).selectinload(User.user_roles))
            .where(
                AuthToken.token_hash == token_hash,
                AuthToken.token_type == token_type,
                AuthToken.is_used.is_(False),
                AuthToken.expires_at > now,
            )
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

    async def get_by_hash(
        self,
        session: Union[AsyncSession, Session],
        token_hash: str,
        token_type: Optional[str] = None,
    ) -> Optional[AuthToken]:
        """Retrieve a token by its hash, with optional token_type filter."""
        conditions = [AuthToken.token_hash == token_hash]
        if token_type is not None:
            conditions.append(AuthToken.token_type == token_type)
        stmt = (
            select(AuthToken)
            .options(selectinload(AuthToken.user).selectinload(User.user_roles))
            .where(*conditions)
        )
        if isinstance(session, AsyncSession):
            result = await session.execute(stmt)
        else:
            result = session.execute(stmt)
        return result.scalars().first()

    async def consume_token(
        self,
        session: Union[AsyncSession, Session],
        token_id: Union[uuid.UUID, str],
    ) -> bool:
        """Atomically mark a token as used."""
        tid = uuid.UUID(str(token_id)) if not isinstance(token_id, uuid.UUID) else token_id
        stmt = (
            update(AuthToken)
            .where(
                AuthToken.id == tid,
                AuthToken.is_used.is_(False),
            )
            .values(is_used=True)
        )
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount > 0

    async def invalidate_user_tokens(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        token_type: Optional[str] = None,
    ) -> int:
        """Invalidate (mark used) any pending unused tokens for a user."""
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        conditions = [
            AuthToken.user_id == uid,
            AuthToken.is_used.is_(False),
        ]
        if token_type is not None:
            conditions.append(AuthToken.token_type == token_type)

        stmt = update(AuthToken).where(*conditions).values(is_used=True)
        if isinstance(session, AsyncSession):
            res = await session.execute(stmt)
            await session.flush()
        else:
            res = session.execute(stmt)
            session.flush()
        return res.rowcount
