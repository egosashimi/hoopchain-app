// ============================================================
// HOOPCHAIN — StatsPanel Component
// Clean stat sheet layout — large Barlow Condensed numbers
// ============================================================

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useGame } from '../hooks/useGame';
import { useUserStore } from '../store/userStore';

export function StatsPanel() {
  const { showStats, setShowStats } = useGame();
  const stats = useUserStore();

  useEffect(() => {
    if (!showStats) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setShowStats(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [showStats, setShowStats]);

  const winPct = stats.totalPlayed > 0
    ? Math.round((stats.totalWon / stats.totalPlayed) * 100)
    : 0;

  return (
    <AnimatePresence>
      {showStats && (
        <>
          <motion.div
            className="fixed inset-0 z-70"
            style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowStats(false)}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="stats-panel-title"
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
              transition={{ type: 'spring', stiffness: 320, damping: 30 }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '14px 20px',
                  borderBottom: '1px solid var(--color-border)',
                  background: 'var(--color-surface-2)',
                }}
              >
                <h2
                  id="stats-panel-title"
                  style={{
                    fontFamily: "'Bebas Neue', sans-serif",
                    fontSize: '1.4rem',
                    letterSpacing: '0.08em',
                    color: 'var(--color-text)',
                  }}
                >
                  YOUR STATS
                </h2>
                <button
                  onClick={() => setShowStats(false)}
                  className="btn btn-ghost"
                  style={{ width: 32, height: 32, padding: 0, borderRadius: 2 }}
                  aria-label="Close stats"
                >
                  ✕
                </button>
              </div>

              {/* Stats */}
              <div style={{ padding: '16px 20px 20px' }}>
                {stats.totalPlayed === 0 ? (
                  <div style={{ textAlign: 'center', padding: '24px 0' }}>
                    <div style={{ fontSize: '2.5rem', marginBottom: 10 }}>🏀</div>
                    <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
                      No games played yet. Complete today's puzzle to start your streak!
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Stat rows — flat list, no cards within cards */}
                    <div style={{ borderTop: '1px solid var(--color-border)' }}>
                      <StatRow label="Current Streak" value={stats.streak > 0 ? `🔥 ${stats.streak}` : '0'} accent={stats.streak > 0} />
                      <StatRow label="Best Streak" value={String(stats.maxStreak)} />
                      <StatRow label="Win Rate" value={`${winPct}%`} sub={`${stats.totalWon} of ${stats.totalPlayed}`} />
                      <StatRow label="Avg Score" value={String(stats.avgScore)} />
                      <StatRow label="Avg Dribbles" value={String(stats.avgHops)} />
                      <StatRow label="Total Played" value={String(stats.totalPlayed)} />
                    </div>

                    {/* Win rate bar */}
                    <div style={{ marginTop: 14 }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontFamily: "'Barlow Condensed', sans-serif",
                          fontWeight: 600,
                          fontSize: 11,
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase' as const,
                          color: 'var(--color-text-muted)',
                          marginBottom: 5,
                        }}
                      >
                        <span>Win Rate</span>
                        <span style={{ color: 'var(--color-text)' }}>{winPct}%</span>
                      </div>
                      <div style={{ height: 6, background: 'var(--color-surface-2)', borderRadius: 2, overflow: 'hidden' }}>
                        <motion.div
                          style={{
                            height: '100%',
                            backgroundColor: winPct >= 50 ? 'var(--color-accent)' : 'var(--color-text-muted)',
                            borderRadius: 2,
                          }}
                          initial={{ width: 0 }}
                          animate={{ width: `${winPct}%` }}
                          transition={{ duration: 0.7, ease: 'easeOut', delay: 0.1 }}
                        />
                      </div>
                    </div>

                    {stats.lastPlayed && (
                      <p
                        style={{
                          fontFamily: "'Barlow', sans-serif",
                          fontSize: 11,
                          color: 'var(--color-text-muted)',
                          textAlign: 'center',
                          marginTop: 12,
                        }}
                      >
                        Last played: {stats.lastPlayed}
                      </p>
                    )}
                  </>
                )}
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function StatRow({
  label,
  value,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 0',
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      <span
        style={{
          fontFamily: "'Barlow', sans-serif",
          fontSize: 13,
          color: 'var(--color-text-muted)',
        }}
      >
        {label}
        {sub && (
          <span style={{ fontSize: 11, marginLeft: 6 }}>({sub})</span>
        )}
      </span>
      <span
        className="jersey-number"
        style={{
          fontSize: '1.5rem',
          color: accent ? 'var(--color-accent)' : 'var(--color-text)',
        }}
      >
        {value}
      </span>
    </div>
  );
}
