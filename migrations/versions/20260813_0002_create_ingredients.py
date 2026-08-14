"""Create ingredients table.

Revision ID: 20260813_0002
Revises: 20260813_0001
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredients",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_normalized", sa.String(length=255), nullable=False),
        sa.Column("kcal_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("protein_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fat_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("carbs_per_100g", sa.Numeric(8, 2), nullable=False),
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
            name=op.f("fk_ingredients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredients")),
        sa.UniqueConstraint(
            "user_id",
            "name_normalized",
            name="uq_ingredients_user_id_name_normalized",
        ),
    )


def downgrade() -> None:
    op.drop_table("ingredients")
