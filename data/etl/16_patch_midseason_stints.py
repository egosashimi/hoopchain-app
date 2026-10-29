"""
HOOPCHAIN ETL — Step 16: Patch mid-season player stints (2023-24 / 2024-25)
============================================================================
Verifies and patches player_seasons for players who changed teams mid-season.
Uses nba_api PlayerGameLog to find actual team stints rather than roster
snapshots (CommonTeamRoster only captures end-of-season roster).

Also regenerates ALL 2023-24 and 2024-25 teammate edges in the graph_edges
Postgres table so that rebuild_graph_from_pg.py produces a complete graph.

Audit players (besides Westbrook):
  - OG Anunoby      (1628384) TOR→NYK mid-2023-24
  - Pascal Siakam   (1627783) TOR→IND mid-2023-24
  - Klay Thompson   (202691)  GSW 2023-24, DAL 2024-25
  - Karl-Anthony Towns (1626157) MIN 2023-24, NYK 2024-25
  - Dejounte Murray (1628374) ATL 2023-24, NOP trade

Run after: confirm player_seasons is up-to-date
Run before: rebuild_graph_from_pg.py (step 4 in task)

Usage:
    python data/etl/16_patch_midseason_stints.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
sys.path.insert(0, str(ETL_DIR.parent.parent / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ETL_DIR / ".env")
    load_dotenv(ETL_DIR.parent.parent / "backend" / ".env")
except ImportError:
    pass

RAW_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5433/hoopchain")
PG_URL = RAW_URL.replace("postgresql+asyncpg://", "postgresql://")

AUDIT_SEASONS = [2023, 2024]  # 2023=2023-24, 2024=2024-25

AUDIT_PLAYERS = [
    # (nba_stats_id, name, expected_teams_per_season)
    ("201566", "Russell Westbrook"),
    ("1628384", "OG Anunoby"),
    ("1627783", "Pascal Siakam"),
    ("202691",  "Klay Thompson"),
    ("1626157", "Karl-Anthony Towns"),
    ("1628374", "Dejounte Murray"),
]

ABBR_TO_TEAM_ID: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "NJN": 1610612751, "BKN": 1610612751,
    "CHA": 1610612766, "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742,
    "DEN": 1610612743, "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745,
    "IND": 1610612754, "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
    "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740,
    "NOH": 1610612740, "NYK": 1610612752, "OKC": 1610612760, "ORL": 1610612753,
    "PHI": 1610612755, "PHX": 1610612756, "POR": 1610612757, "SAC": 1610612758,
    "SAS": 1610612759, "SA":  1610612759, "TOR": 1610612761, "UTA": 1610612762,
    "WAS": 1610612764,
}

TEAM_ID_TO_NAME: dict[int, str] = {
    1610612737: "Atlanta Hawks",        1610612738: "Boston Celtics",
    1610612739: "Cleveland Cavaliers",  1610612740: "New Orleans Pelicans",
    1610612741: "Chicago Bulls",        1610612742: "Dallas Mavericks",
    1610612743: "Denver Nuggets",       1610612744: "Golden State Warriors",
    1610612745: "Houston Rockets",      1610612746: "Los Angeles Clippers",
    1610612747: "Los Angeles Lakers",   1610612748: "Miami Heat",
    1610612749: "Milwaukee Bucks",      1610612750: "Minnesota Timberwolves",
    1610612751: "Brooklyn Nets",        1610612752: "New York Knicks",
    1610612753: "Orlando Magic",        1610612754: "Indiana Pacers",
    1610612755: "Philadelphia 76ers",   1610612756: "Phoenix Suns",
    1610612757: "Portland Trail Blazers", 1610612758: "Sacramento Kings",
    1610612759: "San Antonio Spurs",    1610612760: "Oklahoma City Thunder",
    1610612761: "Toronto Raptors",      1610612762: "Utah Jazz",
    1610612763: "Memphis Grizzlies",    1610612764: "Washington Wizards",
    1610612765: "Detroit Pistons",      1610612766: "Charlotte Hornets",
}


def _season_str(year: int) -> str:
    return f"{year}-{str(year + 1)[2:]}"


def fetch_game_log_teams(player_id: str, season_year: int) -> set[int]:
    """
    Use nba_api PlayerGameLog to find all distinct team IDs a player
    played for in a given season. Returns a set of NBA.com team IDs.
    """
    from nba_api.stats.endpoints import playergamelog

    season_str = _season_str(season_year)
    try:
        for attempt in range(4):
            try:
                ep = playergamelog.PlayerGameLog(
                    player_id=int(player_id),
                    season=season_str,
                    timeout=20,
                )
                df = ep.get_data_frames()[0]
                break
            except Exception as e:
                if attempt == 3:
                    raise
                wait = 2 ** attempt + 1
                log.warning(f"    Retry {attempt + 1}/4 after {wait}s: {e}")
                time.sleep(wait)

        if df.empty:
            return set()

        # TEAM_ID column is the NBA.com team ID
        team_ids = set(int(tid) for tid in df["TEAM_ID"].unique() if tid and tid != 0)
        return team_ids
    except Exception as e:
        log.warning(f"  PlayerGameLog failed for {player_id} {season_str}: {e}")
        return set()


def audit_and_patch_player_seasons(conn) -> list[tuple]:
    """
    For each audit player, fetch their actual team stints from PlayerGameLog
    and insert any missing (player_id, team_id, season) rows into player_seasons.
    Returns list of newly inserted (player_id, team_id, season) tuples.
    """
    cur = conn.cursor()

    # Load existing seasons for audit players
    audit_ids = [p[0] for p in AUDIT_PLAYERS]
    placeholders = ",".join(["%s"] * len(audit_ids))
    cur.execute(
        f"SELECT player_id, team_id, season FROM player_seasons WHERE player_id IN ({placeholders})",
        audit_ids,
    )
    existing: set[tuple] = {(str(r[0]), int(r[1]), int(r[2])) for r in cur.fetchall()}

    # Validate teams exist
    cur.execute("SELECT id FROM teams")
    valid_team_ids = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT id FROM players")
    valid_player_ids = {str(r[0]) for r in cur.fetchall()}

    inserted: list[tuple] = []

    for player_id, name in AUDIT_PLAYERS:
        log.info(f"\n  === {name} ({player_id}) ===")

        # Show existing seasons
        player_existing = sorted(
            [(team_id, season) for pid, team_id, season in existing if pid == player_id],
            key=lambda x: x[1],
        )
        log.info(f"    Existing player_seasons: {player_existing}")

        if player_id not in valid_player_ids:
            log.warning(f"    Player {player_id} not in players table — skipping")
            continue

        for season_year in AUDIT_SEASONS:
            log.info(f"    Fetching game log for {_season_str(season_year)}...")
            team_ids_from_log = fetch_game_log_teams(player_id, season_year)
            time.sleep(0.5)

            log.info(f"    Teams from game log: {[TEAM_ID_TO_NAME.get(t, t) for t in sorted(team_ids_from_log)]}")

            for team_id in team_ids_from_log:
                key = (player_id, team_id, season_year)
                if key in existing:
                    continue
                if team_id not in valid_team_ids:
                    log.warning(f"    Team {team_id} not in teams table — skipping")
                    continue
                try:
                    cur.execute(
                        """INSERT INTO player_seasons (player_id, team_id, season)
                           VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                        (player_id, team_id, season_year),
                    )
                    if cur.rowcount:
                        team_name = TEAM_ID_TO_NAME.get(team_id, str(team_id))
                        log.info(f"    INSERTED: {name} on {team_name} {season_year}")
                        inserted.append(key)
                        existing.add(key)
                    else:
                        log.info(f"    Already exists (conflict): {name} on {team_id} {season_year}")
                except Exception as e:
                    log.warning(f"    Insert failed: {e}")
                    conn.rollback()

    conn.commit()
    log.info(f"\n  player_seasons: {len(inserted)} new rows inserted")
    return inserted


