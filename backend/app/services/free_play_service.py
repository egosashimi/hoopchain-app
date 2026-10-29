"""
HOOPCHAIN — Free-Play Service (W3)
Generates transient puzzles on the fly from a recognizable-endpoint pool.
Does not read from or write to daily_puzzles.

Pool design:
  - Players ranked by recognizability_score (seasons + All-Stars + headshot + draft)
  - Assigned to era buckets by which decades they were active
  - Top-K per era, modern-weighted (2020s/2010s heaviest)

Difficulty bands (dribbles = intermediate players, len(path)−2):
  easy   1 dribble  (~66% of pairs — one intermediate)
  medium 2 dribbles (~18% of pairs — two intermediates)
  hard   3+ dribbles (~7%  of pairs — three or more intermediates)

Hard pairs are sampled as a famous modern star (2010s/2020s) vs. a famous
pre-1995 legend (1980s/pre1980 pool). Era distance does the work of producing
long paths — not player obscurity. Both endpoints must clear RECOGNIZABILITY_FLOOR.
"""

from __future__ import annotations

import logging
import random
import time
import zlib
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .graph_service import compute_optimal_hops_by_mode, get_graph

logger = logging.getLogger(__name__)

# ------------------------------------
# Constants
# ------------------------------------

# Minimum score to appear in the endpoint pool.
# Formula: +1/season, +5/All-Star edge (halved), +10 if CDN headshot exists,
#          +3 if round-1 pick, +2 if drafted after 1990.  Max observed: 34.
# Floor=20 eliminates journeymen with many seasons but limited recognition.
RECOGNIZABILITY_FLOOR = 20

# Higher floor used for hard-mode endpoints to guarantee casual-fan recognizability.
# Score≥26 ≈ players with headshot + All-Star appearance, or 16+ seasons, etc.
# This eliminates obscure-but-long-career players (Dan Schayes, John Long, etc.)
# while keeping the household-name legends (Jordan, Magic, Bird, Barkley…) and
# recognizable modern stars (LeBron, Curry, Giannis, Durant…).
HARD_RECOGNIZABILITY_FLOOR = 26

# Era label → (decade_start, decade_end) for overlap check against player seasons.
ERA_RANGES: dict[str, tuple[int, int]] = {
    "2020s": (2020, 9999),
    "2010s": (2010, 2019),
    "2000s": (2000, 2009),
    "1990s": (1990, 1999),
    "1980s": (1980, 1989),
    "pre1980": (0, 1979),
}

# Target endpoint pool size per era (modern-weighted).
ERA_TARGETS: dict[str, int] = {
    "2020s": 100,
    "2010s": 100,
    "2000s":  75,
    "1990s":  75,
    "1980s":  50,
    "pre1980": 30,
}

# GOAT dribble-count bands (dribbles = intermediate players, len(path)−2).
# Calibrated to the actual distribution in the recognizable-player pool:
#   1 dribble = 66%, 2 dribbles = 18%, 3+ dribbles = 7%.
DIFFICULTY_BANDS: dict[str, tuple[int, int]] = {
    "easy":   (1, 1),    # one intermediate player
    "medium": (2, 2),    # two intermediate players
    "hard":   (3, 999),  # three or more intermediate players
}

POOL_REFRESH_SECONDS = 6 * 3600   # rebuild pool every 6 hours
MAX_SAMPLE_ATTEMPTS = 100         # hard cap on BFS attempts per request
DIFFICULTY_RELAX_AT = 60          # relax GOAT-band filter after this many failed attempts

# Curated list of pre-1995 NBA legends to use as hard-mode "classic era" endpoints.
# These players have broken recognizability_score data in the DB (Bird=1, Magic=1,
# Drexler=1, Hakeem=2) due to incomplete player_seasons records, so they can't be
# discovered through the score-based pool. They ARE in the graph with teammate edges.
# IDs are NBA Stats player IDs (match players.id — String(20)).
HARD_CLASSIC_PLAYER_IDS: list[str] = [
    "893",    # Michael Jordan
    "1449",   # Larry Bird
    "77142",  # Magic Johnson
    "76003",  # Kareem Abdul-Jabbar
    "787",    # Charles Barkley
    "937",    # Scottie Pippen
    "252",    # Karl Malone
    "304",    # John Stockton
    "17",     # Clyde Drexler
    "121",    # Patrick Ewing
    "165",    # Hakeem Olajuwon
    "77449",  # Moses Malone
    "1122",   # Dominique Wilkins
    "397",    # Reggie Miller
    "764",    # David Robinson
    "23",     # Dennis Rodman
    "78318",  # Isiah Thomas
    "76681",  # Julius Erving
]

