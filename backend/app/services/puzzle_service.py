"""
HOOPCHAIN — Puzzle Service
Handles daily puzzle retrieval, caching, mock puzzle generation, and random free-play puzzles.
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DailyPuzzle, Player
from ..redis_client import (
    CacheKey,
    cache_get,
    cache_set,
    ttl_until_midnight_utc,
)
from ..config import settings

logger = logging.getLogger(__name__)

# ------------------------------------
# Mock puzzle for demo mode
# ------------------------------------

MOCK_PUZZLES_BY_DOW: list[dict] = [
    {  # Monday — Easy
        "start_player_id": "2544",
        "end_player_id": "977",
        "start": {"id": "2544", "full_name": "LeBron James", "team_name": "Los Angeles Lakers"},
        "end":   {"id": "977",  "full_name": "Kobe Bryant",  "team_name": "Retired"},
        "optimal_hops": 2,
        "difficulty": "easy",
        "edge_types_used": ["teammate", "teammate"],
    },
    {  # Tuesday — Medium
        "start_player_id": "893",
        "end_player_id": "2544",
        "start": {"id": "893",  "full_name": "Michael Jordan", "team_name": "Retired"},
        "end":   {"id": "2544", "full_name": "LeBron James",   "team_name": "Los Angeles Lakers"},
        "optimal_hops": 3,
        "difficulty": "medium",
        "edge_types_used": ["all_star", "teammate", "teammate"],
    },
    {  # Wednesday — Hard
        "start_player_id": "76003",
        "end_player_id": "201939",
        "start": {"id": "76003",  "full_name": "Kareem Abdul-Jabbar", "team_name": "Retired"},
        "end":   {"id": "201939", "full_name": "Stephen Curry",       "team_name": "Golden State Warriors"},
        "optimal_hops": 4,
        "difficulty": "hard",
        "edge_types_used": ["all_star", "teammate", "all_star", "teammate"],
    },
    {  # Thursday — Medium
        "start_player_id": "708",
        "end_player_id": "201142",
        "start": {"id": "708",    "full_name": "Kevin Garnett", "team_name": "Retired"},
        "end":   {"id": "201142", "full_name": "Kevin Durant",  "team_name": "Phoenix Suns"},
        "optimal_hops": 3,
        "difficulty": "medium",
        "edge_types_used": ["all_star", "teammate", "teammate"],
    },
    {  # Friday — Easy
        "start_player_id": "2548",
        "end_player_id": "101108",
        "start": {"id": "2548",   "full_name": "Dwyane Wade", "team_name": "Retired"},
        "end":   {"id": "101108", "full_name": "Chris Paul",  "team_name": "Golden State Warriors"},
        "optimal_hops": 2,
        "difficulty": "easy",
        "edge_types_used": ["teammate", "all_star"],
    },
    {  # Saturday — Hard
        "start_player_id": "1449",
        "end_player_id": "203507",
        "start": {"id": "1449",   "full_name": "Larry Bird",             "team_name": "Retired"},
        "end":   {"id": "203507", "full_name": "Giannis Antetokounmpo", "team_name": "Milwaukee Bucks"},
        "optimal_hops": 4,
        "difficulty": "hard",
        "edge_types_used": ["all_star", "teammate", "all_star", "teammate"],
    },
    {  # Sunday — Medium
        "start_player_id": "1495",
        "end_player_id": "203954",
        "start": {"id": "1495",   "full_name": "Tim Duncan",   "team_name": "Retired"},
        "end":   {"id": "203954", "full_name": "Joel Embiid",  "team_name": "Philadelphia 76ers"},
        "optimal_hops": 3,
        "difficulty": "medium",
        "edge_types_used": ["all_star", "teammate", "teammate"],
    },
]


def _get_mock_puzzle(puzzle_date: date) -> dict:
    """Return a deterministic mock puzzle based on day of week, with available_modes computed."""
    from .graph_service import compute_available_modes, compute_optimal_hops_by_mode

    dow = puzzle_date.weekday()  # 0=Monday, 6=Sunday
    puzzle_data = MOCK_PUZZLES_BY_DOW[dow]

    epoch = date(2026, 1, 1)
    puzzle_number = (puzzle_date - epoch).days + 1

    try:
        available_modes = compute_available_modes(
            puzzle_data["start_player_id"],
            puzzle_data["end_player_id"],
        )
    except Exception:
        available_modes = ["classic"]

    try:
        optimal_hops_by_mode = compute_optimal_hops_by_mode(
            puzzle_data["start_player_id"],
            puzzle_data["end_player_id"],
        )
    except Exception:
        optimal_hops_by_mode = {"classic": puzzle_data["optimal_hops"]}

    return {
        "puzzle_id": puzzle_number,
        "puzzle_date": puzzle_date.isoformat(),
        "start_player": puzzle_data["start"],
        "end_player": puzzle_data["end"],
        "difficulty": puzzle_data["difficulty"],
        "optimal_hops": puzzle_data["optimal_hops"],
        "available_modes": available_modes,
        "optimal_hops_by_mode": optimal_hops_by_mode,
    }


# ------------------------------------
# Puzzle retrieval
# ------------------------------------

async def get_today_puzzle(db: AsyncSession) -> dict:
    """Get today's puzzle (Redis → Postgres → mock fallback)."""
    today = date.today()
    return await get_puzzle_for_date(db, today)


