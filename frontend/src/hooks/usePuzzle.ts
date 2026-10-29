// ============================================================
// HOOPCHAIN — usePuzzle hook
// Loads today's puzzle on mount, exposes loading/error state
// ============================================================

import { useEffect, useState } from 'react';
import { useGameStore } from '../store/gameStore';

export function usePuzzle() {
  const loadPuzzle = useGameStore((s) => s.loadPuzzle);
  const puzzle = useGameStore((s) => s.puzzle);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    loadPuzzle()
      .catch((err) => setError(err?.message ?? 'Failed to load puzzle'))
      .finally(() => setLoading(false));
  }, [loadPuzzle]);

  return { puzzle, loading, error };
}
