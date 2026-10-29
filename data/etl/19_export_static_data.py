"""
HOOPCHAIN ETL — Step 19: Export static game data for the browser-only frontend
==============================================================================
The frontend runs the whole game client-side (GitHub Pages, no backend). This
script turns backend/graph.pkl into the files it loads:

  frontend/public/data/graph.json  — players, coaches and connection groups
  frontend/public/data/daily.json  — the daily puzzle schedule (append-only)

Seasons after graph.pkl's last one (2024-25) come from data/rosters/*.json
(written by 20_fetch_recent_rosters.py from NBA.com box scores) and are merged in
as teammate groups; players new to the league are added as nodes, and "active"
means on a roster in the latest season file.

Connections are stored as groups rather than pairwise edges: every
"2008-09 Boston Celtics Teammates" label becomes one roster, every draft class /
college / All-Star game one group, and every "Coached by ..." label a coach plus
the players he coached there. Two players are connected when they share a group.
This also restores teammate pairs whose edge the graph build overwrote with a
draft/college edge (the backend patched those with a player_seasons lookup).

The daily schedule is append-only: existing dates are never rewritten, so a
graph rebuild cannot change a puzzle people already played. Re-run after
rebuilding graph.pkl, and before the schedule's last date.

Usage:
    python data/etl/19_export_static_data.py
"""

from __future__ import annotations

import collections
import itertools
import json
import pickle
import random
import re
from datetime import date, timedelta
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]
GRAPH_PKL = ROOT / "backend" / "graph.pkl"
FAMOUS_JSON = ROOT / "data" / "seeds" / "famous_players.json"
ROSTERS_DIR = ROOT / "data" / "rosters"
OUT_DIR = ROOT / "frontend" / "public" / "data"

SCHEDULE_START = date(2026, 10, 1)
SCHEDULE_END = date(2028, 12, 31)

# Mirrors backend/app/services/free_play_service.py
ERA_RANGES = {
    "2020s": (2020, 9999),
    "2010s": (2010, 2019),
    "2000s": (2000, 2009),
    "1990s": (1990, 1999),
    "1980s": (1980, 1989),
    "pre1980": (0, 1979),
}
ERA_TARGETS = {"2020s": 100, "2010s": 100, "2000s": 75, "1990s": 75, "1980s": 50, "pre1980": 30}
RECOGNIZABILITY_FLOOR = 20
HARD_RECOGNIZABILITY_FLOOR = 26
HARD_CLASSIC_PLAYER_IDS = [
    "893", "1449", "77142", "76003", "787", "937", "252", "304", "17",
    "121", "165", "77449", "1122", "397", "764", "23", "78318", "76681",
]
HARD_MODERN_PLAYER_IDS = [
    "203507", "203999", "203954", "202695", "202681", "202691", "202710", "203076", "203081",
]

# Mirrors frontend/src/engine/puzzles.ts DAILY_DIFFICULTY_BY_WEEKDAY (0=Monday)
DAILY_DIFFICULTY_BY_WEEKDAY = ["easy", "easy", "medium", "medium", "medium", "hard", "hard"]
ENDPOINT_COOLDOWN_DAYS = 7

GROUP_TYPE_CODES = {"teammate": "t", "draft_class": "d", "college": "c", "all_star": "a"}


def difficulty_label(dribbles: int) -> str:
    return "easy" if dribbles <= 1 else "medium" if dribbles == 2 else "hard"


