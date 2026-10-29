"""
HOOPCHAIN — Tests for scoring algorithm and share text
"""

import pytest
from app.services.score_service import calculate_score, generate_share_text


class TestScoringAlgorithm:
    def test_perfect_score_at_optimal(self):
        """Hitting optimal hops within 2 min should score near 1000."""
        score = calculate_score(
            hops_used=3,
            optimal_hops=3,
            time_seconds=60,
            difficulty="medium",
            edge_types=["teammate", "teammate", "teammate"],
        )
        assert score > 900, f"Expected score > 900, got {score}"

    def test_extra_hops_reduce_score(self):
        """Each extra hop over optimal reduces by 150."""
        base_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate"]
        )
        extra_hop_score = calculate_score(
            hops_used=4, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate"]
        )
        assert extra_hop_score < base_score
        assert abs(base_score - extra_hop_score - 150) <= 50  # roughly 150 diff

    def test_speed_bonus_for_fast_completion(self):
        """Finishing in < 2 min gives speed bonus."""
        fast_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=60,
            difficulty="medium", edge_types=["teammate"]
        )
        slow_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate"]
        )
        assert fast_score > slow_score

    def test_speed_penalty_for_slow(self):
        """Taking > 5 min gives -100 speed penalty."""
        normal_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate"]
        )
        slow_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=400,
            difficulty="medium", edge_types=["teammate"]
        )
        assert slow_score < normal_score

    def test_difficulty_multiplier_hard(self):
        """Hard difficulty gives 1.3x multiplier."""
        easy_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="easy", edge_types=["teammate"]
        )
        hard_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="hard", edge_types=["teammate"]
        )
        assert hard_score > easy_score

    def test_diversity_bonus_for_rare_edges(self):
        """Using college/draft/all_star edges gives +50 each."""
        base_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate", "teammate", "teammate"]
        )
        diverse_score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=200,
            difficulty="medium", edge_types=["teammate", "college", "draft_class"]
        )
        assert diverse_score > base_score
        # 2 rare edges = +100 * 1.0 multiplier
        assert diverse_score - base_score >= 80  # approximately 100

    def test_score_never_negative(self):
        """Score should always be >= 0, even with massive penalties."""
        score = calculate_score(
            hops_used=20, optimal_hops=2, time_seconds=600,
            difficulty="easy", edge_types=["teammate"]
        )
        assert score >= 0

    def test_score_returns_int(self):
        score = calculate_score(
            hops_used=3, optimal_hops=3, time_seconds=120,
            difficulty="medium", edge_types=["teammate"]
        )
        assert isinstance(score, int)


class TestShareText:
    def _make(self, **kwargs):
        defaults = dict(
            puzzle_date="2026-05-22",
            start_name="LeBron James",
            end_name="Kobe Bryant",
            hops_used=3,
            optimal_hops=3,
            streak=0,
            edge_types=["teammate"],
        )
        defaults.update(kwargs)
        return generate_share_text(**defaults)

    def test_share_text_contains_player_names(self):
        text = self._make(streak=12, edge_types=["teammate", "college", "teammate"])
        assert "LeBron James" in text
        assert "Kobe Bryant" in text

    def test_share_text_contains_hoopchain_and_url(self):
        text = self._make()
        assert "HOOPCHAIN" in text
        assert "hoopchain.app" in text

    def test_share_text_emoji_chain_squares(self):
        text = self._make(
            hops_used=3, optimal_hops=3, streak=0,
            edge_types=["teammate", "college", "all_star"],
        )
        assert "🟩" in text   # teammate
        assert "🟦" in text   # college
        assert "🟥" in text   # all_star
        assert "⬜" in text   # start/end nodes

    def test_share_text_emoji_chain_format(self):
        text = self._make(hops_used=2, optimal_hops=2, edge_types=["teammate", "teammate"])
        assert "⬜ → 🟩 → 🟩 → ⬜" in text

    def test_gave_up_shows_gave_up(self):
        text = self._make(gave_up=True, edge_types=["teammate"])
        assert "gave up" in text
        assert "❌" in text
        assert "⬜" not in text  # no emoji chain when gave up

    def test_streak_shown_when_gte_3(self):
        text = self._make(streak=7)
        assert "7" in text
        assert "🔥" in text

    def test_streak_hidden_when_lt_3(self):
        text = self._make(streak=2)
        assert "🔥" not in text

    def test_beat_goat_shows_lightning(self):
        text = self._make(hops_used=2, optimal_hops=3)
        assert "⚡" in text

    def test_matched_goat_shows_target(self):
        text = self._make(hops_used=3, optimal_hops=3)
        assert "🎯" in text

    def test_over_goat_no_achievement_emoji(self):
        text = self._make(hops_used=4, optimal_hops=3)
        assert "⚡" not in text
        assert "🎯" not in text

    def test_freeplay_shows_free_play_header(self):
        text = self._make(is_freeplay=True)
        assert "FREE PLAY" in text
        assert "2026" not in text

    def test_mode_label_classic(self):
        text = self._make(mode="classic")
        assert "CLASSIC MODE" in text

    def test_mode_label_coach(self):
        text = self._make(mode="coach")
        assert "COACH MODE" in text
