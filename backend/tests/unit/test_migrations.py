"""Unit tests for Alembic migration pipeline configuration and metadata discovery.

Verifies:
1. alembic.ini loading, script_location resolution, and template options.
2. Settings-based database URL resolution with priority hierarchy:
   - Alembic -x argument (highest priority).
   - alembic.ini sqlalchemy.url override.
   - Pydantic Settings get_settings().DATABASE_URL (default single source of truth).
3. Metadata discovery wiring: Base.metadata, constraint naming conventions.
4. Offline SQL generation targeting PostgreSQL without live network connectivity.
5. Migration environment (env.py) importability and execution.
6. Safe autogenerate behavior: detects 0 upgrade operations when no domain tables exist.
7. Revision script template (script.py.mako) syntax and custom UTCDateTime imports.
"""

from configparser import ConfigParser
import io
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import MetaData

from app.core.config import get_settings
from app.models import Base
from app.models.base import POSTGRES_NAMING_CONVENTION

# Path references
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
SCRIPT_MAKO_PATH = MIGRATIONS_DIR / "script.py.mako"
ENV_PY_PATH = MIGRATIONS_DIR / "env.py"
VERSIONS_DIR = MIGRATIONS_DIR / "versions"


class TestAlembicConfigurationLoading:
    """Verifies that alembic.ini is present, well-formed, and points to the migration directory."""

    def test_alembic_ini_file_exists(self):
        """alembic.ini must exist in the backend root directory."""
        assert ALEMBIC_INI_PATH.is_file(), f"Expected alembic.ini at {ALEMBIC_INI_PATH}"

    def test_alembic_ini_structure(self):
        """alembic.ini must contain required sections and script_location."""
        parser = ConfigParser(interpolation=None)
        parser.read(str(ALEMBIC_INI_PATH))

        assert "alembic" in parser.sections()
        assert parser.has_option("alembic", "script_location")
        assert "%(here)s/migrations" in parser.get("alembic", "script_location")
        assert parser.has_option("alembic", "file_template")

    def test_script_directory_resolution(self):
        """Alembic ScriptDirectory must resolve the migrations directory correctly."""
        cfg = Config(str(ALEMBIC_INI_PATH))
        script = ScriptDirectory.from_config(cfg)

        assert script.dir == str(MIGRATIONS_DIR)
        assert Path(script.dir).is_dir()

    def test_versions_directory_exists(self):
        """The migrations/versions directory must exist and be tracked."""
        assert VERSIONS_DIR.is_dir(), f"Expected versions directory at {VERSIONS_DIR}"


