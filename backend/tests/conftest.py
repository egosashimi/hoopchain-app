"""HOOPCHAIN — pytest configuration and fixtures"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.graph_service import load_graph


@pytest.fixture(scope="session", autouse=True)
def setup_graph():
    """Load the mock graph before any tests run."""
    load_graph()


@pytest.fixture
async def client():
    """Async test client for FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
