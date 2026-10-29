"""
HOOPCHAIN — Graph Service
Manages the in-memory NetworkX graph.
Loads from pickle on startup (or falls back to mock graph in dev mode).
Provides BFS path finding, hop validation, and neighbor lookup.
"""

from __future__ import annotations

import logging
import pickle
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from ..config import settings

logger = logging.getLogger(__name__)

# ------------------------------------
# Mode definitions
# ------------------------------------

VALID_MODES: list[str] = ["classic", "wild", "coach"]

# Maps game mode → the single edge type it allows (None = all types)
# classic = teammates only | wild = all edge types | coach = coached_by only
MODE_TO_EDGE_TYPE: dict[str, str | None] = {
    "classic": "teammate",
    "wild":    None,
    "coach":   "coached_by",
}

# ------------------------------------
# NBA team id → display name
# Used to rewrite legacy edge labels that embed raw team_id.
# ------------------------------------

_NBA_TEAM_NAMES: dict[int, str] = {
    1610612737: "Atlanta Hawks",
    1610612738: "Boston Celtics",
    1610612739: "Cleveland Cavaliers",
    1610612740: "New Orleans Pelicans",
    1610612741: "Chicago Bulls",
    1610612742: "Dallas Mavericks",
    1610612743: "Denver Nuggets",
    1610612744: "Golden State Warriors",
    1610612745: "Houston Rockets",
    1610612746: "Los Angeles Clippers",
    1610612747: "Los Angeles Lakers",
    1610612748: "Miami Heat",
    1610612749: "Milwaukee Bucks",
    1610612750: "Minnesota Timberwolves",
    1610612751: "Brooklyn Nets",
    1610612752: "New York Knicks",
    1610612753: "Orlando Magic",
    1610612754: "Indiana Pacers",
    1610612755: "Philadelphia 76ers",
    1610612756: "Phoenix Suns",
    1610612757: "Portland Trail Blazers",
    1610612758: "Sacramento Kings",
    1610612759: "San Antonio Spurs",
    1610612760: "Oklahoma City Thunder",
    1610612761: "Toronto Raptors",
    1610612762: "Utah Jazz",
    1610612763: "Memphis Grizzlies",
    1610612764: "Washington Wizards",
    1610612765: "Detroit Pistons",
    1610612766: "Charlotte Hornets",
}

_LEGACY_TEAMMATE_RE = re.compile(
    r"Teammates?\s+on\s+(\d{4}-\d{2})\s+roster\s+\(team_id=(\d+)\)",
    re.IGNORECASE,
)
_LEGACY_COACHED_RE = re.compile(
    r"Both\s+coached\s+by\s+(.+?)\s+\(team_id=(\d+)\)",
    re.IGNORECASE,
)
_LEGACY_COACHED_SEASON_RE = re.compile(
    r"Both\s+coached\s+by\s+(.+?)\s+on\s+(\d{4}-\d{2})\s+roster\s+\(team_id=(\d+)\)",
    re.IGNORECASE,
)