class TestDatabaseURLResolution:
    """Verifies that Alembic resolves database URLs securely and dynamically."""

    def test_default_url_comes_from_pydantic_settings(self, monkeypatch):
        """When sqlalchemy.url is blank in alembic.ini, env.py must use Pydantic Settings."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+psycopg://test_user:test_pass@localhost:5432/test_settings_db",
        )
        get_settings.cache_clear()

        # Import get_database_url from migrations.env
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from migrations.env import get_database_url

        url = get_database_url()
        assert url == "postgresql+psycopg://test_user:test_pass@localhost:5432/test_settings_db"

    def test_url_override_via_config_main_option(self):
        """Explicitly setting sqlalchemy.url on Alembic Config must take precedence."""
        cfg = Config(str(ALEMBIC_INI_PATH))
        cfg.set_main_option("sqlalchemy.url", "sqlite:///:memory:")

        # Test resolution with config override
        cmd_url = cfg.get_main_option("sqlalchemy.url")
        assert cmd_url == "sqlite:///:memory:"

    def test_url_override_via_x_argument(self, monkeypatch):
        """Passing -x url=... must take precedence over settings."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from alembic import context
        from migrations import env

        cfg = Config(str(ALEMBIC_INI_PATH))
        monkeypatch.setattr(env, "config", cfg)

        # Simulate -x url=sqlite:///custom_override.db
        monkeypatch.setattr(
            context,
            "get_x_argument",
            lambda as_dictionary=True: {"url": "sqlite:///custom_override.db"},
        )

        resolved_url = env.get_database_url()
        assert resolved_url == "sqlite:///custom_override.db"

    def test_precedence_x_arg_over_main_option_and_settings(self, monkeypatch):
        """When -x url, main_option, and settings all exist, -x url must take precedence."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from alembic import context
        from migrations import env

        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/settings_db")
        get_settings.cache_clear()

        cfg = Config(str(ALEMBIC_INI_PATH))
        cfg.set_main_option("sqlalchemy.url", "sqlite:///main_option.db")
        monkeypatch.setattr(env, "config", cfg)

        monkeypatch.setattr(
            context,
            "get_x_argument",
            lambda as_dictionary=True: {"url": "sqlite:///x_arg.db"},
        )

        assert env.get_database_url() == "sqlite:///x_arg.db"

    def test_precedence_main_option_over_settings(self, monkeypatch):
        """When main_option and settings exist (no -x url), main_option must take precedence."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from alembic import context
        from migrations import env

        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/settings_db")
        get_settings.cache_clear()

        cfg = Config(str(ALEMBIC_INI_PATH))
        cfg.set_main_option("sqlalchemy.url", "sqlite:///main_option.db")
        monkeypatch.setattr(env, "config", cfg)

        monkeypatch.setattr(
            context,
            "get_x_argument",
            lambda as_dictionary=True: {},
        )

        assert env.get_database_url() == "sqlite:///main_option.db"

    def test_missing_or_empty_database_url_raises_clear_value_error(self, monkeypatch):
        """When DATABASE_URL is empty or unconfigured, get_database_url must fail clearly."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations import env
        from app.core import config as cfg_mod

        dummy_settings = cfg_mod.Settings.model_construct(DATABASE_URL="")
        monkeypatch.setattr(env, "config", None)
        monkeypatch.setattr(env, "get_settings", lambda: dummy_settings)

        with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
            env.get_database_url()

    def test_invalid_database_url_fails_cleanly_on_engine_creation(self):
        """Passing an unparseable database URL must raise SQLAlchemy ArgumentError."""
        from app.core.database import create_db_engine
        from sqlalchemy.exc import ArgumentError

        with pytest.raises(ArgumentError):
            create_db_engine("invalid_unparseable_url_without_scheme")


class TestIncludeObjectFilter:
    """Verifies that include_object isolates test fixtures without excluding domain tables."""

    def test_test_dummy_tables_are_excluded(self):
        """Tables prefixed specifically with test_dummy_ must be excluded from migrations."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object

        assert include_object(None, "test_dummy_items", "table", False, None) is False
        assert include_object(None, "test_dummy_records", "table", False, None) is False
        assert include_object(None, "test_dummy_simple", "table", False, None) is False

    def test_test_suite_models_are_excluded(self):
        """Models declared inside test suites (tests.*) must be excluded from migrations."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object

        # 'test_constrained_models' declared in test_base_model.py
        assert include_object(None, "test_constrained_models", "table", False, None) is False

    def test_legitimate_domain_tables_starting_with_test_are_included(self):
        """Legitimate educational domain tables starting with 'test_' must NOT be excluded."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object

        # Assessment / practice test domain tables
        assert include_object(None, "test_attempts", "table", False, None) is True
        assert include_object(None, "test_questions", "table", False, None) is True
        assert include_object(None, "test_series", "table", False, None) is True
        assert include_object(None, "tests", "table", False, None) is True

    def test_production_model_starting_with_test_is_included(self):
        """A model declared in app.models.* with a 'test_' table name must be included."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object
        from sqlalchemy.orm import Mapped, mapped_column

        # Simulate a domain model in app.models.assessments
        class AssessmentAttempt(Base):
            __tablename__ = "test_assessment_attempts"
            id: Mapped[int] = mapped_column(primary_key=True)

        AssessmentAttempt.__module__ = "app.models.assessments"

        try:
            assert include_object(None, "test_assessment_attempts", "table", False, None) is True
        finally:
            # Clean up the simulated model from metadata so it does not affect subsequent tests
            Base.metadata.remove(AssessmentAttempt.__table__)

    def test_production_tables_are_included(self):
        """Standard LMS production tables must be included."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object

        assert include_object(None, "users", "table", False, None) is True
        assert include_object(None, "courses", "table", False, None) is True
        assert include_object(None, "auth_sessions", "table", False, None) is True
        assert include_object(None, "quizzes", "table", False, None) is True
        assert include_object(None, "assignments", "table", False, None) is True

    def test_non_table_objects_on_test_tables_are_excluded(self):
        """Indexes and constraints associated with test tables must also be excluded."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object
        from sqlalchemy import Column, Index, String, Table

        test_table = Table("test_dummy_items", Base.metadata, Column("title", String(50)), extend_existing=True)
        test_index = Index("ix_test_dummy_title", test_table.c.title)

        assert include_object(test_index, "ix_test_dummy_title", "index", False, None) is False

    def test_non_table_objects_without_table_are_included(self):
        """Generic non-table objects without a bound table must be included."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations.env import include_object

        assert include_object(None, "some_schema", "schema", False, None) is True


