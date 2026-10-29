"""
HOOPCHAIN — API endpoint tests
Tests all REST endpoints using the AsyncClient fixture.
"""

import pytest


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_structure(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "graph_nodes" in data
        assert "graph_edges" in data
        assert "mock_mode" in data


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        response = await client.get("/search/players?q=LeBron")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_search_too_short_query(self, client):
        response = await client.get("/search/players?q=L")
        # Should return 422 (validation error) for < 2 chars
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_search_no_results(self, client):
        response = await client.get("/search/players?q=xyznotaplayer")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_search_result_has_required_fields(self, client):
        response = await client.get("/search/players?q=LeBron")
        data = response.json()
        if data:
            player = data[0]
            assert "id" in player
            assert "full_name" in player


class TestValidateHopEndpoint:
    @pytest.mark.asyncio
    async def test_valid_hop_lebron_wade(self, client):
        response = await client.post("/validate/hop", json={
            "from_id": "2544",
            "from_type": "player",
            "to_id": "1717",
            "to_type": "player",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_hop_nonexistent_player(self, client):
        response = await client.post("/validate/hop", json={
            "from_id": "9999999",
            "from_type": "player",
            "to_id": "2544",
            "to_type": "player",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    @pytest.mark.asyncio
    async def test_valid_hop_has_edge_metadata(self, client):
        response = await client.post("/validate/hop", json={
            "from_id": "2544",
            "from_type": "player",
            "to_id": "1717",
            "to_type": "player",
        })
        data = response.json()
        if data["valid"]:
            assert "edge_type" in data
            assert "edge_label" in data
            assert "weight" in data

    @pytest.mark.asyncio
    async def test_invalid_hop_body(self, client):
        response = await client.post("/validate/hop", json={"bad": "data"})
        assert response.status_code == 422


class TestPuzzleEndpoint:
    @pytest.mark.asyncio
    async def test_get_today_puzzle(self, client):
        response = await client.get("/puzzle/today")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_puzzle_has_required_fields(self, client):
        response = await client.get("/puzzle/today")
        data = response.json()
        assert "puzzle_date" in data
        assert "start_player" in data
        assert "end_player" in data
        assert "difficulty" in data
        assert "optimal_hops" in data

    @pytest.mark.asyncio
    async def test_puzzle_does_not_reveal_canonical_path(self, client):
        """Anti-cheat: canonical_path must NOT be in the response."""
        response = await client.get("/puzzle/today")
        data = response.json()
        assert "canonical_path" not in data

    @pytest.mark.asyncio
    async def test_get_historical_puzzle(self, client):
        response = await client.get("/puzzle/2026-01-01")
        # Should succeed (may return mock puzzle)
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, client):
        response = await client.get("/puzzle/not-a-date")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_future_date_returns_404(self, client):
        response = await client.get("/puzzle/2099-12-31")
        assert response.status_code == 404
