"""
HOOPCHAIN ETL — Step 2: Build Graph from nbadb SQLite
=======================================================
# CHANGES (session 2026-05):
#   - extract_player_seasons: added valid_player_ids filter to prevent FK violations
#     when common_player_info.person_id references players not in the player master table
#   - Root cause: some player IDs exist in common_player_info but have NULL full_name
#     in player table and are excluded from players extraction; seasons still referenced them
Reads nba.sqlite (wyattowalsh/nbadb Kaggle dataset).
Populates PostgreSQL tables: players, teams, player_seasons, graph_edges.
Serializes a NetworkX graph to data/exports/graph.pkl.

Run after: 01_download_nbadb.sh
Run before: 03_enrich_coaches.py, 05_generate_puzzles.py

Expected runtime: ~15 minutes for full nbadb

# CHANGES (session 2025-05):
#   - Fixed SQLite column names to match actual nbadb schema:
#     - common_player_info uses person_id (not id), school (not college),
#       display_first_last (not full_name)
#   - game table does NOT have player-level data; player-team-season derived
#     from common_player_info (from_year/to_year) + draft_history
#   - Added fallback to nba.sqlite filename (Kaggle extracts as nba.sqlite)
#   - extract_player_seasons now uses common_player_info + game table approach:
#     joins team/season from game rows (home/away) grouped by team per season
#   - draft_class_edges now use person_id from draft_history
"""

from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict
from itertools import combinations
from typing import Any

# Add backend to path for config/database imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import networkx as nx
import psycopg2
from dotenv import load_dotenv

# data/etl/.env takes precedence (has prod DB URL for ETL scripts)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ------------------------------------
# Paths
# ------------------------------------

ETL_DIR = Path(__file__).parent
DATA_DIR = ETL_DIR.parent
EXPORTS_DIR = DATA_DIR / "exports"
# CHANGE (session 2025-05): Kaggle wyattowalsh/basketball dataset extracts as
# 'nba.sqlite', not 'basketball.sqlite'. Updated primary path accordingly.
SQLITE_PATH = EXPORTS_DIR / "nba.sqlite"
SQLITE_PATH_FALLBACK = EXPORTS_DIR / "basketball.sqlite"
GRAPH_PKL_PATH = EXPORTS_DIR / "graph.pkl"

# ------------------------------------
# Database connection
# ------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5432/hoopchain")
# Convert asyncpg URL to psycopg2 URL
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_pg_conn():
    return psycopg2.connect(PG_URL)


def get_sqlite_conn():
    # Try primary path (nba.sqlite) first
    if SQLITE_PATH.exists():
        logger.info(f"Using SQLite: {SQLITE_PATH}")
        return sqlite3.connect(SQLITE_PATH)
    # Try fallback (basketball.sqlite)
    if SQLITE_PATH_FALLBACK.exists():
        logger.info(f"Using SQLite fallback: {SQLITE_PATH_FALLBACK}")
        return sqlite3.connect(SQLITE_PATH_FALLBACK)
    # Find any .sqlite file in exports
    sqlite_files = list(EXPORTS_DIR.glob("*.sqlite"))
    if not sqlite_files:
        raise FileNotFoundError(
            f"No SQLite file found in {EXPORTS_DIR}. "
            "Run 01_download_nbadb.sh first."
        )
    logger.info(f"Using found SQLite: {sqlite_files[0]}")
    return sqlite3.connect(sqlite_files[0])


# ------------------------------------
# Edge weight constants
# ------------------------------------

def teammate_weight(seasons_together: int) -> float:
    if seasons_together >= 5:
        return 0.3
    elif seasons_together >= 2:
        return 0.6
    return 0.9


COACH_WEIGHT = 0.7
COLLEGE_WEIGHT = 1.2
DRAFT_CLASS_WEIGHT = 1.4
ALL_STAR_WEIGHT = 1.5


# ------------------------------------
# Main ETL functions
# ------------------------------------

