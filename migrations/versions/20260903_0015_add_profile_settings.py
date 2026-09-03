"""Add profile settings and account deletion requests.

Revision ID: 20260903_0015
Revises: 20260903_0014
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0015"
down_revision: str | None = "20260903_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "confirm_deletions",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_account_deletion_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_deletion_requests")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_account_deletion_requests_token_hash"),
        ),
        sa.UniqueConstraint(
            "user_id",
            name=op.f("uq_account_deletion_requests_user_id"),
        ),
    )
    op.create_index(
        op.f("ix_account_deletion_requests_expires_at"),
        "account_deletion_requests",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_account_deletion_requests_expires_at"),
        table_name="account_deletion_requests",
    )
    op.drop_table("account_deletion_requests")
    op.drop_column("users", "confirm_deletions")
