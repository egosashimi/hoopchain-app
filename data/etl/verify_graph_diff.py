"""
Verification script: compare previous vs current graph.pkl
Checks:
  1. Edge type breakdown (teammate / coached_by / all_star / college / draft_class)
  2. Pairs in prev but NOT in current (lost legitimate pairs)
  3. New pairs in current not in prev (legitimately added)
  4. Audit 2023-2025 patched players for ID-scramble issues
"""
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations

PREV_PKL = Path(r"C:\Users\Admin\AppData\Local\Temp\graph_prev.pkl")
CURR_PKL = Path(__file__).parent.parent.parent / "backend" / "graph.pkl"

print("Loading graphs...")
with open(PREV_PKL, "rb") as f:
    G_prev = pickle.load(f)
with open(CURR_PKL, "rb") as f:
    G_curr = pickle.load(f)

print(f"\nPREV: {G_prev.number_of_nodes()} nodes, {G_prev.number_of_edges()} edges")
print(f"CURR: {G_curr.number_of_nodes()} nodes, {G_curr.number_of_edges()} edges")

# ── 1. Edge type breakdown ──────────────────────────────────────────────────
def edge_type_counts(G):
    c = Counter()
    for _, _, d in G.edges(data=True):
        c[d.get("type", "unknown")] += 1
    return c

prev_counts = edge_type_counts(G_prev)
curr_counts = edge_type_counts(G_curr)

print("\n=== 1. Edge type breakdown ===")
print(f"{'type':<20} {'prev':>10} {'curr':>10} {'delta':>10}")
print("-" * 55)
all_types = sorted(set(list(prev_counts.keys()) + list(curr_counts.keys())))
for t in all_types:
    p = prev_counts.get(t, 0)
    c = curr_counts.get(t, 0)
    delta = c - p
    flag = "  ** CHANGED **" if delta != 0 else ""
    print(f"{t:<20} {p:>10,} {c:>10,} {delta:>+10,}{flag}")

# ── 2. Pairs lost (in prev but not in curr), by type ──────────────────────
print("\n=== 2. Pairs lost (prev → curr) ===")

def edge_set_by_type(G):
    by_type = defaultdict(set)
    for u, v, d in G.edges(data=True):
        etype = d.get("type", "unknown")
        a, b = sorted([u, v])
        by_type[etype].add((a, b))
    return by_type

prev_by_type = edge_set_by_type(G_prev)
curr_by_type = edge_set_by_type(G_curr)

for etype in sorted(set(list(prev_by_type.keys()) + list(curr_by_type.keys()))):
    prev_set = prev_by_type.get(etype, set())
    curr_set = curr_by_type.get(etype, set())
    lost = prev_set - curr_set
    gained = curr_set - prev_set
    print(f"\n  {etype}: lost={len(lost):,}  gained={len(gained):,}")
    if lost and etype in ("coached_by", "all_star", "teammate"):
        # Show first 20 lost pairs
        sample = sorted(lost)[:20]
        for a, b in sample:
            a_name = G_prev.nodes.get(a, {}).get("name", a)
            b_name = G_prev.nodes.get(b, {}).get("name", b)
            edge_data = G_prev[a][b]
            print(f"    LOST: {a_name} vs {b_name}  [{edge_data.get('label','?')[:60]}]")
        if len(lost) > 20:
            print(f"    ... and {len(lost)-20} more")

# ── 3. Specific sanity checks ──────────────────────────────────────────────
print("\n=== 3. Specific edge checks ===")
CHECKS = [
    ("player:2548", "player:2406", "Wade vs Caron Butler (2003-04 MIA)"),
    ("player:977",  "player:2430", "Kobe vs Boozer (2014-15 LAL)"),
    ("player:2544", "player:2430", "LeBron vs Boozer (2003-04 CLE)"),
    ("player:977",  "player:2397", "Kobe vs Yao Ming (should be NO teammate edge)"),
    ("player:2544", "player:1497", "LeBron vs Rondo (Lakers)"),
    ("player:708",  "player:1718", "KG vs Pierce (Celtics)"),
]
for a, b, label in CHECKS:
    prev_has = G_prev.has_edge(a, b)
    curr_has = G_curr.has_edge(a, b)
    curr_data = G_curr[a][b] if curr_has else {}
    change = "" if prev_has == curr_has else f"  ** CHANGED ** (was {prev_has})"
    print(f"  {'CURR' if curr_has else 'MISS'} | {label}{change}")
    if curr_has:
        print(f"         edge_type={curr_data.get('type')}  label={curr_data.get('label','')[:50]}")

# ── 4. 2023-2025 patched player ID audit ─────────────────────────────────
print("\n=== 4. 2023-2025 patched player ID audit ===")

