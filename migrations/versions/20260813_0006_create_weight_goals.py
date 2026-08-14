"""Create weight goals table.

Revision ID: 20260813_0006
Revises: 20260813_0005
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0006"
down_revision: str | None = "20260813_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

goal_status_enum = postgresql.ENUM(
    "active",
    "completed",
    "cancelled",
    name="goal_status",
    create_type=False,
)


def upgrade() -> None:
    goal_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "weight_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("start_weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column(
            "status",
            goal_status_enum,
            server_default="active",
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "target_weight_kg >= 20 AND target_weight_kg <= 500",
            name="ck_weight_goals_target_weight_range",
        ),
        sa.CheckConstraint(
            "start_weight_kg IS NULL OR "
            "(start_weight_kg >= 20 AND start_weight_kg <= 500)",
            name="ck_weight_goals_start_weight_range",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weight_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weight_goals")),
    )
    op.create_index(
        "ix_weight_goals_user_id_status",
        "weight_goals",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_weight_goals_one_active_per_user",
        "weight_goals",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_weight_goals_one_active_per_user",
        table_name="weight_goals",
    )
    op.drop_index(
        "ix_weight_goals_user_id_status",
        table_name="weight_goals",
    )
    op.drop_table("weight_goals")
    goal_status_enum.drop(op.get_bind(), checkfirst=True)