def generate_teammate_edges_for_seasons(conn, seasons: list[int]) -> list[dict]:
    """
    Generate ALL teammate edges for the given seasons from player_seasons.
    Groups by (team_id, season) and pairs every roster member.
    """
    cur = conn.cursor()
    edges = []

    for season in seasons:
        cur.execute(
            "SELECT team_id, player_id FROM player_seasons WHERE season = %s",
            (season,),
        )
        rows = cur.fetchall()

        team_roster: dict[int, list[str]] = defaultdict(list)
        for team_id, player_id in rows:
            team_roster[team_id].append(str(player_id))

        for team_id, players in team_roster.items():
            team_name = TEAM_ID_TO_NAME.get(team_id, f"Team {team_id}")
            label = f"{season}-{str(season + 1)[2:]} {team_name} Teammates"
            unique_players = sorted(set(players))
            for a, b in combinations(unique_players, 2):
                edges.append({
                    "node_a_type": "player", "node_a_id": a,
                    "node_b_type": "player", "node_b_id": b,
                    "edge_type": "teammate",
                    "edge_label": label,
                    "weight": 0.9,
                })

    log.info(f"Generated {len(edges)} teammate edges for seasons {seasons}")
    return edges


def insert_graph_edges(conn, edges: list[dict]) -> int:
    """
    Insert edges into graph_edges table. Skips existing pairs via ON CONFLICT.
    graph_edges has no unique constraint on node pairs, so we check manually.
    """
    if not edges:
        return 0

    cur = conn.cursor()

    # Load existing teammate pairs for the target seasons (to avoid duplicates)
    # graph_edges has no unique constraint so we must deduplicate ourselves
    cur.execute("""
        SELECT node_a_id, node_b_id FROM graph_edges
        WHERE edge_type = 'teammate'
    """)
    existing_pairs: set[tuple] = set()
    for a, b in cur.fetchall():
        existing_pairs.add((min(a, b), max(a, b)))

    to_insert = []
    for e in edges:
        pair = (min(e["node_a_id"], e["node_b_id"]), max(e["node_a_id"], e["node_b_id"]))
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)
        to_insert.append((
            e["node_a_type"], e["node_a_id"],
            e["node_b_type"], e["node_b_id"],
            e["edge_type"], e["edge_label"],
            e["weight"],
        ))

    if not to_insert:
        log.info("No new edges to insert (all already present)")
        return 0

    psycopg2.extras.execute_values(cur, """
        INSERT INTO graph_edges
            (node_a_type, node_a_id, node_b_type, node_b_id, edge_type, edge_label, weight)
        VALUES %s
    """, to_insert, page_size=500)
    conn.commit()
    log.info(f"Inserted {len(to_insert)} new teammate edges into graph_edges")
    return len(to_insert)


