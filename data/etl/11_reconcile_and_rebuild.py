"""
HOOPCHAIN ETL — Step 11: Identity Reconciliation + Teammate Edge Rebuild
=========================================================================
Fixes:
  A. Identity reconciliation (Phase 1)
     - Delete ghost node 1631168 ("Chet Holmgren" at wrong ID)
     - Remove misassigned player_seasons rows from wrong patch IDs

  B. Roster backfill (Phase 2 prerequisite)
     - Add Caron Butler (2406) season=2003 on Miami Heat
     - Add Carlos Boozer (2430) season=2014 on LA Lakers
     - Fix Boozer's wrong Utah Jazz rows for 2011-2014 (should be CHI/LAL)
     - Add Boozer CHI seasons 2011-2013

  C. Full teammate edge rebuild (Phase 2)
     - Rebuild ALL teammate edges from authoritative player_seasons in Postgres
     - Replaces both graph_edges (Postgres) and graph.pkl teammate edges
     - Does NOT touch college, draft_class, coached_by, or all_star edges

Run: DATABASE_URL=postgresql://... python data/etl/11_reconcile_and_rebuild.py
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2
import psycopg2.extras
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
EXPORTS_GRAPH = ETL_DIR.parent / "exports" / "graph.pkl"
BACKEND_GRAPH  = ETL_DIR.parent.parent / "backend" / "graph.pkl"

sys.path.insert(0, str(ETL_DIR.parent.parent / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ETL_DIR.parent.parent / "backend" / ".env")
except ImportError:
    pass

RAW_URL = os.getenv("DATABASE_URL")
if not RAW_URL:
    raise SystemExit(
        "DATABASE_URL not set. "
        "Set it in backend/.env or pass it on the command line:\n"
        "  DATABASE_URL=postgresql://... python data/etl/11_reconcile_and_rebuild.py"
    )
PG_URL = RAW_URL.replace("postgresql+asyncpg://", "postgresql://")


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

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

MIA = 1610612748
LAL = 1610612747
CHI = 1610612741
UTA = 1610612762


# ---------------------------------------------------------------------------
# Weight helper
# ---------------------------------------------------------------------------

def teammate_weight(seasons_together: int) -> float:
    if seasons_together >= 5:
        return 0.3
    elif seasons_together >= 2:
        return 0.6
    return 0.9


# ---------------------------------------------------------------------------
# Phase 1-A: Identity reconciliation (DB)
# ---------------------------------------------------------------------------

def phase1_identity_db(conn) -> None:
    """
    Remove ghost node 1631168 and all misassigned player_seasons from the DB.
    Does NOT touch graph.pkl (handled later).
    """
    cur = conn.cursor()
    logger.info("=== Phase 1A: Identity reconciliation (Postgres) ===")

    # --- Delete ghost 1631168 from player_seasons ---
    cur.execute("DELETE FROM player_seasons WHERE player_id = '1631168'")
    logger.info(f"  Deleted {cur.rowcount} player_season rows for ghost 1631168")

    # --- Delete ghost 1631168 from graph_edges (should be 0 but be safe) ---
    cur.execute("""
        DELETE FROM graph_edges
        WHERE node_a_id = '1631168' OR node_b_id = '1631168'
    """)
    logger.info(f"  Deleted {cur.rowcount} graph_edge rows for ghost 1631168")

    # --- Delete ghost player row 1631168 ---
    cur.execute("DELETE FROM players WHERE id = '1631168'")
    logger.info(f"  Deleted {cur.rowcount} player row for ghost 1631168")

    # --- Remove misassigned player_seasons ---
    # 1631096 (Chet Holmgren, OKC): has wrong Indiana Pacers rows
    # Those belong to 1631097 (Bennedict Mathurin) which already has them
    cur.execute("""
        DELETE FROM player_seasons
        WHERE player_id = '1631096' AND team_id = 1610612754
    """)
    logger.info(f"  Removed {cur.rowcount} wrong IND rows from 1631096 (Holmgren)")

    # 1631097 (Bennedict Mathurin, IND): has wrong Houston Rockets rows
    # Those were intended for Jabari Smith Jr. (1631095) which already has HOU rows
    cur.execute("""
        DELETE FROM player_seasons
        WHERE player_id = '1631097' AND team_id = 1610612745
    """)
    logger.info(f"  Removed {cur.rowcount} wrong HOU rows from 1631097 (Mathurin)")

    # 1631098 (Johnny Davis, WAS): has wrong Sacramento Kings rows
    # Those were intended for Keegan Murray (1631099) which already has SAC rows
    cur.execute("""
        DELETE FROM player_seasons
        WHERE player_id = '1631098' AND team_id = 1610612758
    """)
    logger.info(f"  Removed {cur.rowcount} wrong SAC rows from 1631098 (Johnny Davis)")

    # 1631107 (Nikola Jovic, MIA): has wrong Orlando Magic rows
    # Those were intended for Paolo Banchero (1631094) which already has ORL rows
    cur.execute("""
        DELETE FROM player_seasons
        WHERE player_id = '1631107' AND team_id = 1610612753
    """)
    logger.info(f"  Removed {cur.rowcount} wrong ORL rows from 1631107 (Jovic)")

    conn.commit()
    logger.info("  Phase 1A committed.")


# ---------------------------------------------------------------------------
# Phase 1-B: Roster backfill (DB)
# ---------------------------------------------------------------------------

# Missing rows: (player_id, team_id, season)
MISSING_ROSTER_ROWS = [
    # Caron Butler (2406) — MIA 2003-04 season (season=2003)
    ("2406", MIA, 2003),
    # Caron Butler (2406) — WAS 2004-05 season (season=2004, traded Aug 2004)
    ("2406", 1610612764, 2004),  # Washington Wizards
    # Caron Butler (2406) — WAS 2007-08 and 2008-09 (gaps in DB)
    ("2406", 1610612764, 2007),
    ("2406", 1610612764, 2008),

    # Carlos Boozer (2430) — CHI 2011-12, 2012-13, 2013-14 (DB had wrong UTA rows)
    ("2430", CHI, 2011),
    ("2430", CHI, 2012),
    ("2430", CHI, 2013),
    # Carlos Boozer (2430) — LAL 2014-15 (amnestied by CHI July 2014)
    ("2430", LAL, 2014),
]

# Wrong rows to remove for Boozer (DB has UTA rows for years when he was on CHI/LAL)
BOOZER_WRONG_UTA_SEASONS = [2002, 2003, 2010, 2011, 2012, 2013, 2014]
# Note: 2002 and 2003 UTA rows are wrong (Boozer was on CLE those years, not yet on UTA).
# 2010 UTA row is wrong (he signed with CHI; the CHI 2010 row is already correct).
# 2011-2014 UTA rows are wrong (he was on CHI 2011-2013, LAL 2014).


def phase1_roster_backfill(conn) -> None:
    """Add missing roster rows and remove known wrong rows."""
    cur = conn.cursor()
    logger.info("=== Phase 1B: Roster backfill ===")

    # Remove wrong Utah Jazz rows for Boozer
    cur.execute("""
        DELETE FROM player_seasons
        WHERE player_id = '2430' AND team_id = %s AND season = ANY(%s)
    """, (UTA, BOOZER_WRONG_UTA_SEASONS))
    logger.info(f"  Removed {cur.rowcount} wrong UTA rows for Boozer")

    # Insert missing rows
    added = 0
    for (pid, tid, season) in MISSING_ROSTER_ROWS:
        cur.execute("""
            INSERT INTO player_seasons (player_id, team_id, season)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
        """, (pid, tid, season))
        if cur.rowcount:
            added += 1
            pname = {
                "2406": "Caron Butler",
                "2430": "Carlos Boozer",
            }.get(pid, pid)
            tname = TEAM_ID_TO_NAME.get(tid, str(tid))
            logger.info(f"  Added: {pname} on {tname} {season}-{str(season+1)[2:]}")

    conn.commit()
    logger.info(f"  Phase 1B committed. {added} rows added.")


# ---------------------------------------------------------------------------
# Phase 2: Full teammate edge rebuild
# ---------------------------------------------------------------------------

def phase2_rebuild_teammate_edges(conn) -> list[dict]:
    """
    Read all player_seasons from Postgres and rebuild every teammate edge.
    Returns the list of edge dicts (for insertion into graph_edges AND graph.pkl).
    """
    logger.info("=== Phase 2: Teammate edge rebuild ===")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Load all player_seasons
    cur.execute("SELECT player_id, team_id, season FROM player_seasons")
    all_seasons = cur.fetchall()
    logger.info(f"  Loaded {len(all_seasons)} player_season rows from Postgres")

    # Validate: only keep player_ids that actually exist in the players table
    cur.execute("SELECT id FROM players")
    valid_players = {r["id"] for r in cur.fetchall()}

    # Group by (team_id, season)
    team_season_players: dict[tuple, set[str]] = defaultdict(set)
    for row in all_seasons:
        pid = str(row["player_id"])
        if pid not in valid_players:
            continue
        key = (int(row["team_id"]), int(row["season"]))
        team_season_players[key].add(pid)

    logger.info(f"  Grouped into {len(team_season_players)} (team, season) buckets")

    # Accumulate seasons-together per unordered player pair
    pair_seasons: dict[tuple, list[tuple]] = defaultdict(list)
    for (team_id, season), players in team_season_players.items():
        player_list = sorted(players)
        for a, b in combinations(player_list, 2):
            pair_seasons[(a, b)].append((team_id, season))

    logger.info(f"  Generated {len(pair_seasons)} unique player pairs")

    # Build edge records
    edges = []
    for (a, b), team_seasons in pair_seasons.items():
        unique_seasons = {s for _, s in team_seasons}
        seasons_together = len(unique_seasons)
        weight = teammate_weight(seasons_together)

        # Most recent (team, season) for label
        most_recent = max(team_seasons, key=lambda x: x[1])
        team_id, season = most_recent
        team_name = TEAM_ID_TO_NAME.get(team_id, f"Team {team_id}")

        edges.append({
            "node_a_type": "player", "node_a_id": a,
            "node_b_type": "player", "node_b_id": b,
            "edge_type": "teammate",
            "edge_label": f"{season}-{str(season + 1)[2:]} {team_name} Teammates",
            "weight": weight,
            "metadata": {
                "team_id": team_id,
                "season": season,
                "seasons_together": seasons_together,
            },
        })

    logger.info(f"  Built {len(edges)} teammate edges")
    return edges


def phase2_insert_teammate_edges_pg(conn, edges: list[dict]) -> None:
    """Replace all teammate edges in Postgres graph_edges with the new set."""
    cur = conn.cursor()
    logger.info("  Replacing teammate edges in Postgres graph_edges...")

    cur.execute("DELETE FROM graph_edges WHERE edge_type = 'teammate'")
    logger.info(f"  Deleted old teammate edges from Postgres")

    rows = [
        (
            e["node_a_type"], e["node_a_id"],
            e["node_b_type"], e["node_b_id"],
            e["edge_type"], e["edge_label"],
            e["weight"], json.dumps(e.get("metadata", {})),
        )
        for e in edges
    ]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO graph_edges
            (node_a_type, node_a_id, node_b_type, node_b_id,
             edge_type, edge_label, weight, metadata)
        VALUES %s
    """, rows, page_size=5000)

    conn.commit()
    logger.info(f"  Inserted {len(edges)} new teammate edges into Postgres")


