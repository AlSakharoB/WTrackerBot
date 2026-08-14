"""Create dishes and dish ingredients tables.

Revision ID: 20260813_0003
Revises: 20260813_0002
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0003"
down_revision: str | None = "20260813_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dishes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_normalized", sa.String(length=255), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_dishes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dishes")),
        sa.UniqueConstraint(
            "user_id",
            "name_normalized",
            name="uq_dishes_user_id_name_normalized",
        ),
    )
    op.create_table(
        "dish_ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("dish_id", sa.BigInteger(), nullable=False),
        sa.Column("ingredient_id", sa.BigInteger(), nullable=False),
        sa.Column("grams", sa.Numeric(10, 2), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["dish_id"],
            ["dishes.id"],
            name=op.f("fk_dish_ingredients_dish_id_dishes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_dish_ingredients_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dish_ingredients")),
        sa.UniqueConstraint(
            "dish_id",
            "ingredient_id",
            name="uq_dish_ingredients_dish_id_ingredient_id",
        ),
    )
    op.create_index(
        op.f("ix_dish_ingredients_ingredient_id"),
        "dish_ingredients",
        ["ingredient_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dish_ingredients_ingredient_id"),
        table_name="dish_ingredients",
    )
    op.drop_table("dish_ingredients")
    op.drop_table("dishes")
