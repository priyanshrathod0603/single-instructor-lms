"""PostgreSQL integration tests for transactional outbox concurrency and locking.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Verifies:
1. PostgreSQL FOR UPDATE SKIP LOCKED provides complete row-level isolation between concurrent workers.
2. Multiple concurrent worker connections process disjoint event batches without duplication or race conditions.
3. PostgreSQL enforces unique constraint on dedupe_key.
4. All tests execute in isolated temporary/unlogged tables, guaranteeing zero destructive side effects on lms_db.
"""

import concurrent.futures
import threading
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import check_db_connectivity

# Determine if real PostgreSQL connectivity is available
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
def pg_temp_outbox_table(pg_engine):
    """Creates an isolated temporary table with the exact production outbox schema and indexes."""
    with pg_engine.connect() as conn:
        conn.execute(text("""
            CREATE TEMPORARY TABLE test_notification_outbox (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                event_type VARCHAR(64) NOT NULL,
                channel VARCHAR(16) DEFAULT 'EMAIL' NOT NULL,
                recipient VARCHAR(255) DEFAULT '' NOT NULL,
                subject VARCHAR(255),
                payload JSONB DEFAULT '{}'::jsonb NOT NULL,
                dedupe_key VARCHAR(128) UNIQUE,
                status VARCHAR(16) DEFAULT 'PENDING' NOT NULL,
                retry_count INTEGER DEFAULT 0 NOT NULL,
                max_retries INTEGER DEFAULT 5 NOT NULL,
                next_retry_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                processed_at TIMESTAMPTZ,
                last_error TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
            );
        """))
        conn.execute(text("""
            CREATE INDEX ix_test_outbox_polling 
            ON test_notification_outbox (status, next_retry_at, created_at);
        """))
        conn.commit()

        yield conn

        try:
            conn.execute(text("DROP TABLE IF EXISTS test_notification_outbox;"))
            conn.commit()
        except Exception:
            pass


class TestPostgreSQLOutboxConcurrency:
    """Verifies PostgreSQL-specific concurrency, row locks, and deduplication."""

    def test_dedupe_key_unique_constraint_enforced_by_postgresql(self, pg_temp_outbox_table):
        """PostgreSQL must reject duplicate dedupe_key inserts with IntegrityError."""
        conn = pg_temp_outbox_table

        # Insert first event
        conn.execute(text("""
            INSERT INTO test_notification_outbox (event_type, dedupe_key)
            VALUES ('AUTH_VERIFY_EMAIL', 'IDEMPOTENT_KEY_ABC');
        """))
        conn.commit()

        # Insert second event with identical dedupe_key
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO test_notification_outbox (event_type, dedupe_key)
                VALUES ('AUTH_VERIFY_EMAIL', 'IDEMPOTENT_KEY_ABC');
            """))
        conn.rollback()

    def test_postgresql_skip_locked_prevents_duplicate_claims(self, pg_engine):
        """Two concurrent connections polling with SKIP LOCKED must claim strictly disjoint sets of rows."""
        # Create unlogged test table so multiple connections can access it
        with pg_engine.connect() as setup_conn:
            setup_conn.execute(text("""
                CREATE UNLOGGED TABLE IF NOT EXISTS test_outbox_concurrency (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    event_type VARCHAR(64) NOT NULL,
                    status VARCHAR(16) DEFAULT 'PENDING' NOT NULL,
                    next_retry_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            """))
            # Insert 10 pending events
            for i in range(10):
                setup_conn.execute(text("""
                    INSERT INTO test_outbox_concurrency (event_type)
                    VALUES (:ev);
                """), {"ev": f"EVENT_{i}"})
            setup_conn.commit()

        conn1_claimed_ids = []
        conn2_claimed_ids = []
        barrier1 = threading.Barrier(2)
        barrier2 = threading.Barrier(2)

        def worker1():
            with pg_engine.connect() as conn1:
                # Select 5 rows with SKIP LOCKED within an active transaction
                trans = conn1.begin()
                res = conn1.execute(text("""
                    SELECT id FROM test_outbox_concurrency
                    WHERE status = 'PENDING' AND next_retry_at <= NOW()
                    ORDER BY created_at ASC
                    LIMIT 5
                    FOR UPDATE SKIP LOCKED;
                """))
                conn1_claimed_ids.extend([row[0] for row in res.fetchall()])

                # Synchronize with worker2: locks are now actively held!
                barrier1.wait()

                # Wait for worker2 to execute its query while worker1 holds the row locks
                barrier2.wait()
                trans.commit()

        def worker2():
            with pg_engine.connect() as conn2:
                # Wait until worker1 has acquired its row locks
                barrier1.wait()
                trans = conn2.begin()

                # Select next available 5 rows with SKIP LOCKED
                res = conn2.execute(text("""
                    SELECT id FROM test_outbox_concurrency
                    WHERE status = 'PENDING' AND next_retry_at <= NOW()
                    ORDER BY created_at ASC
                    LIMIT 5
                    FOR UPDATE SKIP LOCKED;
                """))
                conn2_claimed_ids.extend([row[0] for row in res.fetchall()])

                # Notify worker1 that query execution is finished
                barrier2.wait()
                trans.commit()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(worker1)
                f2 = executor.submit(worker2)
                f1.result()
                f2.result()

            assert len(conn1_claimed_ids) == 5
            assert len(conn2_claimed_ids) == 5

            # The sets of claimed IDs must have ZERO intersection
            intersection = set(conn1_claimed_ids).intersection(set(conn2_claimed_ids))
            assert len(intersection) == 0, f"Concurrent workers claimed overlapping events: {intersection}"

            # Total unique claimed events must be 10
            total_claimed = set(conn1_claimed_ids).union(set(conn2_claimed_ids))
            assert len(total_claimed) == 10

        finally:
            with pg_engine.connect() as cleanup_conn:
                cleanup_conn.execute(text("DROP TABLE IF EXISTS test_outbox_concurrency;"))
                cleanup_conn.commit()
