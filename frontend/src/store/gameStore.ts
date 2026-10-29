// ============================================================
// HOOPCHAIN — Game State (Zustand)
// ============================================================

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type {
  GameState,
  ChainNode,
  EdgeType,
  GameMode,
  Difficulty,
} from '../types';
import { validateApi, gameApi, puzzleApi } from '../api/client';
import { useUserStore } from './userStore';

// ------------------------------------
// Store type (state + actions)
// ------------------------------------

interface GameStore extends GameState {
  // Daily puzzle actions
  loadPuzzle: (date?: string) => Promise<void>;
  // Free play actions
  loadRandomPuzzle: (mode: GameMode, difficulty?: Difficulty) => Promise<void>;
  exitFreePlay: () => Promise<void>;
  // Mode actions
  setMode: (mode: GameMode) => void;
  // Game actions
  startGame: () => void;
  submitHop: (candidate: ChainNode) => Promise<void>;
  removeLastHop: () => void;
  giveUp: () => Promise<void>;
  reset: () => void;
  // UI toggles
  setShowHowToPlay: (show: boolean) => void;
  setShowStats: (show: boolean) => void;
  setShowResult: (show: boolean) => void;
  setShowFreePlay: (show: boolean) => void;
  dismissError: () => void;
  _completeGame: (gaveUp: boolean) => Promise<void>;
}

// ------------------------------------
// Initial state
// ------------------------------------

const initialState: GameState = {
  puzzle: null,
  status: 'idle',
  mode: 'classic',
  isFreePlay: false,

  chains: {},
  seenFreePlayPuzzleIds: [],

  selectedNode: null,

  lastHopValid: null,
  lastHopLabel: null,
  lastHopEdgeType: null,
  invalidAttempts: 0,
  errorMessage: null,
  startedAt: null,
  completedAt: null,

  score: null,
  shareText: null,
  optimalPath: null,

  isValidating: false,
  showResult: false,
  showHowToPlay: false,
  showStats: false,
  showFreePlay: false,
};

// ------------------------------------
// Store
// ------------------------------------