# ---------------------------------------------------------------------------
# Phase 2: graph.pkl update
# ---------------------------------------------------------------------------

def phase2_update_graph_pkl(edges: list[dict]) -> None:
    """
    Load graph.pkl, remove ghost node 1631168 and all teammate edges,
    add new teammate edges, save both pkl copies.
    """
    logger.info("=== Phase 2: Update graph.pkl ===")

    # Determine which pkl to load (prefer exports, fall back to backend)
    pkl_path = EXPORTS_GRAPH if EXPORTS_GRAPH.exists() else BACKEND_GRAPH
    logger.info(f"  Loading graph from {pkl_path}...")

    with open(pkl_path, "rb") as f:
        G: nx.Graph = pickle.load(f)

    logger.info(f"  Graph before: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # --- Remove ghost node ---
    ghost = "player:1631168"
    if G.has_node(ghost):
        G.remove_node(ghost)
        logger.info("  Removed ghost node player:1631168")
    else:
        logger.info("  Ghost node player:1631168 not found (already absent)")

    # --- Remove all teammate edges ---
    teammate_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("type") == "teammate"
    ]
    G.remove_edges_from(teammate_edges)
    logger.info(f"  Removed {len(teammate_edges)} old teammate edges from graph")

    # --- Add new teammate edges ---
    # Ensure player nodes exist for any player_id in new edges
    added_nodes = 0
    skipped = 0
    added_edges = 0

    for e in edges:
        na = f"player:{e['node_a_id']}"
        nb = f"player:{e['node_b_id']}"

        # Skip if either node doesn't exist (ghost IDs, validation)
        if not G.has_node(na) or not G.has_node(nb):
            skipped += 1
            continue

        G.add_edge(
            na, nb,
            type="teammate",
            label=e["edge_label"],
            weight=e["weight"],
        )
        added_edges += 1

    logger.info(f"  Added {added_edges} new teammate edges ({skipped} skipped — node missing)")

    logger.info(f"  Graph after: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # --- Edge type breakdown ---
    from collections import Counter
    counts = Counter(d.get("type") for _, _, d in G.edges(data=True))
    for etype, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        logger.info(f"    {etype}: {cnt:,}")

    # --- Save ---
    EXPORTS_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPORTS_GRAPH, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"  Saved to {EXPORTS_GRAPH}")

    with open(BACKEND_GRAPH, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"  Saved to {BACKEND_GRAPH}")

    return G


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(G: nx.Graph, conn) -> None:
    logger.info("=== Phase 5: Verification ===")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    POSITIVE = [
        ("2548", "2406", "Dwyane Wade <-> Caron Butler (2003-04 MIA)"),
        ("977",  "2430", "Kobe Bryant <-> Carlos Boozer (2014-15 LAL)"),
        ("2544", "2430", "LeBron James <-> Carlos Boozer (2003-04 CLE)"),
    ]
    # Negative: no TEAMMATE edge (Kobe/Yao were never on the same team)
    NEGATIVE = [
        ("977",  "2397", "Kobe Bryant <-> Yao Ming (no teammate edge)"),
    ]
    DEDUP = [
        ("1631096", "Chet Holmgren"),
        ("1641705", "Victor Wembanyama"),
        ("1642277", "Cooper Flagg"),
    ]

    all_ok = True

    for a, b, label in POSITIVE:
        na, nb = f"player:{a}", f"player:{b}"
        ok = G.has_edge(na, nb)
        edge_data = G[na][nb] if ok else {}
        sym = "PASS" if ok else "FAIL"
        logger.info(f"  [{sym}] {label}  edge_label={edge_data.get('label', 'N/A')[:60]}")
        if not ok:
            all_ok = False

    for a, b, label in NEGATIVE:
        na, nb = f"player:{a}", f"player:{b}"
        # Only verify no TEAMMATE edge (other edge types like all_star are ok if they existed before)
        has_teammate = G.has_edge(na, nb) and G[na][nb].get("type") == "teammate"
        ok = not has_teammate
        sym = "PASS" if ok else "FAIL"
        logger.info(f"  [{sym}] {label}")
        if not ok:
            all_ok = False

    for pid, name in DEDUP:
        cur.execute("SELECT id, full_name FROM players WHERE lower(full_name) = lower(%s)", (name,))
        rows = cur.fetchall()
        sym = "PASS" if len(rows) == 1 else "FAIL"
        logger.info(f"  [{sym}] {name}: {len(rows)} node(s) in DB  ids={[r['id'] for r in rows]}")
        if len(rows) != 1:
            all_ok = False

    # Check Yao Ming specifically — should exist as player but not connected to Kobe
    cur.execute("SELECT id, full_name FROM players WHERE lower(full_name) ILIKE '%yao ming%'")
    yao = cur.fetchall()
    if not yao:
        logger.info("  [INFO] Yao Ming not in players table — negative check is vacuously true")

    logger.info(f"\n  {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL Step 11: Reconcile + Rebuild")
    logger.info("=" * 60)

    conn = psycopg2.connect(PG_URL)
    conn.autocommit = False

    # Phase 1A: Identity reconciliation (Postgres)
    phase1_identity_db(conn)

    # Phase 1B: Roster backfill (Postgres)
    phase1_roster_backfill(conn)

    # Phase 2: Build new teammate edges from authoritative player_seasons
    new_edges = phase2_rebuild_teammate_edges(conn)

    # Phase 2: Replace teammate edges in Postgres
    phase2_insert_teammate_edges_pg(conn, new_edges)

    # Phase 2: Update graph.pkl
    G = phase2_update_graph_pkl(new_edges)

    # Verify
    all_ok = verify(G, conn)

    conn.close()

    logger.info("=" * 60)
    logger.info("Step 11 complete.")
    logger.info(f"Final graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    logger.info(f"Teammate edges in Postgres: {len(new_edges)}")
    if all_ok:
        logger.info("All verification checks PASSED.")
    else:
        logger.warning("Some verification checks FAILED — review output above.")
    logger.info("Next: run 06_validate_graph.py, then 07_seed_players_table.py, then commit.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
