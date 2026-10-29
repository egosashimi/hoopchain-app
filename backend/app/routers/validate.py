"""HOOPCHAIN — Validate Router"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.graph_service import validate_hop, find_shortest_path, MODE_TO_EDGE_TYPE, VALID_MODES
from ..redis_client import CacheKey, cache_get, cache_set
from ..services.puzzle_service import get_puzzle_for_date
from datetime import date

router = APIRouter(prefix="/validate", tags=["validate"])


class HopRequest(BaseModel):
    from_id: str
    from_type: Literal["player", "coach"]
    to_id: str
    to_type: Literal["player", "coach"]
    mode: str = "classic"


class PathRequest(BaseModel):
    puzzle_date: str
    path: list[dict]  # [{type: str, id: str}]
    mode: str = "classic"


def _apply_mode_filter(result: dict, mode: str) -> dict:
    """
    Given a raw valid-edge result, return {valid:false, reason:'wrong_edge_type'}
    if the edge type is not allowed in the requested mode.
    Uses MODE_TO_EDGE_TYPE as the single source of truth:
      classic → teammate only | wild → all | coach → coached_by only
    """
    if not result.get("valid"):
        return result
    allowed_type = MODE_TO_EDGE_TYPE.get(mode)
    if allowed_type is None:
        return result  # wild = all edge types allowed
    if result.get("edge_type") != allowed_type:
        return {"valid": False, "reason": "wrong_edge_type"}
    return result


async def _are_teammates_in_db(db: AsyncSession, player_a_id: str, player_b_id: str) -> bool:
    """
    Authoritative teammate check: do these two players share any (team_id, season)
    row in player_seasons? Used as fallback when the stored graph edge_type is not
    'teammate' but the players may still be valid Classic-mode hops (can happen when
    a non-teammate edge was inserted after the teammate edge during a graph build and
    overwrote it in the simple graph).
    """
    result = await db.execute(
        text(
            "SELECT 1 FROM player_seasons a "
            "JOIN player_seasons b ON a.team_id = b.team_id AND a.season = b.season "
            "WHERE a.player_id = :pid_a AND b.player_id = :pid_b "
            "LIMIT 1"
        ),
        {"pid_a": player_a_id, "pid_b": player_b_id},
    )
    return result.fetchone() is not None


@router.post("/hop")
async def validate_hop_endpoint(req: HopRequest, db: AsyncSession = Depends(get_db)):
    """
    Validate a single hop between two nodes.
    Returns {valid, edge_type, edge_label, weight} if connected,
    or {valid: false} / {valid: false, reason: 'wrong_edge_type'} otherwise.

    The Redis cache is mode-agnostic (stores raw edge data).
    Mode filtering is applied after cache lookup so the same cached
    edge data works for any mode.

    Classic mode: if the stored edge_type is not 'teammate', fall back to a
    player_seasons DB query (authoritative teammate check) so graph edge-overwrite
    bugs never cause false rejections.
    """
    mode = req.mode if req.mode in VALID_MODES else "classic"

    # Check cache (mode-agnostic raw edge data)
    cache_key = CacheKey.hop(
        f"{req.from_type}:{req.from_id}",
        f"{req.to_type}:{req.to_id}",
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        filtered = _apply_mode_filter(cached, mode)
        # Classic mode: if mode filter rejected due to wrong edge type, check DB
        if (
            not filtered.get("valid")
            and mode == "classic"
            and cached.get("valid")
            and req.from_type == "player"
            and req.to_type == "player"
        ):
            if await _are_teammates_in_db(db, req.from_id, req.to_id):
                corrected = {**cached, "edge_type": "teammate"}
                await cache_set(cache_key, corrected, ttl=86400 * 7)
                return corrected
        return filtered

    # Validate in graph
    result = validate_hop(req.from_id, req.from_type, req.to_id, req.to_type)

    if result:
        # Classic mode: if graph edge isn't teammate type, verify via DB
        if (
            mode == "classic"
            and result.get("edge_type") != "teammate"
            and req.from_type == "player"
            and req.to_type == "player"
        ):
            if await _are_teammates_in_db(db, req.from_id, req.to_id):
                result = {**result, "edge_type": "teammate"}
        # Cache the raw result (corrected if needed).
        # Invalid results are NOT cached: they could become valid after a graph update.
        await cache_set(cache_key, result, ttl=86400 * 7)
        return _apply_mode_filter(result, mode)

    return {"valid": False}


@router.post("/path")
async def validate_path_endpoint(req: PathRequest, db: AsyncSession = Depends(get_db)):
    """
    Validate a full submitted path against the puzzle's start/end nodes.
    Returns {valid, complete, hops, optimal_hops, edge_types}.
    """
    try:
        puzzle_date = date.fromisoformat(req.puzzle_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid puzzle_date format.")

    mode = req.mode if req.mode in VALID_MODES else "classic"

    puzzle = await get_puzzle_for_date(db, puzzle_date)

    path = req.path
    if not path or len(path) < 2:
        return {"valid": False, "complete": False, "hops": 0,
                "optimal_hops": puzzle["optimal_hops"], "edge_types": []}

    edge_types = []
    for i in range(len(path) - 1):
        a = path[i]
        b = path[i + 1]
        a_type = a.get("type", "player")
        b_type = b.get("type", "player")
        result = validate_hop(a["id"], a_type, b["id"], b_type)
        if not result:
            return {
                "valid": False,
                "complete": False,
                "hops": i,
                "optimal_hops": puzzle["optimal_hops"],
                "edge_types": edge_types,
                "invalid_at_index": i,
            }
        # Apply mode filter; for Classic, fall back to DB teammate check
        filtered = _apply_mode_filter(result, mode)
        if (
            not filtered.get("valid")
            and mode == "classic"
            and a_type == "player"
            and b_type == "player"
        ):
            if await _are_teammates_in_db(db, a["id"], b["id"]):
                result = {**result, "edge_type": "teammate"}
                filtered = result
        if not filtered.get("valid"):
            return {
                "valid": False,
                "complete": False,
                "hops": i,
                "optimal_hops": puzzle["optimal_hops"],
                "edge_types": edge_types,
                "invalid_at_index": i,
                "reason": filtered.get("reason"),
            }
        edge_types.append(result.get("edge_type", "unknown"))

    path_start_id = path[0]["id"]
    path_end_id = path[-1]["id"]
    puzzle_start_id = puzzle["start_player"]["id"]
    puzzle_end_id = puzzle["end_player"]["id"]

    valid = path_start_id == puzzle_start_id
    complete = valid and (path_end_id == puzzle_end_id)

    return {
        "valid": valid,
        "complete": complete,
        "hops": len(path) - 1,
        "optimal_hops": puzzle["optimal_hops"],
        "edge_types": edge_types,
    }