# Famous 2010s/2020s stars whose recognizability_score is broken (Giannis=23, Jokic=22,
# Kawhi=21, Embiid=19, etc.) because recent short careers score poorly on the
# seasons-count formula. Score-eligible pool (≥26) already covers Curry, Durant,
# LeBron, Harden, Westbrook, Chris Paul, Kobe, Duncan, Dirk — so this list
# supplements only the genuinely missing household names.
HARD_MODERN_PLAYER_IDS: list[str] = [
    "203507",  # Giannis Antetokounmpo
    "203999",  # Nikola Jokic
    "203954",  # Joel Embiid
    "202695",  # Kawhi Leonard
    "202681",  # Kyrie Irving
    "202691",  # Klay Thompson
    "202710",  # Jimmy Butler
    "203076",  # Anthony Davis
    "203081",  # Damian Lillard
]

# Ordered era list used for weighted sampling
_ERA_ORDER: list[str] = list(ERA_RANGES.keys())

# Endpoint-1 sampling weights: modern bias
_ERA1_WEIGHTS: list[float] = [0.35, 0.35, 0.15, 0.10, 0.04, 0.01]

# ------------------------------------
# Pool data structures
# ------------------------------------

@dataclass
class PoolEntry:
    id: str
    name: str
    headshot_url: str
    score: int
    eras: list[str]
    first_season: int
    last_season: int


@dataclass
class FreePlayPool:
    by_era: dict[str, list[PoolEntry]]
    flat: list[PoolEntry]   # deduplicated across all eras
    built_at: float

    def size(self) -> int:
        return len(self.flat)

    def era_counts(self) -> dict[str, int]:
        return {era: len(lst) for era, lst in self.by_era.items()}

    def sample_names(self, n: int = 3) -> dict[str, list[str]]:
        return {
            era: [p.name for p in random.sample(lst, min(n, len(lst)))]
            for era, lst in self.by_era.items()
            if lst
        }


# ------------------------------------
# Module-level pool singleton
# ------------------------------------

_pool: Optional[FreePlayPool] = None


def _compute_eras(first_season: int, last_season: int) -> list[str]:
    """Return all era labels a player was active in (range-overlap test)."""
    return [
        era
        for era, (lo, hi) in ERA_RANGES.items()
        if first_season <= hi and last_season >= lo
    ]


def pair_id(start_id: str, end_id: str) -> int:
    """Deterministic positive-32-bit pair ID (order-independent CRC32)."""
    a, b = min(start_id, end_id), max(start_id, end_id)
    return zlib.crc32(f"{a}:{b}".encode()) & 0x7FFFFFFF


