"""HOOPCHAIN — SQLAlchemy models (all tables)"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship

from ..database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(String(20), primary_key=True)          # nba.com player_id
    full_name = Column(String(100), nullable=False)
    first_name = Column(String(50))
    last_name = Column(String(50))
    college = Column(String(100))
    draft_year = Column(Integer)
    draft_round = Column(Integer)
    draft_number = Column(Integer)
    position = Column(String(10))
    birth_date = Column(Date)
    country = Column(String(50))
    is_active = Column(Boolean, default=False)
    headshot_url = Column(String(255))
    search_vector = Column(TSVECTOR)
    recognizability_score = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    seasons = relationship("PlayerSeason", back_populates="player", lazy="select")

    def headshot(self) -> str:
        return self.headshot_url or f"https://cdn.nba.com/headshots/nba/latest/1040x760/{self.id}.png"


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    abbreviation = Column(String(5), nullable=False)
    nickname = Column(String(50))
    city = Column(String(50))
    conference = Column(String(10))
    division = Column(String(20))
    is_active = Column(Boolean, default=True)

    player_seasons = relationship("PlayerSeason", back_populates="team", lazy="select")
    coach_seasons = relationship("CoachSeason", back_populates="team", lazy="select")


class PlayerSeason(Base):
    __tablename__ = "player_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String(20), ForeignKey("players.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    season = Column(Integer, nullable=False)        # e.g. 2023 = 2023-24 season
    games_played = Column(Integer)

    __table_args__ = (
        UniqueConstraint("player_id", "team_id", "season", name="uq_player_team_season"),
    )

    player = relationship("Player", back_populates="seasons")
    team = relationship("Team", back_populates="player_seasons")


class Coach(Base):
    __tablename__ = "coaches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    bref_id = Column(String(50), unique=True)       # basketball-reference identifier

    seasons = relationship("CoachSeason", back_populates="coach", lazy="select")


class CoachSeason(Base):
    __tablename__ = "coach_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coach_id = Column(Integer, ForeignKey("coaches.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    season = Column(Integer, nullable=False)
    role = Column(String(20), default="head_coach")

    __table_args__ = (
        UniqueConstraint("coach_id", "team_id", "season", name="uq_coach_team_season"),
    )

    coach = relationship("Coach", back_populates="seasons")
    team = relationship("Team", back_populates="coach_seasons")


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_a_type = Column(String(20), nullable=False)    # 'player' | 'coach'
    node_a_id = Column(String(30), nullable=False)
    node_b_type = Column(String(20), nullable=False)
    node_b_id = Column(String(30), nullable=False)
    edge_type = Column(String(30), nullable=False)       # 'teammate' | 'college' | 'draft_class' | 'coached_by' | 'all_star'
    edge_label = Column(String(200))                     # human-readable description
    weight = Column(Float, default=1.0)                  # lower = stronger connection
    metadata_ = Column("metadata", JSONB)

    __table_args__ = (
        Index("idx_graph_edges_a", "node_a_type", "node_a_id"),
        Index("idx_graph_edges_b", "node_b_type", "node_b_id"),
    )


class DailyPuzzle(Base):
    __tablename__ = "daily_puzzles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    puzzle_date = Column(Date, unique=True, nullable=False)
    start_player_id = Column(String(20), ForeignKey("players.id"), nullable=False)
    end_player_id = Column(String(20), ForeignKey("players.id"), nullable=False)
    canonical_path = Column(JSONB, nullable=False)      # [{type, id, name, connection_label}, ...]
    optimal_hops = Column(Integer, nullable=False)
    difficulty = Column(String(10), nullable=False)     # 'easy' | 'medium' | 'hard'
    edge_types_used = Column(ARRAY(String))
    available_modes = Column(ARRAY(String), nullable=True)  # modes with valid paths: ['classic', 'teammate', ...]
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    start_player = relationship("Player", foreign_keys=[start_player_id])
    end_player = relationship("Player", foreign_keys=[end_player_id])


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    puzzle_date = Column(Date, nullable=False)
    client_id = Column(String(64), nullable=False)
    mode = Column(String(20), default="classic", nullable=False)
    is_freeplay = Column(Boolean, default=False, nullable=False)
    path_taken = Column(JSONB)
    hops_used = Column(Integer)
    time_seconds = Column(Integer)
    score = Column(Integer)
    completed = Column(Boolean, default=False)
    gave_up = Column(Boolean, default=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("puzzle_date", "client_id", "mode", name="uq_session_puzzle_client_mode"),
    )


class Streak(Base):
    __tablename__ = "streaks"

    client_id = Column(String(64), primary_key=True)
    current_streak = Column(Integer, default=0)
    max_streak = Column(Integer, default=0)
    total_played = Column(Integer, default=0)
    total_won = Column(Integer, default=0)
    last_played = Column(Date)
    score_total = Column(Integer, default=0)


class EmailSubscriber(Base):
    __tablename__ = "email_subscribers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
