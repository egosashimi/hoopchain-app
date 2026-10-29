// ============================================================
// HOOPCHAIN — App.tsx
// Root application component — 70s Topps aesthetic
// ============================================================

import { Suspense, lazy, useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Header } from './components/Header';
import { ChainBuilder } from './components/ChainBuilder';
import { DataInfo } from './components/DataInfo';
import { ModePills } from './components/ModePills';
import { AdminPage } from './pages/AdminPage';
import { usePuzzle } from './hooks/usePuzzle';
import { useGame } from './hooks/useGame';

const HowToPlay    = lazy(() => import('./components/HowToPlay').then(m => ({ default: m.HowToPlay })));
const StatsPanel   = lazy(() => import('./components/StatsPanel').then(m => ({ default: m.StatsPanel })));
const ResultModal  = lazy(() => import('./components/ResultModal').then(m => ({ default: m.ResultModal })));
const FreePlayModal= lazy(() => import('./components/FreePlayModal').then(m => ({ default: m.FreePlayModal })));

type Route = 'game' | 'data' | 'admin' | 'preview';

function useRoute(): { route: Route; previewDate?: string } {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (hash === '#/data') return { route: 'data' };
  if (hash === '#/admin') return { route: 'admin' };
  const previewMatch = hash.match(/^#\/preview\/(\d{4}-\d{2}-\d{2})$/);
  if (previewMatch) return { route: 'preview', previewDate: previewMatch[1] };
  return { route: 'game' };
}

// ------------------------------------
// Preview a specific puzzle by date (admin only)
// ------------------------------------
function PreviewPuzzle({ date }: { date: string }) {
  const { loadPuzzle } = useGame();
  useEffect(() => { loadPuzzle(date); }, [date, loadPuzzle]);
  return null; // renders the normal game UI via the store
}

// ------------------------------------
// Puzzle header (connect: A → B)
// ------------------------------------
function PuzzleHeader() {
  const { puzzle, mode } = useGame();
  if (!puzzle) return null;

  const diffColor = {
    easy:   '#22c55e',
    medium: '#eab308',
    hard:   '#ef4444',
  }[puzzle.difficulty] ?? 'var(--color-text-muted)';

  const goatHops = puzzle.optimal_hops_by_mode?.[mode] ?? puzzle.optimal_hops;

  return (
    <motion.div
      style={{ textAlign: 'center', marginBottom: 16 }}
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
    >
      {/* Difficulty badge — own row */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 6 }}>
        <span
          className="puzzle-difficulty-badge"
          style={{
            padding: '1px 7px',
            border: `2px solid ${diffColor}`,
            borderRadius: 2,
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 700,
            fontSize: 10,
            letterSpacing: '0.12em',
            textTransform: 'uppercase' as const,
            color: diffColor,
          }}
        >
          {puzzle.difficulty}
        </span>
      </div>

      {/* Matchup names row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, flexWrap: 'wrap' as const }}>
        <span
          className="puzzle-player-name"
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 900,
            fontSize: '1.25rem',
            color: 'var(--color-accent)',
            letterSpacing: '0.01em',
          }}
        >
          {puzzle.start_player.full_name}
        </span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-border-2)" strokeWidth="2">
          <path d="M5 12h14" />
          <path d="m12 5 7 7-7 7" />
        </svg>
        <span
          className="puzzle-player-name"
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 900,
            fontSize: '1.25rem',
            color: 'var(--color-text)',
            letterSpacing: '0.01em',
          }}
        >
          {puzzle.end_player.full_name}
        </span>
      </div>

      <p
        className="puzzle-goat-line"
        style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 600,
          fontSize: 12,
          color: 'var(--color-text-muted)',
          marginTop: 6,
          letterSpacing: '0.06em',
        }}
      >
        GOAT: <span style={{ color: 'var(--color-text)', fontWeight: 700 }}>{goatHops} dribbles</span>
      </p>
    </motion.div>
  );
}

// ------------------------------------
// Puzzle load error
// ------------------------------------
function PuzzleError({ error }: { error: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 20px', gap: 14, textAlign: 'center' }}>
      <div style={{ fontSize: '2.5rem' }}>🏀</div>
      <h2 style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '1.5rem', letterSpacing: '0.08em', color: 'var(--color-text)' }}>
        COULDN'T LOAD TODAY'S PUZZLE
      </h2>
      <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)', maxWidth: 320 }}>{error}</p>
      <button
        onClick={() => window.location.reload()}
        className="btn btn-primary"
        style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '0.95rem', letterSpacing: '0.08em', marginTop: 8 }}
      >
        TRY AGAIN
      </button>
      <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: 'var(--color-text-muted)' }}>
        Backend: <code style={{ fontFamily: "'Barlow Condensed', monospace", color: 'var(--color-accent)' }}>
          {import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}
        </code>
      </p>
    </div>
  );
}

// ------------------------------------
// Main App
// ------------------------------------
export default function App() {
  const { loading, error } = usePuzzle();
  const { route, previewDate } = useRoute();

  // Admin page is standalone — no header/footer
  if (route === 'admin') return <AdminPage />;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--color-bg)' }}>
      <Header />

      <main className="flex-1 max-w-game py-6 w-full">
        {route === 'data' ? (
          <DataInfo />
        ) : route === 'preview' ? (
          <PreviewPuzzle date={previewDate!} />
        ) : (
          <AnimatePresence mode="wait">
            {loading ? (
              <motion.div
                key="loading"
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: 12 }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    border: '3px solid var(--color-accent)',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite',
                  }}
                />
                <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
                  Loading today's puzzle...
                </p>
              </motion.div>
            ) : error ? (
              <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <PuzzleError error={error} />
              </motion.div>
            ) : (
              <motion.div
                key="game"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25 }}
              >
                <PuzzleHeader />
                <ModePills />
                <ChainBuilder />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </main>

      <footer
        style={{
          padding: '12px 0',
          borderTop: '1px solid var(--color-border)',
        }}
      >
        <div className="max-w-game" style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: 'var(--color-text-muted)' }}>
          <span>Hoopchain — Daily NBA Connection Game</span>
        </div>
      </footer>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* Modals — lazy-loaded */}
      <Suspense fallback={null}>
        <HowToPlay />
        <StatsPanel />
        <ResultModal />
        <FreePlayModal />
      </Suspense>

    </div>
  );
}
