// ============================================================
// HOOPCHAIN — Typed API Client
// ============================================================

import axios, { type AxiosInstance, AxiosError } from 'axios';
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
} from '../types';

// ------------------------------------
// Config
// ------------------------------------

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ------------------------------------
// Error handling
// ------------------------------------

export interface ApiError {
  message: string;
  status?: number;
}

function handleError(err: unknown): never {
  if (err instanceof AxiosError) {
    const message =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred';
    throw { message, status: err.response?.status } as ApiError;
  }
  throw { message: 'An unexpected error occurred' } as ApiError;
}

// ------------------------------------
// Health
// ------------------------------------

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    try {
      const { data } = await http.get<HealthResponse>('/health');
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Puzzle
// ------------------------------------

export const puzzleApi = {
  getToday: async (): Promise<Puzzle> => {
    try {
      const { data } = await http.get<Puzzle>('/puzzle/today');
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  getByDate: async (date: string): Promise<Puzzle> => {
    try {
      const { data } = await http.get<Puzzle>(`/puzzle/${date}`);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  getRandom: async (mode?: GameMode, difficulty?: Difficulty, excludeIds?: number[]): Promise<Puzzle> => {
    try {
      const params: Record<string, string> = {};
      if (mode) params.mode = mode;
      if (difficulty) params.difficulty = difficulty;
      if (excludeIds && excludeIds.length > 0) params.exclude_ids = excludeIds.join(',');
      const { data } = await http.get<Puzzle>('/puzzle/random', { params });
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Search
// ------------------------------------

export const searchApi = {
  players: async (query: string, limit = 10): Promise<PlayerSearchResult[]> => {
    try {
      const { data } = await http.get<PlayerSearchResult[]>('/search/players', {
        params: { q: query, limit },
      });
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Validation
// ------------------------------------

export const validateApi = {
  hop: async (req: HopValidationRequest): Promise<HopValidationResponse> => {
    try {
      const { data } = await http.post<HopValidationResponse>('/validate/hop', req);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  path: async (req: PathValidationRequest): Promise<PathValidationResponse> => {
    try {
      const { data } = await http.post<PathValidationResponse>('/validate/path', req);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Game
// ------------------------------------

export const gameApi = {
  complete: async (req: GameCompleteRequest): Promise<GameCompleteResponse> => {
    try {
      const { data } = await http.post<GameCompleteResponse>('/game/complete', req);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  completeFreeplay: async (req: GameCompleteRequest): Promise<GameCompleteResponse> => {
    try {
      const { data } = await http.post<GameCompleteResponse>('/game/complete/freeplay', req);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  getStats: async (clientId: string): Promise<GameStats> => {
    try {
      const { data } = await http.get<GameStats>(`/game/stats/${clientId}`);
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Leaderboard
// ------------------------------------

export const leaderboardApi = {
  getToday: async (): Promise<LeaderboardEntry[]> => {
    try {
      const { data } = await http.get<LeaderboardEntry[]>('/leaderboard/today');
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};

// ------------------------------------
// Email subscription
// ------------------------------------

export const subscribeApi = {
  subscribe: async (email: string): Promise<{ status: string }> => {
    try {
      const { data } = await http.post<{ status: string }>('/subscribe', { email });
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
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

export const adminApi = {
  getPuzzles: async (adminKey: string): Promise<AdminPuzzleRow[]> => {
    try {
      const { data } = await http.get<AdminPuzzleRow[]>('/admin/puzzles', {
        headers: { 'X-Admin-Key': adminKey },
      });
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  overridePuzzle: async (
    adminKey: string,
    puzzleDate: string,
    startPlayerId: string,
    endPlayerId: string,
  ): Promise<{ status: string; optimal_hops: number; difficulty: string }> => {
    try {
      const { data } = await http.post(
        '/admin/puzzle/override',
        { puzzle_date: puzzleDate, start_player_id: startPlayerId, end_player_id: endPlayerId },
        { headers: { 'X-Admin-Key': adminKey } },
      );
      return data;
    } catch (err) {
      return handleError(err);
    }
  },

  getSubscribers: async (adminKey: string, limit = 200): Promise<AdminSubscriberRow[]> => {
    try {
      const { data } = await http.get<AdminSubscriberRow[]>('/admin/subscribers', {
        headers: { 'X-Admin-Key': adminKey },
        params: { limit },
      });
      return data;
    } catch (err) {
      return handleError(err);
    }
  },
};
