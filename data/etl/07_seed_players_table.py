"""
HOOPCHAIN ETL — Step 7: Seed players table from graph.pkl
==========================================================
The production Postgres players table is empty because the full ETL
(02_build_graph.py) was never run against the Railway database — only
graph.pkl was committed to git and deployed.

This script reads every player node directly from backend/graph.pkl
and inserts them into the players table.  It also rebuilds
search_vector so the search endpoint works.

It does NOT need SQLite or the full ETL environment — just:
  - backend/graph.pkl (already in repo)
  - a reachable Postgres DATABASE_URL

Usage:
    DATABASE_URL=postgresql://... python data/etl/07_seed_players_table.py

Or set DATABASE_URL in your environment, then run the script.
"""

from __future__ import annotations

import logging
import os
import pickle
import unicodedata
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# data/etl/.env takes precedence (prod DATABASE_URL); backend/.env is fallback
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GRAPH_PKL_PATH = Path(__file__).parent.parent.parent / "backend" / "graph.pkl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Strip accents: 'Schröder' → 'Schroder' for FTS."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def get_db_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise SystemExit("DATABASE_URL environment variable is not set.")
    # Convert asyncpg URL to psycopg2 URL if needed
    url = raw.replace("postgresql+asyncpg://", "postgresql://")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def load_players_from_graph(pkl_path: Path) -> list[dict]:
    """Extract all player nodes from graph.pkl."""
    logger.info(f"Loading graph from {pkl_path} …")
    with open(pkl_path, "rb") as f:
        G = pickle.load(f)

    players = []
    for node_key, data in G.nodes(data=True):
        if data.get("type") != "player":
            continue
        # node_key is "player:ID"
        player_id = node_key.split(":", 1)[1]
        name = data.get("name", "")
        if not name:
            continue
        parts = name.split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        players.append({
            "id": player_id,
            "full_name": name,
            "first_name": first,
            "last_name": last,
            "is_active": bool(data.get("is_active", False)),
        })

    logger.info(f"Found {len(players)} player nodes in graph")
    return players


def seed_players(conn, players: list[dict]) -> int:
    cur = conn.cursor()
    inserted = 0
    updated = 0

    batch_size = 500
    for i in range(0, len(players), batch_size):
        batch = players[i : i + batch_size]
        for p in batch:
            cur.execute(
                """
                INSERT INTO players (id, full_name, first_name, last_name, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    full_name  = EXCLUDED.full_name,
                    first_name = EXCLUDED.first_name,
                    last_name  = EXCLUDED.last_name,
                    is_active  = EXCLUDED.is_active
                """,
                (p["id"], p["full_name"], p["first_name"], p["last_name"], p["is_active"]),
            )
        conn.commit()
        inserted += len(batch)
        logger.info(f"  Upserted {inserted}/{len(players)} players …")

    # Rebuild search vectors (always, not just NULL rows)
    logger.info("Rebuilding search_vector for all players …")
    cur.execute("""
        UPDATE players
        SET search_vector = to_tsvector('english', full_name)
    """)
    conn.commit()
    logger.info("search_vector rebuilt.")
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 7: Seed players table from graph.pkl")
    logger.info("=" * 60)

    if not GRAPH_PKL_PATH.exists():
        raise SystemExit(f"graph.pkl not found at {GRAPH_PKL_PATH}")

    db_url = get_db_url()
    logger.info(f"Connecting to Postgres … ({db_url[:40]}…)")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False

    # Quick check: current count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players")
    before = cur.fetchone()[0]
    logger.info(f"Players before: {before}")

    players = load_players_from_graph(GRAPH_PKL_PATH)
    total = seed_players(conn, players)

    cur.execute("SELECT COUNT(*) FROM players")
    after = cur.fetchone()[0]
    logger.info(f"Players after:  {after}")

    # Quick spot-checks
    for name_fragment in ["%Rondo%", "%Nash%", "%LeBron%", "%Garnett%"]:
        cur.execute("SELECT id, full_name FROM players WHERE full_name ILIKE %s LIMIT 1", (name_fragment,))
        row = cur.fetchone()
        status = f"✅  {row[1]} (id={row[0]})" if row else "❌  NOT FOUND"
        logger.info(f"  {name_fragment:<20} {status}")

    conn.close()
    logger.info("=" * 60)
    logger.info(f"Done. {total} rows upserted, {after} total players in DB.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
