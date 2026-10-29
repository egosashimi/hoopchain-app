"""HOOPCHAIN — Health Router"""

from fastapi import APIRouter
from ..services.graph_service import graph_stats

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    stats = graph_stats()
    return {
        "status": "ok",
        "graph_nodes": stats["nodes"],
        "graph_edges": stats["edges"],
        "mock_mode": stats["mock_mode"],
    }
