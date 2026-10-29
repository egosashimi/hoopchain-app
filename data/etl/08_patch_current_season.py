"""
HOOPCHAIN ETL — Step 8: DEPRECATED — DO NOT USE
=================================================
This script used hardcoded Balldontlie player IDs that were WRONG for at least
10 marquee players (Luka, Morant, Edwards, LaMelo, Trae, Brunson, Poole, Mobley,
Green, + others). Running it writes seasons onto the wrong players, creating
phantom edges (false connections the game accepts) and missing real connections.

REPLACEMENT: Use 12_topup_modern_seasons.py which fetches canonical NBA Stats IDs
directly from nba_api for all 30 teams × 2023-24 and 2024-25 seasons.

Original docstring preserved for reference:
Fetches 2023-24 and 2024-25 NBA season rosters from the Balldontlie API
(free tier, no API key required) and adds any missing player-team-season
edges to the existing graph.pkl without removing existing edges.

This script is idempotent — safe to re-run multiple times.

After running, Wembanyama (1641705) and Cooper Flagg (1642277) should
appear in the graph.

Usage (DEPRECATED — use 12_topup_modern_seasons.py instead):
    python data/etl/08_patch_current_season.py
    # or against production:
    DATABASE_URL=postgresql://... python data/etl/08_patch_current_season.py
"""

import sys
print("ERROR: 08_patch_current_season.py is DEPRECATED.")
print("Use 12_topup_modern_seasons.py instead.")
print("See the docstring for details on why this script was retired.")
sys.exit(1)

from __future__ import annotations

import logging
import os
import pickle
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2
import requests
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
GRAPH_PKL_PATH = ETL_DIR.parent / "exports" / "graph.pkl"
BACKEND_GRAPH_PKL = ETL_DIR.parent.parent / "backend" / "graph.pkl"

BDL_BASE = "https://api.balldontlie.io/v1"
SEASONS = [2023, 2024]  # 2023 = 2023-24 season, 2024 = 2024-25 season
PER_PAGE = 100

# Known BDL player ID → NBA.com player ID mapping for key recent players.
# BDL uses its own internal IDs; we must map to NBA.com IDs to match the graph.
# The NBA.com ID is found in common_player_info.person_id.
BDL_TO_NBA_ID: dict[int, str] = {
    # These are looked up via BDL's player search endpoint and cross-referenced
    # with nba.com stats pages. Populated as needed.
}


