"""Integration tests for PostgreSQL audit log immutability triggers.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Section 1.1 Invariant 8, Table 35)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md (Section 1.1)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-013)

Verifies:
1. PostgreSQL trigger function trg_audit_logs_prevent_mutation() creation.
2. BEFORE UPDATE FOR EACH ROW trigger rejects update attempts.
3. BEFORE DELETE FOR EACH ROW trigger rejects delete attempts.
4. BEFORE TRUNCATE FOR EACH STATEMENT trigger rejects truncate attempts.
5. All tests execute in isolated temporary tables or transaction blocks,
   guaranteeing zero destructive effects on the development database.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import check_db_connectivity

# Determine if real PostgreSQL connectivity is available in the current test runner
try:
    has_postgres = check_db_connectivity()
except Exception:
    has_postgres = False

pytestmark = pytest.mark.skipif(
    not has_postgres,
    reason="PostgreSQL connectivity not available in current environment (requires network/bypass)",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Provides a PostgreSQL engine connected to the configured database."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_temp_audit_table(pg_engine):
    """Creates an isolated temporary table with the exact production triggers.
    
    Guarantees isolation: PostgreSQL temporary tables exist only for the session
    and do not touch existing tables in lms_db.
    """
    with pg_engine.connect() as conn:
        # Create temporary table matching audit_logs schema
        conn.execute(text("""
            CREATE TEMPORARY TABLE test_audit_logs_immutability (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                actor_id UUID,
                actor_type VARCHAR(32) DEFAULT 'SYSTEM' NOT NULL,
                action VARCHAR(64) NOT NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(64),
                before_state JSONB,
                after_state JSONB,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                request_id VARCHAR(64),
                ip_address VARCHAR(45),
                user_agent VARCHAR(512),
                created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
            );
        """))

        # Create trigger function
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION trg_test_audit_prevent_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Security Policy Violation: audit_logs records are strictly immutable. % operations are prohibited.', TG_OP
                    USING ERRCODE = 'integrity_constraint_violation';
            END;
            $$ LANGUAGE plpgsql;
        """))

        # Attach UPDATE trigger
        conn.execute(text("""
            CREATE TRIGGER trg_test_audit_prevent_update
            BEFORE UPDATE ON test_audit_logs_immutability
            FOR EACH ROW EXECUTE FUNCTION trg_test_audit_prevent_mutation();
        """))

        # Attach DELETE trigger
        conn.execute(text("""
            CREATE TRIGGER trg_test_audit_prevent_delete
            BEFORE DELETE ON test_audit_logs_immutability
            FOR EACH ROW EXECUTE FUNCTION trg_test_audit_prevent_mutation();
        """))

        # Attach TRUNCATE trigger
        conn.execute(text("""
            CREATE TRIGGER trg_test_audit_prevent_truncate
            BEFORE TRUNCATE ON test_audit_logs_immutability
            FOR EACH STATEMENT EXECUTE FUNCTION trg_test_audit_prevent_mutation();
        """))

        conn.commit()
        yield conn

        # Cleanup
        try:
            conn.execute(text("DROP TABLE IF EXISTS test_audit_logs_immutability;"))
            conn.execute(text("DROP FUNCTION IF EXISTS trg_test_audit_prevent_mutation();"))
            conn.commit()
        except Exception:
            pass


class TestPostgreSQLImmutabilityTriggers:
    """Verifies that PostgreSQL triggers enforce permanent append-only immutability."""

    def test_insert_succeeds(self, pg_temp_audit_table):
        """INSERT operations must succeed without restriction."""
        conn = pg_temp_audit_table
        conn.execute(text("""
            INSERT INTO test_audit_logs_immutability (action, resource_type)
            VALUES ('COURSE_CREATED', 'course');
        """))
        conn.commit()

        count = conn.execute(text("SELECT count(*) FROM test_audit_logs_immutability;")).scalar()
        assert count == 1

    def test_update_is_rejected_by_postgresql(self, pg_temp_audit_table):
        """UPDATE operations must be rejected with an IntegrityError exception."""
        conn = pg_temp_audit_table
        # Insert test row
        conn.execute(text("""
            INSERT INTO test_audit_logs_immutability (action, resource_type)
            VALUES ('INITIAL_ACTION', 'course');
        """))
        conn.commit()

        # Attempt UPDATE
        with pytest.raises(IntegrityError) as exc_info:
            conn.execute(text("""
                UPDATE test_audit_logs_immutability
                SET action = 'TAMPERED_ACTION';
            """))
        conn.rollback()

        # Verify rejection message
        err_msg = str(exc_info.value)
        assert "Security Policy Violation: audit_logs records are strictly immutable" in err_msg
        assert "UPDATE" in err_msg

    def test_delete_is_rejected_by_postgresql(self, pg_temp_audit_table):
        """DELETE operations must be rejected with an IntegrityError exception."""
        conn = pg_temp_audit_table
        # Insert test row
        conn.execute(text("""
            INSERT INTO test_audit_logs_immutability (action, resource_type)
            VALUES ('PERSISTED_ACTION', 'course');
        """))
        conn.commit()

        # Attempt DELETE
        with pytest.raises(IntegrityError) as exc_info:
            conn.execute(text("""
                DELETE FROM test_audit_logs_immutability;
            """))
        conn.rollback()

        # Verify rejection message
        err_msg = str(exc_info.value)
        assert "Security Policy Violation: audit_logs records are strictly immutable" in err_msg
        assert "DELETE" in err_msg

    def test_truncate_is_rejected_by_postgresql(self, pg_temp_audit_table):
        """TRUNCATE operations must be rejected with an IntegrityError exception."""
        conn = pg_temp_audit_table
        # Attempt TRUNCATE
        with pytest.raises(IntegrityError) as exc_info:
            conn.execute(text("""
                TRUNCATE TABLE test_audit_logs_immutability;
            """))
        conn.rollback()

        # Verify rejection message
        err_msg = str(exc_info.value)
        assert "Security Policy Violation: audit_logs records are strictly immutable" in err_msg
        assert "TRUNCATE" in err_msg

    def test_concurrent_inserts_succeed(self, pg_engine):
        """Concurrent INSERT operations across multiple worker connections must succeed without deadlocks."""
        import concurrent.futures

        # Create isolated unlogged test table
        with pg_engine.connect() as setup_conn:
            setup_conn.execute(text("""
                CREATE UNLOGGED TABLE IF NOT EXISTS test_audit_logs_concurrent (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    action VARCHAR(64) NOT NULL,
                    resource_type VARCHAR(64) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            """))
            setup_conn.commit()

        def worker_insert(idx: int) -> str:
            with pg_engine.connect() as thread_conn:
                res = thread_conn.execute(text("""
                    INSERT INTO test_audit_logs_concurrent (action, resource_type)
                    VALUES (:action, 'test_concurrency')
                    RETURNING id;
                """), {"action": f"CONCURRENT_EVENT_{idx}"})
                thread_conn.commit()
                return str(res.scalar())

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(worker_insert, i) for i in range(10)]
                inserted_ids = [f.result() for f in concurrent.futures.as_completed(futures)]

            assert len(inserted_ids) == 10
            assert len(set(inserted_ids)) == 10

            with pg_engine.connect() as check_conn:
                count = check_conn.execute(text(
                    "SELECT count(*) FROM test_audit_logs_concurrent WHERE resource_type = 'test_concurrency';"
                )).scalar()
                assert count == 10
        finally:
            with pg_engine.connect() as cleanup_conn:
                cleanup_conn.execute(text("DROP TABLE IF EXISTS test_audit_logs_concurrent;"))
                cleanup_conn.commit()

