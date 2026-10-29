"""
HOOPCHAIN ETL — Step 12: Top-up 2023-24 and 2024-25 seasons via nba_api
=========================================================================
Replaces 08_patch_current_season.py (DEPRECATED).

WHY: The nbadb Kaggle export used by 02_build_graph.py contains game data only
through 2022-23. This script adds 2023-24 and 2024-25 player-team-season records
to Postgres and graph.pkl using canonical NBA Stats IDs from the official nba_api.

HOW: For each of the 30 teams, query CommonTeamRoster for the target seasons.
nba_api returns NBA.com player IDs directly — no guessing, no hardcoded maps.
Players already in nbadb get their recent seasons added; players new to the
dataset (e.g. Wembanyama, Cooper Flagg) are added to the players table too.

Run after: 02_build_graph.py, 03_enrich_coaches.py, 10_patch_connections.py
Run before: committing graph.pkl

Usage:
    DATABASE_URL=postgresql://... python data/etl/12_topup_modern_seasons.py
"""

from __future__ import annotations

import logging
import os
import pickle
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2
import psycopg2.extras
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
EXPORTS_GRAPH = ETL_DIR.parent / "exports" / "graph.pkl"
BACKEND_GRAPH = ETL_DIR.parent.parent / "backend" / "graph.pkl"

sys.path.insert(0, str(ETL_DIR.parent.parent / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ETL_DIR / ".env")
    load_dotenv(ETL_DIR.parent.parent / "backend" / ".env")
except ImportError:
    pass

RAW_URL = os.getenv("DATABASE_URL")
if not RAW_URL:
    raise SystemExit(
        "DATABASE_URL not set. Pass it as an env var:\n"
        "  DATABASE_URL=postgresql://... python data/etl/12_topup_modern_seasons.py"
    )
PG_URL = RAW_URL.replace("postgresql+asyncpg://", "postgresql://")

# Seasons to top-up (start year: 2023 = 2023-24, 2024 = 2024-25)
TOP_UP_SEASONS = [2023, 2024]

# Season string format for nba_api (e.g. 2023 → "2023-24")
def _season_str(year: int) -> str:
    return f"{year}-{str(year + 1)[2:]}"


def teammate_weight(seasons_together: int) -> float:
    if seasons_together >= 5:
        return 0.3
    elif seasons_together >= 2:
        return 0.6
    return 0.9


# ---------------------------------------------------------------------------
# nba_api helpers
# ---------------------------------------------------------------------------

def _fetch_with_retry(fn, *args, retries: int = 4, **kwargs):
    """Call fn(*args, **kwargs) with exponential back-off on failure."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt + 1
            log.warning(f"  Retry {attempt + 1}/{retries} after {wait}s ({e})")
            time.sleep(wait)


def fetch_all_rosters(seasons: list[int]) -> list[dict]:
    """
    Query CommonTeamRoster for all 30 teams × target seasons.
    Returns list of {player_id, full_name, team_id, season}.
    nba_api PLAYER_ID is the canonical NBA.com ID — no mapping needed.
    """
    from nba_api.stats.static import teams as nba_teams
    from nba_api.stats.endpoints import commonteamroster

    all_records: list[dict] = []
    team_list = nba_teams.get_teams()
    log.info(f"Fetching rosters for {len(team_list)} teams × {len(seasons)} seasons")

    for season_year in seasons:
        season_str = _season_str(season_year)
        log.info(f"  Season {season_str}…")
        for team in team_list:
            team_id = team["id"]
            try:
                roster_ep = _fetch_with_retry(
                    commonteamroster.CommonTeamRoster,
                    team_id=team_id,
                    season=season_str,
                    timeout=15,
                )
                df = roster_ep.get_data_frames()[0]
                for _, row in df.iterrows():
                    pid = str(row["PLAYER_ID"])
                    name = str(row.get("PLAYER", "")).strip()
                    if pid and pid != "0":
                        all_records.append({
                            "player_id": pid,
                            "full_name": name,
                            "team_id": team_id,
                            "season": season_year,
                        })
                time.sleep(0.4)  # polite rate limit
            except Exception as e:
                log.warning(f"  Failed {team['abbreviation']} {season_str}: {e}")
                time.sleep(1)

    log.info(f"Fetched {len(all_records)} raw roster records")
    return all_records


def fetch_player_details(player_ids: list[str]) -> dict[str, dict]:
    """
    Fetch CommonPlayerInfo for a list of player_ids to get full name,
    college, draft year etc. for players not yet in nbadb.
    """
    from nba_api.stats.endpoints import commonplayerinfo

    details: dict[str, dict] = {}
    for pid in player_ids:
        try:
            ep = _fetch_with_retry(
                commonplayerinfo.CommonPlayerInfo,
                player_id=int(pid),
                timeout=10,
            )
            df = ep.get_data_frames()[0]
            if df.empty:
                continue
            row = df.iloc[0]
            details[pid] = {
                "id": pid,
                "full_name": str(row.get("DISPLAY_FIRST_LAST", "")),
                "first_name": str(row.get("FIRST_NAME", "")),
                "last_name": str(row.get("LAST_NAME", "")),
                "college": str(row.get("SCHOOL", "")) or None,
                "draft_year": int(row["DRAFT_YEAR"]) if str(row.get("DRAFT_YEAR", "")).isdigit() else None,
                "draft_round": int(row["DRAFT_ROUND"]) if str(row.get("DRAFT_ROUND", "")).isdigit() else None,
                "draft_number": int(row["DRAFT_NUMBER"]) if str(row.get("DRAFT_NUMBER", "")).isdigit() else None,
                "position": str(row.get("POSITION", ""))[:10] or None,
                "is_active": True,
            }
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"  CommonPlayerInfo failed for {pid}: {e}")
    return details


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

def get_pg_conn():
    return psycopg2.connect(PG_URL)


def load_existing_player_ids(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT id FROM players")
    return {str(r[0]) for r in cur.fetchall()}


def load_existing_seasons(conn) -> set[tuple]:
    cur = conn.cursor()
    cur.execute("SELECT player_id, team_id, season FROM player_seasons")
    return {(str(r[0]), int(r[1]), int(r[2])) for r in cur.fetchall()}


def upsert_players(conn, players: list[dict]) -> int:
    cur = conn.cursor()
    rows = [
        (
            p["id"], p["full_name"],
            p.get("first_name") or p["full_name"].split()[0],
            p.get("last_name") or p["full_name"].split()[-1],
            p.get("college"), p.get("draft_year"),
            p.get("draft_round"), p.get("draft_number"),
            (p.get("position") or "")[:10] or None,
            None, None, True,
        )
        for p in players
    ]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO players (id, full_name, first_name, last_name, college, draft_year,
            draft_round, draft_number, position, birth_date, country, is_active)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            is_active = EXCLUDED.is_active,
            college = COALESCE(EXCLUDED.college, players.college),
            draft_year = COALESCE(EXCLUDED.draft_year, players.draft_year)
    """, rows, page_size=200)
    conn.commit()
    log.info(f"  Upserted {len(players)} players")
    return len(players)


