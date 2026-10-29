"""
Part 3: Targeted checks
  - LeBron-Rondo edge (using Rondo's real ID 200765)
  - Lillard-Giannis: find their real node IDs
  - Edge-overwrite: confirm college/draft_class pairs now show as teammates
  - ID-scrambled players: check Postgres for wrong season rows
"""
import os, pickle
from pathlib import Path
import psycopg2, psycopg2.extras

CURR_PKL = Path(__file__).parent.parent.parent / "backend" / "graph.pkl"
print("Loading current graph...")
with open(CURR_PKL, "rb") as f:
    G = pickle.load(f)

# --- LeBron vs Rondo ---
print("\n=== LeBron-Rondo (real IDs) ===")
lebron = "player:2544"
rondo = "player:200765"
if G.has_edge(lebron, rondo):
    d = G[lebron][rondo]
    print(f"  PRESENT: type={d.get('type')}  label={d.get('label','')[:60]}")
else:
    print("  MISSING from graph!")

# --- Lillard and Giannis real node IDs ---
print("\n=== Lillard and Giannis nodes ===")
for node, data in G.nodes(data=True):
    name = (data.get("name") or "").strip()
    if name in ("Damian Lillard", "Giannis Antetokounmpo"):
        edges = list(G.edges(node, data=True))
        tm = [(u,v,d) for u,v,d in edges if d.get("type")=="teammate"]
        astar = [(u,v,d) for u,v,d in edges if d.get("type")=="all_star"]
        print(f"  {name} ({node}): {len(edges)} total edges, {len(tm)} teammate, {len(astar)} all_star")
# Check if they're connected
lillard_node = None; giannis_node = None
for node, data in G.nodes(data=True):
    if (data.get("name") or "").strip() == "Damian Lillard":
        lillard_node = node
    if (data.get("name") or "").strip() == "Giannis Antetokounmpo":
        giannis_node = node
if lillard_node and giannis_node:
    if G.has_edge(lillard_node, giannis_node):
        d = G[lillard_node][giannis_node]
        print(f"\n  Lillard-Giannis edge: type={d.get('type')}  label={d.get('label','')[:60]}")
    else:
        print(f"\n  NO EDGE between Lillard ({lillard_node}) and Giannis ({giannis_node})")

# --- Confirm edge-overwrite: sample a lost college pair ---
print("\n=== Edge-overwrite confirmation ===")
# Rondo lost 13 college edges. Check what edge Rondo now has to those players.
rondo_node = "player:200765"
# Get all current Rondo edges
rondo_edges = {v: d for u, v, d in G.edges(rondo_node, data=True)}
rondo_edges.update({u: d for u, v, d in G.edges(rondo_node, data=True) if u != rondo_node})
print(f"  Rondo current edges: {len(list(G.edges(rondo_node)))}")
# Check some known Kentucky teammates (Rondo went to Kentucky)
# Look for players with college=Kentucky in CURR
kentucky_players = []
for node, data in G.nodes(data=True):
    for nbr in G.neighbors(node):
        ed = G[node][nbr]
        if ed.get("type") == "college" and "Kentucky" in ed.get("label",""):
            kentucky_players.append((node, data.get("name"), nbr))
            break
print(f"  Players with a college=Kentucky edge in current graph: {len(kentucky_players)}")
# Is Rondo one of them?
rondo_has_kentucky = any(node == rondo_node for node, _, _ in kentucky_players)
print(f"  Rondo has a college-Kentucky edge in CURR: {rondo_has_kentucky}")
# What type does Rondo have to Malik Monk (player:1628370)?
monk = "player:1628370"
if G.has_edge(rondo_node, monk):
    d = G[rondo_node][monk]
    name = G.nodes.get(monk, {}).get("name", monk)
    print(f"  Rondo-Monk edge: type={d.get('type')}  label={d.get('label','')[:60]}")
    print(f"  (Monk is {name}, both Kentucky — should be college but may be overwritten by teammate)")
else:
    print(f"  No edge between Rondo and Monk (player:1628370)")

# --- Postgres: check for wrong season rows ---
print("\n=== Postgres: wrong season rows from ID-scramble ===")
RAW = os.getenv("DATABASE_URL")
if not RAW:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")
        RAW = os.getenv("DATABASE_URL")
    except ImportError:
        pass

if not RAW:
    print("  DATABASE_URL not set — skipping Postgres checks")
    print("  Set DATABASE_URL to the prod DB URL to run these checks")
else:
    PG = RAW.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = psycopg2.connect(PG)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check for wrong seasons: Ja Morant (1629630) should only have MEM seasons
        print("\n  Ja Morant (1629630) player_seasons:")
        cur.execute("""
            SELECT ps.player_id, p.full_name, t.abbreviation, ps.season
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE ps.player_id = '1629630'
            ORDER BY ps.season
        """)
        rows = cur.fetchall()
        for r in rows:
            flag = " ** WRONG **" if r["abbreviation"] not in ("MEM", None) else ""
            print(f"    {r['full_name']} ({r['player_id']}) on {r['abbreviation']} {r['season']}{flag}")

        # Check Trae Young (1629027) — should be ATL only
        print("\n  Trae Young (1629027) player_seasons:")
        cur.execute("""
            SELECT ps.player_id, p.full_name, t.abbreviation, ps.season
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE ps.player_id = '1629027'
            ORDER BY ps.season
        """)
        rows = cur.fetchall()
        for r in rows:
            flag = " ** WRONG **" if r["abbreviation"] not in ("ATL", None) else ""
            print(f"    {r['full_name']} ({r['player_id']}) on {r['abbreviation']} {r['season']}{flag}")

        # Check LaMelo Ball (1630163) — should be CHA only
        print("\n  LaMelo Ball (1630163) player_seasons:")
        cur.execute("""
            SELECT ps.player_id, p.full_name, t.abbreviation, ps.season
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE ps.player_id = '1630163'
            ORDER BY ps.season
        """)
        rows = cur.fetchall()
        for r in rows:
            flag = " ** WRONG **" if r["abbreviation"] not in ("CHA", None) else ""
            print(f"    {r['full_name']} ({r['player_id']}) on {r['abbreviation']} {r['season']}{flag}")

        # Check Anthony Edwards (1630162) — should be MIN
        print("\n  Anthony Edwards (1630162) player_seasons:")
        cur.execute("""
            SELECT ps.player_id, p.full_name, t.abbreviation, ps.season
            FROM player_seasons ps
            JOIN players p ON p.id = ps.player_id
            LEFT JOIN teams t ON t.id = ps.team_id
            WHERE ps.player_id = '1630162'
            ORDER BY ps.season
        """)
        rows = cur.fetchall()
        for r in rows:
            flag = " ** WRONG **" if r["abbreviation"] not in ("MIN", None) else ""
            print(f"    {r['full_name']} ({r['player_id']}) on {r['abbreviation']} {r['season']}{flag}")

        conn.close()
    except Exception as e:
        print(f"  DB error: {e}")

print("\nDone.")
