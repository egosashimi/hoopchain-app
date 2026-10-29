"""HOOPCHAIN — Puzzle Router"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.puzzle_service import get_today_puzzle, get_puzzle_for_date
from ..services.free_play_service import generate_free_play_puzzle

router = APIRouter(prefix="/puzzle", tags=["puzzle"])


@router.get("/today")
async def get_today(db: AsyncSession = Depends(get_db)):
    """Get today's puzzle. Does NOT reveal the canonical path (anti-cheat)."""
    try:
        return await get_today_puzzle(db)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to load puzzle: {str(e)}")


@router.get("/random")
async def get_random(
    mode: str = Query(default="classic", description="classic | wild"),
    difficulty: str | None = Query(default=None, description="easy | medium | hard"),
    exclude_ids: str | None = Query(
        default=None,
        description="Comma-separated pair IDs already seen this session (prevents quick repeats)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a free-play puzzle on the fly from the recognizable-endpoint pool.
    Pairs are sampled fresh each call — no daily_puzzles reads or writes.
    Pass exclude_ids (comma-separated puzzle_id integers) to skip recently-served pairs.
    """
    valid_modes = {"classic", "wild"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"mode must be one of: {', '.join(sorted(valid_modes))}")

    valid_difficulties = {"easy", "medium", "hard"}
    if difficulty and difficulty not in valid_difficulties:
        raise HTTPException(status_code=400, detail=f"difficulty must be one of: {', '.join(valid_difficulties)}")

    parsed_exclude: list[int] = []
    if exclude_ids:
        for part in exclude_ids.split(","):
            part = part.strip()
            if part.isdigit():
                parsed_exclude.append(int(part))

    try:
        puzzle = await generate_free_play_puzzle(
            db,
            mode=mode,
            difficulty=difficulty,
            exclude_ids=parsed_exclude or None,
        )
        if puzzle is None:
            raise HTTPException(
                status_code=503,
                detail="Could not generate a free-play puzzle. Try again.",
            )
        return puzzle
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to generate free-play puzzle: {str(e)}")


@router.get("/{puzzle_date}")
async def get_by_date(puzzle_date: str, db: AsyncSession = Depends(get_db)):
    """Get a historical puzzle by date (YYYY-MM-DD)."""
    try:
        d = date.fromisoformat(puzzle_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if d > date.today():
        raise HTTPException(status_code=404, detail="Puzzle not available yet.")

    try:
        return await get_puzzle_for_date(db, d)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to load puzzle: {str(e)}")
