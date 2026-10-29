#!/usr/bin/env python3
"""
HOOPCHAIN ETL — Step 13: Fix optimal_hops for all daily_puzzles.

Re-derives optimal_hops using unweighted BFS (len(path)-1 = hop count) for every
row in daily_puzzles. The old 05_generate_puzzles.py used weighted nx.shortest_path
which could return a longer unweighted path when edge weights vary.  This script
resets the column to the true graph-theoretic minimum hop count.

Also updates `available_modes` and `difficulty` to stay consistent with the corrected
hop count.

After running, call the admin flush endpoint to bust the Redis puzzle cache:
    curl -X POST https://hoopchain-backend-production.up.railway.app/admin/flush-puzzle-cache \\
         -H "X-Admin-Key: <API_SECRET_KEY>"

Usage (from repo root):
    python data/etl/13_fix_optimal_hops.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

# Ensure stdout handles Unicode on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
import networkx as nx
import psycopg2

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
GRAPH_PATH = REPO_ROOT / "backend" / "graph.pkl"

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set in data/etl/.env")

MODE_TO_EDGE_TYPE: dict[str, str | None] = {
    "classic": "teammate",
    "wild":    None,
    "coach":   "coached_by",
}

# ---------------------------------------------------------------------------
# Load graph
# ---------------------------------------------------------------------------

if not GRAPH_PATH.exists():
    sys.exit(f"ERROR: graph.pkl not found at {GRAPH_PATH} — run ETL first")

print(f"Loading graph from {GRAPH_PATH} ...")
with open(GRAPH_PATH, "rb") as f:
    G: nx.Graph = pickle.load(f)
print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# Pre-build mode subgraphs (same logic as graph_service.py)
_subgraphs: dict[str, nx.Graph] = {"wild": G}
for mode, edge_type in MODE_TO_EDGE_TYPE.items():
    if edge_type is not None:
        sub_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
        _subgraphs[mode] = G.edge_subgraph(sub_edges)


def bfs_hops(start_id: str, end_id: str, mode: str) -> int | None:
    """Return unweighted hop count between two player IDs in the given mode."""
    a, b = f"player:{start_id}", f"player:{end_id}"
    sub = _subgraphs.get(mode, G)
    if not sub.has_node(a) or not sub.has_node(b):
        return None
    try:
        return nx.shortest_path_length(sub, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def available_modes(start_id: str, end_id: str) -> list[str]:
    return [m for m in ("classic", "wild", "coach") if bfs_hops(start_id, end_id, m) is not None]


def difficulty_for_hops(hops: int) -> str:
    if hops <= 2:
        return "easy"
    if hops <= 3:
        return "medium"
    return "hard"


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute(
    "SELECT id, puzzle_date, start_player_id, end_player_id, optimal_hops, difficulty, available_modes "
    "FROM daily_puzzles ORDER BY puzzle_date"
)
rows = cur.fetchall()
print(f"\nFound {len(rows)} daily_puzzle rows\n")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main(dry_run: bool) -> None:
    changed = 0
    unchanged = 0
    skipped = 0

    for row_id, puzzle_date, start_id, end_id, old_hops, old_diff, old_modes in rows:
        classic = bfs_hops(start_id, end_id, "classic")
        if classic is None:
            print(f"  SKIP puzzle {row_id} ({puzzle_date}): no classic path between {start_id} and {end_id}")
            skipped += 1
            continue

        new_diff  = difficulty_for_hops(classic)
        new_modes = available_modes(start_id, end_id)
        old_modes_set = set(old_modes or [])
        new_modes_set = set(new_modes)

        if classic != old_hops or new_diff != old_diff or new_modes_set != old_modes_set:
            print(
                f"  UPDATE {puzzle_date}: optimal_hops {old_hops}→{classic}  "
                f"difficulty {old_diff}→{new_diff}  "
                f"modes {sorted(old_modes_set)}→{sorted(new_modes_set)}"
            )
            if not dry_run:
                cur.execute(
                    "UPDATE daily_puzzles SET optimal_hops=%s, difficulty=%s, available_modes=%s WHERE id=%s",
                    (classic, new_diff, new_modes, row_id),
                )
            changed += 1
        else:
            unchanged += 1

    if not dry_run:
        conn.commit()
        print(f"\nCommitted. changed={changed}  unchanged={unchanged}  skipped={skipped}")
    else:
        print(f"\nDRY RUN (no writes). would-change={changed}  unchanged={unchanged}  skipped={skipped}")

    print("\nNext step: flush Redis puzzle cache via admin endpoint:")
    print("  curl -X POST <backend_url>/admin/flush-puzzle-cache -H 'X-Admin-Key: <API_SECRET_KEY>'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix optimal_hops in daily_puzzles")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
    cur.close()
    conn.close()
