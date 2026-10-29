"""
HOOPCHAIN ETL — Step 9: Score player recognizability
=====================================================
Assigns a recognizability_score to every player in the players table.

Scoring formula (additive):
  +1 per career season played (from player_seasons table)
  +5 per All-Star appearance (from graph_edges with edge_type='all_star')
  +10 if player has a valid headshot on NBA CDN
  +3 if drafted in round 1
  +2 if drafted after 1990

The score is written to the players.recognizability_score column.
Run after: alembic upgrade head (migration 003 must be applied first)

Usage:
    DATABASE_URL=postgresql://... python data/etl/09_score_recognizability.py
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

NBA_CDN_URL = "https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
# Only check CDN for players we suspect are recognizable (score >= 5 before CDN check)
# to avoid 4800 HTTP requests.
CDN_SCORE_THRESHOLD = 5
CDN_REQUEST_DELAY = 0.05  # 50ms between requests


def get_pg_conn():
    raw = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5433/hoopchain")
    url = raw.replace("postgresql+asyncpg://", "postgresql://")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return psycopg2.connect(url)


def check_headshot_exists(player_id: str) -> bool:
    """Return True if the NBA CDN has a headshot for this player."""
    url = NBA_CDN_URL.format(player_id=player_id)
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def compute_scores(conn) -> dict[str, int]:
    """Compute recognizability scores for all players."""
    cur = conn.cursor()

    # Base scores map: player_id → score
    scores: dict[str, int] = {}

    # --- 1pt per career season played ---
    log.info("Computing season-played scores…")
    cur.execute("""
        SELECT player_id, COUNT(DISTINCT season) as seasons
        FROM player_seasons
        GROUP BY player_id
    """)
    for pid, season_count in cur.fetchall():
        scores[pid] = scores.get(pid, 0) + int(season_count)

    log.info(f"  {len(scores)} players have season records; total scores assigned")

    # --- 5pts per All-Star appearance ---
    log.info("Computing All-Star scores…")
    cur.execute("""
        SELECT node_a_id, COUNT(*) as appearances
        FROM graph_edges
        WHERE edge_type = 'all_star'
        GROUP BY node_a_id
        UNION ALL
        SELECT node_b_id, COUNT(*) as appearances
        FROM graph_edges
        WHERE edge_type = 'all_star'
        GROUP BY node_b_id
    """)
    allstar_counts: dict[str, int] = {}
    for pid, count in cur.fetchall():
        allstar_counts[pid] = allstar_counts.get(pid, 0) + int(count)
    # Each All-Star edge appears twice (once for each direction), deduplicate
    for pid, raw_count in allstar_counts.items():
        # Each appearance is one edge; graph has one edge per pair-season
        # Approximation: count distinct edges / 2 for bilateral edges
        appearances = max(1, raw_count // 2)
        scores[pid] = scores.get(pid, 0) + (appearances * 5)

    log.info(f"  {len(allstar_counts)} players have All-Star edges")

    # --- 3pts if drafted in round 1 ---
    log.info("Computing draft round scores…")
    cur.execute("""
        SELECT id FROM players
        WHERE draft_round = 1
    """)
    for (pid,) in cur.fetchall():
        scores[pid] = scores.get(pid, 0) + 3

    # --- 2pts if drafted after 1990 ---
    cur.execute("""
        SELECT id FROM players
        WHERE draft_year > 1990
    """)
    for (pid,) in cur.fetchall():
        scores[pid] = scores.get(pid, 0) + 2

    log.info(f"  Scores before CDN check: {len(scores)} players")

    # --- 10pts if valid NBA CDN headshot ---
    # Only check players with score >= CDN_SCORE_THRESHOLD to limit requests
    candidates = [(pid, s) for pid, s in scores.items() if s >= CDN_SCORE_THRESHOLD]
    log.info(f"Checking NBA CDN headshots for {len(candidates)} players (score >= {CDN_SCORE_THRESHOLD})…")

    cdn_hits = 0
    for i, (pid, _) in enumerate(candidates):
        if check_headshot_exists(pid):
            scores[pid] = scores.get(pid, 0) + 10
            cdn_hits += 1
        if (i + 1) % 100 == 0:
            log.info(f"  CDN checked {i+1}/{len(candidates)}, {cdn_hits} hits so far")
        time.sleep(CDN_REQUEST_DELAY)

    log.info(f"  CDN headshots found: {cdn_hits}/{len(candidates)} checked")

    return scores


def update_scores(conn, scores: dict[str, int]) -> int:
    """Write scores to the players table in batches."""
    cur = conn.cursor()
    updated = 0

    items = list(scores.items())
    batch_size = 500
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        cur.executemany("""
            UPDATE players SET recognizability_score = %s WHERE id = %s
        """, [(score, pid) for pid, score in batch])
        updated += len(batch)
        conn.commit()
        if updated % 2000 == 0:
            log.info(f"  Updated {updated}/{len(items)} players…")

    conn.commit()
    return updated


def main():
    log.info("=" * 60)
    log.info("HOOPCHAIN ETL — Step 9: Score player recognizability")
    log.info("=" * 60)

    conn = get_pg_conn()

    # Verify column exists
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='players' AND column_name='recognizability_score'
    """)
    if not cur.fetchone():
        log.error("recognizability_score column not found. Run: alembic upgrade head")
        raise SystemExit(1)

    scores = compute_scores(conn)
    total = update_scores(conn, scores)
    conn.close()

    # Quick stats
    score_values = sorted(scores.values(), reverse=True)
    above_15 = sum(1 for s in score_values if s >= 15)
    above_10 = sum(1 for s in score_values if s >= 10)
    log.info("")
    log.info("=== Score Distribution ===")
    log.info(f"  Total players scored: {len(scores)}")
    log.info(f"  Score >= 15: {above_15} players (puzzle-eligible endpoints)")
    log.info(f"  Score >= 10: {above_10} players")
    log.info(f"  Top 5 scores: {score_values[:5]}")
    log.info("")
    log.info("=" * 60)
    log.info(f"Done. Updated {total} player rows.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