PATCHED_PLAYERS = [
    # (nba_id, full_name, expected_team_abbr, seasons_list)
    ("1641705", "Victor Wembanyama",  "SAS", [2023, 2024]),
    ("1642277", "Cooper Flagg",       "BOS", [2024]),
    ("1641706", "Brandon Miller",     "CHA", [2023, 2024]),
    ("1629073", "Scoot Henderson",    "POR", [2023, 2024]),
    ("1641710", "Jarace Walker",      "IND", [2023, 2024]),
    ("1641712", "Ausar Thompson",     "DET", [2023, 2024]),
    ("1641711", "Amen Thompson",      "HOU", [2023, 2024]),
    ("1631094", "Paolo Banchero",     "ORL", [2022, 2023, 2024]),
    ("1631095", "Jabari Smith Jr.",   "HOU", [2022, 2023, 2024]),
    ("1631096", "Chet Holmgren",      "OKC", [2023, 2024]),
    ("1631097", "Bennedict Mathurin", "IND", [2022, 2023, 2024]),
    ("1631099", "Keegan Murray",      "SAC", [2022, 2023, 2024]),
    ("1629630", "Jordan Poole",       "WAS", [2022, 2023, 2024]),
    ("1630162", "Evan Mobley",        "CLE", [2021, 2022, 2023, 2024]),
    ("1630163", "Jalen Green",        "HOU", [2021, 2022, 2023, 2024]),
    ("1629027", "Ja Morant",          "MEM", [2019, 2020, 2021, 2022, 2023, 2024]),
    ("1628973", "Luka Doncic",        "DAL", [2018, 2019, 2020, 2021, 2022, 2023]),
]

print(f"  {'ID':<12} {'Name':<25} {'In graph':<10} {'Teammate count':<16} {'Notes'}")
print("  " + "-"*90)

# Build name→id map for collision detection
name_to_ids = defaultdict(list)
for node, data in G_curr.nodes(data=True):
    if data.get("type") == "player":
        name = (data.get("name") or "").strip().lower()
        nid = node.split(":", 1)[1]
        name_to_ids[name].append(nid)

for nba_id, full_name, team, seasons in PATCHED_PLAYERS:
    node_key = f"player:{nba_id}"
    in_graph = G_curr.has_node(node_key)

    # Teammate edges in current graph
    tm_edges = 0
    if in_graph:
        for nbr in G_curr.neighbors(node_key):
            if G_curr[node_key][nbr].get("type") == "teammate":
                tm_edges += 1

    # Duplicate name check
    name_lower = full_name.strip().lower()
    all_ids_for_name = name_to_ids.get(name_lower, [])
    dup_flag = ""
    if len(all_ids_for_name) > 1:
        dup_flag = f"  DUPLICATE IDs: {all_ids_for_name}"
    elif len(all_ids_for_name) == 1 and all_ids_for_name[0] != nba_id:
        dup_flag = f"  NAME AT WRONG ID: actual={all_ids_for_name[0]}, expected={nba_id}"

    # ID range check: 2022 class should be 163xxxx, 2023 class 164xxxx, 2024 class 164xxxx
    min_season = min(seasons)
    id_int = int(nba_id)
    id_flag = ""
    if min_season in (2022, 2023, 2024):
        if id_int < 1620000:
            id_flag = "  SUSPICIOUS: very low ID for modern player"

    notes = (dup_flag or id_flag or "OK")
    print(f"  {nba_id:<12} {full_name:<25} {'YES' if in_graph else 'NO!':<10} {tm_edges:<16} {notes}")

# Cross-check: any player with name matching a patched player but different ID?
print("\n  --- Duplicate node scan (any player node whose name matches a patched player) ---")
PATCHED_NAMES = {p[1].strip().lower() for p in PATCHED_PLAYERS}
found_any_dup = False
for node, data in G_curr.nodes(data=True):
    if data.get("type") != "player":
        continue
    name = (data.get("name") or "").strip().lower()
    nid = node.split(":", 1)[1]
    if name in PATCHED_NAMES:
        expected_id = next(p[0] for p in PATCHED_PLAYERS if p[1].strip().lower() == name)
        if nid != expected_id:
            print(f"  GHOST: {data.get('name')} at id={nid} (expected {expected_id})")
            found_any_dup = True
if not found_any_dup:
    print("  No ghost nodes found — all patched players are at their expected IDs only.")

# ── 5. Scoot Henderson ID sanity ───────────────────────────────────────────
print("\n=== 5. Scoot Henderson ID sanity ===")
# 1629073 is a 162xxxx range — typical for 2018-era players.
# Verify the graph has this node and that it has teammate edges consistent with POR 2023-24
scoot_node = "player:1629073"
if G_curr.has_node(scoot_node):
    nbrs = list(G_curr.neighbors(scoot_node))
    tm_nbrs = [(n, G_curr[scoot_node][n]) for n in nbrs if G_curr[scoot_node][n].get("type") == "teammate"]
    print(f"  Scoot Henderson (1629073) is in graph with {len(tm_nbrs)} teammate edges")
    for n, d in tm_nbrs[:10]:
        name = G_curr.nodes.get(n, {}).get("name", n)
        print(f"    -> {name}  [{d.get('label','')[:50]}]")
else:
    print("  Scoot Henderson (1629073) NOT in graph!")

print("\nDone.")
