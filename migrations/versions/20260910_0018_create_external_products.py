"""Create external product cache and ingredient source links.

Revision ID: 20260910_0018
Revises: 20260910_0017
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260910_0018"
down_revision: str | None = "20260910_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_product_cache",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column(
            "response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint(
            "provider", "barcode", name=op.f("pk_external_product_cache")
        ),
    )
    op.create_index(
        "ix_external_product_cache_expires_at",
        "external_product_cache",
        ["expires_at"],
    )
    op.create_table(
        "ingredient_external_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("ingredient_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_code", sa.String(length=64), nullable=False),
        sa.Column(
            "source_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
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
            ["user_id", "ingredient_id"],
            ["ingredients.user_id", "ingredients.id"],
            name="fk_ingredient_external_sources_user_ingredient",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredient_external_sources")),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "external_code",
            name="uq_ingredient_external_sources_user_provider_code",
        ),
    )


def downgrade() -> None:
    op.drop_table("ingredient_external_sources")
    op.drop_index(
        "ix_external_product_cache_expires_at", table_name="external_product_cache"
    )
    op.drop_table("external_product_cache")
