#!/usr/bin/env python3
"""
HOOPCHAIN ETL -- Step 18: Migrate optimal_hops to dribble (intermediate) count.

Historically optimal_hops stored edge count (len(path) - 1).
The new definition: dribbles = intermediates = len(path) - 2 = old value - 1.

This script subtracts 1 from every daily_puzzle's optimal_hops so the DB
stays consistent with the new graph_service.compute_optimal_hops_by_mode
formula and the test_future_puzzles_valid check.

Difficulty classification is preserved because bands shift by 1 along with
the metric (old easy ≤ 2 edges ↔ new easy ≤ 1 intermediate).

Usage (from repo root):
    python data/etl/18_migrate_optimal_hops_to_intermediates.py [--dry-run]

Requires data/etl/.env with DATABASE_URL pointing to the external proxy.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in data/etl/.env", file=sys.stderr)
    sys.exit(1)

PG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate optimal_hops to dribble count")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, no writes")
    args = parser.parse_args()

    conn = psycopg2.connect(PG_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # Preview affected rows
    cur.execute("SELECT COUNT(*) FROM daily_puzzles WHERE optimal_hops > 0")
    (total,) = cur.fetchone()
    print(f"  Rows with optimal_hops > 0: {total}")

    cur.execute(
        "SELECT puzzle_date, optimal_hops, difficulty "
        "FROM daily_puzzles ORDER BY puzzle_date"
    )
    rows = cur.fetchall()
    print(f"  {'Date':<14} {'Old GOAT':>10} {'New GOAT':>10}  Difficulty")
    print("  " + "-" * 50)
    for puzzle_date, old_hops, diff in rows:
        new_hops = old_hops - 1
        print(f"  {str(puzzle_date):<14} {old_hops:>10} {new_hops:>10}  {diff}")

    if args.dry_run:
        print("\n  [DRY RUN] No changes written.")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE daily_puzzles SET optimal_hops = optimal_hops - 1")
    affected = cur.rowcount
    conn.commit()
    print(f"\n  Updated {affected} rows — optimal_hops decremented by 1.")
    print("  Flush Redis puzzle cache via /admin/flush-puzzle-cache to clear stale values.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
