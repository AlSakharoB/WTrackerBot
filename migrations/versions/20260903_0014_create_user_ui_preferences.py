"""Create user UI preferences.

Revision ID: 20260903_0014
Revises: 20260902_0013
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0014"
down_revision: str | None = "20260902_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ui_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "theme_mode",
            sa.String(length=16),
            server_default="system",
            nullable=False,
        ),
        sa.Column(
            "default_section",
            sa.String(length=16),
            server_default="ration",
            nullable=False,
        ),
        sa.Column(
            "default_weight_unit",
            sa.String(length=8),
            server_default="kg",
            nullable=False,
        ),
        sa.Column(
            "compact_lists",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "theme_mode IN ('system', 'light', 'dark')",
            name="theme_mode",
        ),
        sa.CheckConstraint(
            "default_section IN ('ration', 'food', 'weight', 'profile')",
            name="default_section",
        ),
        sa.CheckConstraint(
            "default_weight_unit IN ('kg')",
            name="weight_unit",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_ui_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_ui_preferences")),
    )


def downgrade() -> None:
    op.drop_table("user_ui_preferences")