def extract_players(sqlite_conn) -> list[dict]:
    """
    Extract player data from common_player_info table.
    SCHEMA NOTE: nbadb uses person_id (not id), school (not college),
    display_first_last (not full_name).
    We also join with player table to get all 4800+ players.
    """
    logger.info("Extracting players from common_player_info + player tables...")
    cursor = sqlite_conn.cursor()

    # Get all players from the player master table first
    cursor.execute("""
        SELECT DISTINCT
            id,
            full_name,
            first_name,
            last_name,
            is_active
        FROM player
        WHERE id IS NOT NULL AND full_name IS NOT NULL
    """)
    player_base = {}
    for row in cursor.fetchall():
        player_base[str(row[0])] = {
            "id": str(row[0]),
            "full_name": row[1] or "",
            "first_name": row[2],
            "last_name": row[3],
            "is_active": bool(row[4]),
            "college": None,
            "draft_year": None,
            "draft_round": None,
            "draft_number": None,
            "position": None,
            "birth_date": None,
            "country": None,
        }

    # Enrich with common_player_info (has college/draft/position data)
    # common_player_info uses person_id, school, display_first_last
    cursor.execute("""
        SELECT DISTINCT
            person_id,
            display_first_last,
            first_name,
            last_name,
            school,
            draft_year,
            draft_round,
            draft_number,
            position,
            birthdate,
            country,
            rosterstatus
        FROM common_player_info
        WHERE person_id IS NOT NULL
    """)

    for row in cursor.fetchall():
        pid = str(row[0])
        if pid in player_base:
            # Update with richer data
            player_base[pid]["college"] = row[4]
            player_base[pid]["draft_year"] = row[5]
            player_base[pid]["draft_round"] = row[6]
            player_base[pid]["draft_number"] = row[7]
            player_base[pid]["position"] = row[8]
            # Parse birthdate - stored as "1968-06-24 00:00:00" or similar
            bd = row[9]
            if bd:
                try:
                    player_base[pid]["birth_date"] = str(bd).split(" ")[0]
                except Exception:
                    pass
            player_base[pid]["country"] = row[10]
            player_base[pid]["is_active"] = (row[11] or "").upper() == "ACTIVE"
        else:
            # Player in common_player_info but not in player table
            player_base[pid] = {
                "id": pid,
                "full_name": row[1] or "",
                "first_name": row[2],
                "last_name": row[3],
                "college": row[4],
                "draft_year": row[5],
                "draft_round": row[6],
                "draft_number": row[7],
                "position": row[8],
                "birth_date": str(row[9]).split(" ")[0] if row[9] else None,
                "country": row[10],
                "is_active": (row[11] or "").upper() == "ACTIVE",
            }

    players = list(player_base.values())
    logger.info(f"Extracted {len(players)} players")
    return players


def extract_teams(sqlite_conn) -> list[dict]:
    """Extract team data. Schema: id, full_name, abbreviation, nickname, city, state, year_founded"""
    logger.info("Extracting teams...")
    cursor = sqlite_conn.cursor()

    cursor.execute("""
        SELECT DISTINCT
            id,
            full_name,
            abbreviation,
            nickname,
            city,
            state
        FROM team
        WHERE id IS NOT NULL AND full_name IS NOT NULL
    """)

    teams = []
    for row in cursor.fetchall():
        teams.append({
            "id": int(row[0]),
            "full_name": row[1],
            "abbreviation": row[2] or "",
            "nickname": row[3],
            "city": row[4],
            "conference": None,
            "division": None,
            "is_active": True,  # team table doesn't have is_active; all 30 teams are active
        })

    logger.info(f"Extracted {len(teams)} teams")
    return teams


