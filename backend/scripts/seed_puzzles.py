"""
Seed daily_puzzles table — idempotent, safe to run on every deploy.

Generates 120 puzzles using the deployed graph.pkl and inserts them
starting from today, skipping any dates that already have a puzzle.
Exits with code 0 whether or not new rows were inserted.

Endpoint quality: START and END players must have recognizability_score >= 15
(from the players table). Falls back to a hardcoded famous-player list if the
column is not yet populated.

Usage (Railway pre-deploy or one-off):
    python scripts/seed_puzzles.py

Replace low-quality existing puzzles (next 90 days):
    REPLACE_LOW_QUALITY=1 python scripts/seed_puzzles.py
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import random
from datetime import date, timedelta
from pathlib import Path

import networkx as nx
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode availability helpers
# ---------------------------------------------------------------------------

VALID_MODES = ["classic", "wild", "coach"]

MODE_TO_EDGE_TYPE: dict[str, str | None] = {
    "classic": "teammate",
    "wild":    None,
    "coach":   "coached_by",
}


def compute_available_modes(G: nx.Graph, start_id: str, end_id: str) -> list[str]:
    """Return which game modes have a valid path between start_id and end_id."""
    a = f"player:{start_id}"
    b = f"player:{end_id}"
    if not G.has_node(a) or not G.has_node(b):
        return []

    available: list[str] = []
    for mode in VALID_MODES:
        edge_type = MODE_TO_EDGE_TYPE[mode]
        try:
            if edge_type is None:
                nx.shortest_path(G, a, b, weight="weight")
            else:
                sub_edges = [
                    (u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type
                ]
                if not sub_edges:
                    continue
                subgraph = G.edge_subgraph(sub_edges)
                nx.shortest_path(subgraph, a, b)
            available.append(mode)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    return available

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GRAPH_PKL_PATH = Path(os.getenv("GRAPH_PICKLE_PATH", "/app/graph.pkl"))

_raw_db = os.getenv("DATABASE_URL", "")
DATABASE_URL = (
    _raw_db.replace("postgresql+asyncpg://", "postgresql://")
    if "postgresql+asyncpg://" in _raw_db
    else _raw_db.replace("postgres://", "postgresql://", 1)
    if _raw_db.startswith("postgres://")
    else _raw_db
)

TARGET_PUZZLES = 120
MIN_RECOGNIZABILITY = 15  # minimum score for START/END endpoint players

# Fallback famous player list used when recognizability_score is not populated.
FAMOUS_PLAYER_IDS = [
    # Classic era
    "76003", "77142", "77449", "76375", "77146", "77404", "77455", "77816",
    "78498", "78497", "77967", "78022", "78118", "77948", "165", "250",
    "174",
    # 1990s-2000s
    "893",    # Michael Jordan
    "977",    # Kobe Bryant
    "406",    # Shaquille O'Neal
    "959",    # Steve Nash
    "708",    # Kevin Garnett
    "947",    # Allen Iverson
    "1495",   # Tim Duncan
    "1478",   # Ray Allen
    "1717",   # Dirk Nowitzki
    "1718",   # Paul Pierce
    "1894",   # Vince Carter
    "2548",   # Dwyane Wade
    "2730",   # Dwight Howard
    "101108", # Chris Paul
    "2404",   # Chauncey Billups
    "2546",   # Carmelo Anthony
    "101114", # Deron Williams
    "2199",   # Baron Davis
    "2509",   # Tony Parker
    "2216",   # Manu Ginobili
    "200765", # Rajon Rondo
    # Modern era
    "2544",   # LeBron James
    "201150", # Kevin Love
    "201566", "201142", "201935", "201939", "201950", "201580",
    "201609", "202681", "202691", "203076", "203081", "203110", "203114",
    "203507", "203897", "203932", "203944", "203952", "203954", "203994",
    "203999", "1626164", "1628366", "1628369", "1628384", "1628386",
    "1629011", "1629027", "1629029", "1629628", "1629630", "1630162",
    "1630169", "1630178", "1630595", "1631093", "1631094", "1630596",
    # Recent stars
    "1641705",  # Victor Wembanyama
    "1628973",  # Luka Doncic
    "1631107",  # Paolo Banchero
]


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def load_graph() -> nx.Graph:
    if not GRAPH_PKL_PATH.exists():
        raise FileNotFoundError(f"graph.pkl not found at {GRAPH_PKL_PATH}")
    log.info(f"Loading graph from {GRAPH_PKL_PATH} …")
    with open(GRAPH_PKL_PATH, "rb") as f:
        return pickle.load(f)


def load_eligible_player_ids(conn, G: nx.Graph) -> list[str]:
    """
    Return player IDs eligible as puzzle endpoints.
    Uses recognizability_score >= MIN_RECOGNIZABILITY from the players table.
    Falls back to FAMOUS_PLAYER_IDS if the score column isn't populated.
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id FROM players
            WHERE recognizability_score >= %s
        """, (MIN_RECOGNIZABILITY,))
        rows = cur.fetchall()
        if rows:
            ids = [row[0] for row in rows]
            log.info(f"Loaded {len(ids)} players with recognizability_score >= {MIN_RECOGNIZABILITY}")
            # Filter to only those actually in the graph
            valid = [pid for pid in ids if G.has_node(f"player:{pid}")]
            log.info(f"  {len(valid)}/{len(ids)} are present in graph")
            if len(valid) >= 20:
                return valid
            log.warning("Too few scored players in graph; falling back to hardcoded list")
    except Exception as e:
        log.warning(f"Could not load recognizability scores: {e}")

    # Fallback
    valid = [pid for pid in FAMOUS_PLAYER_IDS if G.has_node(f"player:{pid}")]
    log.info(f"Fallback: {len(valid)}/{len(FAMOUS_PLAYER_IDS)} famous players in graph")
    return valid


def generate_puzzles(G: nx.Graph, valid: list[str], n: int) -> list[dict]:
    log.info(f"Generating {n} puzzles from {len(valid)} eligible endpoint players…")

    if len(valid) < 10:
        raise RuntimeError("Too few eligible players found in graph; check ETL and recognizability scores.")

    puzzles: list[dict] = []
    seen: set[tuple] = set()
    attempts = 0
    max_attempts = n * 20

    while len(puzzles) < n and attempts < max_attempts:
        attempts += 1
        start, end = random.sample(valid, 2)
        pair = tuple(sorted([start, end]))
        if pair in seen:
            continue
        seen.add(pair)

        try:
            path = nx.shortest_path(G, f"player:{start}", f"player:{end}", weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

        hops = len(path) - 1
        if not (2 <= hops <= 6):
            continue

        edge_types, edge_labels = [], []
        for i in range(len(path) - 1):
            ed = G[path[i]][path[i + 1]]
            edge_types.append(ed.get("type", "unknown"))
            edge_labels.append(ed.get("label", ""))

        weight_sum = sum(
            G[path[i]][path[i + 1]].get("weight", 1.0)
            for i in range(len(path) - 1)
        )
        difficulty = "easy" if weight_sum < 2.5 else "medium" if weight_sum < 4.0 else "hard"

        canonical_path = []
        for idx, node_key in enumerate(path):
            node_type, node_id = node_key.split(":", 1)
            nd = G.nodes[node_key]
            entry: dict = {"type": node_type, "id": node_id, "name": nd.get("name", node_id)}
            if idx < len(edge_labels):
                entry["connection_label"] = edge_labels[idx]
                entry["edge_type"] = edge_types[idx]
            canonical_path.append(entry)

        available_modes = compute_available_modes(G, start, end)

        puzzles.append({
            "start_player_id": start,
            "end_player_id": end,
            "canonical_path": canonical_path,
            "optimal_hops": hops,
            "difficulty": difficulty,
            "edge_types_used": edge_types,
            "available_modes": available_modes,
        })

    log.info(f"Generated {len(puzzles)} puzzles in {attempts} attempts")
    return puzzles


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def count_existing(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM daily_puzzles")
    return cur.fetchone()[0]


def insert_puzzles(conn, puzzles: list[dict]) -> int:
    cur = conn.cursor()

    cur.execute("SELECT puzzle_date FROM daily_puzzles")
    existing: set[date] = {row[0] for row in cur.fetchall()}

    inserted = 0
    current = date.today()

    for puzzle in puzzles:
        while current in existing:
            current += timedelta(days=1)
        try:
            cur.execute(
                """
                INSERT INTO daily_puzzles
                    (puzzle_date, start_player_id, end_player_id, canonical_path,
                     optimal_hops, difficulty, edge_types_used, available_modes, is_published)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (puzzle_date) DO NOTHING
                """,
                (
                    current,
                    puzzle["start_player_id"],
                    puzzle["end_player_id"],
                    json.dumps(puzzle["canonical_path"]),
                    puzzle["optimal_hops"],
                    puzzle["difficulty"],
                    puzzle["edge_types_used"],
                    puzzle.get("available_modes", ["classic"]),
                ),
            )
            existing.add(current)
            inserted += 1
            current += timedelta(days=1)
        except Exception as exc:
            log.warning(f"Skipping {current}: {exc}")
            current += timedelta(days=1)

    return inserted


def replace_low_quality_puzzles(conn, G: nx.Graph, eligible_ids: list[str]) -> int:
    """
    Scan the next 90 days of puzzles and replace any where either endpoint
    has recognizability_score < MIN_RECOGNIZABILITY.
    Returns count of replaced puzzles.
    """
    cur = conn.cursor()
    today = date.today()
    window_end = today + timedelta(days=90)

    # Fetch puzzles in the next 90 days
    cur.execute("""
        SELECT p.puzzle_date, p.start_player_id, p.end_player_id,
               ps.recognizability_score AS start_score,
               pe.recognizability_score AS end_score
        FROM daily_puzzles p
        LEFT JOIN players ps ON ps.id = p.start_player_id
        LEFT JOIN players pe ON pe.id = p.end_player_id
        WHERE p.puzzle_date >= %s AND p.puzzle_date <= %s
        ORDER BY p.puzzle_date
    """, (today, window_end))

    rows = cur.fetchall()
    log.info(f"Checking {len(rows)} puzzles between {today} and {window_end}…")

    eligible_set = set(eligible_ids)
    replaced = 0
    seen_pairs: set[tuple] = set()

    for puzzle_date, start_id, end_id, start_score, end_score in rows:
        start_ok = (start_score is not None and start_score >= MIN_RECOGNIZABILITY) or start_id in eligible_set
        end_ok = (end_score is not None and end_score >= MIN_RECOGNIZABILITY) or end_id in eligible_set

        if start_ok and end_ok:
            continue

        log.info(
            f"  Replacing {puzzle_date}: {start_id}(score={start_score}) → "
            f"{end_id}(score={end_score})"
        )

        # Generate a replacement puzzle for this date
        replacement = None
        for _ in range(50):
            new_start, new_end = random.sample(eligible_ids, 2)
            pair = tuple(sorted([new_start, new_end]))
            if pair in seen_pairs:
                continue
            try:
                path = nx.shortest_path(G, f"player:{new_start}", f"player:{new_end}", weight="weight")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            hops = len(path) - 1
            if not (2 <= hops <= 6):
                continue

            edge_types, edge_labels = [], []
            for i in range(len(path) - 1):
                ed = G[path[i]][path[i + 1]]
                edge_types.append(ed.get("type", "unknown"))
                edge_labels.append(ed.get("label", ""))

            weight_sum = sum(
                G[path[i]][path[i + 1]].get("weight", 1.0)
                for i in range(len(path) - 1)
            )
            difficulty = "easy" if weight_sum < 2.5 else "medium" if weight_sum < 4.0 else "hard"

            canonical_path = []
            for idx, node_key in enumerate(path):
                node_type, node_id = node_key.split(":", 1)
                nd = G.nodes[node_key]
                entry: dict = {"type": node_type, "id": node_id, "name": nd.get("name", node_id)}
                if idx < len(edge_labels):
                    entry["connection_label"] = edge_labels[idx]
                    entry["edge_type"] = edge_types[idx]
                canonical_path.append(entry)

            available_modes = compute_available_modes(G, new_start, new_end)
            replacement = {
                "start_player_id": new_start,
                "end_player_id": new_end,
                "canonical_path": json.dumps(canonical_path),
                "optimal_hops": hops,
                "difficulty": difficulty,
                "edge_types_used": edge_types,
                "available_modes": available_modes,
            }
            seen_pairs.add(pair)
            break

        if not replacement:
            log.warning(f"  Could not find replacement for {puzzle_date}")
            continue

        cur.execute("""
            UPDATE daily_puzzles SET
                start_player_id = %s,
                end_player_id   = %s,
                canonical_path  = %s,
                optimal_hops    = %s,
                difficulty      = %s,
                edge_types_used = %s,
                available_modes = %s
            WHERE puzzle_date = %s
        """, (
            replacement["start_player_id"],
            replacement["end_player_id"],
            replacement["canonical_path"],
            replacement["optimal_hops"],
            replacement["difficulty"],
            replacement["edge_types_used"],
            replacement.get("available_modes", ["classic"]),
            puzzle_date,
        ))
        replaced += 1

    conn.commit()
    log.info(f"Replaced {replaced} low-quality puzzles")
    return replaced


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("HOOPCHAIN — Seed daily_puzzles")
    log.info("=" * 60)

    if not DATABASE_URL:
        log.error("DATABASE_URL is not set — cannot connect to Postgres")
        raise SystemExit(1)

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    G = load_graph()
    eligible_ids = load_eligible_player_ids(conn, G)

    # Optionally replace low-quality puzzles in next 90 days
    replace_mode = os.getenv("REPLACE_LOW_QUALITY", "").lower() in ("1", "true", "yes")
    if replace_mode:
        log.info("REPLACE_LOW_QUALITY=1 — scanning next 90 days for low-recognizability puzzles…")
        replaced = replace_low_quality_puzzles(conn, G, eligible_ids)
        log.info(f"Replaced {replaced} puzzles")

    existing_count = count_existing(conn.cursor())
    log.info(f"Existing puzzles in DB: {existing_count}")

    if existing_count >= TARGET_PUZZLES and not replace_mode:
        log.info(f"Already have {existing_count} puzzles (>= {TARGET_PUZZLES}). Nothing to do.")
        conn.close()
        return

    needed = TARGET_PUZZLES - existing_count
    if needed <= 0:
        log.info("No new puzzles needed.")
        conn.close()
        return

    log.info(f"Need to add {needed} more puzzles")
    puzzles = generate_puzzles(G, eligible_ids, needed + 20)  # small buffer

    inserted = insert_puzzles(conn, puzzles)
    conn.close()

    log.info(f"Inserted {inserted} puzzles. Total now: {existing_count + inserted}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error(f"Seeder failed (deploy will continue): {exc}", exc_info=True)
        raise SystemExit(0)
