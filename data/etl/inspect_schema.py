"""Deep inspect nba.sqlite schema"""
import sqlite3

conn = sqlite3.connect(r'C:/Users/Admin/Desktop/hoopchain/data/exports/nba.sqlite')
cur = conn.cursor()

# Check common_player_info all columns
cur.execute("PRAGMA table_info(common_player_info)")
cols = [(r[1], r[2]) for r in cur.fetchall()]
print("common_player_info columns:")
for c in cols:
    print(f"  {c}")

print()
# Sample a row
cur.execute("SELECT * FROM common_player_info LIMIT 2")
rows = cur.fetchall()
col_names = [d[0] for d in cur.description]
print("common_player_info sample row:")
for i, cn in enumerate(col_names):
    print(f"  {cn}: {rows[0][i] if rows else 'N/A'}")

print()
# Check game table - look for player info
cur.execute("PRAGMA table_info(game)")
gcols = [r[1] for r in cur.fetchall()]
print("game columns:", gcols)

print()
# game sample
cur.execute("SELECT * FROM game LIMIT 1")
grows = cur.fetchall()
grow_names = [d[0] for d in cur.description]
for i, cn in enumerate(grow_names):
    print(f"  game.{cn}: {grows[0][i] if grows else 'N/A'}")

print()
# line_score all cols
cur.execute("PRAGMA table_info(line_score)")
lscols = [(r[1]) for r in cur.fetchall()]
print("line_score all columns:", lscols)

print()
# draft_history sample
cur.execute("SELECT * FROM draft_history LIMIT 2")
dr = cur.fetchall()
dr_names = [d[0] for d in cur.description]
print("draft_history cols:", dr_names)
if dr:
    for i, cn in enumerate(dr_names):
        print(f"  {cn}: {dr[0][i]}")

conn.close()
