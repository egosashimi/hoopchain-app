"""
Post-processing patch: add coach nodes and coached_by edges to graph.pkl.

Run after 02_build_graph.py and 03_enrich_coaches.py.
02_build_graph.py truncates graph_edges before re-inserting, which would wipe
any coach edges inserted by 03. This script re-derives coach edges from the
normalized coach_seasons + player_seasons tables (which survive the truncate)
and patches them directly into graph.pkl.
"""

from __future__ import annotations

import logging
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5432/hoopchain")
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

ETL_DIR = Path(__file__).parent
GRAPH_PKL_PATH = ETL_DIR.parent / "exports" / "graph.pkl"


def main():
    import psycopg2

    if not GRAPH_PKL_PATH.exists():
        logger.error(f"graph.pkl not found at {GRAPH_PKL_PATH} — run 02_build_graph.py first")
        sys.exit(1)

    logger.info(f"Loading graph from {GRAPH_PKL_PATH}")
    with open(GRAPH_PKL_PATH, "rb") as f:
        G = pickle.load(f)
    logger.info(f"Graph before patch: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()

    # Add any missing coach nodes
    cur.execute("SELECT id, full_name FROM coaches")
    coaches = cur.fetchall()
    added_nodes = 0
    for coach_id, coach_name in coaches:
        node_key = f"coach:{coach_id}"
        if not G.has_node(node_key):
            G.add_node(node_key, type="coach", name=coach_name)
            added_nodes += 1
    logger.info(f"Added {added_nodes} new coach nodes (total coaches: {len(coaches)})")

    # Derive coach edges from normalized tables
    cur.execute("""
        SELECT
            ps.player_id,
            cs.coach_id,
            t.full_name AS team_name,
            ps.season,
            c.full_name AS coach_name
        FROM player_seasons ps
        JOIN coach_seasons cs ON ps.team_id = cs.team_id AND ps.season = cs.season
        JOIN coaches c ON cs.coach_id = c.id
        JOIN teams t ON ps.team_id = t.id
        WHERE cs.role = 'head_coach'
    """)
    rows = cur.fetchall()
    conn.close()
    logger.info(f"Found {len(rows)} player-coach-season records")

    added_edges = 0
    skipped_missing_node = 0
    for player_id, coach_id, team_name, season, coach_name in rows:
        a = f"player:{player_id}"
        b = f"coach:{coach_id}"
        if not G.has_node(a) or not G.has_node(b):
            skipped_missing_node += 1
            continue
        if not G.has_edge(a, b):
            label = f"Coached by {coach_name} with {team_name} ({season}-{str(season+1)[2:]})"
            G.add_edge(a, b, type="coached_by", label=label, weight=0.7)
            added_edges += 1

    if skipped_missing_node:
        logger.warning(f"Skipped {skipped_missing_node} records — player or coach node missing from graph")

    logger.info(f"Added {added_edges} coach edges to graph")
    logger.info(f"Graph after patch: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    with open(GRAPH_PKL_PATH, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"Saved patched graph to {GRAPH_PKL_PATH}")

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Coach edge patch complete: {added_edges} edges added")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
