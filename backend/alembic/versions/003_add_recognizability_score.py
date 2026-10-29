"""Add recognizability_score to players table

Revision ID: 003_add_recognizability_score
Revises: 002_drop_player_fk_from_daily_puzzles
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("recognizability_score", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_players_recognizability",
        "players",
        ["recognizability_score"],
    )


def downgrade() -> None:
    op.drop_index("idx_players_recognizability", table_name="players")
    op.drop_column("players", "recognizability_score")
