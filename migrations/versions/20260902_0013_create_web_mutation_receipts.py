"""Create Web API mutation receipts.

Revision ID: 20260902_0013
Revises: 20260824_0012
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260902_0013"
down_revision: str | None = "20260824_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_mutation_receipts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column(
            "response_body_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "response_status >= 100 AND response_status <= 599",
            name="response_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_web_mutation_receipts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_web_mutation_receipts")),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "idempotency_key",
            name="uq_web_mutation_receipts_user_operation_key",
        ),
    )
    op.create_index(
        "ix_web_mutation_receipts_expires_at",
        "web_mutation_receipts",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_web_mutation_receipts_expires_at",
        table_name="web_mutation_receipts",
    )
    op.drop_table("web_mutation_receipts")
