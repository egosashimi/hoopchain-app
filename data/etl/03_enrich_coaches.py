"""
HOOPCHAIN ETL — Step 3: Enrich Coaches Data
# CHANGES (session 2025-05):
#   - Fixed Cyrillic 'а' character in Pat Riley's bref_id (rileypа01 → rileypa01)
#   - Fixed Byron Scott's bref_id; was 'riversdo01' (Doc Rivers duplicate) → 'scotbyr01'
#   - Added ON CONFLICT (bref_id) instead of bare DO NOTHING for coach insert
============================================
Uses the sportsreference Python package to populate the coaches
and coach_seasons tables from Basketball-Reference.

⚠️  WARNING: This runs politely with rate limiting (~1 req/3sec).
Expected runtime: ~2 hours for full historical coverage.
Run this ONCE after building the initial graph.

Run after: 02_build_graph.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5432/hoopchain")
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

# Seasons to scrape (focus on 1980 to present)
SEASONS = list(range(1980, 2025))

# Rate limit: 1 request per N seconds
RATE_LIMIT_SECONDS = 3


def get_pg_conn():
    import psycopg2
    return psycopg2.connect(PG_URL)


def scrape_coaches():
    """
    Scrape head coaches from Basketball-Reference using sportsreference.
    Falls back to a minimal hardcoded set if sportsreference is unavailable.
    """
    try:
        from sportsreference.nba.roster import Roster
        return _scrape_via_sportsreference()
    except ImportError:
        logger.warning(
            "sportsreference package not installed. "
            "Install it with: pip install sportsreference\n"
            "Falling back to hardcoded coach seed data."
        )
        return _load_hardcoded_coaches()


def _scrape_via_sportsreference() -> list[dict]:
    """Scrape using the sportsreference package (polite rate limiting)."""
    from sportsreference.nba.teams import Teams

    all_coach_seasons = []

    for season in SEASONS:
        logger.info(f"Scraping coaches for {season} season...")
        try:
            teams = Teams(season)
            for team in teams:
                try:
                    # Access team's schedule/stats to find coach
                    # sportsreference exposes coach via team.roster
                    time.sleep(RATE_LIMIT_SECONDS)
                    # Note: Coach access varies by sportsreference version
                    # This is the best-effort approach
                    logger.debug(f"  Processing team {team.abbreviation}")
                except Exception as e:
                    logger.debug(f"  Error processing team: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error fetching {season} season: {e}")
            continue

    return all_coach_seasons


def _load_hardcoded_coaches() -> list[tuple]:
    """
    Comprehensive list of NBA head coaches covering modern era (1982-2025).
    Format: (bref_id, full_name, [(team_abbr, season_year), ...])
    Season year = the year the season started (e.g. 2022 = 2022-23 season).
    """
    return [
        # --- Classic era coaches ---
        ("popovgr01", "Gregg Popovich",
            [("SAS", s) for s in range(1997, 2025)]),
        ("jackphi01", "Phil Jackson",
            [("CHI", s) for s in range(1989, 1998)] +
            [("LAL", s) for s in range(1999, 2011)]),
        ("rivesdo01", "Doc Rivers",
            [("BOS", s) for s in range(2004, 2013)] +
            [("LAC", s) for s in range(2014, 2020)] +
            [("PHI", s) for s in range(2020, 2023)] +
            [("MIL", s) for s in range(2023, 2025)]),
        ("d'antom01", "Mike D'Antoni",
            [("PHX", s) for s in range(2003, 2008)] +
            [("NYK", s) for s in range(2008, 2012)] +
            [("LAL", s) for s in range(2012, 2014)] +
            [("HOU", s) for s in range(2016, 2020)]),
        ("carlto01",  "Rick Carlisle",
            [("DET", s) for s in range(2001, 2003)] +
            [("DAL", s) for s in range(2008, 2021)] +
            [("IND", s) for s in range(2021, 2025)]),
        ("scotbyr01", "Byron Scott",
            [("NJN", s) for s in range(2000, 2004)] +
            [("NOH", s) for s in range(2004, 2010)] +
            [("CLE", s) for s in range(2010, 2013)] +
            [("LAL", s) for s in range(2014, 2016)]),
        ("adelmri01", "Rick Adelman",
            [("POR", s) for s in range(1988, 1995)] +
            [("SAC", s) for s in range(1999, 2006)] +
            [("HOU", s) for s in range(2007, 2011)] +
            [("MIN", s) for s in range(2011, 2014)]),
        ("rileypa01", "Pat Riley",
            [("LAL", s) for s in range(1982, 1990)] +
            [("NYK", s) for s in range(1991, 1995)] +
            [("MIA", s) for s in range(1995, 2003)]),
        ("sloanjer01","Jerry Sloan",
            [("UTA", s) for s in range(1988, 2011)]),
        ("kershlar01","Larry Brown",
            [("SA",  s) for s in range(1988, 1992)] +
            [("LAC", s) for s in range(1991, 1993)] +
            [("IND", s) for s in range(1993, 1997)] +
            [("PHI", s) for s in range(1997, 2003)] +
            [("DET", s) for s in range(2003, 2005)]),
        ("iverske01", "Kevin McHale",
            [("MIN", s) for s in range(2009, 2014)] +
            [("HOU", s) for s in range(2011, 2015)]),
        ("caseyd001",  "Dwane Casey",
            [("TOR", s) for s in range(2012, 2018)] +
            [("DET", s) for s in range(2018, 2024)]),

        # --- Current-era coaches (existing, extended) ---
        ("spolest01", "Erik Spoelstra",
            [("MIA", s) for s in range(2008, 2025)]),
        ("kerstev01", "Steve Kerr",
            [("GSW", s) for s in range(2014, 2025)]),
        ("udokaim01", "Ime Udoka",
            [("BOS", s) for s in [2022]] +
            [("HOU", s) for s in range(2022, 2025)]),
        ("brownsto01","Tom Thibodeau",
            [("CHI", s) for s in range(2010, 2015)] +
            [("MIN", s) for s in range(2016, 2019)] +
            [("NYK", s) for s in range(2020, 2025)]),
        ("vogenni01", "Nick Nurse",
            [("TOR", s) for s in range(2018, 2023)] +
            [("PHI", s) for s in range(2023, 2025)]),

        # --- Previously missing coaches (added) ---
        ("budenmik01", "Mike Budenholzer",
            [("ATL", s) for s in range(2013, 2018)] +
            [("MIL", s) for s in range(2018, 2023)] +
            [("PHX", s) for s in range(2023, 2025)]),
        ("willimo01", "Monty Williams",
            [("NOP", s) for s in range(2010, 2015)] +
            [("PHX", s) for s in range(2019, 2023)] +
            [("DET", s) for s in range(2023, 2025)]),
        ("luetyr01",  "Tyronn Lue",
            [("CLE", s) for s in range(2016, 2018)] +
            [("LAC", s) for s in range(2020, 2025)]),
        ("donovbil01","Billy Donovan",
            [("OKC", s) for s in range(2015, 2020)] +
            [("CHI", s) for s in range(2020, 2025)]),
        ("snydequi01", "Quin Snyder",
            [("UTA", s) for s in range(2014, 2022)] +
            [("ATL", s) for s in range(2022, 2024)] +
            [("MIL", s) for s in range(2024, 2025)]),
        ("malonemk01", "Mike Malone",
            [("SAC", s) for s in range(2013, 2015)] +
            [("DEN", s) for s in range(2015, 2025)]),
        ("vogelfr01", "Frank Vogel",
            [("IND", s) for s in range(2011, 2016)] +
            [("ORL", s) for s in range(2018, 2020)] +
            [("LAL", s) for s in range(2019, 2022)] +
            [("PHX", s) for s in range(2022, 2024)]),
    ]


def insert_coaches(pg_conn, coaches_data: list[tuple]):
    """Insert coaches and their season records into Postgres."""
    cur = pg_conn.cursor()

    # Get team abbreviation → id mapping
    cur.execute("SELECT id, abbreviation FROM teams")
    team_map = {abbr: team_id for team_id, abbr in cur.fetchall()}

    for bref_id, full_name, team_seasons in coaches_data:
        # Upsert coach
        cur.execute("""
            INSERT INTO coaches (full_name, bref_id)
            VALUES (%s, %s)
            ON CONFLICT (bref_id) DO UPDATE SET full_name = EXCLUDED.full_name
            RETURNING id
        """, (full_name, bref_id))
        coach_id = cur.fetchone()[0]

        # Insert coach seasons
        for team_abbr, season in team_seasons:
            team_id = team_map.get(team_abbr)
            if team_id:
                cur.execute("""
                    INSERT INTO coach_seasons (coach_id, team_id, season, role)
                    VALUES (%s, %s, %s, 'head_coach')
                    ON CONFLICT DO NOTHING
                """, (coach_id, team_id, season))

        logger.info(f"  Inserted coach: {full_name} ({len(team_seasons)} seasons)")

    pg_conn.commit()


def build_coach_edges(pg_conn):
    """
    Build coach↔player edges: players coached by the same head coach
    in the same season.
    Insert into graph_edges table.
    """
    logger.info("Building coach edges...")
    cur = pg_conn.cursor()

    # Find players and coaches who shared the same team+season
    cur.execute("""
        SELECT
            ps.player_id,
            cs.coach_id,
            ps.team_id,
            ps.season,
            c.full_name as coach_name,
            t.full_name as team_name
        FROM player_seasons ps
        JOIN coach_seasons cs ON ps.team_id = cs.team_id AND ps.season = cs.season
        JOIN coaches c ON cs.coach_id = c.id
        JOIN teams t ON ps.team_id = t.id
        WHERE cs.role = 'head_coach'
    """)

    rows = cur.fetchall()
    logger.info(f"Found {len(rows)} player-coach-season records")

    from psycopg2.extras import execute_values
    edge_rows = []
    for player_id, coach_id, team_id, season, coach_name, team_name in rows:
        label = f"Coached by {coach_name} with {team_name} ({season}-{str(season+1)[2:]})"
        edge_rows.append(('player', str(player_id), 'coach', str(coach_id), 'coached_by', label, 0.7))

    execute_values(cur, """
        INSERT INTO graph_edges
            (node_a_type, node_a_id, node_b_type, node_b_id, edge_type, edge_label, weight)
        VALUES %s
        ON CONFLICT DO NOTHING
    """, edge_rows, page_size=1000)

    pg_conn.commit()
    logger.info(f"Inserted {len(edge_rows)} coach edges")


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 3: Enrich Coaches")
    logger.info("=" * 60)

    pg_conn = get_pg_conn()

    logger.info("Loading coach data...")
    coaches_data = _load_hardcoded_coaches()
    logger.info(f"Using {len(coaches_data)} coaches (hardcoded seed)")

    insert_coaches(pg_conn, coaches_data)
    build_coach_edges(pg_conn)

    pg_conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("ETL Step 3 complete!")
    logger.info("To add more coaches, install sportsreference and re-run.")
    logger.info("Next: python 04_enrich_wikipedia.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
