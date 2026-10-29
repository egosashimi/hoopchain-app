"""
HOOPCHAIN — Score Service
Implements the scoring algorithm and share text generator.
Terminology: "dribbles" (not hops), "GOAT" for optimal count.
"""

from __future__ import annotations

MODE_LABEL: dict[str, str] = {
    "classic": "CLASSIC MODE",
    "wild":    "WILD MODE",
    "coach":   "COACH MODE",
}


def calculate_score(
    hops_used: int,
    optimal_hops: int,
    time_seconds: int,
    difficulty: str,
    edge_types: list[str],
) -> int:
    """
    Scoring algorithm:
    Base: 1000 pts
    - Efficiency: lose 150 per dribble over GOAT
    - Speed: +bonus if under 2 min, -100 if over 5 min
    - Difficulty: 0.8x (easy) / 1.0x (medium) / 1.3x (hard)
    - Edge diversity: +50 per rare edge type used (college, draft_class, all_star)
    """
    base = 1000

    hop_delta = hops_used - optimal_hops
    efficiency = max(0, base - (hop_delta * 150))

    if time_seconds < 120:
        speed_bonus = int((120 - time_seconds) * 1.5)
    elif time_seconds > 300:
        speed_bonus = -100
    else:
        speed_bonus = 0

    diff_mult = {"easy": 0.8, "medium": 1.0, "hard": 1.3}.get(difficulty, 1.0)

    rare_edges = {"college", "draft_class", "all_star"}
    diversity_bonus = len(set(edge_types) & rare_edges) * 50

    return max(0, int((efficiency + speed_bonus + diversity_bonus) * diff_mult))


def generate_share_text(
    puzzle_date: str,
    start_name: str,
    end_name: str,
    hops_used: int,
    optimal_hops: int,
    streak: int,
    edge_types: list[str],
    gave_up: bool = False,
    mode: str = "classic",
    is_freeplay: bool = False,
) -> str:
    """
    Generate the shareable emoji string.

    Completed game example:
      HOOPCHAIN 🏀 Jun 2, 2026
      Tim Duncan → Joel Embiid
      CLASSIC MODE | 2 dribbles (GOAT: 3) ⚡
      🔥 12-day streak

      ⬜ → 🟩 → ⬜

      hoopchain.app

    Gave-up example:
      HOOPCHAIN 🏀 Jun 2, 2026
      Tim Duncan → Joel Embiid
      CLASSIC MODE | gave up ❌

      hoopchain.app
    """
    from datetime import datetime

    if is_freeplay:
        date_header = "FREE PLAY"
    else:
        try:
            dt = datetime.strptime(puzzle_date, "%Y-%m-%d")
            date_header = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
        except Exception:
            date_header = puzzle_date

    mode_label = MODE_LABEL.get(mode, mode.upper() + " MODE")

    if gave_up:
        result_line = f"{mode_label} | gave up ❌"
    else:
        achievement = " 🎯" if hops_used == optimal_hops else ""
        dribble_word = "dribble" if hops_used == 1 else "dribbles"
        result_line = f"{mode_label} | {hops_used} {dribble_word} (GOAT: {optimal_hops}){achievement}"

    streak_line = f"🔥 {streak}-day streak" if streak >= 3 else None

    lines = [
        f"HOOPCHAIN 🏀 {date_header}",
        f"{start_name} → {end_name}",
        result_line,
    ]
    if streak_line:
        lines.append(streak_line)
    lines.append("")
    lines.append("hoopchain.app")

    return "\n".join(lines)
