"""
HOOPCHAIN — FastAPI Application Entry Point
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .limiter import limiter
from .services.graph_service import load_graph
from .redis_client import get_redis
from .routers import health, puzzle, search, validate, game, leaderboard, subscribe, admin

logging.basicConfig(
    level=logging.INFO if settings.is_production else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> None:
    """Run alembic upgrade head synchronously. Safe to call on every startup."""
    try:
        from alembic.config import Config
        from alembic import command
        ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        cfg = Config(os.path.abspath(ini_path))
        command.upgrade(cfg, "head")
        logger.info("Database migrations up to date")
    except Exception as e:
        logger.warning(f"Alembic migration warning (may be a false positive): {e}")


async def _populate_available_modes() -> None:
    """
    For any published daily puzzle with available_modes=NULL, compute and store the modes.
    Runs after the graph is loaded so compute_available_modes() is available.
    """
    from sqlalchemy import select
    from .models import DailyPuzzle
    from .database import AsyncSessionLocal
    from .services.graph_service import compute_available_modes

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DailyPuzzle).where(
                    DailyPuzzle.available_modes.is_(None),
                    DailyPuzzle.is_published == True,
                )
            )
            puzzles = result.scalars().all()

            if not puzzles:
                logger.info("available_modes: all puzzles already populated")
                return

            logger.info(f"Populating available_modes for {len(puzzles)} puzzles...")
            updated = 0
            for puzzle in puzzles:
                try:
                    modes = compute_available_modes(puzzle.start_player_id, puzzle.end_player_id)
                    puzzle.available_modes = modes if modes else ["classic"]
                    updated += 1
                except Exception as e:
                    logger.warning(f"Could not compute modes for puzzle {puzzle.id}: {e}")
                    puzzle.available_modes = ["classic"]

            await session.commit()
            logger.info(f"available_modes populated for {updated} puzzles")
    except Exception as e:
        logger.warning(f"available_modes population failed: {e}")

# ------------------------------------
# Lifespan: load graph at startup
# ------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations, load graph, populate available_modes, warm Redis cache."""
    logger.info("🏀 Hoopchain API starting up...")

    # Run DB migrations first (idempotent — safe on every deploy)
    await asyncio.get_event_loop().run_in_executor(None, _run_alembic_upgrade)

    G = load_graph()
    edge_count = G.number_of_edges()
    logger.info(
        f"Graph ready: {G.number_of_nodes()} nodes, {edge_count} edges "
        f"({'mock' if settings.use_mock_graph else 'real'} mode)"
    )
    # Flush stale hop-validation cache entries whenever the graph is updated.
    # hop keys use "path:*"; we compare the current edge count against the last
    # recorded count to detect graph changes and avoid flushing on routine restarts.
    try:
        redis = get_redis()
        stored = await redis.get("graph:edge_count")
        if stored is None or int(stored) != edge_count:
            keys = await redis.keys("path:*")
            if keys:
                await redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} stale hop cache entries (graph: {stored} → {edge_count} edges)")
            await redis.set("graph:edge_count", str(edge_count))
    except Exception as e:
        logger.warning(f"Could not refresh hop cache on startup: {e}")

    # Populate available_modes for any puzzles that are missing it
    if not settings.use_mock_graph:
        await _populate_available_modes()

    yield
    logger.info("Hoopchain API shutting down.")


# ------------------------------------
# FastAPI app
# ------------------------------------

app = FastAPI(
    title="Hoopchain API",
    description="Backend for the Hoopchain daily NBA connection game",
    version=settings.app_version,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://([a-zA-Z0-9-]+\.vercel\.app|egosashimi\.github\.io)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ------------------------------------
# Include routers
# ------------------------------------

app.include_router(health.router)
app.include_router(puzzle.router)
app.include_router(search.router)
app.include_router(validate.router)
app.include_router(game.router)
app.include_router(leaderboard.router)
app.include_router(subscribe.router)
app.include_router(admin.router)

# ------------------------------------
# Root
# ------------------------------------


@app.get("/")
async def root():
    return {
        "name": "Hoopchain API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


# ------------------------------------
# Global error handler
# ------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