def insert_player_seasons(conn, records: list[tuple]) -> int:
    """records: list of (player_id, team_id, season)"""
    cur = conn.cursor()
    psycopg2.extras.execute_values(cur, """
        INSERT INTO player_seasons (player_id, team_id, season)
        VALUES %s ON CONFLICT DO NOTHING
    """, records, page_size=500)
    inserted = cur.rowcount
    conn.commit()
    return inserted


def rebuild_search_vectors(conn):
    cur = conn.cursor()
    cur.execute("UPDATE players SET search_vector = to_tsvector('english', full_name)")
    conn.commit()


# ---------------------------------------------------------------------------
# Graph updates
# ---------------------------------------------------------------------------

def get_team_name_map(conn) -> dict[int, str]:
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM teams")
    return {r[0]: r[1] for r in cur.fetchall()}


def add_seasons_to_graph(
    G: nx.Graph,
    all_new_seasons: list[tuple],  # (player_id, team_id, season) for all new records
    team_id_to_name: dict[int, str],
    player_id_to_name: dict[str, str],
    conn,  # Postgres connection to query full rosters per team/season
) -> int:
    """Add new player nodes and teammate edges for the new season records.

    For each (team_id, season) group, queries Postgres to get the FULL roster
    (both new and already-existing players) and connects all roster pairs where
    both nodes are present in the graph. This avoids the graph-traversal bug
    that would fan out through all historical teammate edges.
    """
    # Add missing player nodes
    nodes_added = 0
    for pid, team_id, season in all_new_seasons:
        node = f"player:{pid}"
        if not G.has_node(node):
            name = player_id_to_name.get(pid, pid)
            G.add_node(node, type="player", name=name, is_active=True)
            nodes_added += 1
    if nodes_added:
        log.info(f"  Added {nodes_added} new player nodes to graph")

    # Find unique (team_id, season) groups that have new records
    affected_groups: set[tuple] = {(team_id, season) for _, team_id, season in all_new_seasons}

    cur = conn.cursor()
    edges_added = 0

    for team_id, season in sorted(affected_groups):
        team_name = team_id_to_name.get(team_id, f"Team {team_id}")
        label = f"{season}-{str(season + 1)[2:]} {team_name} Teammates"

        # Get the FULL roster for this team/season from Postgres (authoritative)
        cur.execute(
            "SELECT player_id FROM player_seasons WHERE team_id = %s AND season = %s",
            (team_id, season),
        )
        roster = sorted({str(r[0]) for r in cur.fetchall()})

        # Pair every roster member who is in the graph
        graph_roster = [pid for pid in roster if G.has_node(f"player:{pid}")]
        for a, b in combinations(graph_roster, 2):
            na, nb = f"player:{a}", f"player:{b}"
            if not G.has_edge(na, nb):
                G.add_edge(na, nb, type="teammate", label=label, weight=0.9)
                edges_added += 1

    log.info(f"  Added {edges_added} new teammate edges to graph")
    return edges_added