def main() -> None:
    G: nx.Graph = pickle.load(open(GRAPH_PKL, "rb"))
    famous_ids = {p["id"] for p in json.load(open(FAMOUS_JSON))["players"]}

    # ---- Recent-season rosters (in memory only; graph.pkl is not modified) ----
    roster_groups: dict[str, set[str]] = collections.defaultdict(set)
    latest_roster: set[str] | None = None
    for path in sorted(ROSTERS_DIR.glob("*.json")):
        season = json.loads(path.read_text())
        latest_roster = set()
        for team in season["teams"].values():
            label = f"{season['season']} {team['name']} Teammates"
            for pid, name in team["players"].items():
                key = f"player:{pid}"
                if key not in G:
                    G.add_node(key, type="player", name=name, is_active=True)
                roster_groups[label].add(key)
                latest_roster.add(key)
    if latest_roster is not None:
        for k, d in G.nodes(data=True):
            if d.get("type") == "player":
                d["is_active"] = k in latest_roster

    keys = sorted(G.nodes, key=lambda k: (G.nodes[k].get("type") != "player", k))
    index = {k: i for i, k in enumerate(keys)}

    # ---- Groups ----
    groups: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    coach_groups: dict[str, set[str]] = collections.defaultdict(set)
    for u, v, d in G.edges(data=True):
        if d["type"] == "coached_by":
            coach_groups[d["label"]].update((u, v))
        else:
            groups[(d["type"], d["label"])].update((u, v))
    for label, members in roster_groups.items():
        groups[("teammate", label)].update(members)

    # ---- Per-player derived attributes ----
    seasons: dict[str, set[int]] = collections.defaultdict(set)
    draft_year: dict[str, int] = {}
    all_star_games: collections.Counter[str] = collections.Counter()
    for (gtype, label), members in groups.items():
        if gtype == "teammate":
            m = re.match(r"(\d{4})-\d{2} ", label)
            if m:
                for k in members:
                    seasons[k].add(int(m.group(1)))
        elif gtype == "draft_class":
            m = re.search(r"(\d{4}) NBA Draft", label)
            if m:
                for k in members:
                    draft_year[k] = int(m.group(1))
        elif gtype == "all_star":
            for k in members:
                all_star_games[k] += 1

    def score(k: str) -> int:
        # Approximates 09_score_recognizability.py from graph-only data:
        # +1/season, +5/All-Star game, +10 headshot era (played 1997+), draft bonuses
        s = seasons.get(k)
        if not s:
            return 0
        pts = len(s) + 5 * all_star_games[k]
        if max(s) >= 1997:
            pts += 10
        if k in draft_year:
            pts += 3 + (2 if draft_year[k] > 1990 else 0)
        if k.split(":", 1)[1] in famous_ids:
            pts += 10
        return pts

    def eras(k: str) -> list[str]:
        s = seasons.get(k)
        if not s:
            return []
        first, last = min(s), max(s)
        return [e for e, (lo, hi) in ERA_RANGES.items() if first <= hi and last >= lo]

    players = [k for k in keys if G.nodes[k].get("type") == "player"]
    roster_seasons = sorted({l[:7] for _, l in groups if l[:7] > "2024-25" and l[4] == "-"})
    scores = {k: score(k) for k in players}

    # ---- Free-play pools (same construction as free_play_service._build_pool) ----
    by_score = sorted(players, key=lambda k: -scores[k])
    eligible = [k for k in by_score if scores[k] >= RECOGNIZABILITY_FLOOR and eras(k)]
    pools: dict[str, list[int]] = {}
    for era, target in ERA_TARGETS.items():
        pools[era] = [index[k] for k in eligible if era in eras(k)][:target]
    hard_modern = [k for k in eligible if scores[k] >= HARD_RECOGNIZABILITY_FLOOR
                   and any(e in eras(k) for e in ("2020s", "2010s"))]
    hard_modern += [f"player:{pid}" for pid in HARD_MODERN_PLAYER_IDS
                    if f"player:{pid}" in index and f"player:{pid}" not in hard_modern]
    hard_modern.sort(key=lambda k: -scores[k])
    pools["hard_modern"] = [index[k] for k in hard_modern[:60]]
    pools["hard_classic"] = [index[f"player:{pid}"] for pid in HARD_CLASSIC_PLAYER_IDS
                             if f"player:{pid}" in index]

    # ---- Classic (teammate) graph for schedule difficulty ----
    classic = nx.Graph()
    wild_pairs: set[tuple[str, str]] = set()
    for (gtype, _), members in groups.items():
        pairs = list(itertools.combinations(sorted(members), 2))
        wild_pairs.update(pairs)
        if gtype == "teammate":
            classic.add_edges_from(pairs)
    for members in coach_groups.values():
        coach = next(k for k in members if k.startswith("coach:"))
        wild_pairs.update(tuple(sorted((coach, p))) for p in members if p != coach)

    # ---- Write graph.json ----
    nodes_out = []
    for k in keys:
        d = G.nodes[k]
        s = seasons.get(k)
        nodes_out.append([
            k.split(":", 1)[1],
            d.get("name", k),
            "c" if d.get("type") == "coach" else "p",
            1 if d.get("is_active") else 0,
            min(s) if s else 0,
            max(s) if s else 0,
            scores.get(k, 0),
        ])
    groups_out = [
        [GROUP_TYPE_CODES[gtype], label, sorted(index[k] for k in members)]
        for (gtype, label), members in sorted(groups.items())
    ]
    coaches_out = []
    for label, members in sorted(coach_groups.items()):
        coach = next(k for k in members if k.startswith("coach:"))
        coaches_out.append([label, index[coach], sorted(index[k] for k in members if k != coach)])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    graph_json = {
        "version": 1,
        "stats": {"nodes": len(keys), "edges": len(wild_pairs)},
        "nodes": nodes_out,
        "groups": groups_out,
        "coach_groups": coaches_out,
        "pools": pools,
    }
    (OUT_DIR / "graph.json").write_text(json.dumps(graph_json, separators=(",", ":"), ensure_ascii=False))

    # ---- Daily schedule (append-only) ----
    candidates = sorted(
        {k for k in players if k.split(":", 1)[1] in famous_ids}
        | {f"player:{pid}" for pid in HARD_CLASSIC_PLAYER_IDS + HARD_MODERN_PLAYER_IDS}
        | {k for k in players if scores[k] >= HARD_RECOGNIZABILITY_FLOOR}
    )
    candidates = [k for k in candidates if k in classic]
    band_pairs: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for a in candidates:
        dist = nx.single_source_shortest_path_length(classic, a)
        for b in candidates:
            if b > a and b in dist and dist[b] >= 2:
                band_pairs[difficulty_label(dist[b] - 1)].append((a, b))

    def fame(pair: tuple[str, str]) -> int:
        return sum(k.split(":", 1)[1] in famous_ids for k in pair)

    daily_path = OUT_DIR / "daily.json"
    existing: list[list[str]] = []
    if daily_path.exists():
        prev = json.loads(daily_path.read_text())
        assert prev["start"] == SCHEDULE_START.isoformat(), "schedule start must never change"
        existing = prev["puzzles"]

    schedule = list(existing)
    used = {tuple(sorted(f"player:{x}" for x in p)) for p in schedule}
    total_days = (SCHEDULE_END - SCHEDULE_START).days + 1
    for offset in range(len(schedule), total_days):
        day = SCHEDULE_START + timedelta(days=offset)
        rng = random.Random(f"hoopchain-daily-{day.isoformat()}")
        recent = {f"player:{x}" for p in schedule[-ENDPOINT_COOLDOWN_DAYS:] for x in p}
        target = DAILY_DIFFICULTY_BY_WEEKDAY[day.weekday()]
        if target == "hard":
            # Hard pairs between recognizable players are scarce: spread them evenly over
            # the remaining hard days and fill the rest with medium
            hard_left = sum(1 for p in band_pairs["hard"] if p not in used)
            hard_days_left = sum(
                1 for o in range(offset, total_days)
                if DAILY_DIFFICULTY_BY_WEEKDAY[(SCHEDULE_START + timedelta(days=o)).weekday()] == "hard"
            )
            if rng.random() >= hard_left / hard_days_left:
                target = "medium"
        # Nearest band first if the target one is exhausted
        order = {"easy": ["easy", "medium", "hard"],
                 "medium": ["medium", "easy", "hard"],
                 "hard": ["hard", "medium", "easy"]}[target]
        pick = None
        for band in order:
            open_pairs = [p for p in band_pairs[band] if p not in used and not (set(p) & recent)]
            if open_pairs:
                best = max(fame(p) for p in open_pairs)
                pick = rng.choice([p for p in open_pairs if fame(p) == best])
                break
        assert pick, f"no puzzle available for {day}"
        used.add(pick)
        a, b = pick if rng.random() < 0.5 else pick[::-1]
        schedule.append([a.split(":", 1)[1], b.split(":", 1)[1]])

    daily_path.write_text(json.dumps({"start": SCHEDULE_START.isoformat(), "puzzles": schedule}))

    band_count = collections.Counter()
    for offset, (a, b) in enumerate(schedule):
        hops = nx.shortest_path_length(classic, f"player:{a}", f"player:{b}") - 1
        band_count[(DAILY_DIFFICULTY_BY_WEEKDAY[(SCHEDULE_START + timedelta(days=offset)).weekday()],
                    difficulty_label(hops))] += 1
    print(f"recent seasons merged from data/rosters: {roster_seasons or 'none'}")
    print(f"graph.json: {len(keys)} nodes, {len(groups_out)} groups, {len(coaches_out)} coach groups, "
          f"{len(wild_pairs)} connected pairs; pools: " + ", ".join(f"{k}={len(v)}" for k, v in pools.items()))
    print(f"daily.json: {len(schedule)} days ({len(existing)} kept) {SCHEDULE_START}..{SCHEDULE_END}; "
          f"candidate pairs per band: " + ", ".join(f"{k}={len(v)}" for k, v in sorted(band_pairs.items())))
    print("daily (target, actual) bands:", dict(sorted(band_count.items())))


if __name__ == "__main__":
    main()
