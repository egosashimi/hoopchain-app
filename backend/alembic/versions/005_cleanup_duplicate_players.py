"""Remove duplicate player entries that have no graph edges

Revision ID: 005
Revises: 004
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove Chet Holmgren duplicate (id=1631168, 0 edges — real node is 1631096 with 91 edges)
    op.execute(
        "DELETE FROM players WHERE id = '1631168' AND full_name ILIKE '%Holmgren%'"
    )


def downgrade() -> None:
    pass  # Data-only cleanup; cannot be meaningfully reversed
