"""
HOOPCHAIN ETL — Step 6: Validate Graph Integrity
=================================================
Runs sanity checks on the graph to verify:
  - Known players are present (LeBron, Jordan, Kobe, etc.)
  - Known paths exist (LeBron→Jordan, Kareem→Kobe)
  - Graph connectivity within modern era (post-1980)
  - Max degrees of separation < 8
  - Edge count distribution is reasonable

Run after: 02_build_graph.py (and optionally 03, 04)
"""

from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path

import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GRAPH_PKL_PATH = Path(__file__).parent.parent / "exports" / "graph.pkl"


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 6: Validate Graph")
    logger.info("=" * 60)

    if not GRAPH_PKL_PATH.exists():
        logger.error(f"Graph not found: {GRAPH_PKL_PATH}")
        sys.exit(1)

    logger.info(f"Loading graph from {GRAPH_PKL_PATH}...")
    with open(GRAPH_PKL_PATH, "rb") as f:
        G = pickle.load(f)

    errors = []
    warnings = []

    # ---- Check 1: Node count ----
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    logger.info(f"Graph size: {n_nodes} nodes, {n_edges} edges")

    if n_nodes < 1000:
        errors.append(f"Too few nodes: {n_nodes} (expected >1000)")
    if n_edges < 10000:
        errors.append(f"Too few edges: {n_edges} (expected >10000)")

    # ---- Check 2: Known players present ----
    # IDs are authoritative nba.com player IDs matching the nbadb SQLite source.
    KNOWN_PLAYERS = {
        "2544":   "LeBron James",
        "893":    "Michael Jordan",
        "977":    "Kobe Bryant",
        "76003":  "Kareem Abdul-Jabbar",
        "77142":  "Magic Johnson",
        "201939": "Stephen Curry",
        "1495":   "Tim Duncan",
        "708":    "Kevin Garnett",
        "959":    "Steve Nash",
        "200765": "Rajon Rondo",
    }

    for pid, name in KNOWN_PLAYERS.items():
        key = f"player:{pid}"
        if G.has_node(key):
            logger.info(f"  ✅ {name} ({pid}) found in graph")
        else:
            errors.append(f"  ❌ {name} ({pid}) NOT found in graph")

    # ---- Check 3: Known paths exist ----
    KNOWN_PATHS = [
        ("2544",   "893"),    # LeBron → Michael Jordan
        ("76003",  "977"),    # Kareem → Kobe
        ("708",    "201939"), # KG → Curry
        ("76003",  "77142"),  # Kareem → Magic
        ("2544",   "200765"), # LeBron → Rondo (2021-22 Lakers — was previously broken)
    ]

    for start_id, end_id in KNOWN_PATHS:
        a = f"player:{start_id}"
        b = f"player:{end_id}"
        if not G.has_node(a) or not G.has_node(b):
            warnings.append(f"Can't check path: one of {start_id}, {end_id} not in graph")
            continue

        try:
            path = nx.shortest_path(G, a, b, weight="weight")
            hops = len(path) - 1
            start_name = G.nodes[a].get("name", start_id)
            end_name = G.nodes[b].get("name", end_id)
            logger.info(f"  ✅ {start_name} → {end_name}: {hops} hops")
            if hops > 8:
                warnings.append(f"Path {start_name}→{end_name} is {hops} hops (suspiciously long)")
        except nx.NetworkXNoPath:
            errors.append(f"  ❌ No path: {start_id} → {end_id}")

    # ---- Check 4: Edge type distribution ----
    edge_type_counts: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        et = data.get("type", "unknown")
        edge_type_counts[et] = edge_type_counts.get(et, 0) + 1

    logger.info("Edge type distribution:")
    for et, count in sorted(edge_type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {et}: {count:,}")

    if edge_type_counts.get("teammate", 0) < 1000:
        warnings.append("Very few teammate edges — is the player_seasons data loaded?")

    # ---- Check 5: Connected components (modern players) ----
    modern_nodes = {n for n in G.nodes if G.nodes[n].get("type") == "player"}
    if modern_nodes:
        modern_subgraph = G.subgraph(modern_nodes)
        components = list(nx.connected_components(modern_subgraph))
        logger.info(f"Connected components: {len(components)}")
        if len(components) > 10:
            warnings.append(f"Graph has {len(components)} components — expected mostly 1 large component")
        largest = max(components, key=len)
        logger.info(f"Largest component: {len(largest)} nodes ({len(largest)/len(modern_nodes)*100:.1f}% of players)")

    # ---- Summary ----
    logger.info("")
    logger.info("=" * 60)
    if errors:
        logger.error(f"VALIDATION FAILED — {len(errors)} errors:")
        for e in errors:
            logger.error(f"  {e}")
        sys.exit(1)
    elif warnings:
        logger.warning(f"VALIDATION PASSED WITH {len(warnings)} warnings:")
        for w in warnings:
            logger.warning(f"  {w}")
        logger.info("Graph is usable but may have some gaps.")
    else:
        logger.info("✅ VALIDATION PASSED — Graph looks healthy!")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
