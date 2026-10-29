// ============================================================
// HOOPCHAIN — useGame hook
// ============================================================

import { useGameStore } from '../store/gameStore';

export function useGame() {
  const puzzle         = useGameStore((s) => s.puzzle);
  const status         = useGameStore((s) => s.status);
  const mode           = useGameStore((s) => s.mode);
  const isFreePlay     = useGameStore((s) => s.isFreePlay);
  const chains         = useGameStore((s) => s.chains);
  const isValidating   = useGameStore((s) => s.isValidating);
  const lastHopValid   = useGameStore((s) => s.lastHopValid);
  const lastHopLabel   = useGameStore((s) => s.lastHopLabel);
  const lastHopEdgeType= useGameStore((s) => s.lastHopEdgeType);
  const invalidAttempts= useGameStore((s) => s.invalidAttempts);
  const errorMessage   = useGameStore((s) => s.errorMessage);
  const startedAt      = useGameStore((s) => s.startedAt);
  const completedAt    = useGameStore((s) => s.completedAt);
  const score          = useGameStore((s) => s.score);
  const shareText      = useGameStore((s) => s.shareText);
  const optimalPath    = useGameStore((s) => s.optimalPath);
  const showResult     = useGameStore((s) => s.showResult);
  const showHowToPlay  = useGameStore((s) => s.showHowToPlay);
  const showStats      = useGameStore((s) => s.showStats);
  const showFreePlay   = useGameStore((s) => s.showFreePlay);

  const loadPuzzle       = useGameStore((s) => s.loadPuzzle);
  const loadRandomPuzzle = useGameStore((s) => s.loadRandomPuzzle);
  const exitFreePlay     = useGameStore((s) => s.exitFreePlay);
  const setMode          = useGameStore((s) => s.setMode);
  const startGame        = useGameStore((s) => s.startGame);
  const submitHop        = useGameStore((s) => s.submitHop);
  const removeLastHop    = useGameStore((s) => s.removeLastHop);
  const giveUp           = useGameStore((s) => s.giveUp);
  const reset            = useGameStore((s) => s.reset);
  const setShowHowToPlay = useGameStore((s) => s.setShowHowToPlay);
  const setShowStats     = useGameStore((s) => s.setShowStats);
  const setShowResult    = useGameStore((s) => s.setShowResult);
  const setShowFreePlay  = useGameStore((s) => s.setShowFreePlay);
  const dismissError     = useGameStore((s) => s.dismissError);

  const chain       = chains[mode] ?? [];
  const currentNode = chain[chain.length - 1] ?? null;
  const hopsUsed    = Math.max(0, chain.length - 2);
  const isPlaying   = status === 'playing';
  const isFinished  = status === 'won' || status === 'given_up';
  const hasStarted  = status !== 'idle';

  return {
    // State
    puzzle, status, mode, isFreePlay, chains, chain, currentNode, hopsUsed,
    isValidating, lastHopValid, lastHopLabel, lastHopEdgeType,
    invalidAttempts, errorMessage,
    startedAt, completedAt, score, shareText, optimalPath,
    showResult, showHowToPlay, showStats, showFreePlay,
    // Derived
    isPlaying, isFinished, hasStarted,
    // Actions
    loadPuzzle, loadRandomPuzzle, exitFreePlay,
    setMode, startGame, submitHop, removeLastHop, giveUp, reset,
    setShowHowToPlay, setShowStats, setShowResult, setShowFreePlay, dismissError,
  };
}
