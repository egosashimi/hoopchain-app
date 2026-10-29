"""HOOPCHAIN — Search Router"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.search_service import search_players

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/players")
async def search_players_endpoint(
    q: str = Query(..., min_length=2, max_length=50, description="Player name query"),
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    Player autocomplete search.
    Returns up to `limit` matching players with headshot URLs.
    Backed by Postgres full-text search; falls back to mock list in demo mode.
    """
    if not q or len(q.strip()) < 2:
        return []

    results = await search_players(db, q.strip(), limit)
    return results
