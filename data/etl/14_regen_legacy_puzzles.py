#!/usr/bin/env python3
"""
HOOPCHAIN ETL — Step 14: Replace legacy-ID future puzzles.

13_fix_optimal_hops.py skipped rows whose player IDs are absent from the
post-W1 graph (old Balldontlie IDs, etc.).  This script:
  1. Finds every future-dated daily_puzzle (puzzle_date >= today) whose
     start_player_id or end_player_id is missing from graph.pkl.
  2. Replaces each broken row with a fresh pair sampled from the
     famous_players seed (filtered to IDs in graph), ensuring:
       - valid classic path (GOAT 2–5 hops, unweighted BFS)
       - no pair reused with another future puzzle
       - optimal_hops / difficulty / available_modes re-derived from graph
  3. Prints a final assertion: zero future puzzles reference an ID absent
     from the graph.

Usage (from repo root):
    python data/etl/14_regen_legacy_puzzles.py [--dry-run]

Requires data/etl/.env with DATABASE_URL pointing to the external proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import sys
from datetime import date
from pathlib import Path

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
FAMOUS_PATH = REPO_ROOT / "data" / "seeds" / "famous_players.json"

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
    sys.exit(f"ERROR: graph.pkl not found at {GRAPH_PATH}")

print(f"Loading graph from {GRAPH_PATH} ...")
with open(GRAPH_PATH, "rb") as f:
    G: nx.Graph = pickle.load(f)
print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# Pre-build mode subgraphs
_subgraphs: dict[str, nx.Graph] = {"wild": G}
for _mode, _etype in MODE_TO_EDGE_TYPE.items():
    if _etype is not None:
        _edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == _etype]
        _subgraphs[_mode] = G.edge_subgraph(_edges)


def bfs_hops(start_id: str, end_id: str, mode: str) -> int | None:
    a, b = f"player:{start_id}", f"player:{end_id}"
    sub = _subgraphs.get(mode, G)
    if not sub.has_node(a) or not sub.has_node(b):
        return None
    try:
        return nx.shortest_path_length(sub, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def compute_available_modes(start_id: str, end_id: str) -> list[str]:
    return [m for m in ("classic", "wild", "coach") if bfs_hops(start_id, end_id, m) is not None]


def difficulty_for_hops(hops: int) -> str:
    if hops <= 2:
        return "easy"
    if hops <= 3:
        return "medium"
    return "hard"


def build_canonical_path(start_id: str, end_id: str) -> list[dict]:
    """BFS path in classic (teammate) mode as a minimal JSON array."""
    a, b = f"player:{start_id}", f"player:{end_id}"
    sub = _subgraphs.get("classic", G)
    try:
        path = nx.shortest_path(sub, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    result = []
    for i, node_key in enumerate(path):
        ntype, nid = node_key.split(":", 1)
        entry: dict = {"type": ntype, "id": nid, "name": G.nodes[node_key].get("name", nid)}
        if i < len(path) - 1:
            edata = G[path[i]][path[i + 1]]
            entry["edge_type"] = edata.get("type", "")
            entry["connection_label"] = edata.get("label", "")
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Load famous players seed
# ---------------------------------------------------------------------------

with open(FAMOUS_PATH) as f:
    _seed = json.load(f)

ALL_FAMOUS_IDS: list[str] = [p["id"] for p in _seed["players"]]
# Keep only those that exist as nodes in the current graph
VALID_FAMOUS_IDS: list[str] = [pid for pid in ALL_FAMOUS_IDS if G.has_node(f"player:{pid}")]
print(f"Famous players in seed: {len(ALL_FAMOUS_IDS)}, in graph: {len(VALID_FAMOUS_IDS)}")

if len(VALID_FAMOUS_IDS) < 10:
    sys.exit("ERROR: Too few valid famous players in graph — check ETL")


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

today = date.today()

cur.execute(
    "SELECT id, puzzle_date, start_player_id, end_player_id, optimal_hops, difficulty, available_modes "
    "FROM daily_puzzles WHERE puzzle_date >= %s ORDER BY puzzle_date",
    (today,),
)
future_rows = cur.fetchall()
print(f"\nFuture daily_puzzle rows (>= {today}): {len(future_rows)}")


# ---------------------------------------------------------------------------
# Identify broken rows
# ---------------------------------------------------------------------------

def in_graph(player_id: str) -> bool:
    return G.has_node(f"player:{player_id}")


broken: list[tuple] = [
    row for row in future_rows
    if not in_graph(row[2]) or not in_graph(row[3])
]
valid_future: list[tuple] = [row for row in future_rows if row not in broken]

print(f"  Good rows: {len(valid_future)}")
print(f"  Broken rows (legacy IDs): {len(broken)}")

if not broken:
    print("\nNo broken rows — nothing to replace.")
else:
    for row in broken:
        _, pd, sid, eid, *_ = row
        missing = []
        if not in_graph(sid):
            missing.append(f"start={sid}")
        if not in_graph(eid):
            missing.append(f"end={eid}")
        print(f"  BROKEN {pd}: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Generate replacement pairs
# ---------------------------------------------------------------------------

def pick_replacement(
    used_pairs: set[tuple[str, str]],
    max_attempts: int = 2000,
) -> tuple[str, str] | None:
    """
    Sample pairs from VALID_FAMOUS_IDS until we find one with a classic path
    of 2–5 hops that hasn't been used yet.
    """
    pool = VALID_FAMOUS_IDS.copy()
    random.shuffle(pool)
    attempts = 0
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if attempts >= max_attempts:
                return None
            attempts += 1
            pair = (min(a, b), max(a, b))
            if pair in used_pairs:
                continue
            hops = bfs_hops(a, b, "classic")
            if hops is None or not (2 <= hops <= 5):
                continue
            return (a, b)
    return None


def main(dry_run: bool) -> None:
    if not broken:
        print("\nNothing to do.")
        _assert_all_valid(dry_run=True)
        return

    # Collect pairs already committed in good future rows so we don't reuse them
    used_pairs: set[tuple[str, str]] = {
        (min(row[2], row[3]), max(row[2], row[3]))
        for row in valid_future
    }

    replaced = 0
    failed = 0

    for row in broken:
        row_id, puzzle_date, old_start, old_end, *_ = row

        pair = pick_replacement(used_pairs)
        if pair is None:
            print(f"  FAIL {puzzle_date}: could not find a valid replacement pair")
            failed += 1
            continue

        new_start, new_end = pair
        classic_hops = bfs_hops(new_start, new_end, "classic")
        assert classic_hops is not None
        new_diff = difficulty_for_hops(classic_hops)
        new_modes = compute_available_modes(new_start, new_end)
        canonical = build_canonical_path(new_start, new_end)

        start_name = G.nodes[f"player:{new_start}"].get("name", new_start)
        end_name   = G.nodes[f"player:{new_end}"].get("name", new_end)

        print(
            f"  {'DRY-RUN ' if dry_run else ''}UPDATE {puzzle_date}: "
            f"{old_start}/{old_end} → {new_start}/{new_end} "
            f"({start_name} → {end_name}, GOAT={classic_hops}, diff={new_diff})"
        )

        if not dry_run:
            cur.execute(
                """UPDATE daily_puzzles
                   SET start_player_id=%s, end_player_id=%s,
                       canonical_path=%s, optimal_hops=%s,
                       difficulty=%s, available_modes=%s, edge_types_used=%s
                   WHERE id=%s""",
                (
                    new_start, new_end,
                    json.dumps(canonical),
                    classic_hops, new_diff, new_modes,
                    [n.get("edge_type") for n in canonical if n.get("edge_type")],
                    row_id,
                ),
            )
        used_pairs.add(pair)
        replaced += 1

    if not dry_run:
        conn.commit()
        print(f"\nCommitted: replaced={replaced}, failed={failed}")
    else:
        print(f"\nDRY RUN (no writes): would-replace={replaced}, failed={failed}")

    _assert_all_valid(dry_run)


def _assert_all_valid(dry_run: bool) -> None:
    """Re-query future rows and assert all player IDs are in the graph."""
    cur.execute(
        "SELECT puzzle_date, start_player_id, end_player_id FROM daily_puzzles WHERE puzzle_date >= %s",
        (today,),
    )
    rows = cur.fetchall()
    bad = [
        (pd, sid, eid)
        for pd, sid, eid in rows
        if not in_graph(sid) or not in_graph(eid)
    ]
    print("\n--- ASSERTION ---")
    if bad:
        print(f"FAIL: {len(bad)} future puzzle(s) still have invalid IDs:")
        for pd, sid, eid in bad:
            print(f"  {pd}: start={sid} ({'OK' if in_graph(sid) else 'MISSING'}) "
                  f"end={eid} ({'OK' if in_graph(eid) else 'MISSING'})")
        if not dry_run:
            sys.exit(1)
    else:
        print(f"PASS: all {len(rows)} future puzzle(s) have valid player IDs in graph")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replace legacy-ID future daily puzzles")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing to DB")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
    cur.close()
    conn.close()
