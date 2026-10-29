"""HOOPCHAIN — Game Router"""

from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import GameSession, Streak
from ..services.score_service import calculate_score, generate_share_text
from ..redis_client import leaderboard_add
from ..services.puzzle_service import get_puzzle_for_date
from ..services.graph_service import (
    find_shortest_path_with_labels_for_mode,
    compute_optimal_hops_by_mode,
    get_graph,
)

router = APIRouter(prefix="/game", tags=["game"])


# ------------------------------------
# Request/response models
# ------------------------------------

class ChainNodeModel(BaseModel):
    id: str
    type: Literal["player", "coach"] = "player"
    name: str
    edgeType: str | None = None
    connectionLabel: str | None = None


class GameCompleteRequest(BaseModel):
    puzzle_date: str
    client_id: str
    path: list[ChainNodeModel]
    hops_used: int
    time_seconds: int
    gave_up: bool
    mode: str = "classic"


# ------------------------------------
# Shared completion logic
# ------------------------------------

async def _record_completion(
    req: GameCompleteRequest,
    db: AsyncSession,
    is_freeplay: bool = False,
) -> dict:
    """
    Core game completion logic shared by /complete and /complete/freeplay.
    Free play sessions skip streak updates and leaderboard writes.

    puzzle_date formats accepted:
      "YYYY-MM-DD"          — daily puzzle (looked up in daily_puzzles table)
      "free:{start}:{end}"  — on-the-fly free-play puzzle (reconstructed from graph)
    """
    mode = req.mode or "classic"

    # ---- Resolve puzzle metadata ----
    if req.puzzle_date.startswith("free:"):
        parts = req.puzzle_date[5:].split(":", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid puzzle_date.")
        fp_start_id, fp_end_id = parts
        puzzle_date = date.today()

        # Reconstruct player names from the in-memory graph
        G = get_graph()
        sn = G.nodes.get(f"player:{fp_start_id}", {})
        en = G.nodes.get(f"player:{fp_end_id}", {})
        start_name = sn.get("name") or (req.path[0].name if req.path else fp_start_id)
        end_name = en.get("name", fp_end_id)

        # Recompute GOAT (fast BFS — same as at generation time)
        hops_fp = compute_optimal_hops_by_mode(fp_start_id, fp_end_id)
        mode_opt = hops_fp.get(mode) if hops_fp.get(mode) is not None else (hops_fp.get("classic") or 1)
        ch = hops_fp.get("classic", mode_opt)
        diff = "easy" if ch <= 1 else ("medium" if ch <= 2 else "hard")

        puzzle = {
            "start_player": {"id": fp_start_id, "full_name": start_name},
            "end_player":   {"id": fp_end_id,   "full_name": end_name},
            "difficulty":   diff,
            "optimal_hops": mode_opt,
            "optimal_hops_by_mode": hops_fp,
        }
    else:
        try:
            puzzle_date = date.fromisoformat(req.puzzle_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid puzzle_date format.")
        puzzle = await get_puzzle_for_date(db, puzzle_date)

    edge_types = [n.edgeType for n in req.path if n.edgeType]
    mode_optimal_hops = (puzzle.get("optimal_hops_by_mode") or {}).get(mode) or puzzle["optimal_hops"]
    score = 0 if req.gave_up else calculate_score(
        hops_used=req.hops_used,
        optimal_hops=mode_optimal_hops,
        time_seconds=req.time_seconds,
        difficulty=puzzle["difficulty"],
        edge_types=edge_types,
    )

    current_streak = 0

    if not is_freeplay:
        # Upsert session — keyed by (puzzle_date, client_id, mode)
        existing = await db.execute(
            select(GameSession).where(
                GameSession.puzzle_date == puzzle_date,
                GameSession.client_id == req.client_id,
                GameSession.mode == mode,
            )
        )
        existing_session = existing.scalar_one_or_none()

        if not existing_session:
            db.add(GameSession(
                puzzle_date=puzzle_date,
                client_id=req.client_id,
                mode=mode,
                is_freeplay=False,
                path_taken=[n.model_dump() for n in req.path],
                hops_used=req.hops_used,
                time_seconds=req.time_seconds,
                score=score,
                completed=not req.gave_up,
                gave_up=req.gave_up,
                completed_at=datetime.now(tz=timezone.utc),
            ))

        # Update streak
        streak_result = await db.execute(
            select(Streak).where(Streak.client_id == req.client_id)
        )
        streak_row = streak_result.scalar_one_or_none()

        if streak_row is None:
            streak_row = Streak(client_id=req.client_id)
            db.add(streak_row)

        current_streak = streak_row.current_streak
        won = not req.gave_up

        if won:
            yesterday = date.fromordinal(puzzle_date.toordinal() - 1)
            if streak_row.last_played == yesterday or streak_row.last_played is None:
                current_streak += 1
            elif streak_row.last_played == puzzle_date:
                pass  # already counted today
            else:
                current_streak = 1

            streak_row.current_streak = current_streak
            streak_row.max_streak = max(streak_row.max_streak, current_streak)
            streak_row.total_won = (streak_row.total_won or 0) + 1
        else:
            current_streak = 0
            streak_row.current_streak = 0

        streak_row.total_played = (streak_row.total_played or 0) + 1
        streak_row.last_played = puzzle_date
        streak_row.score_total = (streak_row.score_total or 0) + score

        await db.flush()

        # Only real (non-freeplay) scores go to the leaderboard
        if score > 0:
            await leaderboard_add(req.client_id, score)

    share_text = generate_share_text(
        puzzle_date=req.puzzle_date,
        start_name=puzzle["start_player"]["full_name"],
        end_name=puzzle["end_player"]["full_name"],
        hops_used=req.hops_used,
        optimal_hops=mode_optimal_hops,
        streak=current_streak,
        edge_types=edge_types,
        gave_up=req.gave_up,
        mode=mode,
        is_freeplay=is_freeplay,
    )

    # Compute optimal path for post-game reveal (respects the active mode's subgraph)
    try:
        optimal_path = find_shortest_path_with_labels_for_mode(
            puzzle["start_player"]["id"], "player",
            puzzle["end_player"]["id"], "player",
            mode,
        )
    except Exception:
        optimal_path = None

    result = {"score": score, "share_text": share_text, "optimal_path": optimal_path}
    if not is_freeplay:
        result["streak"] = current_streak
    return result


# ------------------------------------
# Endpoints
# ------------------------------------

@router.post("/complete")
async def complete_game(req: GameCompleteRequest, db: AsyncSession = Depends(get_db)):
    """
    Record a completed game session.
    Updates streak, records score, returns share text.
    A client can complete the same puzzle in multiple modes.
    """
    return await _record_completion(req, db, is_freeplay=False)


@router.post("/complete/freeplay")
async def complete_freeplay_game(req: GameCompleteRequest, db: AsyncSession = Depends(get_db)):
    """
    Record a completed free-play game session.
    Does NOT update streak or contribute to leaderboard.
    Returns score and share text only.
    """
    return await _record_completion(req, db, is_freeplay=True)


@router.get("/stats/{client_id}")
async def get_stats(client_id: str, db: AsyncSession = Depends(get_db)):
    """Get user stats by client_id."""
    result = await db.execute(
        select(Streak).where(Streak.client_id == client_id)
    )
    streak = result.scalar_one_or_none()

    if streak is None:
        return {
            "streak": 0,
            "max_streak": 0,
            "total_played": 0,
            "win_pct": 0.0,
            "avg_score": 0,
            "avg_hops": 0.0,
        }

    total_played = streak.total_played or 0
    total_won = streak.total_won or 0

    return {
        "streak": streak.current_streak,
        "max_streak": streak.max_streak,
        "total_played": total_played,
        "win_pct": round(total_won / total_played, 3) if total_played > 0 else 0.0,
        "avg_score": round(streak.score_total / total_played) if total_played > 0 else 0,
        "avg_hops": 0.0,
        "last_played": streak.last_played.isoformat() if streak.last_played else None,
    }