# ---------------------------------------------------------------------------
# BDL API helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: dict) -> dict:
    """GET with automatic retry on 429."""
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 2)) + attempt
                log.warning(f"Rate limited, waiting {wait}s…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 4:
                raise
            log.warning(f"Request failed ({e}), retrying in {2**attempt}s…")
            time.sleep(2 ** attempt)
    return {}


def fetch_season_players(season: int) -> list[dict]:
    """
    Fetch all players who appeared in a given season via /players endpoint.
    Returns list of {bdl_id, first_name, last_name, team_id, team_abbr, ...}.
    """
    log.info(f"Fetching all players for {season}-{str(season+1)[2:]} season…")
    players = []
    cursor = None

    while True:
        params: dict = {"per_page": PER_PAGE, "seasons[]": season}
        if cursor:
            params["cursor"] = cursor

        data = _get(f"{BDL_BASE}/players", params)
        batch = data.get("data", [])
        players.extend(batch)

        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        log.info(f"  Season {season}: fetched {len(players)} players so far (cursor={next_cursor})")

        if not next_cursor:
            break
        cursor = next_cursor
        time.sleep(0.25)  # polite rate limit

    log.info(f"  Total players for {season}: {len(players)}")
    return players


def fetch_season_stats(season: int) -> list[dict]:
    """
    Fetch season averages to get player-team associations for a season.
    Returns list of {player_id, team_id, ...}.
    """
    log.info(f"Fetching season stats for {season} (player-team associations)…")
    stats = []
    cursor = None

    while True:
        params: dict = {"per_page": PER_PAGE, "season": season}
        if cursor:
            params["cursor"] = cursor

        data = _get(f"{BDL_BASE}/season_averages", params)
        batch = data.get("data", [])
        if not batch:
            break
        stats.extend(batch)

        meta = data.get("meta", {})
        next_cursor = meta.get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor
        time.sleep(0.25)

    log.info(f"  Total stats entries for {season}: {len(stats)}")
    return stats


def search_bdl_player(first: str, last: str) -> list[dict]:
    """Search BDL for a player by name to get their BDL ID."""
    data = _get(f"{BDL_BASE}/players", {"search": f"{first} {last}", "per_page": 5})
    return data.get("data", [])


def fetch_bdl_player_nba_id(bdl_player_id: int) -> str | None:
    """Try to get the NBA.com player ID from a BDL player entry."""
    data = _get(f"{BDL_BASE}/players/{bdl_player_id}", {})
    p = data.get("data", data)
    # BDL may include nba_id or external IDs in some responses
    return str(p.get("nba_id", "")) or None


# ---------------------------------------------------------------------------
# NBA.com ID resolution via BDL player search
# ---------------------------------------------------------------------------

# Players definitely in BDL that we need in the graph.
# Format: (nba_com_id, first_name, last_name, expected_team_abbr)
# IMPORTANT: IDs must match NBA Stats (nba.com) IDs, NOT sequential guesses.
# Verified against nbadb and cdn.nba.com/headshots/nba/latest/1040x760/{id}.png
PLAYERS_TO_PATCH = [
    # 2023-24 draft class rookies and key additions
    ("1641705", "Victor",    "Wembanyama", "SAS"),
    ("1642277", "Cooper",    "Flagg",       "BOS"),  # 2024-25 rookie
    ("1631096", "Chet",      "Holmgren",    "OKC"),  # #2 pick 2022 — ID 1631096
    ("1629073", "Scoot",     "Henderson",   "POR"),
    ("1641706", "Brandon",   "Miller",      "CHA"),
    ("1631094", "Paolo",     "Banchero",    "ORL"),  # #1 pick 2022 — ID 1631094
    ("1631095", "Jabari",    "Smith",       "HOU"),  # #3 pick 2022 — ID 1631095
    ("1641710", "Jarace",    "Walker",      "IND"),
    ("1641712", "Ausar",     "Thompson",    "DET"),
    ("1641711", "Amen",      "Thompson",    "HOU"),
    ("1631097", "Bennedict", "Mathurin",    "IND"),  # #6 pick 2022 — ID 1631097
    ("1631099", "Keegan",    "Murray",      "SAC"),  # #4 pick 2022 — ID 1631099
]

# Map NBA.com team abbreviation to the team ID used in the graph/DB.
# These are the canonical 30 teams.
ABBR_TO_TEAM_ID: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "NJN": 1610612751, "BKN": 1610612751,
    "CHA": 1610612766, "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742,
    "DEN": 1610612743, "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745,
    "IND": 1610612754, "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
    "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740,
    "NYK": 1610612752, "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755,
    "PHX": 1610612756, "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759,
    "TOR": 1610612761, "UTA": 1610612762, "WAS": 1610612764,
}

# NBA.com team ID → display name
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

# BDL team abbreviation → NBA.com team ID mapping (BDL sometimes uses different abbrs)
BDL_ABBR_TO_TEAM_ID: dict[str, int] = {
    **ABBR_TO_TEAM_ID,
    "GS":  1610612744,  # Golden State Warriors
    "NO":  1610612740,  # New Orleans Pelicans
    "NY":  1610612752,  # New York Knicks
    "OKC": 1610612760,
    "SA":  1610612759,  # San Antonio Spurs
    "PHO": 1610612756,  # Phoenix Suns
}


def teammate_weight(seasons_together: int) -> float:
    if seasons_together >= 5:
        return 0.3
    elif seasons_together >= 2:
        return 0.6
    return 0.9


# ---------------------------------------------------------------------------
# BDL player-team-season extraction
# ---------------------------------------------------------------------------

def fetch_bdl_player_seasons() -> list[dict]:
    """
    For each target season, fetch all player-team associations from BDL.
    Returns list of {player_id (BDL), nba_com_id (if resolvable), team_id, season}.
    """
    all_records: list[dict] = []

    for season in SEASONS:
        players_data = fetch_season_players(season)
        for p in players_data:
            # BDL player object has: id, first_name, last_name, team (nested)
            bdl_id = p.get("id")
            team = p.get("team") or {}
            team_abbr = (team.get("abbreviation") or "").upper()
            team_id = BDL_ABBR_TO_TEAM_ID.get(team_abbr)

            if not team_id:
                continue

            all_records.append({
                "bdl_id": bdl_id,
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "team_id": team_id,
                "team_abbr": team_abbr,
                "season": season,
            })

    log.info(f"Fetched {len(all_records)} player-team-season records from BDL across {SEASONS}")
    return all_records


