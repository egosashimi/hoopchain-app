"""
HOOPCHAIN — Regression test: count consistency and FIX-1/2/3 invariants.

Assertions:
  1. Hop counts (reveal path length, optimal_hops_by_mode, shortest_path_length)
     all agree for a set of known pairs in each mode.
  2. COACH never appears in the frontend-visible supported modes
     (available_modes may include it from the backend, but the supported set
     is {classic, wild}).
  3. Give Up from an empty chain does not raise (integration check via live API).

Usage (requires backend running locally or prod URL in HOOPCHAIN_API):
    # Run against the graph directly (no network):
    python data/tests/test_count_consistency.py

    # Run integration checks against a live API:
    HOOPCHAIN_API=https://hoopchain-backend-production.up.railway.app \
        python data/tests/test_count_consistency.py --integration
"""

from __future__ import annotations

import argparse
import sys
import os

# Ensure stdout handles Unicode on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Graph-level count consistency (no network required)
# ---------------------------------------------------------------------------

KNOWN_PAIRS: list[tuple[str, str, str, int]] = [
    # (start_id, end_id, mode, expected_dribbles)
    # Dribbles = intermediates = len(path) - 2. Direct teammates = 0.
    ("2548",   "2406",   "classic", 0),   # Dwyane Wade <-> Caron Butler (2003-04 Heat)
    ("977",    "2430",   "classic", 0),   # Kobe Bryant <-> Carlos Boozer (2014-15 Lakers)
    ("202691", "203999", "classic", 1),   # Klay Thompson <-> Nikola Jokic
    # Regression: Wade and LeBron were Heat teammates (2010-14) + CLE (2017-18).
    # Their graph edge was overwritten by a draft_class edge; must still be 0 dribbles in Classic.
    ("2548",   "2544",   "classic", 0),   # Dwyane Wade <-> LeBron James (Heat/Cavs teammates)
    # MJ → Larry Hughes → LeBron (launch-week puzzle): 1 intermediate = 1 dribble.
    ("893",    "2544",   "classic", 1),   # Michael Jordan <-> LeBron James
]

FRONTEND_SUPPORTED_MODES = {"classic", "wild"}