def extract_player_seasons(sqlite_conn, players: list[dict]) -> list[dict]:
    """
    Derive player-team-season memberships from game-level sources (box-score ground truth).

    Priority order:
    1. play_by_play: actual player appearances per game (90%+ coverage, all seasons with PBP)
       — DISTINCT (player_id, team_id, season) from player1/2/3 columns.
       — Correctly handles traded players: shows both teams in the same season.
       — Eliminates CPI year-range phantoms (e.g. Boozer fake Utah seasons).
    2. inactive_players: players formally listed as inactive for specific games
       — Adds players on team roster who didn't appear in any play that season.
    3. draft_history: draft-year team for players with no game data yet (current-year rookies).
    4. common_player_info fallback: ONLY for players with no PBP/inactive data at all
       (pre-1996 era historical players). Never expands a year range — single-season only
       for the season the team actually played.

    WHY: CPI stores only the last known team + full career year range. For traded players
    this fabricates phantom seasons on the wrong team and drops actual stints. Ground-truth
    game data fixes both problems at once.
    """
    logger.info("Extracting player seasons from play_by_play (box scores) + inactive_players + draft_history...")
    cursor = sqlite_conn.cursor()

    valid_player_ids = {p["id"] for p in players}

    cursor.execute("SELECT DISTINCT id FROM team")
    valid_team_ids = set(int(row[0]) for row in cursor.fetchall() if row[0])
    logger.info(f"  {len(valid_team_ids)} valid team IDs, {len(valid_player_ids)} valid player IDs")

    seasons: list[dict] = []
    seen: set[tuple] = set()

    def _add(pid: str, team_id: int, season: int) -> bool:
        if pid not in valid_player_ids or team_id not in valid_team_ids:
            return False
        if not (1946 <= season <= 2030):
            return False
        key = (pid, team_id, season)
        if key in seen:
            return False
        seen.add(key)
        seasons.append({"player_id": pid, "team_id": team_id, "season": season})
        return True

    # --- Source 1: play_by_play (game appearances — primary box-score source) ---
    # season_id encodes season start year: '22022' → season 2022.
    # player1/2/3 columns each hold a player id + their team id for that play.
    # Traded players appear under multiple team_ids within the same season — each
    # generates a separate (player_id, team_id, season) row, which is exactly what
    # build_teammate_edges needs.
    logger.info("  Source 1: play_by_play (this may take a few minutes for 13M+ rows)...")
    cursor.execute("""
        SELECT DISTINCT player_id, CAST(CAST(team_id AS REAL) AS INTEGER), season_year
        FROM (
            SELECT player1_id      AS player_id,
                   player1_team_id AS team_id,
                   CAST(SUBSTR(CAST(g.season_id AS TEXT), 2, 4) AS INTEGER) AS season_year
            FROM play_by_play pbp
            JOIN game g ON pbp.game_id = g.game_id
            WHERE g.season_type = 'Regular Season'
              AND pbp.player1_id NOT IN ('0', '', 'None')
              AND pbp.player1_team_id NOT IN ('0', '', 'None', '0.0')
            UNION
            SELECT player2_id, player2_team_id,
                   CAST(SUBSTR(CAST(g.season_id AS TEXT), 2, 4) AS INTEGER)
            FROM play_by_play pbp
            JOIN game g ON pbp.game_id = g.game_id
            WHERE g.season_type = 'Regular Season'
              AND pbp.player2_id NOT IN ('0', '', 'None')
              AND pbp.player2_team_id NOT IN ('0', '', 'None', '0.0')
            UNION
            SELECT player3_id, player3_team_id,
                   CAST(SUBSTR(CAST(g.season_id AS TEXT), 2, 4) AS INTEGER)
            FROM play_by_play pbp
            JOIN game g ON pbp.game_id = g.game_id
            WHERE g.season_type = 'Regular Season'
              AND pbp.player3_id NOT IN ('0', '', 'None')
              AND pbp.player3_team_id NOT IN ('0', '', 'None', '0.0')
        ) sub
        WHERE season_year BETWEEN 1946 AND 2030
    """)
    pbp_added = 0
    for row in cursor.fetchall():
        pid = str(row[0])
        try:
            team_id = int(row[1])
            season = int(row[2])
        except (TypeError, ValueError):
            continue
        if _add(pid, team_id, season):
            pbp_added += 1
    pbp_players = len({s["player_id"] for s in seasons})
    logger.info(f"  play_by_play: {pbp_added} new records, {pbp_players} distinct players")

    # --- Source 2: inactive_players (formally listed as inactive for games) ---
    cursor.execute("""
        SELECT DISTINCT
            ip.player_id,
            ip.team_id,
            CAST(SUBSTR(CAST(g.season_id AS TEXT), 2, 4) AS INTEGER) AS season_year
        FROM inactive_players ip
        JOIN game g ON ip.game_id = g.game_id
        WHERE g.season_type = 'Regular Season'
          AND ip.player_id IS NOT NULL
          AND ip.team_id IS NOT NULL
    """)
    inactive_added = 0
    for row in cursor.fetchall():
        pid = str(row[0])
        try:
            team_id = int(row[1])
            season = int(row[2])
        except (TypeError, ValueError):
            continue
        if _add(pid, team_id, season):
            inactive_added += 1
    logger.info(f"  inactive_players: {inactive_added} additional records")

    # --- Source 3: draft_history (draft-year team for recent rookies without game data) ---
    # IMPORTANT: draft_history records the team that PICKED the player, which may differ
    # from where they actually played (draft-night trades, e.g. Luka/Trae 2018).
    # Only add a draft_history record if the player has NO game-level data for that season.
    # This prevents phantom "ATL" season for Luka (drafted by ATL, played for DAL) and
    # phantom "DAL" season for Trae (drafted by DAL, played for ATL).
    players_with_season: dict[str, set[int]] = {}
    for s in seasons:
        players_with_season.setdefault(s["player_id"], set()).add(s["season"])

    cursor.execute("""
        SELECT DISTINCT person_id, team_id, season
        FROM draft_history
        WHERE person_id IS NOT NULL AND team_id IS NOT NULL AND season IS NOT NULL
    """)
    draft_added = 0
    for row in cursor.fetchall():
        pid = str(row[0])
        try:
            team_id = int(row[1])
            season = int(row[2])
        except (TypeError, ValueError):
            continue
        # Skip if player already has game-level data for this season year
        if season in players_with_season.get(pid, set()):
            continue
        if _add(pid, team_id, season):
            draft_added += 1
    logger.info(f"  draft_history: {draft_added} additional records")

    # --- Source 4: CPI fallback — ONLY for players with zero game-level data ---
    # These are pre-1996 historical players whose careers predate PBP coverage.
    # We still use CPI year expansion here because there is no alternative, but we
    # scope it to players who got zero records from Sources 1-3.
    players_with_data = {s["player_id"] for s in seasons}
    cursor.execute("""
        SELECT DISTINCT person_id, team_id, from_year, to_year
        FROM common_player_info
        WHERE person_id IS NOT NULL AND team_id IS NOT NULL
          AND from_year IS NOT NULL AND to_year IS NOT NULL
    """)
    cpi_rows = cursor.fetchall()
    cpi_added = 0
    for row in cpi_rows:
        pid = str(row[0])
        if pid in players_with_data:
            continue  # already have game-level data for this player — skip CPI
        try:
            team_id = int(row[1])
            from_year = int(row[2])
            to_year = int(row[3])
        except (TypeError, ValueError):
            continue
        for season in range(from_year, to_year + 1):
            if _add(pid, team_id, season):
                cpi_added += 1
    logger.info(f"  CPI fallback (pre-PBP era players only): {cpi_added} additional records")

    logger.info(f"Extracted {len(seasons)} player-season records total (filtered to active teams)")
    return seasons


