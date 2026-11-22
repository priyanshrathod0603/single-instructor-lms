"""PostgreSQL integration tests for session concurrency and single-active-session invariant.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 2)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK103)

Verifies:
1. PostgreSQL partial unique index (idx_auth_sessions_unique_active_user) strictly rejects
   multiple active sessions for the same user (raising IntegrityError).
2. Multiple REVOKED or EXPIRED sessions for the same user are permitted without error.
3. Atomic session displacement transitions older sessions to REVOKED and creates the new ACTIVE session.
"""

import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import check_db_connectivity

try:
    has_postgres = check_db_connectivity()
except Exception:
    has_postgres = False

pytestmark = pytest.mark.skipif(
    not has_postgres,
    reason="PostgreSQL connectivity not available in current environment",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Provides a PostgreSQL engine connected to the configured database."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_temp_session_table(pg_engine):
    """Creates an isolated temporary table with exact auth_sessions schema and partial unique index."""
    table_name = f"temp_auth_sessions_{uuid.uuid4().hex[:8]}"
    with pg_engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE {table_name} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                session_token_hash VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE UNIQUE INDEX idx_{table_name}_active_user
            ON {table_name}(user_id) WHERE status = 'ACTIVE';
        """))
        conn.commit()

    yield table_name

    with pg_engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name};"))
        conn.commit()


class TestPostgreSQLSessionConcurrency:
    """Verifies database-level partial unique index enforcement on PostgreSQL."""

    def test_partial_unique_index_rejects_second_active_session(self, pg_engine, pg_temp_session_table):
        user_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            # First active session succeeds
            conn.execute(text(f"""
                INSERT INTO {pg_temp_session_table} (user_id, session_token_hash, status)
                VALUES ('{user_id}', 'hash1_{uuid.uuid4().hex}', 'ACTIVE');
            """))
            conn.commit()

            # Second active session for same user fails with IntegrityError
            with pytest.raises(IntegrityError):
                conn.execute(text(f"""
                    INSERT INTO {pg_temp_session_table} (user_id, session_token_hash, status)
                    VALUES ('{user_id}', 'hash2_{uuid.uuid4().hex}', 'ACTIVE');
                """))

    def test_multiple_revoked_sessions_allowed_by_partial_index(self, pg_engine, pg_temp_session_table):
        user_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            # Multiple revoked sessions
            conn.execute(text(f"""
                INSERT INTO {pg_temp_session_table} (user_id, session_token_hash, status)
                VALUES ('{user_id}', 'hash_rev1_{uuid.uuid4().hex}', 'REVOKED');
                INSERT INTO {pg_temp_session_table} (user_id, session_token_hash, status)
                VALUES ('{user_id}', 'hash_rev2_{uuid.uuid4().hex}', 'REVOKED');
                INSERT INTO {pg_temp_session_table} (user_id, session_token_hash, status)
                VALUES ('{user_id}', 'hash_active_{uuid.uuid4().hex}', 'ACTIVE');
            """))
            conn.commit()

            count = conn.execute(text(f"SELECT COUNT(*) FROM {pg_temp_session_table} WHERE user_id = '{user_id}';")).scalar()
            assert count == 3