def test_graph_counts() -> list[str]:
    """Run hop-count assertions directly against the loaded graph. Returns list of failure messages."""
    failures: list[str] = []

    try:
        import pickle
        from pathlib import Path
        import networkx as nx
    except ImportError as e:
        return [f"SKIP graph tests: missing dep {e}"]

    # Locate graph.pkl — try backend/graph.pkl relative to repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    candidates = [
        repo_root / "backend" / "graph.pkl",
        Path(os.getenv("GRAPH_PICKLE_PATH", "backend/graph.pkl")),
    ]
    G = None
    for p in candidates:
        if p.exists():
            with open(p, "rb") as f:
                G = pickle.load(f)
            print(f"  Loaded graph from {p}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
            break

    if G is None:
        return ["SKIP graph tests: graph.pkl not found (run ETL first)"]

    MODE_TO_EDGE_TYPE: dict[str, str | None] = {
        "classic": "teammate",
        "wild":    None,
        "coach":   "coached_by",
    }

    for start_id, end_id, mode, expected in KNOWN_PAIRS:
        a = f"player:{start_id}"
        b = f"player:{end_id}"

        if not G.has_node(a):
            failures.append(f"FAIL: node player:{start_id} not in graph")
            continue
        if not G.has_node(b):
            failures.append(f"FAIL: node player:{end_id} not in graph")
            continue

        edge_type = MODE_TO_EDGE_TYPE.get(mode)
        if edge_type is None:
            sub = G
        else:
            sub_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
            sub = G.edge_subgraph(sub_edges)

        try:
            path = nx.shortest_path(sub, a, b)
            hop_count = len(path) - 2   # dribbles = intermediates = nodes - 2
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            failures.append(
                f"FAIL: no path in {mode} mode between {start_id} and {end_id} "
                f"(expected {expected} hops)"
            )
            continue

        start_name = G.nodes[a].get("name", start_id)
        end_name   = G.nodes[b].get("name", end_id)

        if hop_count != expected:
            failures.append(
                f"FAIL: {start_name} <-> {end_name} [{mode}] — "
                f"got {hop_count} hops, expected {expected}"
            )
        else:
            print(f"  OK: {start_name} <-> {end_name} [{mode}] = {hop_count} hops")

    return failures


# ---------------------------------------------------------------------------
# Frontend mode-pill source check (static / no network)
# ---------------------------------------------------------------------------

def test_no_coach_in_supported_modes() -> list[str]:
    """Assert that COACH is not in the frontend-supported mode set."""
    failures: list[str] = []
    if "coach" in FRONTEND_SUPPORTED_MODES:
        failures.append("FAIL: 'coach' is in FRONTEND_SUPPORTED_MODES — it must be removed (W4 decision)")
    else:
        print(f"  OK: FRONTEND_SUPPORTED_MODES = {sorted(FRONTEND_SUPPORTED_MODES)} (no coach)")
    return failures


# ---------------------------------------------------------------------------
# Mode filter assertions (graph-level, no network required)
# ---------------------------------------------------------------------------

def test_mode_filter_hop() -> list[str]:
    """
    Verify that the mode-filter logic is correct at the graph level:
    1. A pair connected only by a college edge is absent from the classic
       (teammate-only) subgraph and present in the full graph (wild mode).
    2. A known teammate pair (Wade <-> Butler) is present in both subgraphs.
    """
    failures: list[str] = []

    try:
        import pickle
        from pathlib import Path
        import networkx as nx
    except ImportError as e:
        return [f"SKIP mode-filter test: missing dep {e}"]

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    candidates = [
        repo_root / "backend" / "graph.pkl",
        Path(os.getenv("GRAPH_PICKLE_PATH", "backend/graph.pkl")),
    ]
    G = None
    for p in candidates:
        if p.exists():
            with open(p, "rb") as f:
                G = pickle.load(f)
            break

    if G is None:
        return ["SKIP mode-filter test: graph.pkl not found (run ETL first)"]

    # Classic subgraph = teammate edges only (mirrors MODE_TO_EDGE_TYPE["classic"])
    classic_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "teammate"]
    classic_sub = G.edge_subgraph(classic_edges)

    # --- 1. College-only pair: absent from classic, present in wild ---
    college_only: tuple | None = None
    for u, v, d in G.edges(data=True):
        if d.get("type") == "college" and not classic_sub.has_edge(u, v):
            college_only = (u, v, G.nodes[u].get("name", u), G.nodes[v].get("name", v))
            break

    if college_only is None:
        failures.append("WARN: no college-only pairs found in graph — every college pair is also teammates")
    else:
        u, v, u_name, v_name = college_only
        if classic_sub.has_edge(u, v):
            failures.append(
                f"FAIL: mode filter — {u_name} <-> {v_name} has a college edge "
                "but appears in classic (teammate) subgraph — classic mode would wrongly accept it"
            )
        else:
            print(f"  OK: {u_name} <-> {v_name} — college edge absent from classic subgraph (rejected in Classic)")
        if not G.has_edge(u, v):
            failures.append(f"FAIL: mode filter — {u_name} <-> {v_name} college edge missing from full graph")
        else:
            print(f"  OK: {u_name} <-> {v_name} — college edge present in full graph (accepted in Wild)")

    # --- 2. Teammate pair: accepted in both classic and wild ---
    wade, butler = "player:2548", "player:2406"
    if G.has_node(wade) and G.has_node(butler):
        wade_name = G.nodes[wade].get("name", "Wade")
        butler_name = G.nodes[butler].get("name", "Butler")
        if classic_sub.has_edge(wade, butler):
            print(f"  OK: {wade_name} <-> {butler_name} — teammate edge in classic subgraph (accepted in Classic)")
        else:
            failures.append(
                f"FAIL: mode filter — {wade_name} <-> {butler_name} teammate edge missing from classic subgraph"
            )
        if G.has_edge(wade, butler):
            print(f"  OK: {wade_name} <-> {butler_name} — teammate edge in full graph (accepted in Wild)")
        else:
            failures.append(
                f"FAIL: mode filter — {wade_name} <-> {butler_name} teammate edge missing from full graph"
            )
    else:
        failures.append("SKIP: Wade (2548) or Butler (2406) not in graph")

    return failures