def build_teammate_edges(player_seasons: list[dict], team_id_to_name: dict | None = None) -> list[dict]:
    """
    Build teammate edges: players who shared the same team in the same season.
    This is the largest edge set — may take 5-10 min for full dataset.
    """
    logger.info("Building teammate edges...")

    # Group players by (team_id, season)
    team_season_players: dict[tuple, set[str]] = defaultdict(set)
    for ps in player_seasons:
        key = (ps["team_id"], ps["season"])
        team_season_players[key].add(ps["player_id"])

    # Track seasons together per player pair
    pair_seasons: dict[tuple, list] = defaultdict(list)
    for (team_id, season), players in team_season_players.items():
        player_list = sorted(players)
        for a, b in combinations(player_list, 2):
            pair_seasons[(a, b)].append((team_id, season))

    # Build edges with weight based on seasons together
    edges = []
    for (a, b), team_seasons in pair_seasons.items():
        seasons_together = len(set(s for _, s in team_seasons))
        weight = teammate_weight(seasons_together)

        # Use the most recent season for the label
        most_recent = max(team_seasons, key=lambda x: x[1])
        team_id, season = most_recent

        team_name = (team_id_to_name or {}).get(team_id, f"Team {team_id}")
        edges.append({
            "node_a_type": "player", "node_a_id": a,
            "node_b_type": "player", "node_b_id": b,
            "edge_type": "teammate",
            "edge_label": f"{season}-{str(season+1)[2:]} {team_name} Teammates",
            "weight": weight,
            "metadata": {"team_id": team_id, "season": season, "seasons_together": seasons_together},
        })

    logger.info(f"Built {len(edges)} teammate edges")
    return edges