class TestMetadataDiscovery:
    """Verifies that Alembic discovers Base.metadata and preserves PostgreSQL naming conventions."""

    def test_env_py_wires_base_metadata(self):
        """migrations/env.py must wire target_metadata to Base.metadata."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations import env

        assert env.target_metadata is Base.metadata
        assert isinstance(env.target_metadata, MetaData)

    def test_metadata_preserves_naming_conventions(self):
        """target_metadata must contain standard PostgreSQL constraint naming patterns."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations import env

        convention = env.target_metadata.naming_convention
        assert convention["ix"] == POSTGRES_NAMING_CONVENTION["ix"]
        assert convention["uq"] == POSTGRES_NAMING_CONVENTION["uq"]
        assert convention["ck"] == POSTGRES_NAMING_CONVENTION["ck"]
        assert convention["fk"] == POSTGRES_NAMING_CONVENTION["fk"]
        assert convention["pk"] == POSTGRES_NAMING_CONVENTION["pk"]

    def test_domain_tables_at_part3_curriculum(self):
        """At Part 3, target_metadata must contain approved foundation, auth, rbac, and curriculum tables."""
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from migrations import env

        # Foundation, Auth, RBAC, and Curriculum domain tables registered in Base.metadata
        domain_tables = []
        table_to_module = {m.local_table.name: m.class_.__module__ for m in Base.registry.mappers}
        for table_name in env.target_metadata.tables:
            mod = table_to_module.get(table_name, "")
            # Filter out models belonging to test modules or test fixture models
            if not (
                mod.startswith("tests.")
                or mod.startswith("test_")
                or table_name.startswith("test_dummy_")
                or table_name.startswith("test_constrained_")
            ):
                domain_tables.append(table_name)

        expected_tables = [
            "assignment_submissions",
            "assignments",
            "audit_logs",
            "auth_sessions",
            "auth_tokens",
            "blog_posts",
            "certificates",
            "course_progress_summaries",
            "course_revisions",
            "course_tags",
            "courses",
            "curriculum_lessons",
            "curriculum_sections",
            "enrollments",
            "grade_overrides",
            "lesson_progress",
            "lesson_resources",
            "media_assets",
            "media_transcode_jobs",
            "notes",
            "notification_outbox",
            "notifications",
            "offers",
            "orders",
            "payment_transactions",
            "permissions",
            "platform_settings",
            "quiz_answers",
            "quiz_attempts",
            "quiz_question_options",
            "quiz_questions",
            "quizzes",
            "refunds",
            "role_permissions",
            "roles",
            "rubric_criteria",
            "rubric_scores",
            "rubrics",
            "user_roles",
            "users",
        ]
        assert sorted(domain_tables) == sorted(expected_tables), f"Unexpected domain tables: {domain_tables}"