async def get_puzzle_for_date(db: AsyncSession, puzzle_date: date) -> dict:
    """Get puzzle for a specific date."""

    # 1. Check Redis cache
    cache_key = CacheKey.puzzle_date(puzzle_date.isoformat())
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # 2. Check database
    if not settings.use_mock_graph:
        try:
            stmt = select(DailyPuzzle).where(
                DailyPuzzle.puzzle_date == puzzle_date,
                DailyPuzzle.is_published == True,
            )
            result = await db.execute(stmt)
            puzzle = result.scalar_one_or_none()

            if puzzle:
                data = await _puzzle_to_response(puzzle, db)
                ttl = ttl_until_midnight_utc() if puzzle_date == date.today() else 86400 * 30
                await cache_set(cache_key, data, ttl)
                return data
        except Exception as e:
            logger.warning(f"Database puzzle fetch failed: {e}")

    # 3. Fall back to mock puzzle
    data = _get_mock_puzzle(puzzle_date)
    ttl = ttl_until_midnight_utc() if puzzle_date == date.today() else 3600
    await cache_set(cache_key, data, ttl)
    return data


async def get_random_puzzle(
    db: AsyncSession,
    mode: str = "classic",
    difficulty: str | None = None,
    exclude_ids: list[int] | None = None,
) -> dict | None:
    """
    Return a random published puzzle that is NOT today's puzzle and IS
    available for the requested mode. If difficulty is specified, filter
    to only puzzles of that difficulty.
    Returns None if no matching puzzle exists.
    Does not cache — each call returns a different puzzle.
    """
    today = date.today()

    if not settings.use_mock_graph:
        try:
            stmt = select(DailyPuzzle).where(
                DailyPuzzle.is_published == True,
                DailyPuzzle.puzzle_date != today,
            )
            if difficulty:
                stmt = stmt.where(DailyPuzzle.difficulty == difficulty)

            result = await db.execute(stmt)
            puzzles = result.scalars().all()

            # Exclude already-seen puzzles this session
            if exclude_ids:
                epoch = date(2026, 1, 1)
                exclude_set = set(exclude_ids)
                puzzles = [
                    p for p in puzzles
                    if (p.puzzle_date - epoch).days + 1 not in exclude_set
                ]

            # Filter by mode availability
            eligible = [
                p for p in puzzles
                if p.available_modes and mode in p.available_modes
            ]

            if not eligible:
                # Fall back to classic if mode not available
                if mode != "classic":
                    eligible = [
                        p for p in puzzles
                        if p.available_modes and "classic" in p.available_modes
                    ]
                if not eligible:
                    eligible = list(puzzles)

            if not eligible:
                return None

            puzzle = random.choice(eligible)
            return await _puzzle_to_response(puzzle, db)
        except Exception as e:
            logger.warning(f"Database random puzzle fetch failed: {e}")

    # Mock fallback: return a random day-of-week puzzle that isn't today
    today_dow = today.weekday()
    other_dows = [i for i in range(7) if i != today_dow]
    if difficulty:
        diff_map = {"easy": [0, 4], "medium": [1, 3, 6], "hard": [2, 5]}
        candidates = [i for i in other_dows if i in diff_map.get(difficulty, other_dows)]
        other_dows = candidates or other_dows

    if not other_dows:
        return None

    target_dow = random.choice(other_dows)
    puzzle_data = MOCK_PUZZLES_BY_DOW[target_dow]
    # Use a fake puzzle_date a few days back as a stand-in for the random puzzle
    fake_date = today - timedelta(days=(today_dow - target_dow) % 7 + 1)
    epoch = date(2026, 1, 1)
    puzzle_number = (fake_date - epoch).days + 1

    from .graph_service import compute_available_modes, compute_optimal_hops_by_mode
    try:
        available_modes = compute_available_modes(
            puzzle_data["start_player_id"],
            puzzle_data["end_player_id"],
        )
    except Exception:
        available_modes = ["classic"]

    try:
        optimal_hops_by_mode = compute_optimal_hops_by_mode(
            puzzle_data["start_player_id"],
            puzzle_data["end_player_id"],
        )
    except Exception:
        optimal_hops_by_mode = {"classic": puzzle_data["optimal_hops"]}

    return {
        "puzzle_id": puzzle_number,
        "puzzle_date": fake_date.isoformat(),
        "start_player": puzzle_data["start"],
        "end_player": puzzle_data["end"],
        "difficulty": puzzle_data["difficulty"],
        "optimal_hops": puzzle_data["optimal_hops"],
        "available_modes": available_modes,
        "optimal_hops_by_mode": optimal_hops_by_mode,
    }


