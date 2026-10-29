// ============================================================
// HOOPCHAIN — Typed API Client
// The game runs entirely in the browser (GitHub Pages, no backend):
// every call is answered by src/engine from the static data files.
// The interface matches the old FastAPI endpoints so callers are unchanged.
// ============================================================

import type {
  HealthResponse,
  Puzzle,
  PlayerSearchResult,
  HopValidationRequest,
  HopValidationResponse,
  PathValidationRequest,
  PathValidationResponse,
  GameCompleteRequest,
  GameCompleteResponse,
  GameStats,
  LeaderboardEntry,
  GameMode,
  Difficulty,
  EdgeType,
} from '../types';
import { EDGE_WEIGHT, MODE_TO_EDGE_TYPE, loadGraph } from '../engine/graph';
import {
  calculateScore,
  generateShareText,
  getDailyPuzzle,
  getFreePlayPuzzle,
  resolvePuzzle,
  shiftDate,
  todayDate,
} from '../engine/puzzles';
import { useUserStore } from '../store/userStore';

// ------------------------------------
// Error handling
// ------------------------------------

export interface ApiError {
  message: string;
  status?: number;
}

function apiError(message: string, status?: number): ApiError {
  return { message, status };
}

async function run<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (err && typeof err === 'object' && 'message' in err) throw apiError(String(err.message), (err as ApiError).status);
    throw apiError('An unexpected error occurred');
  }
}

const VALID_MODES: GameMode[] = ['classic', 'wild', 'coach'];

function normalizeMode(mode?: GameMode): GameMode {
  return mode && VALID_MODES.includes(mode) ? mode : 'classic';
}

// ------------------------------------
// Health
// ------------------------------------

export const healthApi = {
  check: (): Promise<HealthResponse> => run(async () => {
    const g = await loadGraph();
    return { status: 'ok', graph_nodes: g.stats.nodes, graph_edges: g.stats.edges, mock_mode: false };
  }),
};

// ------------------------------------
// Puzzle
// ------------------------------------

export const puzzleApi = {
  getToday: (): Promise<Puzzle> => run(() => getDailyPuzzle(todayDate())),

  getByDate: (date: string): Promise<Puzzle> => run(async () => {
    if (date > todayDate()) throw apiError('Puzzle not available yet.', 404);
    return getDailyPuzzle(date);
  }),

  getRandom: (mode?: GameMode, difficulty?: Difficulty, excludeIds?: number[]): Promise<Puzzle> => run(async () => {
    const puzzle = await getFreePlayPuzzle(normalizeMode(mode), difficulty, excludeIds);
    if (!puzzle) throw apiError('Could not generate a free-play puzzle. Try again.', 503);
    return puzzle;
  }),
};

// ------------------------------------
// Search
// ------------------------------------

export const searchApi = {
  players: (query: string, limit = 10): Promise<PlayerSearchResult[]> => run(async () => {
    const g = await loadGraph();
    return g.searchPlayers(query.trim(), Math.min(Math.max(limit, 1), 20));
  }),
};

// ------------------------------------
// Validation
// ------------------------------------

export const validateApi = {
  hop: (req: HopValidationRequest): Promise<HopValidationResponse> => run(async () => {
    const g = await loadGraph();
    const mode = normalizeMode(req.mode);
    const a = g.indexOf(req.from_type, req.from_id);
    const b = g.indexOf(req.to_type, req.to_id);
    if (a === undefined || b === undefined) return { valid: false };

    const c = g.connection(a, b, mode);
    if (c) return { valid: true, edge_type: c.type, edge_label: c.label, weight: EDGE_WEIGHT[c.type] };
    // Connected, just not by the edge type this mode allows
    if (MODE_TO_EDGE_TYPE[mode] !== null && g.connection(a, b, 'wild')) return { valid: false, reason: 'wrong_edge_type' };
    return { valid: false };
  }),

  path: (req: PathValidationRequest): Promise<PathValidationResponse> => run(async () => {
    const g = await loadGraph();
    const mode = normalizeMode(req.mode);
    const puzzle = await getDailyPuzzle(req.puzzle_date);
    const path = req.path;
    if (!path || path.length < 2) {
      return { valid: false, complete: false, hops: 0, optimal_hops: puzzle.optimal_hops, edge_types: [] };
    }

    const edgeTypes: EdgeType[] = [];
    for (let i = 0; i < path.length - 1; i++) {
      const hop = await validateApi.hop({
        from_id: path[i].id, from_type: path[i].type ?? 'player',
        to_id: path[i + 1].id, to_type: path[i + 1].type ?? 'player',
        mode,
      });
      if (!hop.valid || !hop.edge_type) {
        return {
          valid: false, complete: false, hops: i, optimal_hops: puzzle.optimal_hops, edge_types: edgeTypes,
          invalid_at_index: i, reason: hop.reason,
        } as PathValidationResponse;
      }
      edgeTypes.push(hop.edge_type);
    }

    const valid = path[0].id === puzzle.start_player.id && g.indexOf('player', path[0].id) !== undefined;
    return {
      valid,
      complete: valid && path[path.length - 1].id === puzzle.end_player.id,
      hops: path.length - 1,
      optimal_hops: puzzle.optimal_hops,
      edge_types: edgeTypes,
    };
  }),
};

