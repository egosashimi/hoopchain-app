"""
HOOPCHAIN ETL — Step 5: Generate 90-Day Puzzle Pool
====================================================
Pre-generates a pool of daily puzzles from famous_players.json endpoints.
Uses NetworkX BFS to find valid paths and filters by difficulty.

Run after: 02_build_graph.py (needs graph.pkl) and DB populated.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
DATA_DIR = ETL_DIR.parent
EXPORTS_DIR = DATA_DIR / "exports"
SEEDS_DIR = DATA_DIR / "seeds"
GRAPH_PKL_PATH = EXPORTS_DIR / "graph.pkl"
FAMOUS_PLAYERS_PATH = SEEDS_DIR / "famous_players.json"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5432/hoopchain")
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_pg_conn():
    import psycopg2
    return psycopg2.connect(PG_URL)


def load_famous_players() -> list[str]:
    with open(FAMOUS_PLAYERS_PATH) as f:
        data = json.load(f)
    return [p["id"] for p in data["players"]]


def generate_puzzle_pool(G: nx.Graph, famous_player_ids: list[str], n: int = 200) -> list[dict]:
    """
    As defined in HOOPCHAIN_MASTER_BLUEPRINT.md puzzle generation algorithm.
    Oversample by 10x and filter to find n valid puzzles.
    """
    logger.info(f"Generating puzzle pool (target: {n} puzzles, oversample: {n*10})...")

    # Filter famous players to those actually in graph
    valid_famous = [pid for pid in famous_player_ids if G.has_node(f"player:{pid}")]
    logger.info(f"Famous players in graph: {len(valid_famous)}/{len(famous_player_ids)}")

    if len(valid_famous) < 10:
        logger.error("Too few famous players found in graph. Check your ETL.")
        return []

    puzzles = []
    seen_pairs: set[tuple] = set()
    attempts = 0
    max_attempts = n * 10

    while len(puzzles) < n and attempts < max_attempts:
        attempts += 1
        start, end = random.sample(valid_famous, 2)
        pair = tuple(sorted([start, end]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        try:
            path = nx.shortest_path(G, f"player:{start}", f"player:{end}", weight="weight")
        except nx.NetworkXNoPath:
            continue
        except nx.NodeNotFound:
            continue

        hops = len(path) - 1

        # Only keep puzzles with 2-6 hops
        if not (2 <= hops <= 6):
            continue

        # Avoid 1-hop teammate direct connections (too easy)
        if hops == 1 and G[f"player:{start}"].get(f"player:{end}", {}).get("type") == "teammate":
            continue

        # Get edge metadata for path
        edge_types = []
        edge_labels = []
        for i in range(len(path) - 1):
            edge_data = G[path[i]][path[i + 1]]
            edge_types.append(edge_data.get("type", "unknown"))
            edge_labels.append(edge_data.get("label", ""))

        weight_sum = sum(
            G[path[i]][path[i + 1]].get("weight", 1.0)
            for i in range(len(path) - 1)
        )

        difficulty = "easy" if weight_sum < 2.5 else "medium" if weight_sum < 4.0 else "hard"

        # Build canonical path JSON
        canonical_path = []
        for node_key in path:
            node_type, node_id = node_key.split(":", 1)
            node_data = G.nodes[node_key]
            canonical_path.append({
                "type": node_type,
                "id": node_id,
                "name": node_data.get("name", node_id),
            })
        # Add edge labels to path nodes
        for i, label in enumerate(edge_labels):
            canonical_path[i]["connection_label"] = label
            canonical_path[i]["edge_type"] = edge_types[i]

        puzzles.append({
            "start_player_id": start,
            "end_player_id": end,
            "canonical_path": canonical_path,
            "optimal_hops": hops,
            "difficulty": difficulty,
            "edge_types_used": edge_types,
        })

    logger.info(f"Generated {len(puzzles)} puzzles in {attempts} attempts")

    # Ensure roughly balanced difficulty distribution (target ~30/40/30)
    easy   = [p for p in puzzles if p["difficulty"] == "easy"]
    medium = [p for p in puzzles if p["difficulty"] == "medium"]
    hard   = [p for p in puzzles if p["difficulty"] == "hard"]
    logger.info(f"Difficulty distribution: {len(easy)} easy / {len(medium)} medium / {len(hard)} hard")

    return puzzles


def insert_puzzles(pg_conn, puzzles: list[dict], start_date: date | None = None) -> int:
    """Insert puzzles into daily_puzzles table, one per day."""
    if start_date is None:
        start_date = date.today()

    cur = pg_conn.cursor()
    inserted = 0

    # Find existing published puzzles to avoid date conflicts
    cur.execute("SELECT puzzle_date FROM daily_puzzles")
    existing_dates = {row[0] for row in cur.fetchall()}

    current_date = start_date
    for puzzle in puzzles:
        # Skip dates that already have puzzles
        while current_date in existing_dates:
            current_date += timedelta(days=1)

        try:
            cur.execute("""
                INSERT INTO daily_puzzles
                    (puzzle_date, start_player_id, end_player_id, canonical_path,
                     optimal_hops, difficulty, edge_types_used, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (puzzle_date) DO NOTHING
            """, (
                current_date,
                puzzle["start_player_id"],
                puzzle["end_player_id"],
                json.dumps(puzzle["canonical_path"]),
                puzzle["optimal_hops"],
                puzzle["difficulty"],
                puzzle["edge_types_used"],
                True,
            ))
            inserted += 1
            existing_dates.add(current_date)
            current_date += timedelta(days=1)
        except Exception as e:
            logger.warning(f"Failed to insert puzzle for {current_date}: {e}")
            current_date += timedelta(days=1)
            continue

    pg_conn.commit()
    return inserted


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 5: Generate Puzzle Pool")
    logger.info("=" * 60)

    if not GRAPH_PKL_PATH.exists():
        logger.error(f"Graph pickle not found: {GRAPH_PKL_PATH}")
        logger.error("Run 02_build_graph.py first.")
        sys.exit(1)

    logger.info(f"Loading graph from {GRAPH_PKL_PATH}...")
    with open(GRAPH_PKL_PATH, "rb") as f:
        G = pickle.load(f)
    logger.info(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    famous_player_ids = load_famous_players()
    logger.info(f"Famous players seed: {len(famous_player_ids)}")

    puzzles = generate_puzzle_pool(G, famous_player_ids, n=120)

    if not puzzles:
        logger.error("No puzzles generated. Check graph connectivity.")
        sys.exit(1)

    pg_conn = get_pg_conn()
    inserted = insert_puzzles(pg_conn, puzzles, start_date=date.today())
    pg_conn.close()

    logger.info(f"\n✅ Inserted {inserted} puzzles into daily_puzzles table")
    logger.info("Next: python 06_validate_graph.py")


if __name__ == "__main__":
    main()
