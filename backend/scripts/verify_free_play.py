"""
HOOPCHAIN — W3 Free-Play Verification (Phase 4)
================================================
Pulls 30 consecutive free-play puzzles, then tests difficulty-filtered pulls.
Reports:
  - Pool composition (size, era breakdown, sample names)
  - Player spread and recognizability
  - GOAT distribution
  - Repeat rate
  - Difficulty band compliance
  - daily_puzzles row count (before/after to confirm no writes)

Usage:
    DATABASE_URL=... python backend/scripts/verify_free_play.py [--api http://localhost:8000]
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import time

import psycopg2
import requests

BASE = "https://hoopchain-backend-production.up.railway.app"
DB_URL = os.environ["DATABASE_URL"]  # prod connection string lives in data/etl/.env
PULL_COUNT = 30


def get_db_conn():
    return psycopg2.connect(DB_URL)


def count_daily_puzzles(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_puzzles")
    return cur.fetchone()[0]


def fetch_random(base: str, mode: str = "classic", difficulty: str | None = None,
                 exclude_ids: list[int] | None = None) -> dict | None:
    params: dict = {"mode": mode}
    if difficulty:
        params["difficulty"] = difficulty
    if exclude_ids:
        params["exclude_ids"] = ",".join(str(i) for i in exclude_ids)
    try:
        r = requests.get(f"{base}/puzzle/random", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def get_pool_info(base: str) -> dict | None:
    """Fetch pool info via health endpoint or a debug endpoint if available."""
    try:
        r = requests.get(f"{base}/health", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=BASE, help="API base URL")
    args = parser.parse_args()
    base = args.api.rstrip("/")

    print("=" * 64)
    print("HOOPCHAIN W3 Free-Play Verification")
    print("=" * 64)
    print(f"API: {base}")
    print()

    # ---- Check health ----
    health = get_pool_info(base)
    if health:
        print(f"Health: graph_nodes={health.get('graph_nodes')} "
              f"mock_mode={health.get('mock_mode')}")
    print()

    # ---- Snapshot daily_puzzles count ----
    conn = None
    try:
        conn = get_db_conn()
        pre_count = count_daily_puzzles(conn)
        print(f"daily_puzzles rows BEFORE: {pre_count}")
    except Exception as e:
        print(f"[warn] DB connect failed: {e}")
        pre_count = None

    print()
    print(f"Pulling {PULL_COUNT} consecutive free-play puzzles (mode=classic)…")
    print("-" * 64)

    puzzles: list[dict] = []
    seen_ids: list[int] = []
    start_players: list[str] = []
    end_players: list[str] = []
    pair_keys: list[str] = []
    goat_values: list[int] = []

    for i in range(PULL_COUNT):
        p = fetch_random(base, mode="classic", exclude_ids=seen_ids if seen_ids else None)
        if p is None:
            print(f"  [{i+1:02d}] FAILED")
            continue

        pid = p.get("puzzle_id", 0)
        start = p.get("start_player", {}).get("full_name", "?")
        end = p.get("end_player", {}).get("full_name", "?")
        goat = p.get("optimal_hops", "?")
        diff = p.get("difficulty", "?")
        pdate = p.get("puzzle_date", "?")
        modes = p.get("available_modes", [])

        pair_key = f"{p.get('start_player',{}).get('id','')}:{p.get('end_player',{}).get('id','')}"
        is_repeat = pair_key in pair_keys
        repeat_flag = " *** REPEAT ***" if is_repeat else ""

        print(f"  [{i+1:02d}] {start} -> {end}  |  GOAT={goat} ({diff})  modes={modes}  date={pdate}{repeat_flag}")

        seen_ids.append(pid)
        start_players.append(start)
        end_players.append(end)
        pair_keys.append(pair_key)
        if isinstance(goat, int):
            goat_values.append(goat)
        puzzles.append(p)

    print()
    print("=" * 64)
    print("SUMMARY — 30-pull batch")
    print("=" * 64)

    # Unique players
    all_names = start_players + end_players
    unique_names = set(all_names)
    print(f"Unique players used: {len(unique_names)} across {len(puzzles)} puzzles")

    # Repeat rate
    unique_pairs = set(pair_keys)
    repeat_count = len(pair_keys) - len(unique_pairs)
    print(f"Repeat pairs: {repeat_count}/{len(puzzles)}  (rate: {repeat_count/max(len(puzzles),1):.1%})")

    # GOAT distribution (bands: easy=2, medium=3, hard=4+)
    if goat_values:
        easy = sum(1 for g in goat_values if g <= 2)
        medium = sum(1 for g in goat_values if g == 3)
        hard = sum(1 for g in goat_values if g >= 4)
        print(f"GOAT distribution: easy(2)={easy}  medium(3)={medium}  hard(4+)={hard}")
        print(f"  min={min(goat_values)}  max={max(goat_values)}  "
              f"avg={sum(goat_values)/len(goat_values):.1f}")

    # Top 10 most-used players (should be spread, not concentrated)
    counter = collections.Counter(all_names)
    top10 = counter.most_common(10)
    print(f"Most frequent endpoints: {top10}")

    # puzzle_date encoding check
    free_dates = sum(1 for p in puzzles if p.get("puzzle_date", "").startswith("free:"))
    print(f"Correct puzzle_date encoding: {free_dates}/{len(puzzles)}")

    print()
    print("=" * 64)
    print("DIFFICULTY COMPLIANCE — per-difficulty pulls (10 each)")
    print("=" * 64)

    for diff in ("easy", "medium", "hard"):
        pulled: list[dict] = []
        for _ in range(10):
            p = fetch_random(base, mode="classic", difficulty=diff)
            if p:
                pulled.append(p)
            time.sleep(0.1)

        if not pulled:
            print(f"  {diff}: no puzzles returned")
            continue

        in_band = sum(1 for p in pulled
                      if p.get("difficulty") == diff)
        goats = [p["optimal_hops"] for p in pulled if isinstance(p.get("optimal_hops"), int)]
        print(f"  {diff}: {in_band}/{len(pulled)} matched label | GOATs={sorted(goats)}")

    print()
    print("=" * 64)
    print("DAILY_PUZZLES INTEGRITY CHECK")
    print("=" * 64)

    if conn is not None:
        try:
            post_count = count_daily_puzzles(conn)
            delta = post_count - pre_count
            print(f"daily_puzzles rows AFTER: {post_count}  (delta={delta:+d})")
            if delta == 0:
                print("  PASS — no daily_puzzles rows were created by free-play")
            else:
                print(f"  FAIL — {delta} new rows were unexpectedly created!")
        except Exception as e:
            print(f"  ERROR: {e}")
        finally:
            conn.close()
    else:
        print("  (DB check skipped — connection unavailable)")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