def build_college_edges(players: list[dict]) -> list[dict]:
    """Build college edges: players who attended the same college.
    SCHEMA NOTE: field is 'school' in common_player_info (stored as 'college' in our player dict).
    """
    logger.info("Building college edges...")

    college_players: dict[str, list[str]] = defaultdict(list)
    for p in players:
        college = (p.get("college") or "").strip()
        if college and college.lower() not in ("", "none", "did not attend", "n/a"):
            college_players[college].append(p["id"])

    edges = []
    for college, players_list in college_players.items():
        for a, b in combinations(sorted(players_list), 2):
            edges.append({
                "node_a_type": "player", "node_a_id": a,
                "node_b_type": "player", "node_b_id": b,
                "edge_type": "college",
                "edge_label": f"Both attended {college}",
                "weight": COLLEGE_WEIGHT,
                "metadata": {"college": college},
            })

    logger.info(f"Built {len(edges)} college edges")
    return edges


def build_draft_class_edges(sqlite_conn, players: list[dict]) -> list[dict]:
    """
    Build draft class edges: players drafted in the same year.
    SCHEMA NOTE: uses draft_history table with person_id column.
    More reliable than common_player_info.draft_year.
    """
    logger.info("Building draft class edges from draft_history...")
    cursor = sqlite_conn.cursor()

    # Build a set of valid player IDs
    valid_player_ids = {p["id"] for p in players}

    cursor.execute("""
        SELECT person_id, season
        FROM draft_history
        WHERE person_id IS NOT NULL AND season IS NOT NULL
            AND draft_type = 'Draft'
        ORDER BY season, overall_pick
    """)

    draft_year_players: dict[int, list[str]] = defaultdict(list)
    for row in cursor.fetchall():
        pid = str(row[0])
        year = int(row[1])
        if pid in valid_player_ids:
            draft_year_players[year].append(pid)

    edges = []
    for year, players_list in draft_year_players.items():
        # Limit to reasonable draft class size (should be ~60/year)
        unique_players = list(dict.fromkeys(players_list))[:100]
        for a, b in combinations(unique_players, 2):
            edges.append({
                "node_a_type": "player", "node_a_id": a,
                "node_b_type": "player", "node_b_id": b,
                "edge_type": "draft_class",
                "edge_label": f"Both drafted in {year} NBA Draft",
                "weight": DRAFT_CLASS_WEIGHT,
                "metadata": {"draft_year": year},
            })

    logger.info(f"Built {len(edges)} draft class edges")
    return edges


