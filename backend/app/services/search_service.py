"""
HOOPCHAIN — Search Service
Player autocomplete using Postgres full-text search.
Falls back to mock player list when database is unavailable.
"""

from __future__ import annotations

import logging
import unicodedata

from sqlalchemy import select, text, func, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Player
from ..services.graph_service import get_mock_players_for_search
from ..config import settings

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Strip accents from a string so 'Schröder' matches 'Schroder'."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").strip()


async def search_players(
    db: AsyncSession,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """
    Search players by name using PostgreSQL full-text search with trigram fallback.
    Both the query and indexed names are normalized (accents stripped) so that
    'Schroder' and 'Schröder' both find Dennis Schröder.
    Falls back to mock player list if DB has no data.
    """
    if settings.use_mock_graph:
        return get_mock_players_for_search(query, limit)

    # Normalize the query: strip accents so ö→o, é→e, etc.
    normalized_query = _normalize(query)
    search_term = normalized_query if normalized_query else query

    # PostgreSQL requires regconfig type for the language arg, not a bound varchar param.
    # literal_column emits the string as literal SQL so Postgres implicitly casts 'english'
    # to regconfig instead of seeing it as character varying (which has no matching overload).
    _ts_lang = literal_column("'english'")

    logger.warning(
        "SEARCH_DEBUG: query=%r normalized=%r use_mock=%s",
        query, search_term, settings.use_mock_graph,
    )

    try:
        # Full-text search using tsvector (built on normalized names in ETL)
        stmt = (
            select(Player)
            .where(
                Player.search_vector.op("@@")(
                    func.plainto_tsquery(_ts_lang, search_term)
                )
            )
            .order_by(
                func.ts_rank(Player.search_vector, func.plainto_tsquery(_ts_lang, search_term)).desc()
            )
            .limit(limit)
        )
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        logger.warning("SEARCH_DEBUG FTS sql=%s", str(compiled))
        result = await db.execute(stmt)
        players = result.scalars().all()
        logger.warning("SEARCH_DEBUG FTS hit count=%d", len(players))

        if not players:
            # Trigram fallback: match on both original and normalized name
            stmt = (
                select(Player)
                .where(
                    Player.full_name.ilike(f"%{search_term}%")
                    | Player.full_name.ilike(f"%{query}%")
                )
                .order_by(Player.is_active.desc(), Player.full_name)
                .limit(limit)
            )
            compiled = stmt.compile(compile_kwargs={"literal_binds": True})
            logger.warning("SEARCH_DEBUG ILIKE sql=%s", str(compiled))
            result = await db.execute(stmt)
            players = result.scalars().all()
            logger.warning("SEARCH_DEBUG ILIKE hit count=%d", len(players))

        return [_player_to_dict(p) for p in players]

    except Exception as e:
        logger.warning("SEARCH_DEBUG exception type=%s msg=%s", type(e).__name__, e, exc_info=True)
        return get_mock_players_for_search(query, limit)


def _player_to_dict(player: Player) -> dict:
    return {
        "id": player.id,
        "full_name": player.full_name,
        "position": player.position,
        "team_name": None,  # Would join with player_seasons in a full impl
        "headshot_url": player.headshot(),
        "seasons_active": None,
        "is_active": player.is_active,
    }

