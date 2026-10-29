#!/usr/bin/env python3
"""
HOOPCHAIN ETL -- Step 15: Pin launch-week daily puzzles (2026-06-05 through 06-11).

Hand-curated marquee pairs verified against graph.pkl BFS.  All pairs have a
clean 2-hop unweighted classic (teammate-only) path.  Script UPSERTs each row
so it works whether the slot is blank or was previously auto-generated.

Usage (from repo root):
    python data/etl/15_pin_launch_week.py [--dry-run]

Requires data/etl/.env with DATABASE_URL pointing to the external proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
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

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set in data/etl/.env")

# Launch-week pinned puzzles (verified 2026-06-05).
# Format: (puzzle_date, start_player_id, end_player_id, notes)
# All pairs confirmed as unweighted GOAT=2 in classic (teammate-only) BFS.
PINNED: list[tuple[str, str, str, str]] = [
    ("2026-06-05", "893",    "2544",   "MJ -> LeBron via Larry Hughes (Wizards + Cavs)"),
    ("2026-06-06", "977",    "2544",   "Kobe -> LeBron via Larry Nance Jr. (Lakers + Cavs)"),
    ("2026-06-07", "893",    "977",    "MJ -> Kobe via Kwame Brown (Wizards + Lakers)"),
    ("2026-06-08", "977",    "1495",   "Kobe -> Duncan via Robert Horry (Lakers + Spurs, 2003 Finals)"),
    ("2026-06-09", "2544",   "201142", "LeBron -> KD via Andrew Bogut (Cavs + Warriors)"),
    ("2026-06-10", "406",    "1495",   "Shaq -> Duncan via Danny Green (Heat + Spurs)"),
    ("2026-06-11", "893",    "1495",   "MJ -> Duncan via Steve Kerr (Bulls + Spurs)"),
]

MODE_EDGE_TYPE: dict[str, str | None] = {
    "classic": "teammate",
    "wild":    None,
    "coach":   "coached_by",
}


# ---------------------------------------------------------------------------
# Load graph & subgraphs
# ---------------------------------------------------------------------------

print(f"Loading graph from {GRAPH_PATH} ...")
with open(GRAPH_PATH, "rb") as f:
    G: nx.Graph = pickle.load(f)
print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges\n")

_subgraphs: dict[str, nx.Graph] = {"wild": G}
for _mode, _etype in MODE_EDGE_TYPE.items():
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


def bfs_path(start_id: str, end_id: str, mode: str) -> list[str]:
    a, b = f"player:{start_id}", f"player:{end_id}"
    sub = _subgraphs.get(mode, G)
    try:
        return nx.shortest_path(sub, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


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
    node_keys = bfs_path(start_id, end_id, "classic")
    if not node_keys:
        return []
    result = []
    for i, nk in enumerate(node_keys):
        ntype, nid = nk.split(":", 1)
        entry: dict = {"type": ntype, "id": nid, "name": G.nodes[nk].get("name", nid)}
        if i < len(node_keys) - 1:
            edata = G[node_keys[i]][node_keys[i + 1]]
            entry["edge_type"] = edata.get("type", "")
            entry["connection_label"] = edata.get("label", "")
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Validate all pinned pairs before touching the DB
# ---------------------------------------------------------------------------

print("=== Validating pinned pairs ===\n")
errors: list[str] = []

for puzzle_date_str, sid, eid, notes in PINNED:
    a_key, b_key = f"player:{sid}", f"player:{eid}"
    a_name = G.nodes[a_key].get("name", sid) if G.has_node(a_key) else "MISSING"
    b_name = G.nodes[b_key].get("name", eid) if G.has_node(b_key) else "MISSING"

    classic_hops = bfs_hops(sid, eid, "classic")
    wild_hops    = bfs_hops(sid, eid, "wild")

    if not G.has_node(a_key) or not G.has_node(b_key):
        errors.append(f"{puzzle_date_str}: MISSING NODE {sid if not G.has_node(a_key) else eid}")
        print(f"  {puzzle_date_str} FAIL: {a_name} -> {b_name} -- missing node")
        continue

    if classic_hops is None:
        errors.append(f"{puzzle_date_str}: {a_name} -> {b_name} has NO classic path")
        print(f"  {puzzle_date_str} FAIL: {a_name} -> {b_name} -- no classic path")
        continue

    if not (2 <= classic_hops <= 3):
        errors.append(f"{puzzle_date_str}: {a_name} -> {b_name} classic hops={classic_hops} (want 2-3)")
        print(f"  {puzzle_date_str} WARN: {a_name} -> {b_name} classic hops={classic_hops} (want 2-3)")
        continue

    path_names = " -> ".join(G.nodes[nk].get("name", nk) for nk in bfs_path(sid, eid, "classic"))
    print(f"  {puzzle_date_str} OK:  {a_name} -> {b_name}  |  classic={classic_hops}h, wild={wild_hops}h")
    print(f"    Path: {path_names}  ({notes})")

print()

if errors:
    for e in errors:
        print(f"ERROR: {e}")
    sys.exit("Aborting — fix errors before writing to DB.")


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

def main(dry_run: bool) -> None:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    for puzzle_date_str, sid, eid, notes in PINNED:
        puzzle_date = date.fromisoformat(puzzle_date_str)
        classic_hops = bfs_hops(sid, eid, "classic")
        assert classic_hops is not None

        diff        = difficulty_for_hops(classic_hops)
        avail_modes = compute_available_modes(sid, eid)
        canonical   = build_canonical_path(sid, eid)
        edge_types  = [n.get("edge_type") for n in canonical if n.get("edge_type")]

        s_name = G.nodes[f"player:{sid}"].get("name", sid)
        e_name = G.nodes[f"player:{eid}"].get("name", eid)
        print(
            f"  {'DRY-RUN ' if dry_run else ''}UPSERT {puzzle_date}: "
            f"{s_name} -> {e_name}  GOAT={classic_hops}, diff={diff}, modes={avail_modes}"
        )

        if not dry_run:
            cur.execute(
                """
                INSERT INTO daily_puzzles
                    (puzzle_date, start_player_id, end_player_id,
                     canonical_path, optimal_hops, difficulty,
                     available_modes, edge_types_used, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (puzzle_date) DO UPDATE SET
                    start_player_id = EXCLUDED.start_player_id,
                    end_player_id   = EXCLUDED.end_player_id,
                    canonical_path  = EXCLUDED.canonical_path,
                    optimal_hops    = EXCLUDED.optimal_hops,
                    difficulty      = EXCLUDED.difficulty,
                    available_modes = EXCLUDED.available_modes,
                    edge_types_used = EXCLUDED.edge_types_used,
                    is_published    = EXCLUDED.is_published
                """,
                (
                    puzzle_date, sid, eid,
                    json.dumps(canonical), classic_hops, diff,
                    avail_modes, edge_types, True,
                ),
            )

    if not dry_run:
        conn.commit()
        print("\nCommitted all pinned puzzles.")
    else:
        print("\n(dry-run: nothing written)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pin launch-week puzzles 2026-06-05 through 06-11")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print plan without DB writes")
    args = parser.parse_args()
    print("=== Upserting pinned puzzles ===\n")
    main(dry_run=args.dry_run)
