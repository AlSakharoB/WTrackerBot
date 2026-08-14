"""Create reminder settings.

Revision ID: 20260814_0010
Revises: 20260814_0009
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0010"
down_revision: str | None = "20260814_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

reminder_type = postgresql.ENUM(
    "weigh_in",
    "nutrition",
    name="reminder_type",
    create_type=False,
)


def upgrade() -> None:
    reminder_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "reminder_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reminder_type", reminder_type, nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("time_local", sa.Time(), nullable=False),
        sa.Column("weekdays_mask", sa.Integer(), nullable=False),
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
            "weekdays_mask >= 1 AND weekdays_mask <= 127",
            name="ck_reminder_settings_weekdays_mask",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reminder_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_settings")),
        sa.UniqueConstraint(
            "user_id",
            "reminder_type",
            name="uq_reminder_settings_user_id_reminder_type",
        ),
    )
    op.create_index(
        "ix_reminder_settings_enabled",
        "reminder_settings",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reminder_settings_enabled", table_name="reminder_settings")
    op.drop_table("reminder_settings")
    reminder_type.drop(op.get_bind(), checkfirst=True)
