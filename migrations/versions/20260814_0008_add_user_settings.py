"""Add typed user settings.

Revision ID: 20260814_0008
Revises: 20260813_0007
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0008"
down_revision: str | None = "20260813_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "number_format",
            sa.String(length=16),
            server_default="automatic",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "after_food_add_action",
            sa.String(length=16),
            server_default="open_today",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_number_format",
        "users",
        "number_format IN ('automatic', 'one_decimal', 'two_decimals')",
    )
    op.create_check_constraint(
        "ck_users_after_food_add_action",
        "users",
        "after_food_add_action IN ('open_today', 'stay')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_after_food_add_action",
        "users",
        type_="check",
    )
    op.drop_constraint("ck_users_number_format", "users", type_="check")
    op.drop_column("users", "after_food_add_action")
    op.drop_column("users", "number_format")