async def _build_pool(db: AsyncSession) -> FreePlayPool:
    """Query the DB and build the in-memory endpoint pool."""
    _ERA_SQL = """
        WITH player_eras AS (
            SELECT player_id,
                   MIN(season) AS first_season,
                   MAX(season) AS last_season
            FROM player_seasons
            GROUP BY player_id
        )
        SELECT p.id, p.full_name, p.headshot_url,
               p.recognizability_score, pe.first_season, pe.last_season
        FROM players p
        JOIN player_eras pe ON p.id = pe.player_id
        WHERE {where}
        ORDER BY p.recognizability_score DESC
    """

    G = get_graph()

    def _to_entries(rows: list) -> list[PoolEntry]:
        out = []
        for pid, full_name, headshot_url, score, first_season, last_season in rows:
            if not G.has_node(f"player:{pid}"):
                continue
            eras = _compute_eras(first_season, last_season)
            if not eras:
                continue
            url = headshot_url or f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"
            out.append(PoolEntry(
                id=pid, name=full_name, headshot_url=url,
                score=score or 0, eras=eras,
                first_season=first_season, last_season=last_season,
            ))
        return out

    # Standard pool: score-eligible players for all era buckets and hard_modern.
    result = await db.execute(
        text(_ERA_SQL.format(where="p.recognizability_score >= :floor")),
        {"floor": RECOGNIZABILITY_FLOOR},
    )
    entries = _to_entries(result.fetchall())

    # hard_classic pool: curated list of pre-1995 household-name legends.
    # These players have broken recognizability_score values (Bird=1, Magic=1,
    # Drexler=1, Hakeem=2) due to incomplete player_seasons rows, so they don't
    # appear in the score-eligible pool. Fetched separately by ID, then verified
    # against the graph (all 18 have full teammate edges).
    hc_ids_sql = ", ".join(f"'{pid}'" for pid in HARD_CLASSIC_PLAYER_IDS)
    hc_result = await db.execute(
        text(_ERA_SQL.format(where=f"p.id IN ({hc_ids_sql})")),
    )
    hard_classic_entries = _to_entries(hc_result.fetchall())

    # Per-era pools: sort by score DESC, cap to ERA_TARGETS
    pool_by_era: dict[str, list[PoolEntry]] = {}
    for era, target in ERA_TARGETS.items():
        era_list = [e for e in entries if era in e.eras]
        era_list.sort(key=lambda x: x.score, reverse=True)
        pool_by_era[era] = era_list[:target]

    # hard_modern: score-eligible 2010s/2020s stars (Curry, Durant, LeBron, Kobe…)
    # supplemented by curated famous players with broken scores (Giannis, Jokic, Kawhi…).
    hard_modern_score = [
        e for e in entries
        if any(era in e.eras for era in ("2020s", "2010s"))
        and e.score >= HARD_RECOGNIZABILITY_FLOOR
    ]
    hm_ids_sql = ", ".join(f"'{pid}'" for pid in HARD_MODERN_PLAYER_IDS)
    hm_result = await db.execute(
        text(_ERA_SQL.format(where=f"p.id IN ({hm_ids_sql})")),
    )
    hard_modern_curated = _to_entries(hm_result.fetchall())
    # Merge, dedup by id, sort by score DESC
    seen_hm: set[str] = {e.id for e in hard_modern_score}
    hard_modern_all = hard_modern_score + [e for e in hard_modern_curated if e.id not in seen_hm]
    hard_modern_all.sort(key=lambda x: x.score, reverse=True)
    pool_by_era["hard_modern"] = hard_modern_all[:60]

    pool_by_era["hard_classic"] = hard_classic_entries

    # Flat deduplicated pool for fallback sampling
    seen: set[str] = set()
    pool_flat: list[PoolEntry] = []
    for era_list in pool_by_era.values():
        for p in era_list:
            if p.id not in seen:
                seen.add(p.id)
                pool_flat.append(p)

    pool = FreePlayPool(by_era=pool_by_era, flat=pool_flat, built_at=time.monotonic())
    logger.info(
        "FreePlayPool built: %d unique players | era breakdown: %s",
        pool.size(),
        pool.era_counts(),
    )
    for era, names in pool.sample_names(3).items():
        logger.info("  %s sample: %s", era, ", ".join(names))
    return pool


async def get_or_build_pool(db: AsyncSession) -> FreePlayPool:
    """Return the cached pool, rebuilding if stale (>6 h) or absent."""
    global _pool
    if _pool is None or (time.monotonic() - _pool.built_at) > POOL_REFRESH_SECONDS:
        _pool = await _build_pool(db)
    return _pool


# ------------------------------------
# Pair sampling
# ------------------------------------

def _pick_eras(difficulty: str | None = None) -> tuple[str, str]:
    """
    Sample two era labels for the pair endpoints.

    For easy / no-filter: modern bias for both; suppress same-era.
    For medium: force modern endpoint vs. 1990s/2000s (temporal gap encourages longer paths).
    For hard: force modern endpoint vs. 1980s/pre1980 (large gap maximises GOAT length).
    """
    if difficulty == "hard":
        # Pair a famous modern star with a famous pre-1995 legend.
        # hard_modern/hard_classic sub-pools use HARD_RECOGNIZABILITY_FLOOR so only
        # household names appear. Era distance produces the long path, not obscurity.
        return "hard_modern", "hard_classic"
    if difficulty == "medium":
        # 2020s/2010s vs 1990s gives ~33% GOAT=3 pairs (vs near-zero for same-era).
        era1 = random.choice(["2020s", "2010s"])
        era2 = random.choices(["1990s", "1980s", "2000s"], weights=[0.55, 0.3, 0.15])[0]
        return era1, era2

    # Default: modern bias + cross-era suppression
    era1 = random.choices(_ERA_ORDER, weights=_ERA1_WEIGHTS)[0]
    w2 = list(_ERA1_WEIGHTS)
    idx = _ERA_ORDER.index(era1)
    w2[idx] *= 0.2
    total = sum(w2)
    w2 = [w / total for w in w2]
    era2 = random.choices(_ERA_ORDER, weights=w2)[0]
    return era1, era2