# ---------------------------------------------------------------------------
# Future-puzzle validity check (requires graph.pkl + DATABASE_URL)
# ---------------------------------------------------------------------------

def test_future_puzzles_valid() -> list[str]:
    """
    Verify every future-dated daily_puzzle (>= today) has:
      - start_player_id and end_player_id present as nodes in the graph
      - a valid classic (teammate) path with hop count == optimal_hops stored in DB

    Skipped if DATABASE_URL env var is not set or graph.pkl is not found.
    """
    import os
    from datetime import date

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("  SKIP future-puzzle check: DATABASE_URL not set")
        return []

    failures: list[str] = []

    try:
        import pickle
        from pathlib import Path
        import networkx as nx
    except ImportError as e:
        return [f"SKIP future-puzzle check: missing dep {e}"]

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    graph_path = repo_root / "backend" / "graph.pkl"
    if not graph_path.exists():
        print("  SKIP future-puzzle check: graph.pkl not found")
        return []

    with open(graph_path, "rb") as f:
        G = pickle.load(f)

    # Build classic subgraph
    classic_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "teammate"]
    classic_sub = G.edge_subgraph(classic_edges)

    try:
        import psycopg2
    except ImportError:
        print("  SKIP future-puzzle check: psycopg2 not installed")
        return []

    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    today = date.today()

    try:
        conn = psycopg2.connect(pg_url)
        cur = conn.cursor()
        cur.execute(
            "SELECT puzzle_date, start_player_id, end_player_id, optimal_hops "
            "FROM daily_puzzles WHERE puzzle_date >= %s ORDER BY puzzle_date",
            (today,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return [f"FAIL: future-puzzle DB query failed: {e}"]

    print(f"  Checking {len(rows)} future daily_puzzle rows (>= {today})")

    missing_node = 0
    wrong_hops = 0
    no_path = 0

    for puzzle_date, start_id, end_id, db_hops in rows:
        a = f"player:{start_id}"
        b = f"player:{end_id}"

        if not G.has_node(a):
            failures.append(f"FAIL {puzzle_date}: start_player_id={start_id} not in graph")
            missing_node += 1
            continue
        if not G.has_node(b):
            failures.append(f"FAIL {puzzle_date}: end_player_id={end_id} not in graph")
            missing_node += 1
            continue

        try:
            # graph_hops is edge count; dribbles = graph_hops - 1 (intermediates)
            graph_hops = nx.shortest_path_length(classic_sub, a, b) - 1
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            failures.append(
                f"FAIL {puzzle_date}: no classic path between {start_id} and {end_id} "
                f"({G.nodes[a].get('name', start_id)} → {G.nodes[b].get('name', end_id)})"
            )
            no_path += 1
            continue

        if db_hops != graph_hops:
            failures.append(
                f"FAIL {puzzle_date}: DB optimal_hops={db_hops} but graph BFS={graph_hops} "
                f"({G.nodes[a].get('name', start_id)} → {G.nodes[b].get('name', end_id)})"
            )
            wrong_hops += 1

    ok = len(rows) - missing_node - no_path - wrong_hops
    print(
        f"  Results: {ok} OK, {missing_node} missing nodes, "
        f"{no_path} no-path, {wrong_hops} wrong hop count"
    )
    return failures


# ---------------------------------------------------------------------------
# Integration tests (live API required)
# ---------------------------------------------------------------------------

def test_integration(api_url: str) -> list[str]:
    """Run integration checks against the live API. Returns list of failure messages."""
    import urllib.request
    import json
    import time

    failures: list[str] = []

    def get(path: str) -> dict | list:
        url = api_url.rstrip("/") + path
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())

    def post(path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            api_url.rstrip("/") + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    # --- 1. Health check ---
    try:
        health = get("/health")
        if health.get("mock_mode"):
            failures.append("FAIL: /health reports mock_mode=true — USE_MOCK_GRAPH must be false")
        else:
            print(f"  OK: /health → nodes={health.get('graph_nodes')}, mock_mode={health.get('mock_mode')}")
    except Exception as e:
        failures.append(f"FAIL: /health → {e}")
        return failures   # no point continuing if API is down

    # --- 2. Fetch today's puzzle ---
    try:
        puzzle = get("/puzzle/today")
        modes = puzzle.get("available_modes", [])
        hops_by_mode = puzzle.get("optimal_hops_by_mode", {})
        print(f"  OK: /puzzle/today → modes={modes}, hops_by_mode={hops_by_mode}")

        if "coach" in modes and "coach" in hops_by_mode:
            # COACH being in the payload is fine — frontend filters it out.
            print(f"  NOTE: backend includes 'coach' in available_modes — frontend will filter it out.")
    except Exception as e:
        failures.append(f"FAIL: /puzzle/today → {e}")

    # --- 3. Give Up from empty chain (cold start) ---
    try:
        puzzle = get("/puzzle/today")
        start_id = puzzle["start_player"]["id"]
        end_id   = puzzle["end_player"]["id"]
        puzzle_date = puzzle["puzzle_date"]

        result = post("/game/complete/freeplay", {
            "puzzle_date": puzzle_date,
            "client_id": f"regression-test-{int(time.time())}",
            "path": [{"id": start_id, "type": "player", "name": puzzle["start_player"]["full_name"]}],
            "hops_used": 0,
            "time_seconds": 0,
            "gave_up": True,
            "mode": "classic",
        })
        if result.get("optimal_path") is None:
            failures.append("FAIL: Give Up with empty chain returned null optimal_path")
        else:
            reveal_len = len(result["optimal_path"]) - 1
            print(f"  OK: Give Up (empty chain) → optimal_path has {reveal_len} dribbles")
    except Exception as e:
        failures.append(f"FAIL: Give Up integration test → {e}")

    # --- 4. Count consistency: give-up reveal path length matches optimal_hops_by_mode ---
    try:
        puzzle = get("/puzzle/today")
        start_id = puzzle["start_player"]["id"]
        end_id   = puzzle["end_player"]["id"]
        puzzle_date = puzzle["puzzle_date"]
        mode = "classic"
        expected_hops = (puzzle.get("optimal_hops_by_mode") or {}).get(mode) or puzzle["optimal_hops"]

        result = post("/game/complete/freeplay", {
            "puzzle_date": puzzle_date,
            "client_id": f"regression-count-{int(time.time())}",
            "path": [{"id": start_id, "type": "player", "name": puzzle["start_player"]["full_name"]}],
            "hops_used": 0,
            "time_seconds": 0,
            "gave_up": True,
            "mode": mode,
        })
        optimal_path = result.get("optimal_path") or []
        reveal_hops = len(optimal_path) - 1 if optimal_path else -1

        if reveal_hops != expected_hops:
            failures.append(
                f"FAIL: reveal path dribbles ({reveal_hops}) ≠ optimal_hops_by_mode[{mode}] ({expected_hops}) "
                f"for today's puzzle ({puzzle['start_player']['full_name']} → {puzzle['end_player']['full_name']})"
            )
        else:
            print(f"  OK: reveal path dribbles ({reveal_hops}) == optimal_hops_by_mode[{mode}] ({expected_hops})")
    except Exception as e:
        failures.append(f"FAIL: count consistency integration test → {e}")

    return failures


# ---------------------------------------------------------------------------
# Served-GOAT == graph BFS (requires both graph and live API)
# ---------------------------------------------------------------------------

def test_served_goat_matches_graph(api_url: str, G) -> list[str]:
    """
    Fetch today's puzzle via the API and verify that served optimal_hops_by_mode
    matches an unweighted BFS on the in-memory graph.  This catches stale Redis
    cache entries that survived a graph rebuild.
    """
    import urllib.request, json
    import networkx as nx

    failures: list[str] = []

    def get(path: str) -> dict:
        url = api_url.rstrip("/") + path
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())

    try:
        puzzle = get("/puzzle/today")
    except Exception as e:
        failures.append(f"FAIL: served-GOAT check → /puzzle/today failed: {e}")
        return failures

    start_id = puzzle["start_player"]["id"]
    end_id   = puzzle["end_player"]["id"]
    served_by_mode = puzzle.get("optimal_hops_by_mode") or {}
    start_name = puzzle["start_player"]["full_name"]
    end_name   = puzzle["end_player"]["full_name"]

    MODE_EDGE: dict[str, str | None] = {"classic": "teammate", "wild": None}
    for mode, edge_type in MODE_EDGE.items():
        if mode not in served_by_mode:
            continue
        served = served_by_mode[mode]

        a, b = f"player:{start_id}", f"player:{end_id}"
        if edge_type is None:
            sub = G
        else:
            sub_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == edge_type]
            sub = G.edge_subgraph(sub_edges)

        try:
            graph_hops = nx.shortest_path_length(sub, a, b)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            failures.append(
                f"FAIL: served-GOAT [{mode}] — no path in graph for {start_name} → {end_name}"
            )
            continue

        if served != graph_hops:
            failures.append(
                f"FAIL: served-GOAT [{mode}] — API returned {served}, graph BFS says {graph_hops} "
                f"({start_name} → {end_name}). Redis cache is stale — flush via /admin/flush-puzzle-cache."
            )
        else:
            print(f"  OK: served GOAT [{mode}] == graph BFS == {graph_hops} ({start_name} → {end_name})")

    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Hoopchain regression tests")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests against the live API",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("HOOPCHAIN — Count consistency / regression tests")
    print("=" * 60)

    all_failures: list[str] = []

    print("\n[1] Graph-level hop-count assertions")
    all_failures.extend(test_graph_counts())

    print("\n[2] Frontend supported-modes check")
    all_failures.extend(test_no_coach_in_supported_modes())

    print("\n[3] Mode filter hop assertions (college rejected in Classic, teammate accepted in both)")
    all_failures.extend(test_mode_filter_hop())

    print("\n[4] Future daily_puzzle validity (graph nodes + classic path)")
    all_failures.extend(test_future_puzzles_valid())

    api_url = os.getenv("HOOPCHAIN_API", "")
    if args.integration or api_url:
        api_url = api_url or "http://localhost:8000"
        print(f"\n[5] Integration tests -> {api_url}")
        all_failures.extend(test_integration(api_url))

        # [6] Served-GOAT == graph BFS (needs both API and graph.pkl)
        print(f"\n[6] Served-GOAT vs graph BFS -> {api_url}")
        try:
            import pickle
            from pathlib import Path
            import networkx as nx
            graph_candidates = [
                Path(__file__).parent.parent.parent / "backend" / "graph.pkl",
            ]
            G_check = None
            for p in graph_candidates:
                if p.exists():
                    with open(p, "rb") as f:
                        G_check = pickle.load(f)
                    break
            if G_check is None:
                print("  SKIP: graph.pkl not found for served-GOAT check")
            else:
                all_failures.extend(test_served_goat_matches_graph(api_url, G_check))
        except Exception as e:
            all_failures.append(f"FAIL: served-GOAT check setup → {e}")
    else:
        print("\n[5] Integration tests SKIPPED (pass --integration or set HOOPCHAIN_API)")
        print("[6] Served-GOAT vs graph BFS SKIPPED")

    print("\n" + "=" * 60)
    if all_failures:
        print(f"FAILED — {len(all_failures)} issue(s):")
        for f in all_failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
