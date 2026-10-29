"""HOOPCHAIN — Email Subscription Router"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..limiter import limiter
from ..models import EmailSubscriber

router = APIRouter(prefix="/subscribe", tags=["subscribe"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SubscribeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        if len(v) > 254:
            raise ValueError("Email too long")
        return v


@router.post("")
@limiter.limit("5/minute")
async def subscribe(request: Request, req: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    """Save an email address for launch notifications. Idempotent — re-subscribing is a no-op."""
    _ = request
    existing = await db.execute(
        select(EmailSubscriber).where(EmailSubscriber.email == req.email)
    )
    if existing.scalar_one_or_none():
        return {"status": "ok"}

    subscriber = EmailSubscriber(email=req.email)
    db.add(subscriber)
    try:
        await db.flush()
    except IntegrityError:
        # Race condition — another request inserted same email concurrently
        pass

    return {"status": "ok"}
