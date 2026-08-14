"""Create diary entries table.

Revision ID: 20260813_0004
Revises: 20260813_0003
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0004"
down_revision: str | None = "20260813_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

entry_type_enum = postgresql.ENUM(
    "ingredient",
    "dish",
    name="diary_entry_type",
    create_type=False,
)
meal_type_enum = postgresql.ENUM(
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "other",
    name="meal_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    entry_type_enum.create(bind, checkfirst=True)
    meal_type_enum.create(bind, checkfirst=True)
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_type", entry_type_enum, nullable=False),
        sa.Column("ingredient_id", sa.BigInteger(), nullable=True),
        sa.Column("dish_id", sa.BigInteger(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("grams", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "meal_type",
            meal_type_enum,
            server_default="other",
            nullable=False,
        ),
        sa.Column("kcal_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("protein_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("fat_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("carbs_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "grams > 0",
            name="ck_diary_entries_grams_positive",
        ),
        sa.CheckConstraint(
            "kcal_snapshot >= 0 AND protein_snapshot >= 0 "
            "AND fat_snapshot >= 0 AND carbs_snapshot >= 0",
            name="ck_diary_entries_snapshots_non_negative",
        ),
        sa.CheckConstraint(
            "(entry_type = 'ingredient' AND dish_id IS NULL) OR "
            "(entry_type = 'dish' AND ingredient_id IS NULL)",
            name="ck_diary_entries_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_diary_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_diary_entries_ingredient_id_ingredients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_diary_entries_dish_id_dishes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diary_entries")),
    )
    op.create_index(
        "ix_diary_entries_user_id_entry_date",
        "diary_entries",
        ["user_id", "entry_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_diary_entries_user_id_entry_date",
        table_name="diary_entries",
    )
    op.drop_table("diary_entries")
    meal_type_enum.drop(op.get_bind(), checkfirst=True)
    entry_type_enum.drop(op.get_bind(), checkfirst=True)
