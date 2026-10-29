"""HOOPCHAIN — Leaderboard Router"""

import hashlib

from fastapi import APIRouter

from ..redis_client import leaderboard_get_top

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/today")
async def get_today_leaderboard():
    """
    Get today's top 10 scores.
    client_ids are SHA-256 hashed before returning (privacy).
    """
    entries = await leaderboard_get_top(10)

    result = []
    for rank, (client_id, score) in enumerate(entries, start=1):
        # Hash client_id for privacy
        hashed = hashlib.sha256(client_id.encode()).hexdigest()[:12]
        result.append({
            "rank": rank,
            "client_id_hash": hashed,
            "score": int(score),
        })

    return result
