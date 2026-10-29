// ============================================================
// HOOPCHAIN — FreePlayModal
// Mode picker: Classic (teammates) / Wild (all) / Coach
// ============================================================

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useGame } from '../hooks/useGame';
import { MODE_META, type GameMode, type Difficulty } from '../types';

// COACH deferred until coach-edge enrichment is complete (W4).
const MODES: GameMode[] = ['classic', 'wild'];

const DIFFICULTIES: { value: Difficulty; label: string; desc: string }[] = [
  { value: 'easy',   label: 'Easy',   desc: '2-3 dribbles' },
  { value: 'medium', label: 'Medium', desc: '3-4 dribbles' },
  { value: 'hard',   label: 'Hard',   desc: '5-6 dribbles' },
];

export function FreePlayModal() {
  const { showFreePlay, setShowFreePlay, loadRandomPuzzle } = useGame();

  const [selectedMode, setSelectedMode] = useState<GameMode>('classic');
  const [selectedDiff, setSelectedDiff] = useState<Difficulty | 'any'>('any');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!showFreePlay) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setShowFreePlay(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [showFreePlay, setShowFreePlay]);

  async function handlePlay() {
    setLoading(true);
    setError(null);
    try {
      await loadRandomPuzzle(
        selectedMode,
        selectedDiff === 'any' ? undefined : selectedDiff,
      );
    } catch {
      setError('No puzzle found for that combination. Try different options.');
    } finally {
      setLoading(false);
    }
  }

  const modeDescriptions: Partial<Record<GameMode, string>> = {
    classic: 'Teammates only',
    wild:    'All connection types',
  };

  return (
    <AnimatePresence>
      {showFreePlay && (
        <>
          {/* Backdrop — no blur */}
          <motion.div
            className="fixed inset-0 z-70"
            style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowFreePlay(false)}
          />

          {/* Modal */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="freeplay-modal-title"
            className="fixed inset-0 z-80 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="w-full max-w-sm overflow-hidden"
              style={{
                background: 'var(--color-surface)',
                border: '2px solid var(--color-border)',
                borderRadius: 4,
              }}
              initial={{ y: 30, scale: 0.97 }}
              animate={{ y: 0, scale: 1 }}
              exit={{ y: 30, scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 300, damping: 28 }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div
                style={{
                  padding: '16px 20px 14px',
                  textAlign: 'center',
                  borderBottom: '1px solid var(--color-border)',
                  background: 'var(--color-surface-2)',
                }}
              >
                <h2
                  id="freeplay-modal-title"
                  style={{
                    fontFamily: "'Bebas Neue', sans-serif",
                    fontSize: '1.4rem',
                    letterSpacing: '0.1em',
                    color: 'var(--color-accent)',
                  }}
                >
                  FREE PLAY
                </h2>
                <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>
                  Results don't count toward your streak
                </p>
              </div>

              <div style={{ padding: '16px 20px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Mode selector */}
                <div>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 10,
                      letterSpacing: '0.14em',
                      textTransform: 'uppercase' as const,
                      color: 'var(--color-text-muted)',
                      marginBottom: 8,
                    }}
                  >
                    Mode
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {MODES.map((m) => {
                      const meta = MODE_META[m];
                      const isActive = m === selectedMode;
                      return (
                        <button
                          key={m}
                          onClick={() => setSelectedMode(m)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            borderRadius: 2,
                            border: `2px solid ${isActive ? meta.color : 'var(--color-border)'}`,
                            background: isActive ? `${meta.color}18` : 'transparent',
                            cursor: 'pointer',
                            transition: 'all 150ms',
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "'Barlow Condensed', sans-serif",
                              fontWeight: 700,
                              fontSize: 12,
                              letterSpacing: '0.08em',
                              textTransform: 'uppercase' as const,
                              color: isActive ? meta.color : 'var(--color-text-muted)',
                            }}
                          >
                            {meta.label}
                          </span>
                          <span
                            style={{
                              fontFamily: "'Barlow', sans-serif",
                              fontSize: 11,
                              color: isActive ? meta.color : 'var(--color-text-muted)',
                              opacity: 0.8,
                            }}
                          >
                            {modeDescriptions[m] ?? ''}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Difficulty selector */}
                <div>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 10,
                      letterSpacing: '0.14em',
                      textTransform: 'uppercase' as const,
                      color: 'var(--color-text-muted)',
                      marginBottom: 8,
                    }}
                  >
                    Difficulty
                  </p>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <DiffButton
                      label="Any"
                      active={selectedDiff === 'any'}
                      onClick={() => setSelectedDiff('any')}
                      color="var(--color-accent)"
                    />
                    {DIFFICULTIES.map((d) => {
                      const diffColor = { easy: '#22c55e', medium: '#eab308', hard: '#ef4444' }[d.value];
                      return (
                        <DiffButton
                          key={d.value}
                          label={d.label}
                          active={selectedDiff === d.value}
                          onClick={() => setSelectedDiff(d.value)}
                          color={diffColor}
                        />
                      );
                    })}
                  </div>
                </div>

                {error && (
                  <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: '#ef4444', textAlign: 'center' }}>
                    {error}
                  </p>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    onClick={() => setShowFreePlay(false)}
                    className="btn btn-ghost flex-1 text-sm"
                    style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePlay}
                    disabled={loading}
                    className="btn btn-primary flex-1 text-sm gap-2"
                    style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '0.95rem', letterSpacing: '0.08em' }}
                  >
                    {loading ? <Spinner /> : null}
                    {loading ? 'FINDING...' : 'PLAY'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function DiffButton({ label, active, onClick, color }: { label: string; active: boolean; onClick: () => void; color: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: '7px 4px',
        borderRadius: 2,
        border: `2px solid ${active ? color : 'var(--color-border)'}`,
        background: active ? `${color}18` : 'transparent',
        cursor: 'pointer',
        fontFamily: "'Barlow Condensed', sans-serif",
        fontWeight: 700,
        fontSize: 11,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        color: active ? color : 'var(--color-text-muted)',
        transition: 'all 150ms',
      }}
    >
      {label}
    </button>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" strokeOpacity="0.3" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}
