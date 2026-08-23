"""Create sharing tables.

Revision ID: 20260823_0011
Revises: 20260814_0010
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0011"
down_revision: str | None = "20260814_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "share_packages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("package_type", sa.String(length=16), nullable=False),
        sa.Column("payload_version", sa.SmallInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "item_count >= 1",
            name="ck_share_packages_item_count",
        ),
        sa.CheckConstraint(
            "package_type IN ('ingredients', 'dishes')",
            name="ck_share_packages_package_type",
        ),
        sa.CheckConstraint(
            "payload_version >= 1",
            name="ck_share_packages_payload_version",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_share_packages_revoked_at",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_share_packages_status",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_share_packages_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_packages")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_share_packages_token_hash"),
        ),
    )
    op.create_index(
        "ix_share_packages_owner_created_at",
        "share_packages",
        ["owner_user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_share_packages_status_expires_at",
        "share_packages",
        ["status", "expires_at"],
        unique=False,
    )

    op.create_table(
        "share_imports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("package_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_ingredients_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "reused_ingredients_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "skipped_ingredients_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_dishes_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "skipped_dishes_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'processing' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_share_imports_completed_at",
        ),
        sa.CheckConstraint(
            "created_ingredients_count >= 0 AND "
            "reused_ingredients_count >= 0 AND "
            "skipped_ingredients_count >= 0 AND "
            "created_dishes_count >= 0 AND "
            "skipped_dishes_count >= 0",
            name="ck_share_imports_counts",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_share_imports_status",
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["share_packages.id"],
            name=op.f("fk_share_imports_package_id_share_packages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_share_imports_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_imports")),
        sa.UniqueConstraint(
            "package_id",
            "recipient_user_id",
            name="uq_share_imports_package_id_recipient_user_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("share_imports")
    op.drop_index(
        "ix_share_packages_status_expires_at",
        table_name="share_packages",
    )
    op.drop_index(
        "ix_share_packages_owner_created_at",
        table_name="share_packages",
    )
    op.drop_table("share_packages")