def _patch_legacy_labels(G: nx.Graph) -> None:
    """
    Rewrite any edge labels that embed raw team_id values.

    Handles:
      "Teammates on 2015-16 roster (team_id=1610612759)"
        → "2015-16 San Antonio Spurs Teammates"
      "Both coached by Erik Spoelstra (team_id=1610612748)"
        → "Both coached by Erik Spoelstra (Miami Heat)"
      "Both coached by Pop on 2005-06 roster (team_id=1610612759)"
        → "Both coached by Pop (2005-06 San Antonio Spurs)"
    """
    patched = 0
    for _u, _v, data in G.edges(data=True):
        label = data.get("label", "")
        if not label:
            continue

        # Teammate pattern
        m = _LEGACY_TEAMMATE_RE.fullmatch(label)
        if m:
            season_str, team_id_str = m.group(1), m.group(2)
            team_name = _NBA_TEAM_NAMES.get(int(team_id_str), f"Team {team_id_str}")
            data["label"] = f"{season_str} {team_name} Teammates"
            patched += 1
            continue

        # Coached-by with season pattern
        m = _LEGACY_COACHED_SEASON_RE.fullmatch(label)
        if m:
            coach_name, season_str, team_id_str = m.group(1), m.group(2), m.group(3)
            team_name = _NBA_TEAM_NAMES.get(int(team_id_str), f"Team {team_id_str}")
            data["label"] = f"Both coached by {coach_name} ({season_str} {team_name})"
            patched += 1
            continue

        # Coached-by without season
        m = _LEGACY_COACHED_RE.fullmatch(label)
        if m:
            coach_name, team_id_str = m.group(1), m.group(2)
            team_name = _NBA_TEAM_NAMES.get(int(team_id_str), f"Team {team_id_str}")
            data["label"] = f"Both coached by {coach_name} ({team_name})"
            patched += 1
            continue

        # Fallback: any remaining raw team_id= substring
        if "team_id=" in label.lower():
            def _replace_team_id(matchobj: re.Match) -> str:
                tid = int(matchobj.group(1))
                return _NBA_TEAM_NAMES.get(tid, matchobj.group(0))
            new_label = re.sub(r"team_id=(\d+)", _replace_team_id, label, flags=re.IGNORECASE)
            if new_label != label:
                data["label"] = new_label
                patched += 1

    if patched:
        logger.info(f"Patched {patched} legacy edge labels")


# ------------------------------------
# Global graph + pre-built mode subgraphs
# ------------------------------------

_graph: nx.Graph | None = None
# Keyed by mode name; populated once after graph load.
# Avoids rescanning all edges on every BFS call (274ms → ~2ms per call).
_mode_subgraphs: dict[str, nx.Graph] = {}


def get_graph() -> nx.Graph:
    global _graph
    if _graph is None:
        raise RuntimeError("Graph not initialized. Call load_graph() at startup.")
    return _graph


def _prebuild_mode_subgraphs(G: nx.Graph) -> None:
    """Pre-build and cache per-mode subgraphs so BFS callers skip the edge scan."""
    global _mode_subgraphs
    _mode_subgraphs = {}
    for mode, edge_type in MODE_TO_EDGE_TYPE.items():
        if edge_type is None:
            _mode_subgraphs[mode] = G   # wild = full graph reference
        else:
            sub_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
            _mode_subgraphs[mode] = G.edge_subgraph(sub_edges)
    edge_counts = {m: sg.number_of_edges() for m, sg in _mode_subgraphs.items()}
    logger.info("Mode subgraphs cached: %s", edge_counts)


# ------------------------------------
# Graph loading
# ------------------------------------

def load_graph() -> nx.Graph:
    """
    Load the NetworkX graph. Strategy:
    1. If USE_MOCK_GRAPH=true → use built-in mock graph
    2. Else → try loading the pickle; fall back to mock if not found
    """
    global _graph

    if settings.use_mock_graph:
        logger.info("USE_MOCK_GRAPH=true — loading mock graph")
        _graph = _build_mock_graph()
        _prebuild_mode_subgraphs(_graph)
        return _graph

    pickle_path = settings.graph_pickle_resolved
    logger.info(f"Attempting to load graph from: {pickle_path}")
    if pickle_path.exists():
        logger.info(f"Loading graph from {pickle_path}")
        with open(pickle_path, "rb") as f:
            _graph = pickle.load(f)
        logger.info(f"Graph loaded: {_graph.number_of_nodes()} nodes, {_graph.number_of_edges()} edges")
        _patch_legacy_labels(_graph)
    else:
        logger.warning(
            f"Graph pickle not found at {pickle_path}. "
            "Falling back to mock graph. Run ETL to generate the real graph."
        )
        _graph = _build_mock_graph()

    _prebuild_mode_subgraphs(_graph)
    return _graph


