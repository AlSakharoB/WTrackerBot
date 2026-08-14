"""Create nutrition goal history.

Revision ID: 20260814_0009
Revises: 20260814_0008
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0009"
down_revision: str | None = "20260814_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nutrition_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kcal_target", sa.Numeric(8, 2), nullable=True),
        sa.Column("protein_target_g", sa.Numeric(8, 2), nullable=True),
        sa.Column("fat_target_g", sa.Numeric(8, 2), nullable=True),
        sa.Column("carbs_target_g", sa.Numeric(8, 2), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
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
            "kcal_target IS NOT NULL OR protein_target_g IS NOT NULL OR "
            "fat_target_g IS NOT NULL OR carbs_target_g IS NOT NULL",
            name="ck_nutrition_goals_at_least_one_target",
        ),
        sa.CheckConstraint(
            "kcal_target IS NULL OR (kcal_target > 0 AND kcal_target <= 10000)",
            name="ck_nutrition_goals_kcal_range",
        ),
        sa.CheckConstraint(
            "protein_target_g IS NULL OR "
            "(protein_target_g > 0 AND protein_target_g <= 1000)",
            name="ck_nutrition_goals_protein_range",
        ),
        sa.CheckConstraint(
            "fat_target_g IS NULL OR (fat_target_g > 0 AND fat_target_g <= 1000)",
            name="ck_nutrition_goals_fat_range",
        ),
        sa.CheckConstraint(
            "carbs_target_g IS NULL OR (carbs_target_g > 0 AND carbs_target_g <= 2000)",
            name="ck_nutrition_goals_carbs_range",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_nutrition_goals_period",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_nutrition_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nutrition_goals")),
    )
    op.create_index(
        "ix_nutrition_goals_user_id_effective_from",
        "nutrition_goals",
        ["user_id", "effective_from"],
        unique=False,
    )
    op.create_index(
        "uq_nutrition_goals_one_open_per_user",
        "nutrition_goals",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_nutrition_goals_one_open_per_user",
        table_name="nutrition_goals",
    )
    op.drop_index(
        "ix_nutrition_goals_user_id_effective_from",
        table_name="nutrition_goals",
    )
    op.drop_table("nutrition_goals")