# ---------------------------------------------------------------------------
# Name matching against the existing graph
# ---------------------------------------------------------------------------

def build_name_to_nba_id(G: nx.Graph) -> dict[str, str]:
    """Build lowercased full_name → nba_com_id map from graph nodes."""
    mapping = {}
    for node, data in G.nodes(data=True):
        if data.get("type") != "player":
            continue
        name = (data.get("name") or "").strip().lower()
        nba_id = node.split(":", 1)[1]
        if name:
            mapping[name] = nba_id
    return mapping


def resolve_nba_id(record: dict, name_map: dict[str, str]) -> str | None:
    """Try to resolve a BDL record to an NBA.com player ID."""
    full = f"{record['first_name']} {record['last_name']}".strip().lower()
    return name_map.get(full)


# ---------------------------------------------------------------------------
# Core patch logic
# ---------------------------------------------------------------------------

def build_new_teammate_edges(new_seasons: list[dict], G: nx.Graph) -> list[dict]:
    """
    Given a list of new player-team-season records (with nba_com_id resolved),
    compute new teammate edges not already in the graph.
    """
    # Group new seasons by (team_id, season)
    team_season_players: dict[tuple, set[str]] = defaultdict(set)
    for rec in new_seasons:
        nba_id = rec.get("nba_com_id")
        if not nba_id:
            continue
        key = (rec["team_id"], rec["season"])
        team_season_players[key].add(nba_id)

    new_edges = []
    existing_edges: set[tuple] = set()
    for u, v, data in G.edges(data=True):
        if data.get("type") == "teammate":
            a = u.split(":", 1)[1]
            b = v.split(":", 1)[1]
            existing_edges.add((min(a, b), max(a, b)))

    for (team_id, season), players in team_season_players.items():
        player_list = sorted(players)
        for a, b in combinations(player_list, 2):
            pair = (min(a, b), max(a, b))
            if pair in existing_edges:
                continue
            na = f"player:{a}"
            nb = f"player:{b}"
            # Only add if at least one player is already in the graph (or both are new)
            if not G.has_node(na) and not G.has_node(nb):
                continue

            team_name = TEAM_ID_TO_NAME.get(team_id, f"Team {team_id}")
            new_edges.append({
                "node_a_type": "player", "node_a_id": a,
                "node_b_type": "player", "node_b_id": b,
                "edge_type": "teammate",
                "edge_label": f"{season}-{str(season+1)[2:]} {team_name} Teammates",
                "weight": 0.9,  # 1 season together
                "metadata": {"team_id": team_id, "season": season, "seasons_together": 1},
            })
            existing_edges.add(pair)

    log.info(f"Generated {len(new_edges)} new teammate edges from BDL data")
    return new_edges


def add_draft_class_edges(G: nx.Graph, new_player_ids: list[str]) -> list[dict]:
    """Add draft class edges for new players based on their draft year from graph metadata."""
    # For new players we know the rough draft year from the season they appear in
    # This is handled upstream when we add players; skip for now
    return []


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

def get_pg_conn():
    raw = os.getenv("DATABASE_URL", "postgresql://hoopchain:hoopchain_dev@localhost:5433/hoopchain")
    url = raw.replace("postgresql+asyncpg://", "postgresql://")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return psycopg2.connect(url)


