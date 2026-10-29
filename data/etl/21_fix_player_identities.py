"""
HOOPCHAIN ETL — Step 21: Correct mislabeled player nodes in graph.pkl
=====================================================================
The modern-season top-up gave four 2023/2024 draftees the names of other
players. Each node's teams prove who it really is, and Wikidata's NBA.com ID
(P3647) agrees; the correctly named players already exist under their own IDs,
so the game showed two Ausar Thompsons, two Jarace Walkers, two Amen
Thompsons and a Cooper Flagg on the 2024-25 Pacers.

  ID       was labeled      actually          evidence (graph teams)
  1642277  Cooper Flagg     Johnny Furphy     2024-25 Pacers   (real Flagg: 1642843, Mavericks)
  1641712  Ausar Thompson   Rayan Rupert      2023-25 Blazers  (real Ausar: 1641709)
  1641710  Jarace Walker    Anthony Black     2023-25 Magic    (real Jarace: 1641716)
  1641711  Amen Thompson    Gradey Dick       2023-25 Raptors  (real Amen: 1641708)

Found by 20_fetch_recent_rosters.py's ID/name check. Idempotent; refuses to
touch a node whose current name is neither the old nor the corrected one.
The dormant backend's Postgres `players` table carries the same wrong names.

Usage:
    python data/etl/21_fix_player_identities.py
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

GRAPH_PKL = Path(__file__).resolve().parents[2] / "backend" / "graph.pkl"

CORRECTIONS = {
    # id: (wrong name, correct name)
    "1642277": ("Cooper Flagg", "Johnny Furphy"),
    "1641712": ("Ausar Thompson", "Rayan Rupert"),
    "1641710": ("Jarace Walker", "Anthony Black"),
    "1641711": ("Amen Thompson", "Gradey Dick"),
}


def main() -> None:
    G = pickle.load(open(GRAPH_PKL, "rb"))
    changed = 0
    for pid, (wrong, right) in CORRECTIONS.items():
        node = G.nodes[f"player:{pid}"]
        if node["name"] == right:
            continue
        if node["name"] != wrong:
            sys.exit(f"player:{pid} is named {node['name']!r}, expected {wrong!r} — not touching it")
        node["name"] = right
        changed += 1
        print(f"player:{pid}: {wrong} → {right}")
    if changed:
        with open(GRAPH_PKL, "wb") as f:
            pickle.dump(G, f)
    print(f"{changed} node(s) corrected")


if __name__ == "__main__":
    main()
