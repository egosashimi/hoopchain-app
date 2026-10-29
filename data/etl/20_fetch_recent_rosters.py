"""
HOOPCHAIN ETL — Step 20: Fetch recent-season rosters from NBA.com box scores
============================================================================
graph.pkl ends at 2024-25. This pulls every game's box score from the public
NBA.com CDN for 2025-26 onward and writes one roster file per season:

  data/rosters/<season>.json  —  {season, games, teams: {TRI: {name, players: {id: name}}}}

Box scores list every player on both rosters (including inactive ones) under
their NBA Stats person ID — the same IDs graph.pkl uses — so a player who
appears for a team in a season is on that team's roster. Preseason and
All-Star games are skipped. 19_export_static_data.py merges these files into
the static game data as "<season> <Team> Teammates" groups.

Runs in GitHub Actions (.github/workflows/update-rosters.yml) — NBA.com is not
reachable from the dev container. Completed seasons are fetched once; the
current season is refreshed on every run.

Usage:
    python data/etl/20_fetch_recent_rosters.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "rosters"

FIRST_SEASON = 2025          # graph.pkl covers through 2024-25
REGULAR_SEASON_GAMES = 1230
SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (hoopchain roster updater)", "Accept": "application/json"}

# Full names as graph.pkl labels them (box scores say "LA Clippers")
TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def get_json(url: str) -> dict | None:
    """GET a JSON document; None if it doesn't exist (403/404). Retries transient errors."""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            err = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            err = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"giving up on {url}: {err}")


def build_rosters(season: str, game_ids: list[str]) -> dict:
    teams: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        boxscores = list(pool.map(lambda gid: get_json(BOXSCORE_URL.format(game_id=gid)), game_ids))
    found = 0
    for box in boxscores:
        if not box:
            continue
        found += 1
        for side in ("homeTeam", "awayTeam"):
            t = box["game"][side]
            tri = t["teamTricode"]
            team = teams.setdefault(tri, {
                "name": TEAM_NAMES.get(tri, f"{t['teamCity']} {t['teamName']}"),
                "players": {},
            })
            for p in t.get("players", []):
                team["players"][str(p["personId"])] = p["name"]
    for team in teams.values():
        team["players"] = dict(sorted(team["players"].items(), key=lambda kv: int(kv[0])))
    return {"season": season, "games": found, "teams": dict(sorted(teams.items()))}


def write(rosters: dict) -> None:
    path = OUT_DIR / f"{rosters['season']}.json"
    path.write_text(json.dumps(rosters, indent=1, ensure_ascii=False) + "\n")
    players = sum(len(t["players"]) for t in rosters["teams"].values())
    print(f"{path.relative_to(ROOT)}: {rosters['games']} games, {len(rosters['teams'])} teams, {players} roster spots")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    schedule = get_json(SCHEDULE_URL)
    if not schedule:
        sys.exit("NBA.com schedule unavailable")
    current = schedule["leagueSchedule"]["seasonYear"]          # e.g. "2026-27"
    current_start = int(current[:4])

    # Completed seasons: every regular-season game, fetched once
    for start in range(FIRST_SEASON, current_start):
        season = season_label(start)
        if (OUT_DIR / f"{season}.json").exists():
            continue
        yy = f"{start % 100:02d}"
        ids = [f"002{yy}{n:05d}" for n in range(1, REGULAR_SEASON_GAMES + 1)]
        rosters = build_rosters(season, ids)
        if rosters["games"] < REGULAR_SEASON_GAMES * 0.95:
            sys.exit(f"{season}: only {rosters['games']}/{REGULAR_SEASON_GAMES} box scores found")
        write(rosters)

    # Current season: every finished game except preseason (001) and All-Star (003)
    ids = [
        g["gameId"]
        for day in schedule["leagueSchedule"]["gameDates"]
        for g in day["games"]
        if g.get("gameStatus") == 3 and not g["gameId"].startswith(("001", "003"))
    ]
    if ids:
        write(build_rosters(current, ids))
    else:
        print(f"{current}: no finished games yet")


if __name__ == "__main__":
    main()
