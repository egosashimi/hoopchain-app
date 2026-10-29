"""
HOOPCHAIN ETL — Utility: Rebuild graph.pkl from Postgres graph_edges table
===========================================================================
Faster than re-running 02_build_graph.py when the SQLite ETL is not needed.
Reads players, coaches, graph_edges from Postgres and serializes graph.pkl.

Usage:
    python data/etl/rebuild_graph_from_pg.py
"""
import logging
import os
import pickle
import shutil
from pathlib import Path

import networkx as nx
import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ETL_DIR = Path(__file__).parent
load_dotenv(ETL_DIR / ".env")
load_dotenv(ETL_DIR.parent.parent / "backend" / ".env")

RAW_URL = os.getenv("DATABASE_URL", "")
PG_URL = RAW_URL.replace("postgresql+asyncpg://", "postgresql://")
EXPORTS_GRAPH = ETL_DIR.parent / "exports" / "graph.pkl"
BACKEND_GRAPH = ETL_DIR.parent.parent / "backend" / "graph.pkl"


def main():
    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()

    G = nx.Graph()

    cur.execute("SELECT id, full_name, is_active FROM players")
    for pid, name, active in cur.fetchall():
        G.add_node(f"player:{pid}", type="player", name=name or str(pid), is_active=bool(active))
    log.info(f"Added {G.number_of_nodes()} player nodes")

    cur.execute("SELECT id, full_name FROM coaches")
    for cid, name in cur.fetchall():
        G.add_node(f"coach:{cid}", type="coach", name=name or str(cid))
    log.info(f"Added coaches, total nodes: {G.number_of_nodes()}")

    cur.execute("""
        SELECT node_a_type, node_a_id, node_b_type, node_b_id,
               edge_type, edge_label, weight
        FROM graph_edges
        ORDER BY CASE WHEN edge_type = 'teammate' THEN 1 ELSE 0 END
    """)
    edges_added = 0
    for at, ai, bt, bi, etype, elabel, weight in cur.fetchall():
        a, b = f"{at}:{ai}", f"{bt}:{bi}"
        if G.has_node(a) and G.has_node(b):
            G.add_edge(a, b, type=etype, label=elabel or "", weight=float(weight or 1.0))
            edges_added += 1
    log.info(f"Added {edges_added} edges from graph_edges table")
    log.info(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    conn.close()

    EXPORTS_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPORTS_GRAPH, "wb") as f:
        pickle.dump(G, f)
    shutil.copy2(EXPORTS_GRAPH, BACKEND_GRAPH)
    log.info(f"Saved to {EXPORTS_GRAPH} and {BACKEND_GRAPH}")


if __name__ == "__main__":
    main()