def add_draft_class_edges(G: nx.Graph, new_player_ids_by_draft_year: dict[int, list[str]]) -> int:
    """Add draft_class edges for new players not yet connected to their draft class."""
    added = 0
    for draft_year, new_pids in new_player_ids_by_draft_year.items():
        # Find existing nodes with a draft_class edge for this year
        existing_draft_class: list[str] = []
        for node, data in G.nodes(data=True):
            if data.get("type") != "player":
                continue
            for nb in G.neighbors(node):
                ed = G[node][nb]
                if ed.get("type") == "draft_class" and str(draft_year) in ed.get("label", ""):
                    existing_draft_class.append(node.split(":", 1)[1])
                    break

        label = f"Both drafted in {draft_year} NBA Draft"
        # Connect new players to each other
        for a, b in combinations(sorted(new_pids), 2):
            na, nb = f"player:{a}", f"player:{b}"
            if G.has_node(na) and G.has_node(nb) and not G.has_edge(na, nb):
                G.add_edge(na, nb, type="draft_class", label=label, weight=1.4)
                added += 1
        # Connect new players to existing draft class members
        for new_pid in new_pids:
            na = f"player:{new_pid}"
            for old_pid in existing_draft_class[:30]:
                nb = f"player:{old_pid}"
                if G.has_node(nb) and not G.has_edge(na, nb):
                    G.add_edge(na, nb, type="draft_class", label=label, weight=1.4)
                    added += 1
    log.info(f"  Draft class edges added: {added}")
    return added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("HOOPCHAIN ETL — Step 12: Top-up 2023-24 / 2024-25 seasons")
    log.info("=" * 60)

    # Load graph
    graph_path = EXPORTS_GRAPH if EXPORTS_GRAPH.exists() else BACKEND_GRAPH
    if not graph_path.exists():
        raise SystemExit("graph.pkl not found. Run 02_build_graph.py first.")
    log.info(f"Loading graph from {graph_path}…")
    with open(graph_path, "rb") as f:
        G = pickle.load(f)
    log.info(f"Graph before top-up: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    conn = get_pg_conn()

    existing_player_ids = load_existing_player_ids(conn)
    existing_seasons = load_existing_seasons(conn)
    log.info(f"DB has {len(existing_player_ids)} players, {len(existing_seasons)} player_seasons")

    # Step 1: Fetch rosters from nba_api
    log.info("\n── Step 1: Fetch team rosters from nba_api ──")
    roster_records = fetch_all_rosters(TOP_UP_SEASONS)

    # Deduplicate and identify new players / new seasons
    new_player_ids: set[str] = set()
    new_season_tuples: list[tuple] = []
    seen_seasons: set[tuple] = set()

    for rec in roster_records:
        pid = rec["player_id"]
        team_id = rec["team_id"]
        season = rec["season"]
        key = (pid, team_id, season)
        if key in seen_seasons:
            continue
        seen_seasons.add(key)
        if key not in existing_seasons:
            new_season_tuples.append((pid, team_id, season))
        if pid not in existing_player_ids:
            new_player_ids.add(pid)

    log.info(f"New season records to insert: {len(new_season_tuples)}")
    log.info(f"New players not yet in DB: {len(new_player_ids)}")

    # Step 2: Fetch details for new players
    new_player_details: list[dict] = []
    if new_player_ids:
        log.info(f"\n── Step 2: Fetch player details for {len(new_player_ids)} new players ──")
        details_map = fetch_player_details(sorted(new_player_ids))
        for pid in new_player_ids:
            if pid in details_map:
                new_player_details.append(details_map[pid])
            else:
                # Minimal record from roster data
                names = [r["full_name"] for r in roster_records if r["player_id"] == pid]
                full = names[0] if names else pid
                parts = full.split(None, 1)
                new_player_details.append({
                    "id": pid, "full_name": full,
                    "first_name": parts[0], "last_name": parts[-1],
                    "is_active": True,
                })
        upsert_players(conn, new_player_details)
    else:
        log.info("\n── Step 2: No new players to add ──")

    # Step 3: Insert new player_seasons
    log.info(f"\n── Step 3: Insert {len(new_season_tuples)} new player_season rows ──")
    inserted = insert_player_seasons(conn, new_season_tuples)
    log.info(f"  Inserted {inserted} rows (ON CONFLICT DO NOTHING)")

    rebuild_search_vectors(conn)
    log.info("  Rebuilt search vectors")

    # Step 4: Update graph
    # Always rebuild teammate edges for ALL target seasons from Postgres, not just
    # new_season_tuples. This handles the case where player_seasons already has the
    # records (from a prior run) but the graph was rebuilt from scratch and lacks them.
    log.info("\n── Step 4: Update graph ──")
    team_name_map = get_team_name_map(conn)
    player_name_map: dict[str, str] = {}
    for node, data in G.nodes(data=True):
        if data.get("type") == "player":
            player_name_map[node.split(":", 1)[1]] = data.get("name", "")
    for p in new_player_details:
        player_name_map[p["id"]] = p["full_name"]

    # Build the full set of (player_id, team_id, season) for ALL target seasons
    # so add_seasons_to_graph queries the correct full rosters
    cur = conn.cursor()
    cur.execute(
        "SELECT player_id, team_id, season FROM player_seasons WHERE season = ANY(%s)",
        ([s for s in TOP_UP_SEASONS],),
    )
    all_topup_season_records = [(str(r[0]), int(r[1]), int(r[2])) for r in cur.fetchall()]
    log.info(f"  Rebuilding graph edges for {len(all_topup_season_records)} records in seasons {TOP_UP_SEASONS}")

    edges_added = add_seasons_to_graph(G, all_topup_season_records, team_name_map, player_name_map, conn)

    # Draft class edges for new players
    draft_year_players: dict[int, list[str]] = defaultdict(list)
    for p in new_player_details:
        if p.get("draft_year"):
            draft_year_players[p["draft_year"]].append(p["id"])
    if draft_year_players:
        add_draft_class_edges(G, dict(draft_year_players))

    # Step 5: Save graph
    log.info(f"\n── Step 5: Save graph ──")
    EXPORTS_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPORTS_GRAPH, "wb") as f:
        pickle.dump(G, f)
    with open(BACKEND_GRAPH, "wb") as f:
        pickle.dump(G, f)
    log.info(f"  Saved to {EXPORTS_GRAPH} and {BACKEND_GRAPH}")

    # Step 6: Verify key players
    log.info("\n── Step 6: Verify key modern players ──")
    checks = [
        ("Victor Wembanyama", "1641705", 1610612759, "SAS"),
        ("Cooper Flagg",      "1642277", 1610612738, "BOS"),
        ("Chet Holmgren",     "1631096", 1610612760, "OKC"),
        ("LeBron James",      "2544",    None, None),
        ("Stephen Curry",     "201939",  None, None),
    ]
    cur = conn.cursor()
    all_ok = True
    for name, pid, expected_team, expected_abbr in checks:
        in_graph = G.has_node(f"player:{pid}")
        cur.execute("SELECT COUNT(*) FROM player_seasons WHERE player_id = %s", (pid,))
        season_count = cur.fetchone()[0]
        status = "✅" if in_graph else "❌"
        log.info(f"  {status} {name} ({pid}): in_graph={in_graph}, seasons_in_db={season_count}")
        if not in_graph:
            all_ok = False

    # Edge count by type
    from collections import Counter
    edge_counts = Counter(d.get("type") for _, _, d in G.edges(data=True))
    log.info("\n── Edge counts ──")
    for etype, count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        log.info(f"  {etype}: {count:,}")

    conn.close()

    log.info("\n" + "=" * 60)
    if all_ok:
        log.info("✅ Modern season top-up complete — all key players verified")
    else:
        log.warning("⚠️  Top-up done but some key players still missing")
    log.info(f"Final graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    log.info("Next: run 06_validate_graph.py, then commit backend/graph.pkl")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
