"""Add game mode support — available_modes on daily_puzzles, mode + is_freeplay on game_sessions

Revision ID: 004
Revises: 003
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add available_modes column to daily_puzzles
    op.add_column(
        "daily_puzzles",
        sa.Column("available_modes", postgresql.ARRAY(sa.String()), nullable=True),
    )

    # Add mode column to game_sessions (NOT NULL with server default)
    op.add_column(
        "game_sessions",
        sa.Column("mode", sa.String(20), server_default="classic", nullable=False),
    )

    # Add is_freeplay column to game_sessions
    op.add_column(
        "game_sessions",
        sa.Column("is_freeplay", sa.Boolean(), server_default="false", nullable=False),
    )

    # Drop old (puzzle_date, client_id) unique constraint
    op.drop_constraint("uq_session_puzzle_client", "game_sessions", type_="unique")

    # New constraint allows the same client to play the same puzzle in multiple modes
    op.create_unique_constraint(
        "uq_session_puzzle_client_mode",
        "game_sessions",
        ["puzzle_date", "client_id", "mode"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_session_puzzle_client_mode", "game_sessions", type_="unique")
    op.create_unique_constraint(
        "uq_session_puzzle_client", "game_sessions", ["puzzle_date", "client_id"]
    )
    op.drop_column("game_sessions", "is_freeplay")
    op.drop_column("game_sessions", "mode")
    op.drop_column("daily_puzzles", "available_modes")
