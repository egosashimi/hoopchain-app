"""
HOOPCHAIN ETL — Step 4: Enrich College/Draft Data via Wikipedia
===============================================================
Fills missing 'college' fields for players who have NULL in nbadb
using the Wikipedia REST API.

Uses Wikipedia's search + page summary API (no scraping required).
Run ONCE after 02_build_graph.py.
Expected runtime: ~30 minutes (respects 1 req/sec rate limit).

# CHANGES (session 2026-05):
#   - Added User-Agent header to httpx requests; Wikipedia REST API returns 403
#     without a descriptive User-Agent identifying the bot/app
#   - Wikipedia policy: https://meta.wikimedia.org/wiki/User-Agent_policy
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5432/hoopchain")
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
RATE_LIMIT = 1.0  # seconds between requests

# Wikipedia requires a descriptive User-Agent (see meta.wikimedia.org/wiki/User-Agent_policy)
HEADERS = {
    "User-Agent": "HoopchainETL/1.0 (https://github.com/egosashimi/hoopchain; hoopchain-bot@noreply) python-httpx"
}


def get_pg_conn():
    import psycopg2
    return psycopg2.connect(PG_URL)


def fetch_college_from_wikipedia(player_name: str) -> str | None:
    """
    Query Wikipedia's REST API for a player's page summary
    and extract their college/university from the description.
    Returns college name string or None if not found.
    """
    try:
        # Encode name for URL
        search_name = player_name.replace(" ", "_")
        url = f"{WIKIPEDIA_API}{search_name}_(basketball)"

        response = httpx.get(url, timeout=10, follow_redirects=True, headers=HEADERS)
        if response.status_code != 200:
            # Try without (basketball) suffix
            url = f"{WIKIPEDIA_API}{search_name}"
            response = httpx.get(url, timeout=10, follow_redirects=True, headers=HEADERS)

        if response.status_code != 200:
            return None

        data = response.json()
        extract = data.get("extract", "")

        # Simple heuristic: look for college/university mentions
        # This is a best-effort approach; Wikipedia summaries vary in structure
        college_keywords = ["attended", "played college basketball at", "at", "from"]
        university_keywords = ["University", "College", "State University", "Institute"]

        for line in extract.split("."):
            for keyword in college_keywords:
                if keyword.lower() in line.lower():
                    for uni_kw in university_keywords:
                        if uni_kw in line:
                            # Extract the institution name
                            idx = line.find(uni_kw)
                            # Walk back to find start of name
                            words = line[:idx + len(uni_kw)].split()
                            if len(words) >= 2:
                                college_name = " ".join(words[-3:]).strip(".,;")
                                if len(college_name) > 5:
                                    return college_name

        return None
    except Exception as e:
        logger.debug(f"Wikipedia lookup failed for {player_name}: {e}")
        return None


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 4: Enrich via Wikipedia")
    logger.info("=" * 60)

    pg_conn = get_pg_conn()
    cur = pg_conn.cursor()

    # Find players with missing college data
    cur.execute("""
        SELECT id, full_name FROM players
        WHERE college IS NULL OR college = ''
        ORDER BY is_active DESC, id
        LIMIT 2000
    """)
    players = cur.fetchall()

    logger.info(f"Found {len(players)} players with missing college data")
    logger.info("Querying Wikipedia REST API (1 req/sec)...")

    enriched = 0
    for i, (player_id, full_name) in enumerate(players):
        time.sleep(RATE_LIMIT)

        college = fetch_college_from_wikipedia(full_name)
        if college:
            cur.execute(
                "UPDATE players SET college = %s WHERE id = %s AND (college IS NULL OR college = '')",
                (college, player_id)
            )
            enriched += 1
            logger.info(f"  {full_name}: {college}")

        # Commit every 50 players so progress survives interruption
        if (i + 1) % 50 == 0:
            pg_conn.commit()
            logger.info(f"  [checkpoint] {i + 1}/{len(players)} players processed, {enriched} enriched so far")

    pg_conn.commit()
    pg_conn.close()

    logger.info(f"\n✅ Enriched {enriched} players with college data from Wikipedia")
    logger.info("Next: python 05_generate_puzzles.py")


if __name__ == "__main__":
    main()