// ------------------------------------
// Game
// ------------------------------------

/** Streak after this game, from the locally stored stats (the backend's Streak table rules). */
function nextStreak(puzzleDate: string, won: boolean): number {
  const { streak, lastPlayed } = useUserStore.getState();
  if (!won) return 0;
  if (lastPlayed === puzzleDate) return streak;           // already counted today
  if (lastPlayed === null || lastPlayed === shiftDate(puzzleDate, -1)) return streak + 1;
  return 1;
}

async function completeGame(req: GameCompleteRequest, isFreeplay: boolean): Promise<GameCompleteResponse> {
  const mode = normalizeMode(req.mode);
  const puzzle = await resolvePuzzle(req.puzzle_date, mode);
  const edgeTypes = req.path.map((n) => n.edgeType).filter((t): t is EdgeType => !!t);
  const optimalHops = puzzle.optimal_hops_by_mode?.[mode] ?? puzzle.optimal_hops;

  const score = req.gave_up
    ? 0
    : calculateScore(req.hops_used, optimalHops, req.time_seconds, puzzle.difficulty, edgeTypes);
  const streak = isFreeplay ? 0 : nextStreak(req.puzzle_date, !req.gave_up);

  const shareText = generateShareText({
    puzzleDate: req.puzzle_date,
    startName: puzzle.start_player.full_name,
    endName: puzzle.end_player.full_name,
    hopsUsed: req.hops_used,
    optimalHops,
    streak,
    gaveUp: req.gave_up,
    mode,
    isFreeplay,
  });

  // Optimal path for the post-game reveal, within the active mode's edge types
  const g = await loadGraph();
  const a = g.indexOf('player', puzzle.start_player.id);
  const b = g.indexOf('player', puzzle.end_player.id);
  const best = a !== undefined && b !== undefined ? g.shortestPath(a, b, mode) : null;

  const result: GameCompleteResponse = {
    score,
    share_text: shareText,
    optimal_path: best ? g.labeledPath(best, mode) : undefined,
  };
  if (!isFreeplay) result.streak = streak;
  return result;
}

export const gameApi = {
  complete: (req: GameCompleteRequest): Promise<GameCompleteResponse> => run(() => completeGame(req, false)),

  completeFreeplay: (req: GameCompleteRequest): Promise<GameCompleteResponse> => run(() => completeGame(req, true)),

  // Stats live in localStorage (userStore); the client ID is no longer needed
  getStats: async (): Promise<GameStats> => {
    const s = useUserStore.getState();
    return {
      streak: s.streak,
      max_streak: s.maxStreak,
      total_played: s.totalPlayed,
      win_pct: s.totalPlayed > 0 ? Math.round((s.totalWon / s.totalPlayed) * 1000) / 1000 : 0,
      avg_score: s.avgScore,
      avg_hops: s.avgHops,
      last_played: s.lastPlayed ?? undefined,
    };
  },
};

// ------------------------------------
// Server-only features — unavailable without the backend
// ------------------------------------

const NO_BACKEND = 'This needs the Hoopchain server, which the static site does not use.';

async function unavailable(): Promise<never> {
  throw apiError(NO_BACKEND, 503);
}

export const leaderboardApi = {
  available: false,
  getToday: async (): Promise<LeaderboardEntry[]> => [],
};

export const subscribeApi: {
  available: boolean;
  subscribe(email: string): Promise<{ status: string }>;
} = {
  available: false,
  subscribe: unavailable,
};

// ------------------------------------
// Admin
// ------------------------------------

export interface AdminPuzzleRow {
  id: number;
  puzzle_date: string;
  start_player_id: string;
  start_player_name: string;
  end_player_id: string;
  end_player_name: string;
  difficulty: string;
  optimal_hops: number;
  available_modes: string[];
  is_published: boolean;
}

export interface AdminSubscriberRow {
  id: number;
  email: string;
  created_at: string | null;
}

export const adminApi: {
  available: boolean;
  getPuzzles(adminKey: string): Promise<AdminPuzzleRow[]>;
  overridePuzzle(
    adminKey: string,
    puzzleDate: string,
    startPlayerId: string,
    endPlayerId: string,
  ): Promise<{ status: string; optimal_hops: number; difficulty: string }>;
  getSubscribers(adminKey: string, limit?: number): Promise<AdminSubscriberRow[]>;
} = {
  available: false,
  getPuzzles: unavailable,
  overridePuzzle: unavailable,
  getSubscribers: unavailable,
};
