// ============================================================
// HOOPCHAIN — User State (Zustand + localStorage persistence)
// Tracks streak, stats, anonymous client ID, and UI theme
// ============================================================

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { generateClientId } from '../types';

// ------------------------------------
// State shape
// ------------------------------------

interface UserStats {
  clientId: string;
  streak: number;
  maxStreak: number;
  totalPlayed: number;
  totalWon: number;
  scoreTotal: number;
  avgScore: number;
  avgHops: number;
  totalHops: number;
  lastPlayed: string | null;     // YYYY-MM-DD
  theme: 'dark' | 'light';
}

interface UserStore extends UserStats {
  updateAfterGame: (result: {
    won: boolean;
    streak: number;
    score: number;
    hops: number;
  }) => void;
  resetStats: () => void;
  setTheme: (theme: 'dark' | 'light') => void;
}

// ------------------------------------
// Initial state
// ------------------------------------

const initialStats: UserStats = {
  clientId: generateClientId(),
  streak: 0,
  maxStreak: 0,
  totalPlayed: 0,
  totalWon: 0,
  scoreTotal: 0,
  avgScore: 0,
  avgHops: 0,
  totalHops: 0,
  lastPlayed: null,
  theme: 'dark',
};

// ------------------------------------
// Store with localStorage persistence
// ------------------------------------

export const useUserStore = create<UserStore>()(
  persist(
    (set, get) => ({
      ...initialStats,

      updateAfterGame: ({ won, streak, score, hops }) => {
        const state = get();
        const today = new Date().toISOString().slice(0, 10);

        // Prevent double-counting if already played today
        if (state.lastPlayed === today) return;

        const newTotalPlayed = state.totalPlayed + 1;
        const newTotalWon = state.totalWon + (won ? 1 : 0);
        const newTotalHops = state.totalHops + hops;
        const newScoreTotal = state.scoreTotal + score;

        set({
          streak,
          maxStreak: Math.max(state.maxStreak, streak),
          totalPlayed: newTotalPlayed,
          totalWon: newTotalWon,
          scoreTotal: newScoreTotal,
          avgScore: Math.round(newScoreTotal / newTotalPlayed),
          avgHops: Math.round((newTotalHops / newTotalPlayed) * 10) / 10,
          totalHops: newTotalHops,
          lastPlayed: today,
        });
      },

      resetStats: () => {
        const { clientId, theme } = get();
        set({ ...initialStats, clientId, theme });
      },

      setTheme: (theme) => {
        localStorage.setItem('hoopchain_theme', theme);
        if (theme === 'light') {
          document.documentElement.classList.add('light');
        } else {
          document.documentElement.classList.remove('light');
        }
        set({ theme });
      },
    }),
    {
      name: 'hoopchain-user',
      onRehydrateStorage: () => (state) => {
        if (state && !state.clientId) {
          state.clientId = generateClientId();
        }
      },
    }
  )
);
