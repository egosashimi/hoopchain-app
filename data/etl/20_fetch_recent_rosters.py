"""
HOOPCHAIN ETL — Step 20: Fetch recent-season rosters from Wikipedia
===================================================================
graph.pkl ends at 2024-25. This rebuilds each later season's rosters from the
revision history of Wikipedia's "Template:<Team> roster" pages, read every
SNAPSHOT_DAYS through the regular season (so players traded mid-season are
kept), and writes one file per season:

  data/rosters/<season>.json  —  {season, source, snapshots, teams: {team: {name, players: {id: name}}}, unresolved}

Players are keyed by NBA Stats person ID (the IDs graph.pkl uses), taken from
Wikidata's "NBA.com player ID" (P3647) on the player's article, else from an
exact, unique name match against graph.pkl. Players with neither are listed
under "unresolved" and left out — never added under a made-up ID.

Uses the MediaWiki/Wikidata APIs with a descriptive User-Agent, per
https://meta.wikimedia.org/wiki/User-Agent_policy. Runs in GitHub Actions
(.github/workflows/update-rosters.yml); the dev container can't reach Wikipedia.
Completed seasons are fetched once (delete the file to refetch); the current
season is refreshed on every run.

Usage:
    python data/etl/20_fetch_recent_rosters.py
"""

from __future__ import annotations

import json
import pickle
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "rosters"
GRAPH_PKL = ROOT / "backend" / "graph.pkl"

FIRST_SEASON = 2025          # graph.pkl covers through 2024-25
SNAPSHOT_DAYS = 14
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
NBA_ID_PROPERTY = "P3647"    # Wikidata: NBA.com player ID
USER_AGENT = "HoopchainETL/1.0 (https://github.com/egosashimi/hoopchain-app; roster updater) python-urllib"
MIN_TEAMS = 28
MIN_PLAYERS_PER_TEAM = 10

TEAMS = [
    "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", "Chicago Bulls",
    "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets", "Detroit Pistons",
    "Golden State Warriors", "Houston Rockets", "Indiana Pacers", "Los Angeles Clippers",
    "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat", "Milwaukee Bucks",
    "Minnesota Timberwolves", "New Orleans Pelicans", "New York Knicks", "Oklahoma City Thunder",
    "Orlando Magic", "Philadelphia 76ers", "Phoenix Suns", "Portland Trail Blazers",
    "Sacramento Kings", "San Antonio Spurs", "Toronto Raptors", "Utah Jazz", "Washington Wizards",
]

# NBA roster templates list players as {{player2 | num = 7 | first = Jaylen | last = Brown | ...}}
PLAYER_TEMPLATE = re.compile(r"\{\{\s*(?:player2?|(?:NBA|Basketball)[ _]roster[ _]player)\s*\|", re.I)


# ------------------------------------
# HTTP
# ------------------------------------

def api(base: str, **params: str) -> dict:
    params = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            if data.get("error", {}).get("code") == "maxlag":
                time.sleep(5 * (attempt + 1))
                continue
            time.sleep(0.2)
            return data
        except Exception as e:  # network errors, 429/5xx
            err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API request failed: {url[:200]}: {err}")


# ------------------------------------
# Template parsing
# ------------------------------------

def _balanced(text: str, start: int) -> str:
    """Return the {{...}} template body starting at text[start] == '{'."""
    depth, i = 0, start
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i):
            depth -= 1
            i += 2
            if depth == 0:
                return text[start + 2:i - 2]
        else:
            i += 1
    return text[start + 2:]


def _params(body: str) -> dict[str, str]:
    """Split a template body into named params (pipes inside {{ }} / [[ ]] don't split)."""
    parts, depth, cur = [], 0, ""
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur += two
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            cur += two
            i += 2
            continue
        if body[i] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += body[i]
        i += 1
    parts.append(cur)
    out = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = _clean(v)
    return out


def _clean(v: str) -> str:
    v = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{.*?\}\}", "", v, flags=re.S)
    return v.strip()


def parse_roster(wikitext: str) -> list[dict[str, str]]:
    """Players in a roster template: [{name, title}]."""
    players = []
    for m in PLAYER_TEMPLATE.finditer(wikitext):
        p = _params(_balanced(wikitext, m.start()))
        name = p.get("name") or f"{p.get('first', '')} {p.get('last', '')}".strip()
        if not name:
            continue
        title = p.get("link") or (f"{name} ({p['dab']})" if p.get("dab") else name)
        players.append({"name": name, "title": title})
    return players


# ------------------------------------
# Wikipedia / Wikidata lookups
# ------------------------------------

