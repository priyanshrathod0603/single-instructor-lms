"""add course metadata fields

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-26 22:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.base import UTCDateTime  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 1 course metadata, categorization, pricing, and thumbnail linkage columns."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("thumbnail_media_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "category",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'General'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "difficulty_level",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'ALL_LEVELS'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "language",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'English'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "learning_outcomes",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "requirements",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("compare_at_price_inr", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "currency",
                sa.String(length=3),
                nullable=False,
                server_default=sa.text("'INR'"),
            )
        )

        batch_op.create_index("ix_courses_category", ["category"], unique=False)
        batch_op.create_index("ix_courses_difficulty_level", ["difficulty_level"], unique=False)
        batch_op.create_index("ix_courses_language", ["language"], unique=False)
        batch_op.create_foreign_key(
            "fk_courses_thumbnail_media_id_media_assets",
            "media_assets",
            ["thumbnail_media_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint("ck_courses_price_non_negative", "price_inr >= 0")
        batch_op.create_check_constraint(
            "ck_courses_compare_at_price_positive",
            "compare_at_price_inr IS NULL OR compare_at_price_inr > 0",
        )
        batch_op.create_check_constraint(
            "ck_courses_compare_at_ge_price",
            "compare_at_price_inr IS NULL OR compare_at_price_inr >= price_inr",
        )
        batch_op.create_check_constraint(
            "ck_courses_free_zero_price",
            "NOT is_free OR (price_inr = 0 AND compare_at_price_inr IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_courses_difficulty_level",
            "difficulty_level IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'ALL_LEVELS')",
        )


def downgrade() -> None:
    """Revert Phase 1 course metadata columns, indexes, and constraints cleanly."""
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_constraint("ck_courses_difficulty_level", type_="check")
        batch_op.drop_constraint("ck_courses_free_zero_price", type_="check")
        batch_op.drop_constraint("ck_courses_compare_at_ge_price", type_="check")
        batch_op.drop_constraint("ck_courses_compare_at_price_positive", type_="check")
        batch_op.drop_constraint("ck_courses_price_non_negative", type_="check")
        batch_op.drop_constraint("fk_courses_thumbnail_media_id_media_assets", type_="foreignkey")
        batch_op.drop_index("ix_courses_language")
        batch_op.drop_index("ix_courses_difficulty_level")
        batch_op.drop_index("ix_courses_category")
        batch_op.drop_column("currency")
        batch_op.drop_column("compare_at_price_inr")
        batch_op.drop_column("requirements")
        batch_op.drop_column("learning_outcomes")
        batch_op.drop_column("language")
        batch_op.drop_column("difficulty_level")
        batch_op.drop_column("category")
        batch_op.drop_column("thumbnail_media_id")
