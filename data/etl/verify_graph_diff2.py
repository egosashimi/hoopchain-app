"""
Part 2: Deeper investigation of:
  - Ghost node 1631168 edges in PREV
  - Why college/draft_class dropped
  - The 5 name-at-wrong-ID players (Jordan Poole, Evan Mobley, Jalen Green, Ja Morant, Luka Doncic)
  - LeBron-Rondo edge status
  - Lillard-Giannis all_star loss
"""
import pickle
from collections import Counter, defaultdict
from pathlib import Path

PREV_PKL = Path(r"C:\Users\Admin\AppData\Local\Temp\graph_prev.pkl")
CURR_PKL = Path(__file__).parent.parent.parent / "backend" / "graph.pkl"

print("Loading graphs...")
with open(PREV_PKL, "rb") as f:
    G_prev = pickle.load(f)
with open(CURR_PKL, "rb") as f:
    G_curr = pickle.load(f)

# --- Ghost node 1631168 in PREV ---
ghost = "player:1631168"
print(f"\n=== Ghost node {ghost} in PREV graph ===")
if G_prev.has_node(ghost):
    edges = list(G_prev.edges(ghost, data=True))
    by_type = Counter(d.get("type", "?") for _, _, d in edges)
    print(f"  Total edges: {len(edges)}")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")
    # Show a few examples
    for u, v, d in sorted(edges, key=lambda x: x[2].get("type",""))[:10]:
        other = v if u == ghost else u
        name = G_prev.nodes.get(other, {}).get("name", other)
        print(f"    [{d.get('type')}] {name}  {d.get('label','')[:50]}")
    if len(edges) > 10:
        print(f"  ... {len(edges)-10} more edges")
else:
    print("  NOT in PREV graph!")

# --- Why did college drop by 712 and draft_class by 7709? ---
# Find pairs that were in PREV but not CURR for college and draft_class
def edge_set_by_type(G):
    by_type = defaultdict(set)
    for u, v, d in G.edges(data=True):
        etype = d.get("type", "unknown")
        a, b = min(u,v), max(u,v)
        by_type[etype].add((a, b))
    return by_type

print("\n=== College lost pairs — sample ===")
prev_by = edge_set_by_type(G_prev)
curr_by = edge_set_by_type(G_curr)
lost_college = prev_by.get("college", set()) - curr_by.get("college", set())
print(f"  Total lost college pairs: {len(lost_college)}")
# Check which nodes are involved
node_counts = Counter()
for a, b in lost_college:
    node_counts[a] += 1
    node_counts[b] += 1
print("  Top nodes by lost college edges:")
for node, cnt in node_counts.most_common(10):
    name = G_prev.nodes.get(node, {}).get("name", node)
    print(f"    {name} ({node}): {cnt} lost college edges")

# Sample 5 lost pairs
for a, b in sorted(lost_college)[:5]:
    a_name = G_prev.nodes.get(a, {}).get("name", a)
    b_name = G_prev.nodes.get(b, {}).get("name", b)
    d = G_prev[a][b]
    # Is either node present in CURR?
    a_in_curr = G_curr.has_node(a)
    b_in_curr = G_curr.has_node(b)
    print(f"    {a_name} vs {b_name}  label={d.get('label','')[:40]}  nodes_in_curr=({a_in_curr},{b_in_curr})")

print("\n=== Draft_class lost pairs — sample ===")
lost_dc = prev_by.get("draft_class", set()) - curr_by.get("draft_class", set())
print(f"  Total lost draft_class pairs: {len(lost_dc)}")
node_counts2 = Counter()
for a, b in lost_dc:
    node_counts2[a] += 1
    node_counts2[b] += 1
print("  Top nodes by lost draft_class edges:")
for node, cnt in node_counts2.most_common(15):
    name = G_prev.nodes.get(node, {}).get("name", node)
    in_curr = G_curr.has_node(node)
    print(f"    {name} ({node}): {cnt} lost dc edges  in_curr={in_curr}")