export const useGameStore = create<GameStore>()(
  immer((set, get) => ({
    ...initialState,

    // ---- Load today's (or a specific date's) daily puzzle ----
    loadPuzzle: async (date?: string) => {
      try {
        const puzzle = date
          ? await puzzleApi.getByDate(date)
          : await puzzleApi.getToday();

        set((state) => {
          state.puzzle = puzzle;
          state.status = 'idle';
          state.isFreePlay = false;
          state.mode = 'classic';

          const startNode: ChainNode = {
            id: puzzle.start_player.id,
            type: 'player',
            name: puzzle.start_player.full_name,
            headshotUrl: puzzle.start_player.headshot_url,
            teamName: puzzle.start_player.team_name,
          };
          // Pre-init every available mode with the start node
          const chains: Record<string, ChainNode[]> = {};
          for (const m of (puzzle.available_modes ?? ['classic'])) {
            chains[m] = [startNode];
          }
          state.chains = chains;
        });
      } catch (err) {
        console.error('Failed to load puzzle', err);
        set((state) => {
          state.errorMessage = 'Failed to load today\'s puzzle. Please refresh.';
        });
      }
    },

    // ---- Load a random puzzle for free play ----
    loadRandomPuzzle: async (mode: GameMode, difficulty?: Difficulty) => {
      try {
        const currentSeen = get().seenFreePlayPuzzleIds;
        const puzzle = await puzzleApi.getRandom(mode, difficulty, currentSeen.length > 0 ? currentSeen : undefined);

        set((state) => {
          state.puzzle = puzzle;
          state.status = 'idle';
          state.isFreePlay = true;
          state.mode = mode;

          const startNode: ChainNode = {
            id: puzzle.start_player.id,
            type: 'player',
            name: puzzle.start_player.full_name,
            headshotUrl: puzzle.start_player.headshot_url,
            teamName: puzzle.start_player.team_name,
          };
          // Fresh puzzle — init all available modes
          const chains: Record<string, ChainNode[]> = {};
          for (const m of (puzzle.available_modes ?? [mode])) {
            chains[m] = [startNode];
          }
          state.chains = chains;

          // Track this puzzle so it won't be served again this session
          if (!state.seenFreePlayPuzzleIds.includes(puzzle.puzzle_id)) {
            state.seenFreePlayPuzzleIds.push(puzzle.puzzle_id);
          }

          state.score = null;
          state.shareText = null;
          state.showResult = false;
          state.showFreePlay = false;
          state.errorMessage = null;
          state.invalidAttempts = 0;
          state.lastHopValid = null;
          state.lastHopLabel = null;
          state.lastHopEdgeType = null;
          state.startedAt = null;
          state.completedAt = null;
        });
      } catch (err) {
        console.error('Failed to load random puzzle', err);
        set((state) => {
          state.errorMessage = 'Failed to load a free play puzzle. Try again.';
        });
      }
    },

    // ---- Exit free play and return to today's daily puzzle ----
    exitFreePlay: async () => {
      await get().loadPuzzle();
    },

    // ---- Switch game mode — saves current chain, restores target mode's chain ----
    setMode: (mode: GameMode) => {
      if (get().mode === mode) return;

      set((s) => {
        // Ensure target mode has a chain (may not if puzzle was loaded before this mode was added)
        if (!s.chains[mode] && s.puzzle) {
          s.chains[mode] = [{
            id: s.puzzle.start_player.id,
            type: 'player',
            name: s.puzzle.start_player.full_name,
            headshotUrl: s.puzzle.start_player.headshot_url,
            teamName: s.puzzle.start_player.team_name,
          }];
        }

        s.mode = mode;

        // Derive status from the restored chain
        const restored = s.chains[mode] ?? [];
        const isComplete = s.puzzle && restored.length > 1 &&
          restored[restored.length - 1].id === s.puzzle.end_player.id;

        if (isComplete) {
          s.status = 'won';
          s.startedAt = null;
        } else if (restored.length > 1) {
          s.status = 'playing';
          s.startedAt = Date.now(); // timer restarts from switch point
        } else {
          s.status = 'idle';
          s.startedAt = null;
        }

        // Reset transient per-hop state
        s.lastHopValid = null;
        s.lastHopLabel = null;
        s.lastHopEdgeType = null;
        s.errorMessage = null;
        s.invalidAttempts = 0;
        s.completedAt = null;
        s.score = null;
        s.shareText = null;
        s.showResult = false;
      });
    },

    // ---- Start the timer ----
    startGame: () => {
      set((state) => {
        if (state.status === 'idle') {
          state.status = 'playing';
          state.startedAt = Date.now();
        }
      });
    },

    // ---- Submit a hop (validate + add to chain if valid) ----
    submitHop: async (candidate: ChainNode) => {
      const state = get();
      const puzzle = state.puzzle;
      if (!puzzle || state.status !== 'playing' || state.isValidating) return;

      const activeChain = state.chains[state.mode] ?? [];
      const fromNode = activeChain[activeChain.length - 1];

      set((s) => {
        s.isValidating = true;
        s.errorMessage = null;
        s.lastHopValid = null;
      });

      try {
        const result = await validateApi.hop({
          from_id: fromNode.id,
          from_type: fromNode.type,
          to_id: candidate.id,
          to_type: candidate.type,
          mode: get().mode,
        });

        if (result.valid) {
          const newNode: ChainNode = {
            ...candidate,
            connectionLabel: result.edge_label,
            edgeType: result.edge_type as EdgeType,
          };

          const isEndPlayer = candidate.id === puzzle.end_player.id;

          set((s) => {
            s.lastHopValid = true;
            s.lastHopLabel = result.edge_label ?? null;
            s.lastHopEdgeType = (result.edge_type as EdgeType) ?? null;

            const chain = s.chains[s.mode];
            const prevIdx = chain.length - 1;
            chain[prevIdx].connectionLabel = result.edge_label;
            chain[prevIdx].edgeType = result.edge_type as EdgeType;
            chain.push(newNode);

            // Keep isValidating=true so auto-complete check blocks further input
            s.isValidating = !isEndPlayer;
          });

          if (isEndPlayer) {
            await get()._completeGame(false);
          } else {
            // Auto-complete: if newNode is one hop from end in current mode, add end player silently
            const currentMode = get().mode;
            try {
              const autoResult = await validateApi.hop({
                from_id: newNode.id,
                from_type: newNode.type,
                to_id: puzzle.end_player.id,
                to_type: 'player',
                mode: currentMode,
              });
              set((s) => { s.isValidating = false; });
              if (autoResult.valid) {
                const endNode: ChainNode = {
                  id: puzzle.end_player.id,
                  type: 'player',
                  name: puzzle.end_player.full_name,
                  headshotUrl: puzzle.end_player.headshot_url,
                  teamName: puzzle.end_player.team_name,
                };
                set((s) => {
                  const chain = s.chains[currentMode];
                  const idx = chain.length - 1;
                  chain[idx].connectionLabel = autoResult.edge_label;
                  chain[idx].edgeType = autoResult.edge_type as EdgeType;
                  chain.push(endNode);
                });
                await get()._completeGame(false);
              }
            } catch {
              set((s) => { s.isValidating = false; });
            }
          }
        } else {
          const reason = result.reason;
          const modeMsg = reason === 'wrong_edge_type'
            ? `That connection doesn't match ${get().mode} mode`
            : `No valid connection found between ${fromNode.name} and ${candidate.name}`;

          set((s) => {
            s.lastHopValid = false;
            s.lastHopLabel = null;
            s.invalidAttempts += 1;
            s.errorMessage = modeMsg;
            s.isValidating = false;
          });
        }
      } catch (err) {
        set((s) => {
          s.lastHopValid = false;
          s.errorMessage = 'Failed to validate. Check your connection.';
          s.isValidating = false;
        });
      }
    },

    // ---- Remove the last hop (undo) ----
    removeLastHop: () => {
      set((state) => {
        const chain = state.chains[state.mode];
        if (!chain || chain.length <= 1) return;
        chain.pop();
        state.lastHopValid = null;
        state.lastHopLabel = null;
        state.errorMessage = null;
      });
    },

    // ---- Give up ----
    giveUp: async () => {
      const state = get();
      // Allow give-up from idle (cold start) and playing; block only when already finished.
      if (!state.puzzle || state.status === 'won' || state.status === 'given_up') return;

      const now = Date.now();
      set((s) => {
        s.status = 'given_up';
        s.completedAt = now;
        if (!s.startedAt) s.startedAt = now;
      });

      await get()._completeGame(true);
    },

    // ---- Internal: record game result ----
    // @ts-ignore — internal method
    _completeGame: async (gaveUp: boolean) => {
      const state = get();
      const puzzle = state.puzzle;
      if (!puzzle) return;

      const completedAt = Date.now();
      const startedAt = state.startedAt ?? completedAt;
      const timeSeconds = Math.floor((completedAt - startedAt) / 1000);
      const clientId = useUserStore.getState().clientId;
      const mode = state.mode;
      const isFreePlay = state.isFreePlay;

      set((s) => {
        s.status = gaveUp ? 'given_up' : 'won';
        s.completedAt = completedAt;
      });

      const currentChain = get().chains[get().mode] ?? [];

      try {
        const req = {
          puzzle_date: puzzle.puzzle_date,
          client_id: clientId,
          path: currentChain,
          hops_used: Math.max(0, currentChain.length - 2),
          time_seconds: timeSeconds,
          gave_up: gaveUp,
          mode,
        };

        console.log('[hoopchain] _completeGame: calling API', { isFreePlay, mode, hops: req.hops_used });
        const result = isFreePlay
          ? await gameApi.completeFreeplay(req)
          : await gameApi.complete(req);

        console.log('[hoopchain] _completeGame: API result', result);

        set((s) => {
          s.score = result.score;
          s.shareText = result.share_text;
          s.optimalPath = result.optimal_path ?? null;
          s.showResult = true;
        });

        if (!isFreePlay) {
          useUserStore.getState().updateAfterGame({
            won: !gaveUp,
            streak: result.streak ?? 0,
            score: result.score,
            hops: Math.max(0, currentChain.length - 2),
          });
        }
      } catch (err) {
        console.error('[hoopchain] _completeGame: API failed, using local fallback', err);
        const fallbackDribbles = Math.max(0, currentChain.length - 2);
        const fallbackShare = `HOOPCHAIN 🏀 ${puzzle.puzzle_date}\n${puzzle.start_player.full_name} → ${puzzle.end_player.full_name}\nCLASSIC MODE | ${fallbackDribbles} ${fallbackDribbles === 1 ? 'dribble' : 'dribbles'}\n\nhoopchain.app`;
        // Compute streak locally from userStore state instead of defaulting to 0
        const userState = useUserStore.getState();
        const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
        const localStreak = (!gaveUp && (userState.lastPlayed === yesterday || userState.lastPlayed === null))
          ? userState.streak + 1
          : (!gaveUp ? 1 : 0);
        set((s) => {
          s.score = 0;
          s.shareText = fallbackShare;
          s.optimalPath = null;
          s.showResult = true;
        });
        if (!isFreePlay) {
          useUserStore.getState().updateAfterGame({
            won: !gaveUp,
            streak: localStreak,
            score: 0,
            hops: currentChain.length - 1,
          });
        }
      }
    },

    // ---- Reset for a new puzzle ----
    reset: () => {
      set(initialState);
    },

    // ---- UI toggles ----
    setShowHowToPlay: (show: boolean) => {
      set((s) => { s.showHowToPlay = show; });
    },

    setShowStats: (show: boolean) => {
      set((s) => { s.showStats = show; });
    },

    setShowResult: (show: boolean) => {
      set((s) => { s.showResult = show; });
    },

    setShowFreePlay: (show: boolean) => {
      set((s) => { s.showFreePlay = show; });
    },

    dismissError: () => {
      set((s) => {
        s.errorMessage = null;
        s.lastHopValid = null;
      });
    },
  }))
);