def roster_at(team: str, when: datetime) -> str | None:
    """Wikitext of the team's roster template as of `when`."""
    data = api(
        WIKIPEDIA_API, action="query", prop="revisions", titles=f"Template:{team} roster",
        rvprop="content", rvslots="main", rvlimit="1", rvdir="older",
        rvstart=when.strftime("%Y-%m-%dT%H:%M:%SZ"), redirects="1",
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or "revisions" not in pages[0]:
        return None
    return pages[0]["revisions"][0]["slots"]["main"]["content"]


def nba_ids_for_titles(titles: list[str]) -> dict[str, str]:
    """Article title → NBA.com player ID, via each article's Wikidata item."""
    title_to_qid: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        data = api(WIKIPEDIA_API, action="query", titles="|".join(batch), redirects="1",
                   prop="pageprops", ppprop="wikibase_item")
        q = data.get("query", {})
        alias = {t: t for t in batch}
        for step in ("normalized", "redirects"):
            for r in q.get(step, []):
                for orig, cur in list(alias.items()):
                    if cur == r["from"]:
                        alias[orig] = r["to"]
        qid_by_title = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in q.get("pages", [])}
        for orig, final in alias.items():
            if qid_by_title.get(final):
                title_to_qid[orig] = qid_by_title[final]

    qids = sorted(set(title_to_qid.values()))
    nba_by_qid: dict[str, str] = {}
    for i in range(0, len(qids), 50):
        data = api(WIKIDATA_API, action="wbgetentities", ids="|".join(qids[i:i + 50]), props="claims")
        for qid, ent in data.get("entities", {}).items():
            claims = ent.get("claims", {}).get(NBA_ID_PROPERTY, [])
            if claims:
                nba_by_qid[qid] = str(claims[0]["mainsnak"]["datavalue"]["value"])
    return {t: nba_by_qid[q] for t, q in title_to_qid.items() if q in nba_by_qid}


# ------------------------------------
# Seasons
# ------------------------------------

def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'’]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def snapshot_times(start_year: int, now: datetime) -> list[datetime]:
    """Every SNAPSHOT_DAYS across the regular season (mid-Oct → mid-Apr), capped at now."""
    first = datetime(start_year, 10, 20, tzinfo=timezone.utc)
    last = min(datetime(start_year + 1, 4, 15, tzinfo=timezone.utc), now)
    times, t = [], first
    while t < last:
        times.append(t)
        t += timedelta(days=SNAPSHOT_DAYS)
    if last >= first:
        times.append(last)
    return times


def build_season(start_year: int, now: datetime, graph_names: dict[str, str | None]) -> dict:
    season = season_label(start_year)
    times = snapshot_times(start_year, now)
    seen: dict[str, dict[str, str]] = {}   # team → {title: name}
    samples: dict[str, str] = {}
    for team in TEAMS:
        seen[team] = {}
        for when in times:
            text = roster_at(team, when)
            if not text:
                continue
            samples.setdefault(team, text)
            for p in parse_roster(text):
                seen[team].setdefault(p["title"], p["name"])

    bad = [t for t in TEAMS if len(seen[t]) < MIN_PLAYERS_PER_TEAM]
    if len(TEAMS) - len(bad) < MIN_TEAMS:
        sample_team = bad[0]
        sys.exit(f"{season}: roster parsing failed for {len(bad)} teams ({', '.join(bad[:5])}...). "
                 f"Sample wikitext for {sample_team}:\n{samples.get(sample_team, '(no revision found)')[:1500]}")

    all_titles = sorted({title for team in TEAMS for title in seen[team]})
    wikidata_ids = nba_ids_for_titles(all_titles)

    teams, unresolved = {}, {}
    via_wikidata = via_name = 0
    for team in TEAMS:
        players = {}
        for title, name in seen[team].items():
            pid = wikidata_ids.get(title)
            if pid:
                via_wikidata += 1
            else:
                pid = graph_names.get(norm(name))
                if pid:
                    via_name += 1
            if pid:
                players[pid] = name
            else:
                unresolved.setdefault(team, []).append(name)
        teams[team] = {"name": team, "players": dict(sorted(players.items(), key=lambda kv: int(kv[0])))}

    # Sanity: Wikidata IDs that the graph already knows should carry the same name
    id_to_graph_name = {pid: n for n, pid in graph_names.items() if pid}
    mismatches = sorted({f"{name} → {pid} (graph: {id_to_graph_name[pid]})"
                         for team in teams.values() for pid, name in team["players"].items()
                         if pid in id_to_graph_name and id_to_graph_name[pid] != norm(name)})
    print(f"{season}: {len(times)} snapshots, {sum(len(t['players']) for t in teams.values())} roster spots "
          f"({via_wikidata} via Wikidata, {via_name} via name match), "
          f"{sum(len(v) for v in unresolved.values())} unresolved, {len(mismatches)} name/ID mismatches")
    for m in mismatches[:20]:
        print(f"  mismatch: {m}")
    for team, names in sorted(unresolved.items()):
        print(f"  unresolved {team}: {', '.join(names)}")

    return {
        "season": season,
        "source": "Wikipedia roster templates; IDs from Wikidata P3647 or graph name match",
        "snapshots": [t.date().isoformat() for t in times],
        "teams": teams,
        "unresolved": {k: sorted(v) for k, v in sorted(unresolved.items())},
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    current_start = now.year if now.month >= 8 else now.year - 1   # seasons tip off in October

    # Exact, unique names in graph.pkl → NBA ID (ambiguous names map to None and never match)
    G = pickle.load(open(GRAPH_PKL, "rb"))
    graph_names: dict[str, str | None] = {}
    for k, d in G.nodes(data=True):
        if d.get("type") == "player":
            n = norm(d.get("name", ""))
            graph_names[n] = None if n in graph_names else k.split(":", 1)[1]

    for start in range(FIRST_SEASON, current_start + 1):
        path = OUT_DIR / f"{season_label(start)}.json"
        if start < current_start and path.exists():
            continue
        if now < datetime(start, 10, 20, tzinfo=timezone.utc):
            print(f"{season_label(start)}: not started")
            continue
        season = build_season(start, now, graph_names)
        path.write_text(json.dumps(season, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