# Sample 5 lost pairs
for a, b in sorted(lost_dc)[:5]:
    a_name = G_prev.nodes.get(a, {}).get("name", a)
    b_name = G_prev.nodes.get(b, {}).get("name", b)
    d = G_prev[a][b]
    a_in_curr = G_curr.has_node(a)
    b_in_curr = G_curr.has_node(b)
    print(f"    {a_name} vs {b_name}  label={d.get('label','')[:40]}  nodes_in_curr=({a_in_curr},{b_in_curr})")

# --- 5 name-at-wrong-ID players ---
print("\n=== Name-at-wrong-ID players (ghost check) ===")
MISMATCHED = [
    ("1629630", "1629673", "Jordan Poole"),
    ("1630162", "1630596", "Evan Mobley"),
    ("1630163", "1630224", "Jalen Green"),
    ("1629027", "1629630", "Ja Morant"),
    ("1628973", "1629029", "Luka Doncic"),
]
for configured_id, actual_id, name in MISMATCHED:
    conf_node = f"player:{configured_id}"
    actual_node = f"player:{actual_id}"
    conf_in_curr = G_curr.has_node(conf_node)
    actual_in_curr = G_curr.has_node(actual_node)
    actual_name = G_curr.nodes.get(actual_node, {}).get("name", "?")
    conf_name = G_curr.nodes.get(conf_node, {}).get("name", "?")
    # Count edges for each
    conf_edges = len(list(G_curr.edges(conf_node))) if conf_in_curr else 0
    actual_edges = len(list(G_curr.edges(actual_node))) if actual_in_curr else 0
    print(f"\n  {name}:")
    print(f"    configured id {configured_id}: in_curr={conf_in_curr}, name={conf_name!r}, edges={conf_edges}")
    print(f"    actual id     {actual_id}: in_curr={actual_in_curr}, name={actual_name!r}, edges={actual_edges}")
    if conf_in_curr and actual_in_curr and conf_name != actual_name:
        print(f"    STATUS: Two different players at these IDs (no ghost — different players)")
    elif actual_in_curr and conf_in_curr and conf_name == actual_name:
        print(f"    STATUS: DUPLICATE — same name at two IDs!")
    elif actual_in_curr and not conf_in_curr:
        print(f"    STATUS: Player exists at actual_id only (configured_id is absent)")

# --- LeBron-Rondo ---
print("\n=== LeBron-Rondo teammate edge ===")
lebron = "player:2544"
rondo = "player:1497"
if G_curr.has_edge(lebron, rondo):
    d = G_curr[lebron][rondo]
    print(f"  PRESENT: type={d.get('type')} label={d.get('label','')[:60]}")
else:
    print("  MISSING in CURR!")
    if G_prev.has_edge(lebron, rondo):
        d = G_prev[lebron][rondo]
        print(f"  Was in PREV: type={d.get('type')} label={d.get('label','')[:60]}")
    else:
        print("  Was also missing in PREV")
    # Check player_id for Rondo
    for node, data in G_curr.nodes(data=True):
        if "rondo" in (data.get("name") or "").lower():
            edges = len(list(G_curr.edges(node)))
            print(f"  Rondo node found: {node}  name={data.get('name')}  edges={edges}")

# --- Lillard-Giannis all_star loss ---
print("\n=== Lillard-Giannis all_star edge ===")
lillard = "player:203081"
giannis = "player:203507"
# Also check by scanning for these names
for node, data in G_curr.nodes(data=True):
    if "lillard" in (data.get("name") or "").lower():
        lillard = node
    if "giannis" in (data.get("name") or "").lower() or "antetokounmpo" in (data.get("name") or "").lower():
        giannis = node

if G_curr.has_edge(lillard, giannis):
    d = G_curr[lillard][giannis]
    print(f"  PRESENT in CURR: type={d.get('type')} label={d.get('label','')[:60]}")
else:
    print(f"  MISSING in CURR (were: {lillard} vs {giannis})")
    if G_prev.has_edge(lillard, giannis):
        d = G_prev[lillard][giannis]
        print(f"  Was in PREV: type={d.get('type')} label={d.get('label','')[:60]}")

print("\nDone.")
