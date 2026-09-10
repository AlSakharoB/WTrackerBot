"""Add optional ingredient package and source metadata.

Revision ID: 20260910_0016
Revises: 20260903_0015
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0016"
down_revision: str | None = "20260903_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingredients",
        sa.Column("package_weight_g", sa.Numeric(precision=10, scale=2)),
    )
    op.add_column("ingredients", sa.Column("photo_url", sa.String(length=2048)))
    op.add_column("ingredients", sa.Column("source_name", sa.String(length=100)))
    op.add_column("ingredients", sa.Column("source_url", sa.String(length=2048)))


def downgrade() -> None:
    op.drop_column("ingredients", "source_url")
    op.drop_column("ingredients", "source_name")
    op.drop_column("ingredients", "photo_url")
    op.drop_column("ingredients", "package_weight_g")
