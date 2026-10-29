// ============================================================
// HOOPCHAIN — HowToPlay Modal
// Explains dribbles, connection types, scoring
// ============================================================

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useGame } from '../hooks/useGame';
import { EDGE_TYPE_META } from '../types';
import type { EdgeType } from '../types';

const EDGE_EXAMPLES: Record<EdgeType, string> = {
  teammate:    '"Both played for the 2012–13 Miami Heat"',
  college:     '"Both attended Duke University"',
  draft_class: '"Both were drafted in the 2003 NBA Draft"',
  coached_by:  '"Both coached by Gregg Popovich with the Spurs" — partial coverage (~20 coaches tracked, 1980 onward; sourced from Wikipedia)',
  all_star:    '"Both selected for the 2016 NBA All-Star Game"',
};

export function HowToPlay() {
  const { showHowToPlay, setShowHowToPlay } = useGame();

  useEffect(() => {
    if (!showHowToPlay) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setShowHowToPlay(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [showHowToPlay, setShowHowToPlay]);

  return (
    <AnimatePresence>
      {showHowToPlay && (
        <>
          {/* Backdrop — no blur */}
          <motion.div
            className="fixed inset-0 z-70"
            style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowHowToPlay(false)}
          />

          {/* Modal */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="how-to-play-title"
            className="fixed inset-0 z-80 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="w-full max-w-lg overflow-hidden"
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
                  id="how-to-play-title"
                  style={{
                    fontFamily: "'Bebas Neue', sans-serif",
                    fontSize: '1.4rem',
                    letterSpacing: '0.08em',
                    color: 'var(--color-text)',
                  }}
                >
                  HOW TO PLAY
                </h2>
                <button
                  onClick={() => setShowHowToPlay(false)}
                  className="btn btn-ghost"
                  style={{ width: 32, height: 32, padding: 0, borderRadius: 2 }}
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>

              {/* Content */}
              <div style={{ padding: '16px 20px 0', maxHeight: '70vh', overflowY: 'auto' }}>

                {/* Goal */}
                <div style={{ marginBottom: 16 }}>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--color-text)',
                      marginBottom: 6,
                      letterSpacing: '0.04em',
                    }}
                  >
                    🏀 THE GOAL
                  </p>
                  <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
                    Connect two NBA players through a chain of real-world relationships.
                    Each <strong style={{ color: 'var(--color-text)' }}>dribble</strong> must be a valid connection
                    between consecutive players. Reach the end player in as few dribbles as possible!
                    Fewest dribbles = best score. GOAT is the optimal dribble count.
                  </p>
                </div>

                {/* Example chain */}
                <div
                  style={{
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    padding: '12px 14px',
                    marginBottom: 10,
                  }}
                >
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 10,
                      letterSpacing: '0.14em',
                      textTransform: 'uppercase' as const,
                      color: 'var(--color-text-muted)',
                      marginBottom: 10,
                    }}
                  >
                    Example Chain
                  </p>
                  {/* Mini NodeCards */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {/* Wembanyama */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <img
                        src="https://cdn.nba.com/headshots/nba/latest/1040x760/1641705.png"
                        alt="Victor Wembanyama"
                        style={{ width: 36, height: 36, borderRadius: 3, objectFit: 'cover', background: 'var(--color-surface)' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: 13, color: 'var(--color-accent)' }}>Victor Wembanyama</span>
                    </div>
                    <div style={{ paddingLeft: 46, paddingBottom: 2 }}>
                      <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: '#22c55e' }}>🟢 Teammates on the San Antonio Spurs</span>
                    </div>
                    {/* Harrison Barnes */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <img
                        src="https://cdn.nba.com/headshots/nba/latest/1040x760/203084.png"
                        alt="Harrison Barnes"
                        style={{ width: 36, height: 36, borderRadius: 3, objectFit: 'cover', background: 'var(--color-surface)' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: 13, color: 'var(--color-text)' }}>Harrison Barnes</span>
                    </div>
                    <div style={{ paddingLeft: 46, paddingBottom: 2 }}>
                      <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: '#22c55e' }}>🟢 Teammates on the Dallas Mavericks</span>
                    </div>
                    {/* Brunson */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <img
                        src="https://cdn.nba.com/headshots/nba/latest/1040x760/1628973.png"
                        alt="Jalen Brunson"
                        style={{ width: 36, height: 36, borderRadius: 3, objectFit: 'cover', background: 'var(--color-surface)' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: 13, color: '#ef4444' }}>Jalen Brunson</span>
                    </div>
                  </div>
                </div>

                {/* Example explanation */}
                <p
                  style={{
                    fontFamily: "'Barlow', sans-serif",
                    fontSize: 12,
                    color: 'var(--color-text-muted)',
                    lineHeight: 1.6,
                    marginBottom: 16,
                    padding: '0 2px',
                  }}
                >
                  Wembanyama and Brunson connect through Harrison Barnes — Barnes was Wembanyama's teammate
                  on the 2024–25 Spurs, and Brunson's teammate on the 2018–19 Mavericks.
                </p>

                {/* Modes */}
                <div style={{ marginBottom: 16 }}>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--color-text)',
                      marginBottom: 8,
                      letterSpacing: '0.04em',
                    }}
                  >
                    Game Modes
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {[
                      { label: 'CLASSIC', color: '#e8520a', desc: 'Teammates only — cleanest challenge' },
                      { label: 'WILD', color: '#d4a017', desc: 'All connection types — most flexible' },
                    ].map((m) => (
                      <div
                        key={m.label}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          padding: '7px 10px',
                          background: 'var(--color-surface-2)',
                          border: '1px solid var(--color-border)',
                          borderRadius: 4,
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "'Barlow Condensed', sans-serif",
                            fontWeight: 700,
                            fontSize: 11,
                            letterSpacing: '0.1em',
                            color: m.color,
                            minWidth: 52,
                          }}
                        >
                          {m.label}
                        </span>
                        <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}>
                          {m.desc}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Connection types */}
                <div style={{ marginBottom: 16 }}>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--color-text)',
                      marginBottom: 8,
                      letterSpacing: '0.04em',
                    }}
                  >
                    Connection Types
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {(Object.keys(EDGE_TYPE_META) as EdgeType[]).map((type) => {
                      const meta = EDGE_TYPE_META[type];
                      return (
                        <div
                          key={type}
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 10,
                            padding: '7px 10px',
                            background: 'var(--color-surface-2)',
                            border: '1px solid var(--color-border)',
                            borderRadius: 4,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 90 }}>
                            <span style={{ fontSize: 14 }}>{meta.emoji}</span>
                            <span
                              style={{
                                fontFamily: "'Barlow Condensed', sans-serif",
                                fontWeight: 700,
                                fontSize: 11,
                                letterSpacing: '0.06em',
                                textTransform: 'uppercase' as const,
                                color: meta.color,
                              }}
                            >
                              {meta.label}
                            </span>
                          </div>
                          <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
                            {EDGE_EXAMPLES[type]}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Scoring */}
                <div style={{ marginBottom: 16 }}>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--color-text)',
                      marginBottom: 6,
                      letterSpacing: '0.04em',
                    }}
                  >
                    🏆 Scoring
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}>
                    <p>• Start with <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>1,000 pts</span> — lose 150 per dribble over GOAT</p>
                    <p>• <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>Speed bonus</span>: finish under 2 minutes for extra points</p>
                    <p>• <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>Difficulty multiplier</span>: hard puzzles = up to 1.3× score</p>
                    <p>• <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>Edge diversity bonus</span>: use rare connection types (+50 pts)</p>
                  </div>
                </div>

                {/* Tips */}
                <div style={{ marginBottom: 16 }}>
                  <p
                    style={{
                      fontFamily: "'Barlow Condensed', sans-serif",
                      fontWeight: 700,
                      fontSize: 13,
                      color: 'var(--color-text)',
                      marginBottom: 6,
                      letterSpacing: '0.04em',
                    }}
                  >
                    💡 Tips
                  </p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}>
                    <p>• Big market teams (Lakers, Celtics, Heat) are great hub players</p>
                    <p>• College connections can bridge wildly different eras</p>
                    <p>• Use <strong style={{ color: 'var(--color-text)' }}>Undo</strong> if you go down a dead end</p>
                    <p>• New puzzle drops at midnight UTC every day</p>
                  </div>
                </div>
              </div>

              {/* Footer CTA */}
              <div style={{ padding: '14px 20px', borderTop: '1px solid var(--color-border)' }}>
                <button
                  onClick={() => setShowHowToPlay(false)}
                  className="btn btn-primary w-full"
                  style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '1rem', letterSpacing: '0.08em' }}
                  id="got-it-button"
                >
                  GOT IT — LET'S PLAY
                </button>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
