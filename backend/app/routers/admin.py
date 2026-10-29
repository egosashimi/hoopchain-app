"""HOOPCHAIN — Admin Router
Password-protected endpoints for puzzle management.
Requires header: X-Admin-Key matching env var API_SECRET_KEY.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import DailyPuzzle, Player, EmailSubscriber
from ..redis_client import get_redis, CacheKey

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------
# Auth dependency
# ------------------------------------

async def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not x_admin_key or x_admin_key != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ------------------------------------
# Models
# ------------------------------------

class PuzzleOverrideRequest(BaseModel):
    puzzle_date: str          # YYYY-MM-DD
    start_player_id: str
    end_player_id: str


# ------------------------------------
# Endpoints
# ------------------------------------

@router.post("/flush-puzzle-cache")
async def flush_puzzle_cache(_: None = Depends(require_admin)):
    """Flush all puzzle:date:* Redis keys. Run once after 13_fix_optimal_hops.py."""
    redis = get_redis()
    deleted = 0
    async for key in redis.scan_iter(match="puzzle:date:*"):
        await redis.delete(key)
        deleted += 1
    return {"status": "ok", "keys_deleted": deleted}


@router.post("/flush-hop-cache")
async def flush_hop_cache(_: None = Depends(require_admin)):
    """Flush all path:* Redis keys (hop validation cache). Run after a graph rebuild."""
    redis = get_redis()
    deleted = 0
    async for key in redis.scan_iter(match="path:*"):
        await redis.delete(key)
        deleted += 1
    return {"status": "ok", "keys_deleted": deleted}


@router.get("/puzzles")
async def list_upcoming_puzzles(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Return the next 30 days of scheduled puzzles (published or not)."""
    today = date.today()
    cutoff = today + timedelta(days=30)

    stmt = (
        select(DailyPuzzle)
        .where(DailyPuzzle.puzzle_date >= today, DailyPuzzle.puzzle_date <= cutoff)
        .order_by(DailyPuzzle.puzzle_date)
    )
    result = await db.execute(stmt)
    puzzles = result.scalars().all()

    rows = []
    for p in puzzles:
        # Fetch player names
        sp_result = await db.execute(select(Player).where(Player.id == p.start_player_id))
        ep_result = await db.execute(select(Player).where(Player.id == p.end_player_id))
        start_player = sp_result.scalar_one_or_none()
        end_player = ep_result.scalar_one_or_none()

        rows.append({
            "id": p.id,
            "puzzle_date": p.puzzle_date.isoformat(),
            "start_player_id": p.start_player_id,
            "start_player_name": start_player.full_name if start_player else "Unknown",
            "end_player_id": p.end_player_id,
            "end_player_name": end_player.full_name if end_player else "Unknown",
            "difficulty": p.difficulty,
            "optimal_hops": p.optimal_hops,
            "available_modes": p.available_modes or ["classic"],
            "is_published": p.is_published,
        })

    return rows


@router.get("/subscribers")
async def list_email_subscribers(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """Return recent newsletter subscribers (newest first)."""
    stmt = select(EmailSubscriber).order_by(EmailSubscriber.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    subscribers = result.scalars().all()

    return [
        {
            "id": s.id,
            "email": s.email,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subscribers
    ]


@router.post("/puzzle/override")
async def override_puzzle(
    req: PuzzleOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Override the puzzle for a specific date.
    Recomputes optimal path via BFS and updates daily_puzzles.
    Clears the Redis cache for that date.
    """
    from ..services.graph_service import (
        find_shortest_path_with_labels_for_mode,
        compute_available_modes,
        compute_optimal_hops_by_mode,
    )

    try:
        puzzle_date = date.fromisoformat(req.puzzle_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Validate players exist
    sp_result = await db.execute(select(Player).where(Player.id == req.start_player_id))
    ep_result = await db.execute(select(Player).where(Player.id == req.end_player_id))
    start_player = sp_result.scalar_one_or_none()
    end_player = ep_result.scalar_one_or_none()

    if not start_player:
        raise HTTPException(status_code=404, detail=f"Start player {req.start_player_id} not found")
    if not end_player:
        raise HTTPException(status_code=404, detail=f"End player {req.end_player_id} not found")

    # Compute canonical path via unweighted BFS on the classic (teammate) subgraph
    path = find_shortest_path_with_labels_for_mode(
        req.start_player_id, "player", req.end_player_id, "player", "classic"
    )
    if not path:
        raise HTTPException(status_code=400, detail="No valid classic-mode path found between these players")

    optimal_hops = len(path) - 1
    edge_types = [n.get("edge_type") for n in path if n.get("edge_type")]

    # Determine difficulty based on classic GOAT
    if optimal_hops <= 1:
        difficulty = "easy"
    elif optimal_hops <= 3:
        difficulty = "medium"
    else:
        difficulty = "hard"

    available_modes = compute_available_modes(req.start_player_id, req.end_player_id)

    # Upsert puzzle
    stmt = select(DailyPuzzle).where(DailyPuzzle.puzzle_date == puzzle_date)
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.start_player_id = req.start_player_id
        existing.end_player_id = req.end_player_id
        existing.canonical_path = path
        existing.optimal_hops = optimal_hops
        existing.difficulty = difficulty
        existing.edge_types_used = edge_types
        existing.available_modes = available_modes
        existing.is_published = True
    else:
        puzzle = DailyPuzzle(
            puzzle_date=puzzle_date,
            start_player_id=req.start_player_id,
            end_player_id=req.end_player_id,
            canonical_path=path,
            optimal_hops=optimal_hops,
            difficulty=difficulty,
            edge_types_used=edge_types,
            available_modes=available_modes,
            is_published=True,
        )
        db.add(puzzle)

    await db.flush()

    # Clear Redis cache for this date
    try:
        redis = get_redis()
        cache_key = CacheKey.puzzle_date(req.puzzle_date)
        await redis.delete(cache_key)
    except Exception:
        pass

    return {
        "status": "ok",
        "puzzle_date": req.puzzle_date,
        "start_player": start_player.full_name,
        "end_player": end_player.full_name,
        "optimal_hops": optimal_hops,
        "difficulty": difficulty,
    }