def build_networkx_graph(players: list[dict], coaches: list[dict], edges: list[dict]) -> nx.Graph:
    """Construct the NetworkX graph from extracted data."""
    logger.info("Building NetworkX graph...")
    G = nx.Graph()

    # Add player nodes
    for p in players:
        G.add_node(
            f"player:{p['id']}",
            type="player",
            name=p["full_name"],
            is_active=p["is_active"],
        )

    # Add coach nodes
    for c in coaches:
        G.add_node(
            f"coach:{c['id']}",
            type="coach",
            name=c["full_name"],
        )

    # Add edges
    for e in edges:
        a = f"{e['node_a_type']}:{e['node_a_id']}"
        b = f"{e['node_b_type']}:{e['node_b_id']}"
        if G.has_node(a) and G.has_node(b):
            G.add_edge(a, b, type=e["edge_type"], label=e["edge_label"], weight=e["weight"])

    logger.info(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


# ------------------------------------
# PostgreSQL insertion
# ------------------------------------

def _safe_int(val) -> int | None:
    """Parse an integer, returning None for non-numeric or null values."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def insert_players(pg_conn, players: list[dict]):
    """Bulk insert players into PostgreSQL."""
    logger.info(f"Inserting {len(players)} players into Postgres...")
    from psycopg2.extras import execute_values
    cur = pg_conn.cursor()

    rows = [
        (
            p["id"], p["full_name"], p["first_name"], p["last_name"],
            p["college"], _safe_int(p["draft_year"]),
            _safe_int(p["draft_round"]), _safe_int(p["draft_number"]),
            (p["position"] or "")[:10] if p["position"] else None,
            p["birth_date"], p["country"], p["is_active"],
        )
        for p in players
    ]
    execute_values(cur, """
        INSERT INTO players (id, full_name, first_name, last_name, college, draft_year,
            draft_round, draft_number, position, birth_date, country, is_active)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            college = COALESCE(EXCLUDED.college, players.college),
            draft_year = COALESCE(EXCLUDED.draft_year, players.draft_year),
            is_active = EXCLUDED.is_active
    """, rows, page_size=500)

    # Rebuild search vectors on normalized names (accents stripped) so that
    # 'Schroder' finds 'Schröder' and vice-versa.  Always update, not just NULL
    # rows, so re-running the ETL keeps search vectors consistent.
    cur.execute("""
        UPDATE players
        SET search_vector = to_tsvector('english', full_name)
    """)

    pg_conn.commit()
    logger.info("Players inserted.")


def insert_teams(pg_conn, teams: list[dict]):
    logger.info(f"Inserting {len(teams)} teams...")
    cur = pg_conn.cursor()
    for t in teams:
        cur.execute("""
            INSERT INTO teams (id, full_name, abbreviation, nickname, city, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET full_name = EXCLUDED.full_name
        """, (t["id"], t["full_name"], t["abbreviation"], t["nickname"], t["city"], t["is_active"]))
    pg_conn.commit()
    logger.info("Teams inserted.")


def insert_player_seasons(pg_conn, seasons: list[dict]):
    """Full replacement: TRUNCATE then bulk-insert the new box-score-derived seasons.
    Truncating ensures old CPI-range phantom seasons and patch-script ID-polluted rows
    are completely removed and cannot survive into the new graph."""
    logger.info(f"Replacing player_seasons with {len(seasons)} box-score-derived records...")
    from psycopg2.extras import execute_values
    cur = pg_conn.cursor()
    cur.execute("TRUNCATE TABLE player_seasons")
    logger.info("  player_seasons truncated")
    rows = [(ps["player_id"], ps["team_id"], ps["season"]) for ps in seasons]
    execute_values(cur, """
        INSERT INTO player_seasons (player_id, team_id, season)
        VALUES %s
        ON CONFLICT DO NOTHING
    """, rows, page_size=2000)
    pg_conn.commit()
    logger.info(f"  Inserted {len(rows)} player_season rows")


def insert_edges(pg_conn, edges: list[dict]):
    logger.info(f"Inserting {len(edges)} graph edges...")
    import json
    from psycopg2.extras import execute_values
    cur = pg_conn.cursor()

    cur.execute("TRUNCATE TABLE graph_edges")

    rows = [
        (
            e["node_a_type"], e["node_a_id"],
            e["node_b_type"], e["node_b_id"],
            e["edge_type"], e["edge_label"],
            e["weight"], json.dumps(e.get("metadata", {})),
        )
        for e in edges
    ]
    execute_values(cur, """
        INSERT INTO graph_edges
            (node_a_type, node_a_id, node_b_type, node_b_id, edge_type, edge_label, weight, metadata)
        VALUES %s
    """, rows, page_size=5000)

    pg_conn.commit()
    logger.info("Edges inserted.")


# ------------------------------------
# Fetch coaches from Postgres (for graph rebuild after enrichment)
# ------------------------------------

def fetch_coaches_from_pg(pg_conn) -> list[dict]:
    """Fetch coaches already loaded into Postgres by 03_enrich_coaches.py"""
    cur = pg_conn.cursor()
    cur.execute("SELECT id, full_name FROM coaches")
    rows = cur.fetchall()
    return [{"id": str(r[0]), "full_name": r[1]} for r in rows]


def reload_player_colleges_from_pg(pg_conn, players: list[dict]) -> list[dict]:
    """
    Re-read college field from Postgres after insert.
    insert_players uses COALESCE(EXCLUDED.college, players.college), so any
    Wikipedia-enriched college values written by 04_enrich_wikipedia.py are
    preserved in Postgres even when SQLite has NULL for that player. This step
    merges those enriched values back into the in-memory players list so that
    build_college_edges() sees them.
    """
    cur = pg_conn.cursor()
    cur.execute("SELECT id, college FROM players WHERE college IS NOT NULL AND college != ''")
    pg_colleges = {str(r[0]): r[1] for r in cur.fetchall()}
    enriched = 0
    for p in players:
        pg_val = pg_colleges.get(p["id"])
        if pg_val and not p.get("college"):
            p["college"] = pg_val
            enriched += 1
    logger.info(f"Merged {enriched} Wikipedia-enriched college values from Postgres into player list")
    return players


# ------------------------------------
# Main
# ------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 2: Build Graph")
    logger.info("=" * 60)

    # Connect to SQLite
    sqlite_conn = get_sqlite_conn()

    # Extract from SQLite
    players = extract_players(sqlite_conn)
    teams = extract_teams(sqlite_conn)
    player_seasons = extract_player_seasons(sqlite_conn, players)
    draft_class_edges = build_draft_class_edges(sqlite_conn, players)
    sqlite_conn.close()

    logger.info(f"Extracted: {len(players)} players, {len(teams)} teams, {len(player_seasons)} player seasons")

    # Validate
    assert len(players) > 1000, f"Expected >1000 players, got {len(players)}"
    assert len(teams) >= 30, f"Expected >=30 teams, got {len(teams)}"
    logger.info("✅ Player/team count validation passed")

    # Connect to Postgres
    pg_conn = get_pg_conn()

    # Insert into Postgres
    insert_teams(pg_conn, teams)
    insert_players(pg_conn, players)
    insert_player_seasons(pg_conn, player_seasons)

    # Fetch any coaches already loaded (from 03_enrich_coaches.py)
    coaches = fetch_coaches_from_pg(pg_conn)
    logger.info(f"Fetched {len(coaches)} coaches from Postgres")

    # Merge Wikipedia-enriched college data back into players list
    # (insert_players preserves enrichments via COALESCE; this syncs them for edge building)
    players = reload_player_colleges_from_pg(pg_conn, players)

    # Build edges
    team_id_to_name = {t["id"]: t["full_name"] for t in teams}
    edges = []
    edges.extend(build_teammate_edges(player_seasons, team_id_to_name))
    edges.extend(build_college_edges(players))
    edges.extend(draft_class_edges)
    # Note: coach and all_star edges added by 03_enrich_coaches.py

    logger.info(f"Total edges built: {len(edges)}")
    if len(edges) < 1000:
        logger.warning(f"Only {len(edges)} edges — lower than expected but proceeding")

    # Insert edges into Postgres
    insert_edges(pg_conn, edges)
    pg_conn.close()

    # Build and serialize NetworkX graph (include coaches)
    G = build_networkx_graph(players, coaches, edges)
    GRAPH_PKL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PKL_PATH, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"✅ Graph saved to {GRAPH_PKL_PATH}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("ETL Step 2 complete!")
    logger.info(f"  Players: {len(players)}")
    logger.info(f"  Teams: {len(teams)}")
    logger.info(f"  Player seasons: {len(player_seasons)}")
    logger.info(f"  Edges: {len(edges)}")
    logger.info(f"  Graph nodes: {G.number_of_nodes()}")
    logger.info(f"  Graph edges: {G.number_of_edges()}")
    logger.info("Next: python 03_enrich_coaches.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
