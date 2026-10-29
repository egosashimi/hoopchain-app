"""Add email_subscribers table

Revision ID: 006
Revises: 005
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_subscribers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_email_subscribers_email", "email_subscribers", ["email"])


def downgrade() -> None:
    op.drop_index("idx_email_subscribers_email", "email_subscribers")
    op.drop_table("email_subscribers")