def difficulty_label(hops: int) -> str:
    """Map a GOAT dribble count (intermediates) to a difficulty label."""
    if hops <= 1:
        return "easy"
    if hops <= 2:
        return "medium"
    return "hard"


async def generate_free_play_puzzle(
    db: AsyncSession,
    mode: str = "classic",
    difficulty: str | None = None,
    exclude_ids: list[int] | None = None,
) -> dict | None:
    """
    Generate a transient free-play puzzle on the fly.

    Sampling loop:
      1. Pick two endpoints from the era pool (modern-weighted, cross-era biased).
      2. BFS to verify reachability in the requested mode; get GOAT.
      3. Reject trivial pairs (GOAT < 2) and unreachable pairs.
      4. Filter by requested difficulty band (relaxed after DIFFICULTY_RELAX_AT attempts).
      5. Return puzzle payload (same shape as daily puzzle response).

    Returns None if no valid pair found after MAX_SAMPLE_ATTEMPTS.
    Does NOT read from or write to daily_puzzles.
    """
    pool = await get_or_build_pool(db)
    if pool.size() < 2:
        logger.error("FreePlayPool too small (%d) — cannot generate puzzle", pool.size())
        return None

    exclude_set: set[int] = set(exclude_ids or [])

    for attempt in range(MAX_SAMPLE_ATTEMPTS):
        relaxed = attempt >= DIFFICULTY_RELAX_AT

        # Hard mode keeps era-gap sampling even when relaxed (only the GOAT band drops).
        # Other difficulties fall back to default sampling when relaxed.
        era_difficulty = difficulty if (not relaxed or difficulty == "hard") else None
        era1, era2 = _pick_eras(difficulty=era_difficulty)
        p1_list = pool.by_era.get(era1) or pool.flat
        p2_list = pool.by_era.get(era2) or pool.flat

        if not p1_list or not p2_list:
            continue

        p1 = random.choice(p1_list)
        p2 = random.choice(p2_list)

        if p1.id == p2.id:
            continue

        pid = pair_id(p1.id, p2.id)
        if pid in exclude_set:
            continue

        # BFS: verify reachability and compute GOAT for all modes
        hops_by_mode = compute_optimal_hops_by_mode(p1.id, p2.id)
        mode_hops = hops_by_mode.get(mode)

        if mode_hops is None:
            continue  # unreachable in the requested mode

        # Hard mode always requires ≥ 2 dribbles even after difficulty relaxation.
        # Non-hard rejects GOAT=0 (direct teammates — trivially unsolvable).
        min_hops = 2 if difficulty == "hard" else 1
        if mode_hops < min_hops:
            continue

        # Difficulty filter — relaxed after DIFFICULTY_RELAX_AT attempts
        if difficulty and not relaxed:
            lo, hi = DIFFICULTY_BANDS[difficulty]
            if not (lo <= mode_hops <= hi):
                continue

        # available_modes: only classic + wild (COACH removed)
        available = [m for m in ("classic", "wild") if hops_by_mode.get(m) is not None]
        if mode in available:
            available = [mode] + [m for m in available if m != mode]

        filtered_hops = {m: h for m, h in hops_by_mode.items() if m in ("classic", "wild")}

        diff = difficulty_label(mode_hops)

        logger.debug(
            "FreePlay [attempt %d/%d]: %s → %s | mode=%s GOAT=%d diff=%s",
            attempt + 1, MAX_SAMPLE_ATTEMPTS, p1.name, p2.name, mode, mode_hops, diff,
        )

        return {
            "puzzle_id": pid,
            # Encode start/end IDs in puzzle_date so the game-completion
            # endpoint can reconstruct puzzle metadata without a DB lookup.
            "puzzle_date": f"free:{p1.id}:{p2.id}",
            "start_player": {
                "id": p1.id,
                "full_name": p1.name,
                "headshot_url": p1.headshot_url,
                "team_name": None,
                "is_active": p1.last_season >= 2023,
            },
            "end_player": {
                "id": p2.id,
                "full_name": p2.name,
                "headshot_url": p2.headshot_url,
                "team_name": None,
                "is_active": p2.last_season >= 2023,
            },
            "difficulty": diff,
            "optimal_hops": mode_hops,
            "available_modes": available,
            "optimal_hops_by_mode": filtered_hops,
        }

    logger.warning(
        "FreePlay: failed to generate puzzle after %d attempts (mode=%s difficulty=%s)",
        MAX_SAMPLE_ATTEMPTS, mode, difficulty,
    )
    return None
