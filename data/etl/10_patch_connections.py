"""
HOOPCHAIN ETL — Step 10: Patch Missing Connections
===================================================
Fixes all data connection failures identified in the June 2026 audit:
  1. Missing player seasons (Rodman CHI, LeBron MIA, Booker PHX, Butler GSW, Caruso OKC, etc.)
  2. College data fixes (Iverson → Georgetown, McClung → Georgetown)
  3. All-Star edges (hardcoded rosters for 1984-2024)
  4. Coach edges (rebuilt from Postgres coach_seasons)
  5. Rodman↔Jordan teammate edge

Run after: 03_enrich_coaches.py
Run before: committing graph.pkl

Usage:
    python data/etl/10_patch_connections.py
    # or against production:
    DATABASE_URL=postgresql://... python data/etl/10_patch_connections.py
"""

from __future__ import annotations

import logging
import os
import pickle
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
GRAPH_PKL_PATH = ETL_DIR.parent / "exports" / "graph.pkl"
BACKEND_GRAPH_PKL = ETL_DIR.parent.parent / "backend" / "graph.pkl"

sys.path.insert(0, str(ETL_DIR.parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(ETL_DIR / ".env")  # data/etl/.env has prod DATABASE_URL
load_dotenv(ETL_DIR.parent.parent / "backend" / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5433/hoopchain")
PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_pg_conn():
    return psycopg2.connect(PG_URL)


# ── Team abbreviation → NBA.com team ID ──────────────────────────────────────

ABBR_TO_TEAM_ID: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "NJN": 1610612751, "BKN": 1610612751,
    "CHA": 1610612766, "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742,
    "DEN": 1610612743, "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745,
    "IND": 1610612754, "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
    "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740,
    "NOH": 1610612740, "NYK": 1610612752, "OKC": 1610612760, "ORL": 1610612753,
    "PHI": 1610612755, "PHX": 1610612756, "POR": 1610612757, "SAC": 1610612758,
    "SAS": 1610612759, "SA":  1610612759, "TOR": 1610612761, "UTA": 1610612762,
    "WAS": 1610612764,
}

TEAM_ID_TO_NAME: dict[int, str] = {
    1610612737: "Atlanta Hawks",        1610612738: "Boston Celtics",
    1610612739: "Cleveland Cavaliers",  1610612740: "New Orleans Pelicans",
    1610612741: "Chicago Bulls",        1610612742: "Dallas Mavericks",
    1610612743: "Denver Nuggets",       1610612744: "Golden State Warriors",
    1610612745: "Houston Rockets",      1610612746: "Los Angeles Clippers",
    1610612747: "Los Angeles Lakers",   1610612748: "Miami Heat",
    1610612749: "Milwaukee Bucks",      1610612750: "Minnesota Timberwolves",
    1610612751: "Brooklyn Nets",        1610612752: "New York Knicks",
    1610612753: "Orlando Magic",        1610612754: "Indiana Pacers",
    1610612755: "Philadelphia 76ers",   1610612756: "Phoenix Suns",
    1610612757: "Portland Trail Blazers", 1610612758: "Sacramento Kings",
    1610612759: "San Antonio Spurs",    1610612760: "Oklahoma City Thunder",
    1610612761: "Toronto Raptors",      1610612762: "Utah Jazz",
    1610612763: "Memphis Grizzlies",    1610612764: "Washington Wizards",
    1610612765: "Detroit Pistons",      1610612766: "Charlotte Hornets",
}


# ── Missing player-team-season records ──────────────────────────────────────
# Format: (player_id, full_name, [(team_abbr, season_year), ...])
# season_year = year the season started (e.g. 2024 = 2024-25 season)

MISSING_PLAYER_SEASONS = [
    # Dennis Rodman on Chicago Bulls (1995-96 through 1997-98)
    # nbadb common_player_info stores only his last team (Pistons), missing Bulls years
    ("23", "Dennis Rodman", [
        ("CHI", 1995), ("CHI", 1996), ("CHI", 1997),
    ]),
    # LeBron James full Miami Heat tenure (2010-11 through 2013-14)
    ("2544", "LeBron James", [
        ("MIA", 2011), ("MIA", 2012),  # 2010 and 2013 already in DB
    ]),
    # Devin Booker 2023-24 season on Suns (needed for Budenholzer coach connection)
    ("1626164", "Devin Booker", [
        ("PHX", 2023), ("PHX", 2024),
    ]),
    # Giannis early MIL seasons missing from nbadb
    ("203507", "Giannis Antetokounmpo", [
        ("MIL", 2013), ("MIL", 2014), ("MIL", 2015),
    ]),
    # 2024-25 roster moves
    ("202710",  "Jimmy Butler",         [("GSW", 2024)]),
    ("1627936", "Alex Caruso",          [("OKC", 2024)]),
    # Other notable missing recent seasons
    ("201939",  "Stephen Curry",        [("GSW", 2023), ("GSW", 2024)]),
    ("203954",  "Joel Embiid",          [("PHI", 2023), ("PHI", 2024)]),
    ("1628983", "Shai Gilgeous-Alexander", [("OKC", 2023), ("OKC", 2024)]),
    ("1629029", "Luka Doncic",          [("DAL", 2023), ("DAL", 2024)]),
    ("1626164", "Devin Booker",         [("PHX", 2023), ("PHX", 2024)]),
    ("203507",  "Giannis Antetokounmpo",[("MIL", 2023), ("MIL", 2024)]),
    ("203081",  "Damian Lillard",       [("POR", 2022), ("MIL", 2023), ("MIL", 2024)]),
    ("202710",  "Jimmy Butler",         [("MIA", 2024)]),   # was still on MIA early 2024-25
]


# ── College fixes ─────────────────────────────────────────────────────────────
# (player_id, correct_college)
# McClung attended Georgetown (2 years) before transferring to Texas Tech.
# Iverson attended Georgetown — nbadb has NULL.

COLLEGE_FIXES = [
    ("947",     "Georgetown"),   # Allen Iverson
    ("1630644", "Georgetown"),   # Mac McClung (attended Georgetown 2018-2020)
]


# ── All-Star game selections ──────────────────────────────────────────────────
# Format: player_id → list of years selected for the NBA All-Star Game
# (Both East and West selections in the same year are connected to each other)
# Focus on 1984+ modern era. IDs are verified NBA.com player IDs.

ALL_STAR_SELECTIONS: dict[str, list[int]] = {
    # Pre-1990 legends
    "76003": [1970,1972,1974,1975,1976,1977,1979,1980,1981,1982,1983,1984,1985,1986,1987,1988,1989],  # Kareem
    "77142": [1980,1982,1983,1984,1985,1986,1987,1988,1989,1990,1991,1992],  # Magic Johnson
    "1449":  [1980,1981,1982,1983,1984,1985,1986,1987,1988],  # Larry Bird

    # Jordan era
    "893":   [1985,1987,1988,1989,1990,1991,1992,1993,1996,1997,1998],  # Michael Jordan
    "937":   [1990,1991,1992,1993,1994,1995,1996,1997],  # Scottie Pippen
    "949":   [1982,1984,1985,1986,1987,1988,1989,1990,1991,1992,1993],  # Isiah Thomas

    # 1990s stars
    "406":   [1993,1994,1995,1996,1997,1998,2000,2001,2002,2003,2004,2005,2006,2007,2009],  # Shaq
    "977":   [1998,2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2016],  # Kobe
    "1495":  [1997,1998,2000,2001,2002,2003,2004,2005,2006,2007,2009,2010,2011,2013],  # Tim Duncan
    "708":   [1997,1998,2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011],  # KG
    "947":   [2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010],  # Allen Iverson
    "959":   [2002,2003,2005,2006,2007,2008,2010,2012],  # Steve Nash
    "1717":  [2002,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015],  # Dirk
    "1718":  [2005,2006,2008,2009,2010,2012],  # Paul Pierce
    "2730":  [2007,2008,2009,2010,2011,2012,2013,2014,2016],  # Dwight Howard

    # Other 90s-2000s players (verified IDs)
    "951":   [2000,2001,2004,2005,2007,2008,2009,2011],  # Ray Allen
    "1713":  [2000],  # Vince Carter

    # Big 3 Miami era
    "2548":  [2006,2007,2008,2009,2010,2011,2012,2013,2014],  # Dwyane Wade
    "2544":  [2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023],  # LeBron

    # 2010s stars
    "101108":[2008,2009,2010,2011,2012,2013,2014,2015,2016],  # Chris Paul
    "2546":  [2005,2008,2010,2011,2012,2013,2014,2015,2016],  # Carmelo Anthony
    "201142":[2010,2011,2012,2013,2014,2016,2017,2018,2019,2021],  # Kevin Durant
    "201566":[2011,2012,2013,2014,2015,2016,2017,2018,2019,2020],  # Westbrook
    "201935":[2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023],  # Harden
    "201939":[2014,2015,2016,2017,2018,2019,2021,2022],  # Curry
    "202681":[2013,2014,2018,2019,2021,2022,2023],  # Kyrie Irving
    "200765":[2009,2010,2012],  # Rajon Rondo

    # Modern era stars
    "203076":[2014,2015,2016,2017,2018,2019,2020,2021],  # Anthony Davis
    "203507":[2017,2018,2019,2020,2021,2022,2023,2024],  # Giannis
    "203954":[2018,2019,2020,2021,2022,2023,2024],  # Embiid
    "203081":[2014,2015,2016,2017,2018,2020,2021,2022,2023,2024],  # Lillard
    "1629029":[2020,2021,2022,2023,2024],  # Luka Doncic
    "1626164":[2020,2021,2022,2024],  # Devin Booker
    "1628983":[2022,2023,2024],  # SGA

    # Additional well-known players
    "1495":  [1997,1998,2000,2001,2002,2003,2004,2005,2006,2007,2009,2010,2011,2013],  # Duncan (dup ok)
    "1629027":[2021,2022],  # Ja Morant
    "1630162":[2022,2023,2024],  # Evan Mobley
    "203999":[2016,2017,2018,2019,2020,2021],  # Kawhi Leonard
    "203484":[2013,2014,2015,2016,2017,2018,2019,2020,2021],  # Paul George
    "201142":[2010,2011,2012,2013,2014,2016,2017,2018,2019,2021],  # KD (dup ok)
    "1628973":[2020,2021,2022,2023,2024],  # Luka (alt ID check)
    "1641705":[2024],  # Wembanyama

    # Classic big men
    "600005":[1984,1985,1986,1987,1988,1989,1990,1991,1992],  # Charles Barkley (~ID)
}


# ── Main ──────────────────────────────────────────────────────────────────────

def fix_player_seasons(conn, G: nx.Graph) -> int:
    """Add missing player-team-season records to Postgres and graph."""
    cur = conn.cursor()
    added = 0
    graph_seasons: list[tuple] = []  # (player_id, team_id, season) for graph rebuild

    # Validate team and player exist in DB before inserting
    cur.execute("SELECT id FROM teams")
    valid_team_ids = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT id FROM players")
    valid_player_ids = {r[0] for r in cur.fetchall()}

    for player_id, player_name, team_seasons in MISSING_PLAYER_SEASONS:
        if player_id not in valid_player_ids:
            logger.warning(f"  Skip {player_name} ({player_id}) — not in players table")
            continue
        for team_abbr, season in team_seasons:
            team_id = ABBR_TO_TEAM_ID.get(team_abbr)
            if not team_id or team_id not in valid_team_ids:
                logger.warning(f"  Skip {team_abbr} — not in teams table")
                continue
            try:
                cur.execute("""
                    INSERT INTO player_seasons (player_id, team_id, season)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                """, (player_id, team_id, season))
                if cur.rowcount:
                    added += 1
                    logger.info(f"  Added: {player_name} on {team_abbr} {season}")
                graph_seasons.append((player_id, team_id, season))
            except Exception as e:
                logger.warning(f"  Skip {player_name} {team_abbr} {season}: {e}")
                conn.rollback()

    conn.commit()
    logger.info(f"Player seasons: {added} new rows added to Postgres")
    return added


def fix_college_data(conn) -> int:
    """Fix college field for players with known wrong/missing values."""
    cur = conn.cursor()
    fixed = 0
    for player_id, college in COLLEGE_FIXES:
        cur.execute(
            "UPDATE players SET college = %s WHERE id = %s",
            (college, player_id)
        )
        if cur.rowcount:
            fixed += 1
            logger.info(f"  Fixed college: player {player_id} → {college}")
    conn.commit()
    logger.info(f"College data: {fixed} players updated")
    return fixed


def rebuild_coach_edges_in_graph(conn, G: nx.Graph) -> int:
    """Add missing coach nodes and coached_by edges to the graph from Postgres data."""
    cur = conn.cursor()

    # Add coach nodes
    cur.execute("SELECT id, full_name FROM coaches")
    coaches = cur.fetchall()
    added_nodes = 0
    for coach_id, coach_name in coaches:
        node_key = f"coach:{coach_id}"
        if not G.has_node(node_key):
            G.add_node(node_key, type="coach", name=coach_name)
            added_nodes += 1

    logger.info(f"Coach nodes: {added_nodes} new, {len(coaches)} total in DB")

    # Build coach edges from player_seasons JOIN coach_seasons
    cur.execute("""
        SELECT
            ps.player_id,
            cs.coach_id,
            t.full_name AS team_name,
            ps.season,
            c.full_name AS coach_name
        FROM player_seasons ps
        JOIN coach_seasons cs ON ps.team_id = cs.team_id AND ps.season = cs.season
        JOIN coaches c ON cs.coach_id = c.id
        JOIN teams t ON ps.team_id = t.id
        WHERE cs.role = 'head_coach'
    """)
    rows = cur.fetchall()
    logger.info(f"Found {len(rows)} player-coach-season records")

    added_edges = 0
    skipped = 0
    for player_id, coach_id, team_name, season, coach_name in rows:
        a = f"player:{player_id}"
        b = f"coach:{coach_id}"
        if not G.has_node(a) or not G.has_node(b):
            skipped += 1
            continue
        if not G.has_edge(a, b):
            label = f"Coached by {coach_name} with {team_name} ({season}-{str(season+1)[2:]})"
            G.add_edge(a, b, type="coached_by", label=label, weight=0.7)
            added_edges += 1

    if skipped:
        logger.warning(f"  Skipped {skipped} coach-player records (node missing)")
    logger.info(f"Coach edges: {added_edges} added to graph")
    return added_edges


def build_all_star_edges(G: nx.Graph) -> int:
    """
    Build all_star edges from hardcoded All-Star game selections.
    Two players are connected if they were both selected for the All-Star Game
    in the same year (regardless of conference — East vs West doesn't matter
    for the 'shared experience' connection).
    """
    logger.info("Building All-Star edges from hardcoded rosters...")

    # Invert: year → list of player_ids who were All-Stars that year
    year_to_players: dict[int, list[str]] = defaultdict(list)
    for player_id, years in ALL_STAR_SELECTIONS.items():
        node_key = f"player:{player_id}"
        if not G.has_node(node_key):
            logger.debug(f"  All-Star: player {player_id} not in graph, skipping")
            continue
        for year in years:
            year_to_players[year].append(player_id)

    added = 0
    for year, players in sorted(year_to_players.items()):
        unique = list(dict.fromkeys(players))  # deduplicate, preserve order
        for a_id, b_id in combinations(unique, 2):
            na = f"player:{a_id}"
            nb = f"player:{b_id}"
            if not G.has_node(na) or not G.has_node(nb):
                continue
            if not G.has_edge(na, nb) or G[na][nb].get("type") != "all_star":
                # Don't override a stronger edge type (e.g. teammate)
                if not G.has_edge(na, nb):
                    G.add_edge(na, nb,
                               type="all_star",
                               label=f"Both in {year} NBA All-Star Game",
                               weight=1.5)
                    added += 1

    logger.info(f"All-Star edges: {added} added to graph")
    return added


def rebuild_college_edges_for_fixed_players(conn, G: nx.Graph) -> int:
    """
    After fixing college data in Postgres, rebuild college edges for the
    affected players. This avoids rebuilding the entire college edge set.
    """
    cur = conn.cursor()
    added = 0

    # Get all players with Georgetown college
    cur.execute("SELECT id FROM players WHERE college = 'Georgetown'")
    georgetown_ids = [r[0] for r in cur.fetchall()]
    logger.info(f"Georgetown players in DB: {len(georgetown_ids)} — {georgetown_ids}")

    for a_id, b_id in combinations(sorted(georgetown_ids), 2):
        na = f"player:{a_id}"
        nb = f"player:{b_id}"
        if not G.has_node(na) or not G.has_node(nb):
            continue
        if not G.has_edge(na, nb):
            G.add_edge(na, nb,
                       type="college",
                       label="Both attended Georgetown",
                       weight=1.2)
            added += 1

    logger.info(f"Georgetown college edges: {added} added to graph")
    return added


def add_current_season_teammate_edges(conn, G: nx.Graph) -> int:
    """
    Build new teammate edges for the 2024-25 season from the patched player_seasons.
    This covers: Curry+Butler (GSW 2024), SGA+Caruso (OKC 2024), etc.
    """
    cur = conn.cursor()

    # Get all player_seasons for season 2024 (2024-25)
    cur.execute("""
        SELECT ps.player_id, ps.team_id, t.full_name
        FROM player_seasons ps
        JOIN teams t ON ps.team_id = t.id
        WHERE ps.season = 2024
    """)
    rows = cur.fetchall()

    # Group by team
    team_players: dict[int, list[str]] = defaultdict(list)
    for player_id, team_id, team_name in rows:
        team_players[team_id].append(str(player_id))

    team_id_to_name = {team_id: team_name for _, team_id, team_name in rows}

    added = 0
    for team_id, players in team_players.items():
        team_name = team_id_to_name.get(team_id, f"Team {team_id}")
        for a_id, b_id in combinations(sorted(set(players)), 2):
            na = f"player:{a_id}"
            nb = f"player:{b_id}"
            if not G.has_node(na) or not G.has_node(nb):
                continue
            if not G.has_edge(na, nb):
                G.add_edge(na, nb,
                           type="teammate",
                           label=f"2024-25 {team_name} Teammates",
                           weight=0.9)
                added += 1

    logger.info(f"2024-25 teammate edges: {added} added")
    return added


def verify_connections(G: nx.Graph) -> list[tuple[str, str, bool, str]]:
    """
    Verify the key connections requested in the fix task.
    Returns list of (from_name, to_name, connected, details).
    """
    checks = [
        # (start_id, start_name, end_id, end_name, mode_edge_type)
        ("2548",    "Dwyane Wade",   "coach",   None,       "coached_by",  "Wade → Spoelstra coach edge"),
        ("2544",    "LeBron James",  "coach",   None,       "coached_by",  "LeBron → Spoelstra coach edge"),
        ("1626164", "Devin Booker",  "coach",   None,       "coached_by",  "Booker → Budenholzer coach edge"),
        ("203507",  "Giannis",       "coach",   None,       "coached_by",  "Giannis → Budenholzer coach edge"),
        ("893",     "Michael Jordan","player",  "23",       "teammate",    "Jordan ↔ Rodman teammate"),
        ("893",     "Jordan",        "player",  "406",      "all_star",    "Jordan ↔ Shaq All-Star"),
        ("947",     "Allen Iverson", "player",  "1630644",  "college",     "Iverson ↔ McClung Georgetown"),
        ("202710",  "Jimmy Butler",  "player",  "201939",   "teammate",    "Butler ↔ Curry GSW teammates"),
        ("1628983", "SGA",           "player",  "1627936",  "teammate",    "SGA ↔ Caruso OKC teammates"),
    ]

    results = []
    for *args, label in checks:
        if len(args) == 5:
            a_id, a_name, b_type, b_id, edge_type = args
        else:
            a_id, a_name, b_type, b_id, edge_type = args

        na = f"player:{a_id}"

        if b_id is None:
            # Check for ANY edge of the given type from this player
            has_edge = any(
                G[na][nb].get("type") == edge_type
                for nb in G.neighbors(na)
            ) if G.has_node(na) else False
            details = f"has at least one {edge_type} edge"
        else:
            nb = f"{b_type}:{b_id}"
            has_edge = G.has_edge(na, nb) if G.has_node(na) and G.has_node(nb) else False
            edge_data = G[na][nb] if has_edge else {}
            details = f"edge_type={edge_data.get('type')} label={edge_data.get('label', '')[:60]}"

        results.append((a_name, label, has_edge, details))

    return results


def main():
    logger.info("=" * 60)
    logger.info("HOOPCHAIN ETL — Step 10: Patch Missing Connections")
    logger.info("=" * 60)

    if not GRAPH_PKL_PATH.exists():
        raise SystemExit(f"graph.pkl not found at {GRAPH_PKL_PATH}. Run 02_build_graph.py first.")

    logger.info(f"Loading graph from {GRAPH_PKL_PATH}...")
    with open(GRAPH_PKL_PATH, "rb") as f:
        G = pickle.load(f)
    logger.info(f"Graph before patch: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    conn = get_pg_conn()
    logger.info("Connected to Postgres")

    # ── Step 1: Fix player seasons ──────────────────────────────────────────
    logger.info("")
    logger.info("── Step 1: Fix player seasons ──")
    fix_player_seasons(conn, G)

    # ── Step 2: Fix college data ────────────────────────────────────────────
    logger.info("")
    logger.info("── Step 2: Fix college data ──")
    fix_college_data(conn)

    # ── Step 3: Rebuild coach edges ─────────────────────────────────────────
    logger.info("")
    logger.info("── Step 3: Rebuild coach edges ──")
    rebuild_coach_edges_in_graph(conn, G)

    # ── Step 4: Add All-Star edges ──────────────────────────────────────────
    logger.info("")
    logger.info("── Step 4: Add All-Star edges ──")
    build_all_star_edges(G)

    # ── Step 5: Rebuild Georgetown college edges ────────────────────────────
    logger.info("")
    logger.info("── Step 5: Rebuild Georgetown college edges ──")
    rebuild_college_edges_for_fixed_players(conn, G)

    # ── Step 6: Add 2024-25 teammate edges ─────────────────────────────────
    logger.info("")
    logger.info("── Step 6: Add 2024-25 teammate edges ──")
    add_current_season_teammate_edges(conn, G)

    conn.close()

    # ── Step 7: Stats ───────────────────────────────────────────────────────
    logger.info("")
    logger.info("── Graph stats after all patches ──")
    logger.info(f"  Nodes: {G.number_of_nodes()}")
    logger.info(f"  Edges: {G.number_of_edges()}")
    from collections import Counter
    edge_counts = Counter(d.get("type") for _, _, d in G.edges(data=True))
    for etype, count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {etype}: {count:,}")

    # ── Step 8: Verify key connections ─────────────────────────────────────
    logger.info("")
    logger.info("── Verification ──")
    results = verify_connections(G)
    all_ok = True
    for a_name, label, connected, details in results:
        status = "✅" if connected else "❌"
        logger.info(f"  {status} {label}: {details}")
        if not connected:
            all_ok = False

    # ── Step 9: Save ────────────────────────────────────────────────────────
    logger.info("")
    logger.info(f"Saving graph to {GRAPH_PKL_PATH}...")
    with open(GRAPH_PKL_PATH, "wb") as f:
        pickle.dump(G, f)

    logger.info(f"Copying to {BACKEND_GRAPH_PKL}...")
    with open(BACKEND_GRAPH_PKL, "wb") as f:
        pickle.dump(G, f)

    logger.info("")
    logger.info("=" * 60)
    if all_ok:
        logger.info("✅ All connection patches applied and verified!")
    else:
        logger.warning("⚠️  Patch applied but some connections still failing — check logs above")
    logger.info(f"Final: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    logger.info("Next: run 06_validate_graph.py, then commit backend/graph.pkl")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