def verify_westbrook_jokic(conn) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT edge_type, edge_label FROM graph_edges
        WHERE (node_a_id = '201566' AND node_b_id = '203999')
           OR (node_a_id = '203999' AND node_b_id = '201566')
    """)
    rows = cur.fetchall()
    if rows:
        log.info(f"  Westbrook-Jokic in graph_edges: {rows[0]}")
        return True
    else:
        log.warning("  Westbrook-Jokic NOT found in graph_edges")
        return False


def report_graph_edge_counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT edge_type, COUNT(*) FROM graph_edges GROUP BY edge_type ORDER BY COUNT(*) DESC")
    log.info("\n=== graph_edges counts after patch ===")
    total = 0
    for etype, cnt in cur.fetchall():
        log.info(f"  {etype}: {cnt:,}")
        total += cnt
    log.info(f"  TOTAL: {total:,}")


def main():
    log.info("=" * 60)
    log.info("HOOPCHAIN ETL — Step 16: Patch mid-season player stints")
    log.info("=" * 60)

    conn = psycopg2.connect(PG_URL)
    log.info("Connected to Postgres")

    # ── Step 1: Diagnose current Westbrook player_seasons ─────────────────────
    log.info("\n── Step 1: Westbrook (201566) player_seasons ──")
    cur = conn.cursor()
    cur.execute(
        "SELECT team_id, season FROM player_seasons WHERE player_id = '201566' ORDER BY season"
    )
    rows = cur.fetchall()
    for team_id, season in rows:
        team_name = TEAM_ID_TO_NAME.get(team_id, str(team_id))
        log.info(f"  season={season}: {team_name} ({team_id})")
    den_rows = [(t, s) for t, s in rows if t == 1610612743]
    log.info(f"DEN rows: {den_rows}")

    # ── Step 2: Audit + patch player_seasons via PlayerGameLog ────────────────
    log.info("\n── Step 2: Audit player stints via nba_api PlayerGameLog ──")
    newly_inserted = audit_and_patch_player_seasons(conn)

    # ── Step 3: Show updated Westbrook seasons ────────────────────────────────
    log.info("\n── Step 3: Westbrook player_seasons after patch ──")
    cur.execute(
        "SELECT team_id, season FROM player_seasons WHERE player_id = '201566' ORDER BY season"
    )
    for team_id, season in cur.fetchall():
        team_name = TEAM_ID_TO_NAME.get(team_id, str(team_id))
        log.info(f"  season={season}: {team_name} ({team_id})")

    # ── Step 4: Generate + insert 2023-24 and 2024-25 teammate edges ──────────
    log.info("\n── Step 4: Generate teammate edges for 2023-24 and 2024-25 ──")
    new_edges = generate_teammate_edges_for_seasons(conn, AUDIT_SEASONS)
    inserted_count = insert_graph_edges(conn, new_edges)

    # ── Step 5: Verify Westbrook-Jokic is now in graph_edges ─────────────────
    log.info("\n── Step 5: Verify Westbrook-Jokic ──")
    ok = verify_westbrook_jokic(conn)

    # ── Step 6: Report final counts ───────────────────────────────────────────
    report_graph_edge_counts(conn)

    conn.close()

    log.info("\n" + "=" * 60)
    log.info(f"player_seasons rows inserted: {len(newly_inserted)}")
    log.info(f"graph_edges rows inserted: {inserted_count}")
    log.info(f"Westbrook-Jokic in graph_edges: {ok}")
    log.info("Next: run rebuild_graph_from_pg.py, then 10_patch_connections.py")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
