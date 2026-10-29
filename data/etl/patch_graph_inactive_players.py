"""
HOOPCHAIN ETL — Graph Patch: Add teammate edges from inactive_players
=====================================================================
The main ETL (02_build_graph.py) only uses common_player_info for
player-team-season data, which stores ONE team per player (their last
known team).  This misses players like LeBron James (absent from CPI
entirely) and Rajon Rondo (whose CPI entry shows Cleveland, not the
2021-22 Lakers where he and LeBron were teammates).

This patch reads the inactive_players table to extract accurate
player-team-season records and adds any missing teammate edges to the
existing graph.pkl without requiring a full ETL re-run.

Run after 02_build_graph.py to supplement the graph:
    python data/etl/patch_graph_inactive_players.py

Writes to both data/exports/graph.pkl and backend/graph.pkl.
"""

from __future__ import annotations

import logging
import pickle
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
DATA_DIR = ETL_DIR.parent
EXPORTS_DIR = DATA_DIR / "exports"
SQLITE_PATH = EXPORTS_DIR / "nba.sqlite"
GRAPH_PKL_EXPORTS = EXPORTS_DIR / "graph.pkl"
GRAPH_PKL_BACKEND = Path(__file__).parent.parent.parent / "backend" / "graph.pkl"


def teammate_weight(seasons_together: int) -> float:
    if seasons_together >= 5:
        return 0.3
    elif seasons_together >= 2:
        return 0.6
    return 0.9


def load_inactive_player_seasons(sqlite_path: Path) -> tuple[list[dict], dict[int, str]]:
    """
    Extract (player_id, team_id, season_year) from inactive_players + game tables.
    Returns (records, team_id_to_name). Only regular-season records included.
    season_id format: '22021' → season_year = int(season_id[1:5]) = 2021
    """
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT id FROM team")
    valid_team_ids = {int(r[0]) for r in cur.fetchall() if r[0]}

    cur.execute("SELECT id, full_name FROM team WHERE full_name IS NOT NULL")
    team_id_to_name = {int(r[0]): r[1] for r in cur.fetchall() if r[0]}

    cur.execute("SELECT id FROM player WHERE full_name IS NOT NULL")
    valid_player_ids = {str(r[0]) for r in cur.fetchall()}

    logger.info("Querying inactive_players for player-team-season records...")
    cur.execute("""
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

    records = []
    for row in cur.fetchall():
        pid = str(row[0])
        try:
            team_id = int(row[1])
            season_year = int(row[2])
        except (TypeError, ValueError):
            continue
        if pid in valid_player_ids and team_id in valid_team_ids and 1946 <= season_year <= 2030:
            records.append({"player_id": pid, "team_id": team_id, "season": season_year})

    conn.close()
    logger.info(f"Found {len(records)} player-team-season records in inactive_players")
    return records, team_id_to_name


def build_new_edges(G: nx.Graph, inactive_seasons: list[dict], team_id_to_name: dict | None = None) -> list[dict]:
    """
    Group inactive_seasons by (team_id, season) and find player pairs that
    share a team+season but don't yet have a teammate edge in the graph.
    """
    # Group by (team_id, season) → set of player_ids
    team_season_players: dict[tuple, set[str]] = defaultdict(set)
    for rec in inactive_seasons:
        key = (rec["team_id"], rec["season"])
        team_season_players[key].add(rec["player_id"])

    # Track seasons together per pair
    pair_seasons: dict[tuple, list[tuple]] = defaultdict(list)
    for (team_id, season), players in team_season_players.items():
        player_list = sorted(players)
        for a, b in combinations(player_list, 2):
            pair_seasons[(a, b)].append((team_id, season))

    new_edges = []
    existing_edges_added = 0
    for (a, b), team_season_list in pair_seasons.items():
        node_a = f"player:{a}"
        node_b = f"player:{b}"
        if not G.has_node(node_a) or not G.has_node(node_b):
            continue
        if G.has_edge(node_a, node_b):
            existing_edges_added += 1
            continue

        seasons_together = len({s for _, s in team_season_list})
        weight = teammate_weight(seasons_together)
        most_recent = max(team_season_list, key=lambda x: x[1])
        team_id, season = most_recent

        team_name = (team_id_to_name or {}).get(team_id, f"Team {team_id}")
        new_edges.append({
            "node_a": node_a,
            "node_b": node_b,
            "edge_type": "teammate",
            "edge_label": f"{season}-{str(season + 1)[2:]} {team_name} Teammates",
            "weight": weight,
            "metadata": {"team_id": team_id, "season": season, "seasons_together": seasons_together,
                         "source": "inactive_players"},
        })

    logger.info(f"  Pairs already connected: {existing_edges_added}")
    logger.info(f"  New teammate edges to add: {len(new_edges)}")
    return new_edges


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN — Patch graph.pkl with inactive_players edges")
    logger.info("=" * 60)

    if not SQLITE_PATH.exists():
        logger.error(f"SQLite not found: {SQLITE_PATH}")
        return

    # Load existing graph
    pkl_path = GRAPH_PKL_BACKEND if GRAPH_PKL_BACKEND.exists() else GRAPH_PKL_EXPORTS
    logger.info(f"Loading graph from {pkl_path} ...")
    with open(pkl_path, "rb") as f:
        G = pickle.load(f)
    logger.info(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges before patch")

    # Load inactive_players data
    inactive_seasons, team_id_to_name = load_inactive_player_seasons(SQLITE_PATH)

    # Build and add new edges
    new_edges = build_new_edges(G, inactive_seasons, team_id_to_name)

    added = 0
    for e in new_edges:
        G.add_edge(
            e["node_a"], e["node_b"],
            type=e["edge_type"],
            label=e["edge_label"],
            weight=e["weight"],
        )
        added += 1

    logger.info(f"Added {added} new teammate edges")
    logger.info(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges after patch")

    # Verify the key Rondo-LeBron edge
    rondo = "player:200765"
    lebron = "player:2544"
    if G.has_edge(rondo, lebron):
        logger.info(f"  ✅ Rondo-LeBron edge present: {G[rondo][lebron]}")
    else:
        logger.warning("  ⚠ Rondo-LeBron edge still missing after patch!")

    # Check LeBron's new degree
    logger.info(f"  LeBron degree: {G.degree(lebron)} (was 53)")

    # Save to both locations
    for out_path in [GRAPH_PKL_EXPORTS, GRAPH_PKL_BACKEND]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            pickle.dump(G, f)
        logger.info(f"Saved to {out_path}")

    logger.info("=" * 60)
    logger.info("Patch complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
