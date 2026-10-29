// ============================================================
// HOOPCHAIN — In-browser connection graph
// Loads public/data/graph.json (built by data/etl/19_export_static_data.py)
// and answers the questions the backend used to: hop validation, BFS
// shortest paths per mode, and player search.
// ============================================================

import type { EdgeType, GameMode, NodeType, OptimalPathNode, PlayerSearchResult } from '../types';

type NodeRow = [id: string, name: string, type: 'p' | 'c', active: 0 | 1, first: number, last: number, score: number];
type GroupRow = [type: 't' | 'd' | 'c' | 'a', label: string, members: number[]];
type CoachGroupRow = [label: string, coach: number, players: number[]];

export interface GraphData {
  version: number;
  stats: { nodes: number; edges: number };
  nodes: NodeRow[];
  groups: GroupRow[];
  coach_groups: CoachGroupRow[];
  pools: Record<string, number[]>;
}

export interface GraphNode {
  id: string;
  type: NodeType;
  name: string;
  isActive: boolean;
  firstSeason: number;
  lastSeason: number;
  score: number;
}

interface Group {
  type: EdgeType;
  label: string;
  members: Set<number>;
  coach?: number;   // coached_by groups connect the coach to each player, not players to each other
}

export interface Connection {
  type: EdgeType;
  label: string;
}

const TYPE_BY_CODE: Record<GroupRow[0], EdgeType> = {
  t: 'teammate',
  d: 'draft_class',
  c: 'college',
  a: 'all_star',
};

// Edge weights from the original graph (teammate varies by tenure; 0.9 is the common case)
export const EDGE_WEIGHT: Record<EdgeType, number> = {
  teammate: 0.9,
  draft_class: 1.4,
  college: 1.2,
  coached_by: 0.7,
  all_star: 1.5,
};

// When a pair shares several connections, the one shown follows this order
const EDGE_PRIORITY: EdgeType[] = ['teammate', 'coached_by', 'all_star', 'college', 'draft_class'];

// Mirrors backend MODE_TO_EDGE_TYPE: classic = teammates only | wild = all | coach = coached_by only
export const MODE_TO_EDGE_TYPE: Record<GameMode, EdgeType | null> = {
  classic: 'teammate',
  wild: null,
  coach: 'coached_by',
};

export function headshotUrl(playerId: string): string {
  return `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`;
}