async def _puzzle_to_response(puzzle: DailyPuzzle, db: AsyncSession) -> dict:
    """Convert a DailyPuzzle ORM object to response dict."""
    from .graph_service import compute_optimal_hops_by_mode

    epoch = date(2026, 1, 1)
    puzzle_number = (puzzle.puzzle_date - epoch).days + 1

    start_result = await db.execute(select(Player).where(Player.id == puzzle.start_player_id))
    start_player = start_result.scalar_one_or_none()

    end_result = await db.execute(select(Player).where(Player.id == puzzle.end_player_id))
    end_player = end_result.scalar_one_or_none()

    try:
        optimal_hops_by_mode = compute_optimal_hops_by_mode(puzzle.start_player_id, puzzle.end_player_id)
        # Prefer live unweighted BFS value over DB-seeded value (which was computed with
        # weighted path and can differ when a low-weight longer route beats a high-weight
        # shorter one).
        live_optimal = optimal_hops_by_mode.get("classic") or puzzle.optimal_hops
    except Exception:
        optimal_hops_by_mode = {"classic": puzzle.optimal_hops}
        live_optimal = puzzle.optimal_hops

    return {
        "puzzle_id": puzzle_number,
        "puzzle_date": puzzle.puzzle_date.isoformat(),
        "start_player": {
            "id": puzzle.start_player_id,
            "full_name": start_player.full_name if start_player else "Unknown",
            "headshot_url": start_player.headshot() if start_player else None,
            "team_name": None,
            "is_active": start_player.is_active if start_player else False,
        },
        "end_player": {
            "id": puzzle.end_player_id,
            "full_name": end_player.full_name if end_player else "Unknown",
            "headshot_url": end_player.headshot() if end_player else None,
            "team_name": None,
            "is_active": end_player.is_active if end_player else False,
        },
        "difficulty": puzzle.difficulty,
        "optimal_hops": live_optimal,
        "available_modes": puzzle.available_modes or ["classic"],
        "optimal_hops_by_mode": optimal_hops_by_mode,
        # NOTE: canonical_path is intentionally NOT returned (anti-cheat)
    }