class TestOfflineMigrationSQLGeneration:
    """Verifies static SQL generation without network/database connectivity."""

    def test_offline_sql_generation_postgresql(self, capsys):
        """alembic upgrade head --sql must generate valid PostgreSQL static DDL."""
        cfg = Config(str(ALEMBIC_INI_PATH))
        command.upgrade(cfg, "head", sql=True)
        captured = capsys.readouterr()

        assert "BEGIN;" in captured.out
        assert "COMMIT;" in captured.out

    def test_offline_sql_generation_custom_url(self, capsys):
        """Offline SQL generation must accept explicit database dialect."""
        cfg = Config(str(ALEMBIC_INI_PATH))
        cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://test:test@localhost:5432/test_db")
        command.upgrade(cfg, "head", sql=True)
        captured = capsys.readouterr()

        assert "BEGIN;" in captured.out
        assert "COMMIT;" in captured.out


class TestAlembicCheckAndSafety:
    """Verifies alembic check behavior and safety guardrails."""

    def test_migration_upgrade_and_downgrade_lifecycle(self):
        """Migration scripts must cleanly execute upgrade and downgrade in isolated environments."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            cfg = Config(str(ALEMBIC_INI_PATH))
            cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp.name}")

            # Upgrade to head
            command.upgrade(cfg, "head")

            # Downgrade back to base
            command.downgrade(cfg, "base")

    def test_alembic_heads_tracks_active_migration(self):
        """Alembic must track exactly the single active migration head."""
        cfg = Config(str(ALEMBIC_INI_PATH))
        script = ScriptDirectory.from_config(cfg)

        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 head, found: {heads}"
        assert heads[0] == "f2a3b4c5d6e7"


class TestMigrationScriptTemplate:
    """Verifies script.py.mako revision template."""

    def test_script_mako_exists(self):
        """script.py.mako must exist in migrations directory."""
        assert SCRIPT_MAKO_PATH.is_file(), f"Expected script.py.mako at {SCRIPT_MAKO_PATH}"

    def test_script_mako_content_structure(self):
        """script.py.mako must define upgrade(), downgrade(), and import UTCDateTime."""
        content = SCRIPT_MAKO_PATH.read_text(encoding="utf-8")

        assert "from alembic import op" in content
        assert "import sqlalchemy as sa" in content
        assert "from app.models.base import UTCDateTime" in content
        assert "def upgrade() -> None:" in content
        assert "def downgrade() -> None:" in content
        assert "revision: str" in content
        assert "down_revision:" in content


class TestFutureModelDiscoverySimulation:
    """Verifies that Alembic's autogenerate detects tables, UUIDs, and UTCDateTime on future models."""

    def test_autogenerate_discovers_future_model_and_types(self):
        """Simulate adding a future model to metadata; verify Alembic autogenerates add_table."""
        import uuid
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from sqlalchemy import Column, String, Table, Uuid, create_engine, text
        from app.models.base import UTCDateTime

        test_metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)
        Table(
            "test_future_model",
            test_metadata,
            Column(
                "id",
                Uuid(as_uuid=True),
                primary_key=True,
                default=uuid.uuid4,
                server_default=text("gen_random_uuid()"),
            ),
            Column("name", String(50), nullable=False),
            Column("created_at", UTCDateTime, nullable=False),
        )

        test_engine = create_engine("sqlite:///:memory:")
        with test_engine.connect() as connection:
            migration_context = MigrationContext.configure(connection)
            diff = compare_metadata(migration_context, test_metadata)

            assert len(diff) == 1
            op_name, table = diff[0]
            assert op_name == "add_table"
            assert table.name == "test_future_model"
            col_names = [col.name for col in table.columns]
            assert "id" in col_names
            assert "name" in col_names
            assert "created_at" in col_names
        test_engine.dispose()
