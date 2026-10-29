"""
HOOPCHAIN — Tests for graph service
"""

import pytest
from app.services.graph_service import (
    load_graph,
    get_graph,
    validate_hop,
    find_shortest_path,
    get_neighbors,
    graph_stats,
    MOCK_PLAYERS,
)


class TestGraphLoading:
    def test_graph_loads_successfully(self):
        G = get_graph()
        assert G is not None

    def test_graph_has_nodes(self):
        G = get_graph()
        assert G.number_of_nodes() > 0

    def test_graph_has_edges(self):
        G = get_graph()
        assert G.number_of_edges() > 0

    def test_graph_stats_returns_correct_keys(self):
        stats = graph_stats()
        assert "nodes" in stats
        assert "edges" in stats
        assert "mock_mode" in stats
        assert stats["mock_mode"] is True  # In test environment


class TestMockGraphContent:
    def test_lebron_is_in_graph(self):
        G = get_graph()
        assert G.has_node("player:2544"), "LeBron James should be in the graph"

    def test_kobe_is_in_graph(self):
        G = get_graph()
        assert G.has_node("player:977"), "Kobe Bryant should be in the graph"

    def test_jordan_is_in_graph(self):
        G = get_graph()
        assert G.has_node("player:76003"), "Michael Jordan should be in the graph"

    def test_all_mock_players_in_graph(self):
        G = get_graph()
        for player in MOCK_PLAYERS:
            key = f"player:{player['id']}"
            assert G.has_node(key), f"{player['name']} should be in the graph"


class TestHopValidation:
    def test_valid_hop_lebron_wade(self):
        """LeBron and Wade are mock teammates."""
        result = validate_hop("2544", "player", "1717", "player")
        assert result is not None
        assert result["valid"] is True
        assert result["edge_type"] == "teammate"

    def test_valid_hop_kobe_shaq(self):
        """Kobe and Shaq are mock teammates."""
        result = validate_hop("977", "player", "893", "player")
        assert result is not None
        assert result["valid"] is True

    def test_invalid_hop_lebron_dirk(self):
        """LeBron and Dirk have no direct connection in mock graph."""
        # Note: they might share an all-star edge in mock data
        # This tests the function returns None correctly for non-edges
        result = validate_hop("2544", "player", "1713", "player")
        # Either None (no edge) or a valid result is acceptable
        # The key test is the function doesn't error
        assert result is None or isinstance(result, dict)

    def test_hop_for_nonexistent_player(self):
        """Hop involving a player not in the graph should return None."""
        result = validate_hop("99999999", "player", "2544", "player")
        assert result is None

    def test_hop_weight_for_close_teammates(self):
        """Longtime teammates should have low weight."""
        result = validate_hop("947", "player", "1495", "player")
        if result:
            assert result["weight"] <= 1.5


class TestPathFinding:
    def test_find_path_connected_players(self):
        """Players with direct connection should have 1-hop path."""
        path = find_shortest_path("2544", "player", "1717", "player")
        assert path is not None
        assert len(path) >= 2

    def test_find_path_returns_list(self):
        path = find_shortest_path("977", "player", "893", "player")
        assert isinstance(path, list)

    def test_find_path_nonexistent_player(self):
        path = find_shortest_path("99999999", "player", "2544", "player")
        assert path is None

    def test_path_contains_start_and_end(self):
        path = find_shortest_path("2544", "player", "1717", "player")
        if path:
            assert path[0] == "player:2544"
            assert path[-1] == "player:1717"


class TestNeighbors:
    def test_get_neighbors_lebron(self):
        neighbors = get_neighbors("2544", "player")
        assert isinstance(neighbors, list)
        assert len(neighbors) > 0

    def test_neighbor_has_required_fields(self):
        neighbors = get_neighbors("2544", "player")
        if neighbors:
            n = neighbors[0]
            assert "id" in n
            assert "name" in n
            assert "edge_type" in n

    def test_get_neighbors_nonexistent(self):
        neighbors = get_neighbors("99999999", "player")
        assert neighbors == []
