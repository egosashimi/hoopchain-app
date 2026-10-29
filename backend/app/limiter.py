"""Shared SlowAPI limiter instance for route-level rate limits."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