def insert_player_seasons_pg(conn, seasons: list[dict]):
    """Insert new player-season records into Postgres (idempotent)."""
    cur = conn.cursor()
    inserted = 0
    for rec in seasons:
        nba_id = rec.get("nba_com_id")
        if not nba_id:
            continue
        try:
            cur.execute("""
                INSERT INTO player_seasons (player_id, team_id, season)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (nba_id, rec["team_id"], rec["season"]))
            inserted += cur.rowcount
        except Exception as e:
            log.warning(f"  Skip player_seasons insert for {nba_id}: {e}")
            conn.rollback()
            continue
    conn.commit()
    log.info(f"  Inserted {inserted} new player_season rows")


def insert_players_pg(conn, players: list[dict]):
    """Insert new player rows into Postgres (idempotent)."""
    cur = conn.cursor()
    inserted = 0
    for p in players:
        try:
            cur.execute("""
                INSERT INTO players (id, full_name, first_name, last_name, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    is_active = EXCLUDED.is_active
            """, (p["id"], p["full_name"], p["first_name"], p["last_name"], p["is_active"]))
            inserted += cur.rowcount
        except Exception as e:
            log.warning(f"  Skip player insert for {p['id']}: {e}")
            conn.rollback()
            continue
    conn.commit()
    log.info(f"  Upserted {inserted} player rows")


def rebuild_search_vectors(conn):
    cur = conn.cursor()
    cur.execute("UPDATE players SET search_vector = to_tsvector('english', full_name)")
    conn.commit()
    log.info("  Rebuilt search_vectors")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("HOOPCHAIN ETL — Step 8: Patch current seasons via BDL")
    log.info("=" * 60)

    # Load existing graph
    if not GRAPH_PKL_PATH.exists():
        raise SystemExit(f"graph.pkl not found at {GRAPH_PKL_PATH}. Run 02_build_graph.py first.")

    log.info(f"Loading graph from {GRAPH_PKL_PATH}…")
    with open(GRAPH_PKL_PATH, "rb") as f:
        G = pickle.load(f)

    log.info(f"Current graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Build name lookup map
    name_map = build_name_to_nba_id(G)
    log.info(f"Name map has {len(name_map)} entries")

    # Step 1: Manually patch well-known recent players not in the base dataset
    # These are players from the 2023-24 and 2024-25 draft classes.
    # We add them as graph nodes and their team-season edges.
    # IMPORTANT: All IDs must match NBA Stats (nba.com) player IDs verified against
    # the nbadb base dataset and cdn.nba.com/headshots/nba/latest/1040x760/{id}.png
    KNOWN_PLAYER_SEASONS = [
        # (nba_com_id, full_name, first, last, is_active, team_id, seasons)
        ("1641705", "Victor Wembanyama", "Victor",    "Wembanyama", True,
         ABBR_TO_TEAM_ID["SAS"], [2023, 2024]),
        ("1642277", "Cooper Flagg",      "Cooper",    "Flagg",      True,
         ABBR_TO_TEAM_ID["BOS"], [2024]),
        ("1631096", "Chet Holmgren",     "Chet",      "Holmgren",   True,
         ABBR_TO_TEAM_ID["OKC"], [2023, 2024]),   # #2 pick 2022, ID confirmed via nbadb
        ("1629073", "Scoot Henderson",   "Scoot",     "Henderson",  True,
         ABBR_TO_TEAM_ID["POR"], [2023, 2024]),
        ("1641706", "Brandon Miller",    "Brandon",   "Miller",     True,
         ABBR_TO_TEAM_ID["CHA"], [2023, 2024]),
        ("1631094", "Paolo Banchero",    "Paolo",     "Banchero",   True,
         ABBR_TO_TEAM_ID["ORL"], [2022, 2023, 2024]),  # #1 pick 2022, ID confirmed via nbadb
        ("1631095", "Jabari Smith Jr.",  "Jabari",    "Smith",      True,
         ABBR_TO_TEAM_ID["HOU"], [2022, 2023, 2024]),  # #3 pick 2022, ID confirmed via nbadb
        ("1641710", "Jarace Walker",     "Jarace",    "Walker",     True,
         ABBR_TO_TEAM_ID["IND"], [2023, 2024]),
        ("1641712", "Ausar Thompson",    "Ausar",     "Thompson",   True,
         ABBR_TO_TEAM_ID["DET"], [2023, 2024]),
        ("1641711", "Amen Thompson",     "Amen",      "Thompson",   True,
         ABBR_TO_TEAM_ID["HOU"], [2023, 2024]),
        ("1631097", "Bennedict Mathurin","Bennedict", "Mathurin",   True,
         ABBR_TO_TEAM_ID["IND"], [2022, 2023, 2024]),  # #6 pick 2022, ID confirmed via nbadb
        ("1631099", "Keegan Murray",     "Keegan",    "Murray",     True,
         ABBR_TO_TEAM_ID["SAC"], [2022, 2023, 2024]),  # #4 pick 2022, ID confirmed via nbadb
        # Other missing active stars
        ("1629630", "Jordan Poole",      "Jordan",    "Poole",      True,
         ABBR_TO_TEAM_ID["WAS"], [2022, 2023, 2024]),
        ("1630162", "Evan Mobley",       "Evan",      "Mobley",     True,
         ABBR_TO_TEAM_ID["CLE"], [2021, 2022, 2023, 2024]),
        ("1630163", "Jalen Green",       "Jalen",     "Green",      True,
         ABBR_TO_TEAM_ID["HOU"], [2021, 2022, 2023, 2024]),
        ("1629027", "Ja Morant",         "Ja",        "Morant",     True,
         ABBR_TO_TEAM_ID["MEM"], [2019, 2020, 2021, 2022, 2023, 2024]),
        ("1628973", "Luka Doncic",       "Luka",      "Doncic",     True,
         ABBR_TO_TEAM_ID["DAL"], [2018, 2019, 2020, 2021, 2022, 2023]),
        ("1629029", "Zion Williamson",   "Zion",      "Williamson", True,
         ABBR_TO_TEAM_ID["NOP"], [2019, 2020, 2021, 2022, 2023, 2024]),
        ("1630169", "Franz Wagner",      "Franz",     "Wagner",     True,
         ABBR_TO_TEAM_ID["ORL"], [2021, 2022, 2023, 2024]),
        ("1630178", "Josh Giddey",       "Josh",      "Giddey",     True,
         ABBR_TO_TEAM_ID["OKC"], [2021, 2022, 2023]),
        # 2024-25 roster moves (mid-season trades and signings)
        ("202710",  "Jimmy Butler",      "Jimmy",     "Butler",     True,
         ABBR_TO_TEAM_ID["GSW"], [2024]),
        ("1627936", "Alex Caruso",       "Alex",      "Caruso",     True,
         ABBR_TO_TEAM_ID["OKC"], [2024]),
    ]

    new_player_records = []
    new_season_records = []
    added_nodes = 0

    for nba_id, full_name, first, last, is_active, team_id, seasons in KNOWN_PLAYER_SEASONS:
        node_key = f"player:{nba_id}"

        # Safety: if the configured ID is not in the graph but a different node with the
        # same name IS, use that existing node instead of creating a ghost duplicate.
        # This prevents duplicate nodes when the hardcoded ID diverges from nbadb's ID.
        if not G.has_node(node_key):
            existing_id = name_map.get(full_name.strip().lower())
            if existing_id and existing_id != nba_id:
                log.warning(
                    f"  Name collision for {full_name!r}: configured id={nba_id} "
                    f"but graph already has this name at id={existing_id}. "
                    f"Using existing node — check KNOWN_PLAYER_SEASONS."
                )
                nba_id = existing_id
                node_key = f"player:{nba_id}"
            else:
                G.add_node(node_key, type="player", name=full_name, is_active=is_active)
                log.info(f"  Added node: {full_name} ({nba_id})")
                added_nodes += 1
                name_map[full_name.strip().lower()] = nba_id

        # Ensure is_active is current
        G.nodes[node_key]["is_active"] = is_active

        new_player_records.append({
            "id": nba_id, "full_name": full_name,
            "first_name": first, "last_name": last, "is_active": is_active,
        })
        for season in seasons:
            new_season_records.append({
                "nba_com_id": nba_id,
                "team_id": team_id,
                "season": season,
            })

    log.info(f"Added {added_nodes} new player nodes; {len(new_season_records)} season records to process")

    # Step 2: Fetch BDL season data for bulk player-team associations
    log.info("Fetching BDL season data for 2023 and 2024…")
    bdl_records: list[dict] = []
    try:
        for season in SEASONS:
            batch = fetch_season_players(season)
            for p in batch:
                team = p.get("team") or {}
                team_abbr = (team.get("abbreviation") or "").upper()
                team_id_resolved = BDL_ABBR_TO_TEAM_ID.get(team_abbr)
                if not team_id_resolved:
                    continue
                first = p.get("first_name", "").strip()
                last = p.get("last_name", "").strip()
                full = f"{first} {last}".strip().lower()
                nba_id = name_map.get(full)
                if nba_id:
                    bdl_records.append({
                        "nba_com_id": nba_id,
                        "team_id": team_id_resolved,
                        "season": season,
                    })
    except Exception as e:
        log.warning(f"BDL fetch failed ({e}); continuing with known-players patch only")

    log.info(f"BDL resolved {len(bdl_records)} player-team-season records with known NBA IDs")

    # Merge all season records (deduplicate)
    all_seasons = new_season_records + bdl_records
    seen_seasons: set[tuple] = set()
    deduped_seasons = []
    for rec in all_seasons:
        key = (rec["nba_com_id"], rec["team_id"], rec["season"])
        if key not in seen_seasons:
            seen_seasons.add(key)
            deduped_seasons.append(rec)

    log.info(f"Total unique new season records: {len(deduped_seasons)}")

    # Step 3: Build new teammate edges
    new_edges = build_new_teammate_edges(deduped_seasons, G)

    # Step 4: Add edges to graph
    edges_added = 0
    for e in new_edges:
        na = f"{e['node_a_type']}:{e['node_a_id']}"
        nb = f"{e['node_b_type']}:{e['node_b_id']}"
        if not G.has_node(na):
            G.add_node(na, type="player", name=e["node_a_id"], is_active=True)
        if not G.has_node(nb):
            G.add_node(nb, type="player", name=e["node_b_id"], is_active=True)
        G.add_edge(na, nb,
                   type=e["edge_type"],
                   label=e["edge_label"],
                   weight=e["weight"])
        edges_added += 1

    log.info(f"Added {edges_added} new edges to graph")

    # Step 5: Also add draft class edges for new players
    # Group new players by draft year (approximate from first season)
    draft_year_players: dict[int, list[str]] = defaultdict(list)
    for nba_id, full_name, first, last, is_active, team_id, seasons in KNOWN_PLAYER_SEASONS:
        if seasons:
            draft_year = min(seasons)
            draft_year_players[draft_year].append(nba_id)

    draft_edges_added = 0
    for draft_year, player_ids in draft_year_players.items():
        # Also include existing players who were drafted the same year
        existing_draft_year_players = []
        for node, data in G.nodes(data=True):
            if data.get("type") != "player":
                continue
            nid = node.split(":", 1)[1]
            # Check via graph edges if they have a draft_class edge for this year
            for neighbor in G.neighbors(node):
                ed = G[node][neighbor]
                if (ed.get("type") == "draft_class" and
                        (ed.get("metadata") or {}).get("draft_year") == draft_year):
                    existing_draft_year_players.append(nid)
                    break

        all_draft_players = list(set(player_ids + existing_draft_year_players[:30]))
        for a, b in combinations(player_ids, 2):
            na = f"player:{a}"
            nb = f"player:{b}"
            if not G.has_edge(na, nb) or G[na][nb].get("type") != "draft_class":
                G.add_edge(na, nb,
                           type="draft_class",
                           label=f"Both in {draft_year} NBA Draft class",
                           weight=1.4)
                draft_edges_added += 1
        # Connect new players to existing draft class members
        for new_pid in player_ids:
            na = f"player:{new_pid}"
            for old_pid in existing_draft_year_players[:20]:
                nb = f"player:{old_pid}"
                if not G.has_edge(na, nb):
                    G.add_edge(na, nb,
                               type="draft_class",
                               label=f"Both in {draft_year} NBA Draft class",
                               weight=1.4)
                    draft_edges_added += 1

    log.info(f"Added {draft_edges_added} draft class edges for new players")

    # Step 6: Save updated graph
    log.info(f"Saving updated graph to {GRAPH_PKL_PATH}…")
    with open(GRAPH_PKL_PATH, "wb") as f:
        pickle.dump(G, f)

    # Also update backend/graph.pkl
    log.info(f"Copying to backend graph.pkl at {BACKEND_GRAPH_PKL}…")
    with open(BACKEND_GRAPH_PKL, "wb") as f:
        pickle.dump(G, f)

    log.info(f"Final graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Step 7: Update Postgres
    try:
        conn = get_pg_conn()
        conn.autocommit = False
        log.info("Updating Postgres…")
        insert_players_pg(conn, new_player_records)
        insert_player_seasons_pg(conn, deduped_seasons)
        rebuild_search_vectors(conn)
        conn.close()
        log.info("Postgres updated successfully")
    except Exception as e:
        log.error(f"Postgres update failed: {e}")
        log.warning("Graph.pkl was updated but Postgres was not. Run 07_seed_players_table.py to sync.")

    # Verify key players
    log.info("")
    log.info("=== Verification ===")
    checks = [
        ("Victor Wembanyama", "1641705"),
        ("Cooper Flagg",      "1642277"),
        ("Chet Holmgren",     "1631168"),
        ("LeBron James",      "2544"),
        ("Stephen Curry",     "201939"),
    ]
    all_ok = True
    for name, nba_id in checks:
        in_graph = G.has_node(f"player:{nba_id}")
        status = "✅" if in_graph else "❌"
        log.info(f"  {status} {name} ({nba_id}): {'in graph' if in_graph else 'MISSING'}")
        if not in_graph:
            all_ok = False

    log.info("")
    log.info("=" * 60)
    if all_ok:
        log.info("✅ Patch complete — all key players verified in graph")
    else:
        log.warning("Patch complete but some key players are still missing")
    log.info("Next: run 09_recognizability_score.py or 07_seed_players_table.py against production")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