function normalizeName(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/['’.]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export class HoopGraph {
  readonly nodes: GraphNode[];
  readonly stats: { nodes: number; edges: number };
  readonly pools: Record<string, number[]>;
  private readonly groups: Group[];
  private readonly groupsOf: number[][];
  private readonly byKey = new Map<string, number>();
  private readonly searchNames: string[];

  constructor(data: GraphData) {
    this.stats = data.stats;
    this.pools = data.pools;
    this.nodes = data.nodes.map(([id, name, type, active, first, last, score], i) => {
      const nodeType: NodeType = type === 'c' ? 'coach' : 'player';
      this.byKey.set(`${nodeType}:${id}`, i);
      return { id, type: nodeType, name, isActive: active === 1, firstSeason: first, lastSeason: last, score };
    });
    this.searchNames = this.nodes.map((n) => normalizeName(n.name));

    this.groups = [
      ...data.groups.map(([code, label, members]): Group => ({
        type: TYPE_BY_CODE[code], label, members: new Set(members),
      })),
      ...data.coach_groups.map(([label, coach, players]): Group => ({
        type: 'coached_by', label, members: new Set(players), coach,
      })),
    ];
    this.groupsOf = this.nodes.map(() => []);
    this.groups.forEach((g, gi) => {
      for (const m of g.members) this.groupsOf[m].push(gi);
      if (g.coach !== undefined) this.groupsOf[g.coach].push(gi);
    });
  }

  indexOf(type: NodeType, id: string): number | undefined {
    return this.byKey.get(`${type}:${id}`);
  }

  private allows(mode: GameMode, type: EdgeType): boolean {
    const only = MODE_TO_EDGE_TYPE[mode];
    return only === null || only === type;
  }

  private *neighbors(i: number, mode: GameMode): Generator<number> {
    for (const gi of this.groupsOf[i]) {
      const g = this.groups[gi];
      if (!this.allows(mode, g.type)) continue;
      if (g.coach === undefined) {
        yield* g.members;
      } else if (g.coach === i) {
        yield* g.members;
      } else {
        yield g.coach;
      }
    }
  }

  /** The connection between two nodes allowed in `mode` (any type for wild), or null. */
  connection(a: number, b: number, mode: GameMode = 'wild'): Connection | null {
    let best: Group | null = null;
    for (const gi of this.groupsOf[a]) {
      const g = this.groups[gi];
      if (!this.allows(mode, g.type)) continue;
      const linked = g.coach === undefined
        ? g.members.has(b)
        : (g.coach === a && g.members.has(b)) || (g.coach === b && g.members.has(a));
      if (!linked || a === b) continue;
      if (!best || EDGE_PRIORITY.indexOf(g.type) < EDGE_PRIORITY.indexOf(best.type)) best = g;
    }
    return best ? { type: best.type, label: best.label } : null;
  }

  /** Unweighted BFS shortest path (node indices), or null if unreachable in `mode`. */
  shortestPath(a: number, b: number, mode: GameMode): number[] | null {
    if (a === b) return [a];
    const parent = new Int32Array(this.nodes.length).fill(-1);
    parent[a] = a;
    let frontier = [a];
    while (frontier.length > 0) {
      const next: number[] = [];
      for (const u of frontier) {
        for (const v of this.neighbors(u, mode)) {
          if (parent[v] !== -1) continue;
          parent[v] = u;
          if (v === b) {
            const path = [b];
            for (let x = b; x !== a; x = parent[x]) path.push(parent[x]);
            return path.reverse();
          }
          next.push(v);
        }
      }
      frontier = next;
    }
    return null;
  }

  /** Dribbles (intermediate players) per mode, for modes with a path. */
  optimalHopsByMode(a: number, b: number, modes: GameMode[]): Partial<Record<GameMode, number>> {
    const out: Partial<Record<GameMode, number>> = {};
    for (const mode of modes) {
      const path = this.shortestPath(a, b, mode);
      if (path) out[mode] = path.length - 2;
    }
    return out;
  }

  labeledPath(path: number[], mode: GameMode): OptimalPathNode[] {
    return path.map((i, k) => {
      const n = this.nodes[i];
      const entry: OptimalPathNode = {
        id: n.id,
        type: n.type,
        name: n.name,
        headshot_url: n.type === 'player' ? headshotUrl(n.id) : undefined,
      };
      if (k < path.length - 1) {
        const c = this.connection(i, path[k + 1], mode);
        if (c) {
          entry.edge_type = c.type;
          entry.connection_label = c.label;
        }
      }
      return entry;
    });
  }

  /** Accent-insensitive player autocomplete, best matches first. */
  searchPlayers(query: string, limit: number): PlayerSearchResult[] {
    const q = normalizeName(query);
    if (q.length < 2) return [];
    const tokens = q.split(' ');
    const matches: { i: number; tier: number }[] = [];
    this.nodes.forEach((n, i) => {
      if (n.type !== 'player') return;
      const name = this.searchNames[i];
      let tier = -1;
      if (name.startsWith(q)) tier = 0;
      else if (tokens.every((t) => name.split(' ').some((w) => w.startsWith(t)))) tier = 1;
      else if (name.includes(q) || name.replace(/ /g, '').includes(q.replace(/ /g, ''))) tier = 2;
      if (tier >= 0) matches.push({ i, tier });
    });
    matches.sort((x, y) =>
      x.tier - y.tier
      || this.nodes[y.i].score - this.nodes[x.i].score
      || this.nodes[x.i].name.localeCompare(this.nodes[y.i].name));
    return matches.slice(0, limit).map(({ i }) => {
      const n = this.nodes[i];
      return { id: n.id, full_name: n.name, headshot_url: headshotUrl(n.id), is_active: n.isActive };
    });
  }
}

let graphPromise: Promise<HoopGraph> | null = null;

export function loadGraph(): Promise<HoopGraph> {
  graphPromise ??= fetch(`${import.meta.env.BASE_URL}data/graph.json`)
    .then((r) => {
      if (!r.ok) throw new Error(`Couldn't load player data (HTTP ${r.status})`);
      return r.json() as Promise<GraphData>;
    })
    .then((data) => new HoopGraph(data))
    .catch((err) => {
      graphPromise = null; // allow a retry
      throw err;
    });
  return graphPromise;
}
