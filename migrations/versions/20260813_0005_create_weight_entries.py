"""Create weight entries table.

Revision ID: 20260813_0005
Revises: 20260813_0004
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0005"
down_revision: str | None = "20260813_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weight_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
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
            "weight_kg >= 20 AND weight_kg <= 500",
            name="ck_weight_entries_weight_range",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weight_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weight_entries")),
    )
    op.create_index(
        "ix_weight_entries_user_id_measured_at",
        "weight_entries",
        ["user_id", sa.text("measured_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_weight_entries_user_id_measured_at",
        table_name="weight_entries",
    )
    op.drop_table("weight_entries")
