"""Add PostgreSQL fuzzy search infrastructure.

Revision ID: 20260813_0007
Revises: 20260813_0006
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0007"
down_revision: str | None = "20260813_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NORMALIZED_NAME_SQL = """
btrim(
    regexp_replace(
        replace(lower(name), 'ё', 'е'),
        '[^[:alnum:]]+',
        ' ',
        'g'
    )
)
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        sa.text(f"UPDATE ingredients SET name_normalized = {NORMALIZED_NAME_SQL}")
    )
    op.execute(sa.text(f"UPDATE dishes SET name_normalized = {NORMALIZED_NAME_SQL}"))
    op.create_index(
        "ix_ingredients_name_normalized_trgm",
        "ingredients",
        ["name_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_normalized": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_dishes_name_normalized_trgm",
        "dishes",
        ["name_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_normalized": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_dishes_name_normalized_trgm", table_name="dishes")
    op.drop_index("ix_ingredients_name_normalized_trgm", table_name="ingredients")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
