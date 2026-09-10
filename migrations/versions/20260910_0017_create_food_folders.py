"""Create food folders and folder item assignments.

Revision ID: 20260910_0017
Revises: 20260910_0016
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0017"
down_revision: str | None = "20260910_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ingredients_user_id_id", "ingredients", ["user_id", "id"]
    )
    op.create_unique_constraint("uq_dishes_user_id_id", "dishes", ["user_id", "id"])
    op.create_table(
        "food_folders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
            "sort_order >= 0", name="ck_food_folders_sort_order_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_food_folders_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_folders")),
        sa.UniqueConstraint("user_id", "id", name="uq_food_folders_user_id_id"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_food_folders_user_id_normalized_name",
        ),
        sa.UniqueConstraint(
            "user_id", "sort_order", name="uq_food_folders_user_id_sort_order"
        ),
    )
    op.create_table(
        "food_folder_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("folder_id", sa.BigInteger(), nullable=False),
        sa.Column("ingredient_id", sa.BigInteger()),
        sa.Column("dish_id", sa.BigInteger()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(ingredient_id IS NOT NULL) <> (dish_id IS NOT NULL)",
            name="ck_food_folder_items_exactly_one_food",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "dish_id"],
            ["dishes.user_id", "dishes.id"],
            name="fk_food_folder_items_user_dish",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "folder_id"],
            ["food_folders.user_id", "food_folders.id"],
            name="fk_food_folder_items_user_folder",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "ingredient_id"],
            ["ingredients.user_id", "ingredients.id"],
            name="fk_food_folder_items_user_ingredient",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_folder_items")),
    )
    op.create_index(
        "ix_food_folder_items_user_folder",
        "food_folder_items",
        ["user_id", "folder_id"],
    )
    op.create_index(
        "uq_food_folder_items_ingredient_id",
        "food_folder_items",
        ["ingredient_id"],
        unique=True,
        postgresql_where=sa.text("ingredient_id IS NOT NULL"),
    )
    op.create_index(
        "uq_food_folder_items_dish_id",
        "food_folder_items",
        ["dish_id"],
        unique=True,
        postgresql_where=sa.text("dish_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_food_folder_items_dish_id", table_name="food_folder_items")
    op.drop_index("uq_food_folder_items_ingredient_id", table_name="food_folder_items")
    op.drop_index("ix_food_folder_items_user_folder", table_name="food_folder_items")
    op.drop_table("food_folder_items")
    op.drop_table("food_folders")
    op.drop_constraint("uq_dishes_user_id_id", "dishes", type_="unique")
    op.drop_constraint("uq_ingredients_user_id_id", "ingredients", type_="unique")