def save_graph(G: nx.Graph, path: Path) -> None:
    """Persist the graph to a pickle file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"Graph saved to {path} ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)")


# ------------------------------------
# Core graph operations
# ------------------------------------

def validate_hop(from_id: str, from_type: str, to_id: str, to_type: str) -> dict | None:
    """
    Check if there is an edge between (from_type:from_id) and (to_type:to_id).
    Returns edge data dict if valid, None if no edge exists.
    """
    G = get_graph()
    a = f"{from_type}:{from_id}"
    b = f"{to_type}:{to_id}"

    if not G.has_node(a) or not G.has_node(b):
        return None

    if G.has_edge(a, b):
        edge_data = G[a][b]
        return {
            "valid": True,
            "edge_type": edge_data.get("type"),
            "edge_label": edge_data.get("label"),
            "weight": edge_data.get("weight", 1.0),
        }
    return None


def find_shortest_path(
    start_id: str,
    start_type: str,
    end_id: str,
    end_type: str,
) -> list[str] | None:
    """
    BFS to find the shortest path between two nodes.
    Returns list of node keys like ['player:123', 'player:456'] or None.
    Uses edge weight for weighted shortest path.
    """
    G = get_graph()
    a = f"{start_type}:{start_id}"
    b = f"{end_type}:{end_id}"

    if not G.has_node(a) or not G.has_node(b):
        return None

    try:
        path = nx.shortest_path(G, a, b, weight="weight")
        return path
    except nx.NetworkXNoPath:
        return None
    except nx.NodeNotFound:
        return None


def find_shortest_path_with_labels(
    start_id: str,
    start_type: str,
    end_id: str,
    end_type: str,
) -> list[dict] | None:
    """
    BFS shortest path returned as a list of node dicts with edge metadata.
    Each entry: {id, type, name, headshot_url, edge_type, connection_label}
    The last node has no edge fields (it's the destination).
    """
    G = get_graph()
    path = find_shortest_path(start_id, start_type, end_id, end_type)
    if not path:
        return None

    result: list[dict] = []
    for i, node_key in enumerate(path):
        parts = node_key.split(":", 1)
        ntype = parts[0] if len(parts) == 2 else "player"
        nid = parts[1] if len(parts) == 2 else node_key
        node_data = G.nodes.get(node_key, {})
        entry: dict = {
            "id": nid,
            "type": ntype,
            "name": node_data.get("name", nid),
            "headshot_url": node_data.get("headshot_url"),
        }
        if i < len(path) - 1:
            next_key = path[i + 1]
            if G.has_edge(node_key, next_key):
                edge = G[node_key][next_key]
                entry["edge_type"] = edge.get("type")
                entry["connection_label"] = edge.get("label")
        result.append(entry)

    return result


def get_neighbors(node_id: str, node_type: str) -> list[dict]:
    """
    Get all neighbors of a node, with edge metadata.
    Used for debugging and graph validation.
    """
    G = get_graph()
    key = f"{node_type}:{node_id}"

    if not G.has_node(key):
        return []

    neighbors = []
    for neighbor in G.neighbors(key):
        edge_data = G[key][neighbor]
        node_data = G.nodes[neighbor]
        neighbors.append({
            "id": neighbor,
            "name": node_data.get("name", neighbor),
            "type": node_data.get("type", "player"),
            "edge_type": edge_data.get("type"),
            "edge_label": edge_data.get("label"),
            "weight": edge_data.get("weight", 1.0),
        })

    return neighbors


def graph_stats() -> dict:
    """Return stats about the loaded graph."""
    G = get_graph()
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "mock_mode": settings.use_mock_graph,
        "player_nodes": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "player"),
        "coach_nodes": sum(1 for _, d in G.nodes(data=True) if d.get("type") == "coach"),
    }


def _get_mode_subgraph(G: nx.Graph, mode: str) -> nx.Graph:
    """Return the cached subgraph for a mode (or full graph for wild)."""
    if mode in _mode_subgraphs:
        return _mode_subgraphs[mode]
    # Fallback: build on demand (e.g., if called before load_graph finishes)
    edge_type = MODE_TO_EDGE_TYPE.get(mode)
    if edge_type is None:
        return G
    sub_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
    return G.edge_subgraph(sub_edges)


def compute_available_modes(start_id: str, end_id: str) -> list[str]:
    """
    Return which game modes have a valid path between start_id and end_id.
    Uses unweighted BFS on each mode's subgraph.
    """
    G = get_graph()
    a = f"player:{start_id}"
    b = f"player:{end_id}"

    if not G.has_node(a) or not G.has_node(b):
        return []

    available: list[str] = []
    for mode in VALID_MODES:
        sub = _get_mode_subgraph(G, mode)
        try:
            nx.shortest_path(sub, a, b)
            available.append(mode)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    return available


def compute_optimal_hops_by_mode(start_id: str, end_id: str) -> dict[str, int]:
    """
    Return the unweighted BFS hop count for each available mode.
    Only modes with valid paths are included.
    """
    G = get_graph()
    a = f"player:{start_id}"
    b = f"player:{end_id}"

    if not G.has_node(a) or not G.has_node(b):
        return {}

    result: dict[str, int] = {}
    for mode in VALID_MODES:
        sub = _get_mode_subgraph(G, mode)
        try:
            path = nx.shortest_path(sub, a, b)
            result[mode] = len(path) - 2  # dribbles = intermediates (exclude start + end)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    return result


def find_shortest_path_with_labels_for_mode(
    start_id: str,
    start_type: str,
    end_id: str,
    end_type: str,
    mode: str,
) -> list[dict] | None:
    """
    Unweighted BFS on the mode-specific subgraph, returned as labeled node dicts.
    Used for the post-game reveal so the path respects the active mode's edge constraints.
    """
    G = get_graph()
    a = f"{start_type}:{start_id}"
    b = f"{end_type}:{end_id}"

    if not G.has_node(a) or not G.has_node(b):
        return None

    sub = _get_mode_subgraph(G, mode)

    try:
        path = nx.shortest_path(sub, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None

    result: list[dict] = []
    for i, node_key in enumerate(path):
        parts = node_key.split(":", 1)
        ntype = parts[0] if len(parts) == 2 else "player"
        nid = parts[1] if len(parts) == 2 else node_key
        node_data = G.nodes.get(node_key, {})
        entry: dict = {
            "id": nid,
            "type": ntype,
            "name": node_data.get("name", nid),
            "headshot_url": node_data.get("headshot_url"),
        }
        if i < len(path) - 1:
            next_key = path[i + 1]
            # Edge data lives on the original graph (subgraph shares references)
            if G.has_edge(node_key, next_key):
                edge = G[node_key][next_key]
                entry["edge_type"] = edge.get("type")
                entry["connection_label"] = edge.get("label")
        result.append(entry)

    return result


# ------------------------------------
# Mock graph (demo mode — no ETL needed)
# ------------------------------------

# KAI: This mock graph contains ~25 famous players for demo purposes.
# It uses realistic connection types but minimal edges.
# Once ETL is run, set USE_MOCK_GRAPH=false to use the real graph.
#
# IDs are the authoritative nba.com player IDs (matching the nbadb SQLite source).

MOCK_PLAYERS: list[dict] = [
    {"id": "2544",   "name": "LeBron James",          "team": "Los Angeles Lakers"},
    {"id": "201939", "name": "Stephen Curry",          "team": "Golden State Warriors"},
    {"id": "203954", "name": "Joel Embiid",            "team": "Philadelphia 76ers"},
    {"id": "1629029","name": "Luka Doncic",            "team": "Dallas Mavericks"},
    {"id": "203507", "name": "Giannis Antetokounmpo",  "team": "Milwaukee Bucks"},
    {"id": "201142", "name": "Kevin Durant",           "team": "Phoenix Suns"},
    {"id": "2546",   "name": "Carmelo Anthony",        "team": "Retired"},
    {"id": "201935", "name": "James Harden",           "team": "Los Angeles Clippers"},
    {"id": "201566", "name": "Russell Westbrook",      "team": "Free Agent"},
    {"id": "101108", "name": "Chris Paul",             "team": "Golden State Warriors"},
    {"id": "977",    "name": "Kobe Bryant",            "team": "Retired"},
    {"id": "406",    "name": "Shaquille O'Neal",       "team": "Retired"},
    {"id": "2548",   "name": "Dwyane Wade",            "team": "Retired"},
    {"id": "1495",   "name": "Tim Duncan",             "team": "Retired"},
    {"id": "708",    "name": "Kevin Garnett",          "team": "Retired"},
    {"id": "1718",   "name": "Paul Pierce",            "team": "Retired"},
    {"id": "1717",   "name": "Dirk Nowitzki",          "team": "Retired"},
    {"id": "2730",   "name": "Dwight Howard",          "team": "Retired"},
    {"id": "893",    "name": "Michael Jordan",         "team": "Retired"},
    {"id": "77142",  "name": "Magic Johnson",          "team": "Retired"},
    {"id": "1449",   "name": "Larry Bird",             "team": "Retired"},
    {"id": "76003",  "name": "Kareem Abdul-Jabbar",    "team": "Retired"},
    {"id": "101114", "name": "Deron Williams",         "team": "Retired"},
    {"id": "200765", "name": "Rajon Rondo",            "team": "Retired"},
    {"id": "203076", "name": "Anthony Davis",          "team": "Los Angeles Lakers"},
    {"id": "203081", "name": "Damian Lillard",         "team": "Milwaukee Bucks"},
    {"id": "959",    "name": "Steve Nash",             "team": "Retired"},
]

# Edge definitions: (player_a_id, player_b_id, edge_type, label, weight)
MOCK_EDGES: list[tuple] = [
    # LeBron connections
    ("2544", "2548",   "teammate",    "Teammates on 2012-13 Miami Heat",           0.3),
    ("2544", "406",    "teammate",    "Teammates on 2003-04 Cleveland Cavaliers",  0.9),
    ("2544", "203076", "teammate",    "Teammates on LA Lakers",                    0.4),
    ("2544", "201939", "all_star",    "Both in 2016 NBA All-Star Game",            1.5),
    ("2544", "2546",   "draft_class", "Both in 2003 NBA Draft Class",              1.4),
    ("2544", "200765", "teammate",    "Teammates on 2021-22 Los Angeles Lakers",   0.9),

    # Kobe connections
    ("977",  "406",    "teammate",    "Teammates on Los Angeles Lakers",           0.3),
    ("977",  "2730",   "teammate",    "Teammates on Los Angeles Lakers",           0.6),

    # MJ connections
    ("893",  "76003",  "all_star",    "Both in 1988 NBA All-Star Game",            1.5),
    ("893",  "77142",  "all_star",    "Both in 1991 NBA All-Star Game",            1.5),
    ("893",  "1449",   "all_star",    "Both in 1988 NBA All-Star Game",            1.5),

    # Big 3 Celtics
    ("708",  "1718",   "teammate",    "Teammates on 2008 Celtics",                 0.3),
    ("708",  "200765", "teammate",    "Teammates on 2008 Celtics",                 0.3),
    ("1718", "200765", "teammate",    "Teammates on 2008 Celtics",                 0.3),
    ("708",  "2548",   "all_star",    "Both in 2012 NBA All-Star Game",            1.5),

    # Nash connections
    ("959",  "1717",   "teammate",    "Teammates on 2011-12 Dallas Mavericks",     0.9),
    ("959",  "406",    "teammate",    "Teammates on 2004-05 Los Angeles Lakers",   0.9),

    # Curry / Warriors
    ("201939","201142","teammate",    "Teammates on Golden State Warriors 2016-17",0.3),
    ("201939","201935","all_star",    "Both in 2015 NBA All-Star Game",            1.5),

    # Wade / Miami
    ("2548", "406",    "teammate",    "Teammates on 2004-05 Miami Heat",           0.6),

    # Dirk
    ("1717", "1629029","teammate",    "Both played for Dallas Mavericks",          0.9),

    # Cross-era college
    ("76003","708",    "college",     "Both attended UCLA",                        1.2),

    # Durant / OKC Big 3
    ("201142","201935","teammate",    "Teammates on OKC Thunder 2009-12",          0.3),
    ("201142","201566","teammate",    "Teammates on OKC Thunder 2008-16",          0.3),
    ("201935","201566","teammate",    "Teammates on OKC Thunder 2009-12",          0.3),
    ("201935","101108","teammate",    "Teammates on OKC Thunder 2011-12",          0.6),

    # CP3
    ("101108","2544",  "all_star",    "Both in 2014 NBA All-Star Game",            1.5),

    # Giannis
    ("203507","203081","all_star",    "Both in 2021 NBA All-Star Game",            1.5),

    # Davis / LeBron to other Lakers
    ("2544", "977",    "college",     "Note: placeholder connection",              1.4),

    # Embiid / Harden
    ("203954","201935","teammate",    "Teammates on Philadelphia 76ers 2021-22",   0.3),

    # Lillard / Giannis
    ("203081","203507","teammate",    "Teammates on Milwaukee Bucks 2023-24",      0.4),

    # Doncic
    ("1629029","201935","all_star",   "Both in 2022 NBA All-Star Game",            1.5),

    # Magic / Kareem
    ("77142","76003",  "teammate",    "Teammates on 1980 Los Angeles Lakers",      0.3),

    # Bird / Magic
    ("1449", "77142",  "college",     "Both attended Indiana State (Bird) / MSU",  1.4),

    # Tim Duncan
    ("1495", "406",    "all_star",    "Both in 2003 NBA All-Star Game",            1.5),
    ("1495", "893",    "all_star",    "Both in 2002 NBA All-Star Game",            1.5),
]


def _build_mock_graph() -> nx.Graph:
    """Build a small demo graph with well-known players."""
    G = nx.Graph()

    # Add player nodes
    for p in MOCK_PLAYERS:
        G.add_node(
            f"player:{p['id']}",
            type="player",
            name=p["name"],
            team=p["team"],
            headshot_url=f"https://cdn.nba.com/headshots/nba/latest/1040x760/{p['id']}.png",
        )

    # Add edges
    for a_id, b_id, edge_type, label, weight in MOCK_EDGES:
        a = f"player:{a_id}"
        b = f"player:{b_id}"
        if G.has_node(a) and G.has_node(b):
            G.add_edge(a, b, type=edge_type, label=label, weight=weight)

    logger.info(f"Mock graph built: {G.number_of_nodes()} players, {G.number_of_edges()} edges")
    return G


def _normalize_name(s: str) -> str:
    """Strip accents so 'Schröder' and 'Schroder' both match."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()


def get_mock_players_for_search(query: str, limit: int = 10) -> list[dict]:
    """
    Search mock players by name for the /search/players endpoint
    when the database isn't available.
    Normalizes unicode so accented queries still find players.
    """
    q_norm = _normalize_name(query)
    results = []
    for p in MOCK_PLAYERS:
        if q_norm in _normalize_name(p["name"]):
            results.append({
                "id": p["id"],
                "full_name": p["name"],
                "position": None,
                "team_name": p["team"],
                "headshot_url": f"https://cdn.nba.com/headshots/nba/latest/1040x760/{p['id']}.png",
                "seasons_active": None,
                "is_active": p["team"] not in ("Retired", "Free Agent"),
            })
    return results[:limit]
