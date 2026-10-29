"""
HOOPCHAIN — Redis client with helper methods
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

import redis.asyncio as aioredis

from .config import settings

# ------------------------------------
# Connection pool (singleton pattern)
# ------------------------------------

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


# ------------------------------------
# TTL helpers
# ------------------------------------

def ttl_until_midnight_utc() -> int:
    """Seconds until next midnight UTC."""
    now = datetime.now(tz=timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60, int((midnight - now).total_seconds()))


# ------------------------------------
# Key constants
# ------------------------------------

class CacheKey:
    PUZZLE_TODAY = "puzzle:today"
    PUZZLE_DATE = "puzzle:v2:date:{date}"
    HOP = "path:{a}:{b}"
    SEARCH = "search:{query}"
    LEADERBOARD_TODAY = "leaderboard:today"

    @staticmethod
    def puzzle_date(date: str) -> str:
        return f"puzzle:v2:date:{date}"

    @staticmethod
    def hop(node_a: str, node_b: str) -> str:
        # Sort for consistent keying regardless of direction
        a, b = sorted([node_a, node_b])
        return f"path:{a}:{b}"

    @staticmethod
    def search(query: str) -> str:
        return f"search:{query.lower().strip()}"


# ------------------------------------
# Cache helpers
# ------------------------------------

async def cache_get(key: str) -> dict | list | None:
    """Get a JSON-serialized value from Redis."""
    try:
        redis = get_redis()
        val = await redis.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set a JSON-serialized value in Redis with TTL (seconds)."""
    try:
        redis = get_redis()
        await redis.setex(key, ttl, json.dumps(value))
        return True
    except Exception:
        return False


async def cache_delete(key: str) -> None:
    """Delete a key from Redis."""
    try:
        redis = get_redis()
        await redis.delete(key)
    except Exception:
        pass


async def leaderboard_add(client_id: str, score: int) -> None:
    """Add/update score in today's leaderboard sorted set."""
    try:
        redis = get_redis()
        key = CacheKey.LEADERBOARD_TODAY
        await redis.zadd(key, {client_id: score})
        await redis.expire(key, ttl_until_midnight_utc())
    except Exception:
        pass


async def leaderboard_get_top(n: int = 10) -> list[tuple[str, float]]:
    """Get top N from today's leaderboard (sorted set, highest score first)."""
    try:
        redis = get_redis()
        key = CacheKey.LEADERBOARD_TODAY
        # withscores returns list of (member, score) tuples
        result = await redis.zrevrange(key, 0, n - 1, withscores=True)
        return result
    except Exception:
        return []
