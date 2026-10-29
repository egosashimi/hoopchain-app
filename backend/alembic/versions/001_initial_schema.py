"""Initial schema — all Hoopchain tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # ---- players ----
    op.create_table(
        "players",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(50)),
        sa.Column("last_name", sa.String(50)),
        sa.Column("college", sa.String(100)),
        sa.Column("draft_year", sa.Integer()),
        sa.Column("draft_round", sa.Integer()),
        sa.Column("draft_number", sa.Integer()),
        sa.Column("position", sa.String(10)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("country", sa.String(50)),
        sa.Column("is_active", sa.Boolean(), server_default="false"),
        sa.Column("headshot_url", sa.String(255)),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_players_search_vector", "players", ["search_vector"],
                    postgresql_using="gin")
    op.create_index("idx_players_full_name_trgm", "players", ["full_name"],
                    postgresql_using="gin",
                    postgresql_ops={"full_name": "gin_trgm_ops"})

    # ---- teams ----
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("abbreviation", sa.String(5), nullable=False),
        sa.Column("nickname", sa.String(50)),
        sa.Column("city", sa.String(50)),
        sa.Column("conference", sa.String(10)),
        sa.Column("division", sa.String(20)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    # ---- player_seasons ----
    op.create_table(
        "player_seasons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("games_played", sa.Integer()),
        sa.UniqueConstraint("player_id", "team_id", "season", name="uq_player_team_season"),
    )
    op.create_index("idx_ps_player_id", "player_seasons", ["player_id"])
    op.create_index("idx_ps_team_season", "player_seasons", ["team_id", "season"])

    # ---- coaches ----
    op.create_table(
        "coaches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("bref_id", sa.String(50), unique=True),
    )

    # ---- coach_seasons ----
    op.create_table(
        "coach_seasons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), server_default="head_coach"),
        sa.UniqueConstraint("coach_id", "team_id", "season", name="uq_coach_team_season"),
    )

    # ---- graph_edges ----
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_a_type", sa.String(20), nullable=False),
        sa.Column("node_a_id", sa.String(30), nullable=False),
        sa.Column("node_b_type", sa.String(20), nullable=False),
        sa.Column("node_b_id", sa.String(30), nullable=False),
        sa.Column("edge_type", sa.String(30), nullable=False),
        sa.Column("edge_label", sa.String(200)),
        sa.Column("weight", sa.Float(), server_default="1.0"),
        sa.Column("metadata", postgresql.JSONB()),
    )
    op.create_index("idx_graph_edges_a", "graph_edges", ["node_a_type", "node_a_id"])
    op.create_index("idx_graph_edges_b", "graph_edges", ["node_b_type", "node_b_id"])

    # ---- daily_puzzles ----
    op.create_table(
        "daily_puzzles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("puzzle_date", sa.Date(), unique=True, nullable=False),
        sa.Column("start_player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("end_player_id", sa.String(20), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("canonical_path", postgresql.JSONB(), nullable=False),
        sa.Column("optimal_hops", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(10), nullable=False),
        sa.Column("edge_types_used", postgresql.ARRAY(sa.String())),
        sa.Column("is_published", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_daily_puzzles_date", "daily_puzzles", ["puzzle_date"])

    # ---- game_sessions ----
    op.create_table(
        "game_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("puzzle_date", sa.Date(), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("path_taken", postgresql.JSONB()),
        sa.Column("hops_used", sa.Integer()),
        sa.Column("time_seconds", sa.Integer()),
        sa.Column("score", sa.Integer()),
        sa.Column("completed", sa.Boolean(), server_default="false"),
        sa.Column("gave_up", sa.Boolean(), server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("puzzle_date", "client_id", name="uq_session_puzzle_client"),
    )
    op.create_index("idx_sessions_client", "game_sessions", ["client_id"])
    op.create_index("idx_sessions_date", "game_sessions", ["puzzle_date"])

    # ---- streaks ----
    op.create_table(
        "streaks",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("current_streak", sa.Integer(), server_default="0"),
        sa.Column("max_streak", sa.Integer(), server_default="0"),
        sa.Column("total_played", sa.Integer(), server_default="0"),
        sa.Column("total_won", sa.Integer(), server_default="0"),
        sa.Column("last_played", sa.Date()),
        sa.Column("score_total", sa.Integer(), server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("streaks")
    op.drop_table("game_sessions")
    op.drop_table("daily_puzzles")
    op.drop_table("graph_edges")
    op.drop_table("coach_seasons")
    op.drop_table("coaches")
    op.drop_table("player_seasons")
    op.drop_table("teams")
    op.drop_table("players")
