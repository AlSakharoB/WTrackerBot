"""Add index for revoked share package cleanup.

Revision ID: 20260824_0012
Revises: 20260823_0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0012"
down_revision: str | None = "20260823_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_share_packages_status_revoked_at",
        "share_packages",
        ["status", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_share_packages_status_revoked_at",
        table_name="share_packages",
    )
