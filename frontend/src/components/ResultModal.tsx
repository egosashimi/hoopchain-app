// ============================================================
// HOOPCHAIN — ResultModal Component
// Vintage scorecard design: dribbles / GOAT, flat, no confetti
// ============================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useGame } from '../hooks/useGame';
import { useUserStore } from '../store/userStore';
import { EDGE_TYPE_META, MODE_META } from '../types';
import type { ChainNode } from '../types';
import { subscribeApi } from '../api/client';
function formatPuzzleDate(puzzleDate: string): string {
  if (puzzleDate.startsWith('free:')) return 'Free Play';
  try {
    const [yr, mo, dy] = puzzleDate.split('-').map(Number);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[mo - 1]} ${dy}, ${yr}`;
  } catch {
    return puzzleDate;
  }
}

export function ResultModal() {
  const {
    showResult, status, puzzle, chain, score,
    mode, isFreePlay, optimalPath,
    setShowResult, setShowFreePlay,
  } = useGame();
  const userStats = useUserStore();
  const [copiedSolution, setCopiedSolution] = useState(false);
  const [copiedPuzzle, setCopiedPuzzle] = useState(false);
  const [flashWin, setFlashWin] = useState(false);
  const flashedRef = useRef(false);

  // Optimal path reveal state
  const [showOptimalPath, setShowOptimalPath] = useState(false);

  // Email capture state
  const [email, setEmail] = useState('');
  const [emailSubmitting, setEmailSubmitting] = useState(false);
  const [emailDone, setEmailDone] = useState(false);

  const won = status === 'won';
  const gaveUp = status === 'given_up';
  const dribbles = Math.max(0, chain.length - 2);
  const modeMeta = MODE_META[mode];
  const goatHops = puzzle ? (puzzle.optimal_hops_by_mode?.[mode] ?? puzzle.optimal_hops) : 0;
  // Ground-truth reveal count: intermediate count of the actual returned path.
  const revealDribbles = optimalPath ? Math.max(0, optimalPath.length - 2) : goatHops;

  // Reset reveal state whenever modal opens for a new result
  useEffect(() => {
    if (showResult) {
      setShowOptimalPath(false);
    }
  }, [showResult]);

  // Auto-reveal optimal path after 1s when player gives up
  useEffect(() => {
    if (!showResult || !gaveUp || !optimalPath) return;
    const t = setTimeout(() => setShowOptimalPath(true), 1000);
    return () => clearTimeout(t);
  }, [showResult, gaveUp, optimalPath]);

  // 1-second background color flash on win (instead of confetti)
  useEffect(() => {
    if (showResult && won && !flashedRef.current) {
      flashedRef.current = true;
      setFlashWin(true);
      const t = setTimeout(() => setFlashWin(false), 1000);
      return () => clearTimeout(t);
    }
    if (!showResult) flashedRef.current = false;
  }, [showResult, won]);

  useEffect(() => {
    if (!showResult) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setShowResult(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [showResult, setShowResult]);

  // Build "A → label → B → label → C" text from the user's chain.
  const buildSolutionText = useCallback((nodes: ChainNode[]): string => {
    if (!nodes.length) return '';
    const parts: string[] = [nodes[0].name];
    for (let i = 0; i < nodes.length - 1; i++) {
      if (nodes[i].connectionLabel) parts.push(nodes[i].connectionLabel!);
      parts.push(nodes[i + 1].name);
    }
    return parts.join(' → ');
  }, []);

  const handleShareSolution = useCallback(async () => {
    const text = buildSolutionText(chain);
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopiedSolution(true);
    setTimeout(() => setCopiedSolution(false), 2000);
  }, [chain, buildSolutionText]);

  const buildPuzzleText = useCallback((): string => {
    if (!puzzle) return '';
    const dateStr = formatPuzzleDate(puzzle.puzzle_date);
    const start = puzzle.start_player.full_name;
    const end = puzzle.end_player.full_name;
    const resultLine = won
      ? `I did it in ${dribbles} dribble${dribbles === 1 ? '' : 's'} — your turn:`
      : `GOAT par is ${goatHops} — can you beat it?`;
    return [
      `HOOPCHAIN 🏀 ${dateStr}`,
      `Can you connect ${start} → ${end}?`,
      resultLine,
      'hoopchain.app',
    ].join('\n');
  }, [puzzle, dribbles, won, goatHops]);

  const handleSharePuzzle = useCallback(async () => {
    const text = buildPuzzleText();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopiedPuzzle(true);
    setTimeout(() => setCopiedPuzzle(false), 2000);
  }, [buildPuzzleText]);

  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setEmailSubmitting(true);
    try {
      await subscribeApi.subscribe(email.trim());
      setEmailDone(true);
    } catch {
      setEmailDone(true); // silent fail — don't annoy user
    } finally {
      setEmailSubmitting(false);
    }
  }

  function handlePlayAgain() {
    setShowResult(false);
    setShowFreePlay(true);
  }

  if (!puzzle) return null;

  return (
    <AnimatePresence>
      {showResult && (
        <>
          {/* Win flash overlay */}
          {flashWin && (
            <div
              className="fixed inset-0 pointer-events-none z-[99]"
              style={{
                backgroundColor: 'var(--color-accent)',
                opacity: 0,
                animation: 'flashBg 1s ease-out forwards',
              }}
            />
          )}

          {/* Backdrop — no blur */}
          <motion.div
            className="fixed inset-0 z-70"
            style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowResult(false)}
          />

          {/* Modal */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="result-modal-title"
            className="fixed inset-0 z-80 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="w-full max-w-md overflow-hidden"
              style={{
                background: 'var(--color-surface)',
                border: '2px solid var(--color-border)',
                borderTop: `4px solid ${won ? 'var(--color-accent)' : 'var(--color-error, #ef4444)'}`,
                borderRadius: 4,
                maxHeight: '90vh',
                overflowY: 'auto',
              }}
              initial={{ y: 40, scale: 0.95 }}
              animate={{ y: 0, scale: 1 }}
              exit={{ y: 40, scale: 0.95 }}
              transition={{ type: 'spring', stiffness: 280, damping: 26 }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Free play banner */}
              {isFreePlay && (
                <div
                  style={{
                    padding: '5px 16px',
                    textAlign: 'center',
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 700,
                    fontSize: 10,
                    letterSpacing: '0.14em',
                    textTransform: 'uppercase' as const,
                    background: 'var(--color-surface-2)',
                    borderBottom: '1px solid var(--color-border)',
                    color: modeMeta.color,
                  }}
                >
                  FREE PLAY — results don't count toward your streak
                </div>
              )}

              {/* Scorecard header */}
              <div
                style={{
                  padding: '20px 24px 16px',
                  textAlign: 'center',
                  borderBottom: '1px solid var(--color-border)',
                  background: 'var(--color-surface-2)',
                }}
              >
                {/* Result label */}
                <div
                  id="result-modal-title"
                  style={{
                    fontFamily: "'Bebas Neue', sans-serif",
                    fontSize: '1.5rem',
                    letterSpacing: '0.1em',
                    color: won ? 'var(--color-accent)' : '#ef4444',
                    marginBottom: 4,
                  }}
                >
                  {won ? 'CHAIN COMPLETE' : 'BETTER LUCK TOMORROW'}
                </div>

                {/* Players */}
                <div
                  style={{
                    fontFamily: "'Barlow', sans-serif",
                    fontSize: 13,
                    color: 'var(--color-text-muted)',
                    marginBottom: 16,
                  }}
                >
                  {puzzle.start_player.full_name} → {puzzle.end_player.full_name}
                </div>

                {/* Large dribble count */}
                <div className="jersey-number" style={{ color: won ? 'var(--color-text)' : '#ef4444' }}>
                  {dribbles}
                </div>
                <div
                  style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 600,
                    fontSize: 12,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase' as const,
                    color: 'var(--color-text-muted)',
                    marginTop: 2,
                    marginBottom: 12,
                  }}
                >
                  DRIBBLES
                </div>

                {/* GOAT */}
                <div
                  style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 700,
                    fontSize: 13,
                    color: 'var(--color-text-muted)',
                    letterSpacing: '0.06em',
                  }}
                >
                  GOAT: <span style={{ color: 'var(--color-text)' }}>{goatHops}</span>
                </div>

                {/* Mode badge (non-classic) */}
                {mode !== 'classic' && (
                  <div style={{ marginTop: 8 }}>
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        border: `2px solid ${modeMeta.color}`,
                        borderRadius: 2,
                        fontFamily: "'Barlow Condensed', sans-serif",
                        fontWeight: 700,
                        fontSize: 10,
                        letterSpacing: '0.12em',
                        textTransform: 'uppercase' as const,
                        color: modeMeta.color,
                      }}
                    >
                      {modeMeta.label} MODE
                    </span>
                  </div>
                )}
              </div>

              <div style={{ padding: '16px 24px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {/* Score stats row */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                  <ScoreStat label="Score" value={score !== null ? `${score}` : '—'} highlight />
                  <ScoreStat label="Dribbles" value={String(dribbles)} />
                  <ScoreStat label="GOAT" value={String(goatHops)} />
                </div>

                {/* Streak — only for non-freeplay wins */}
                {won && !isFreePlay && userStats.streak > 0 && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      padding: '10px 16px',
                      border: '2px solid var(--color-accent)',
                      borderRadius: 4,
                      background: 'var(--color-surface-2)',
                    }}
                  >
                    <span style={{ fontSize: '1.25rem' }}>🔥</span>
                    <span
                      style={{
                        fontFamily: "'Bebas Neue', sans-serif",
                        fontSize: '1.25rem',
                        letterSpacing: '0.06em',
                        color: 'var(--color-accent)',
                      }}
                    >
                      {userStats.streak}-DAY STREAK
                    </span>
                  </div>
                )}

                {/* Chain recap */}
                <div>
                  <div
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
                    Your Chain
                  </div>
                  <ChainDisplay nodes={chain.map(n => ({
                    id: n.id,
                    type: n.type,
                    name: n.name,
                    edge_type: n.edgeType,
                    connection_label: n.connectionLabel,
                  }))} />
                </div>

                {/* Optimal path reveal */}
                {optimalPath && (
                  <div>
                    {/* Toggle button — always available on win; auto-shown on give-up */}
                    {won && !showOptimalPath && (
                      <motion.button
                        onClick={() => setShowOptimalPath(true)}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{
                          opacity: 1,
                          y: 0,
                          boxShadow: [
                            '0 0 0px rgba(232,82,10,0)',
                            '0 0 0px rgba(232,82,10,0)',
                            '0 0 16px rgba(232,82,10,0.6)',
                            '0 0 4px rgba(232,82,10,0.15)',
                            '0 0 16px rgba(232,82,10,0.6)',
                            '0 0 0px rgba(232,82,10,0)',
                          ],
                        }}
                        transition={{
                          opacity: { duration: 0.2, delay: 0.3 },
                          y: { duration: 0.2, delay: 0.3 },
                          boxShadow: { duration: 1.6, delay: 0.7, times: [0, 0.08, 0.28, 0.52, 0.72, 1] },
                        }}
                        whileHover={{ boxShadow: '0 0 12px rgba(232,82,10,0.35)', scale: 1.005 }}
                        whileTap={{ scale: 0.98 }}
                        style={{
                          width: '100%',
                          padding: '11px 16px',
                          border: '2px solid var(--color-accent)',
                          borderRadius: 4,
                          background: 'var(--color-surface-2)',
                          cursor: 'pointer',
                          fontFamily: "'Barlow Condensed', sans-serif",
                          fontWeight: 700,
                          fontSize: 13,
                          letterSpacing: '0.12em',
                          textTransform: 'uppercase' as const,
                          color: 'var(--color-accent)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 8,
                        }}
                      >
                        <EyeIcon /> Show Optimal Path ({revealDribbles} dribbles)
                      </motion.button>
                    )}

                    {/* Revealed path */}
                    {showOptimalPath && (
                      <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25 }}
                      >
                        <div
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
                          Optimal Path ({revealDribbles} dribbles)
                        </div>
                        <ChainDisplay nodes={optimalPath} accent />
                      </motion.div>
                    )}
                  </div>
                )}

                {/* Email capture — needs the backend, so hidden while the site runs static */}
                {subscribeApi.available && (
                <div
                  style={{
                    padding: '12px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface-2)',
                  }}
                >
                  {emailDone ? (
                    <p
                      style={{
                        fontFamily: "'Barlow', sans-serif",
                        fontSize: 13,
                        color: 'var(--color-accent)',
                        textAlign: 'center',
                      }}
                    >
                      Thanks! 🙏
                    </p>
                  ) : (
                    <form onSubmit={handleEmailSubmit} style={{ display: 'flex', gap: 8 }}>
                      <input
                        type="email"
                        placeholder="your@email.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        style={{
                          flex: 1,
                          padding: '6px 10px',
                          background: 'var(--color-surface)',
                          border: '1px solid var(--color-border)',
                          borderRadius: 3,
                          fontFamily: "'Barlow', sans-serif",
                          fontSize: 12,
                          color: 'var(--color-text)',
                          outline: 'none',
                        }}
                      />
                      <button
                        type="submit"
                        disabled={emailSubmitting}
                        className="btn btn-secondary"
                        style={{
                          fontFamily: "'Barlow Condensed', sans-serif",
                          fontWeight: 700,
                          fontSize: 11,
                          letterSpacing: '0.08em',
                          padding: '6px 12px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Subscribe
                      </button>
                    </form>
                  )}
                  {!emailDone && (
                    <p
                      style={{
                        fontFamily: "'Barlow', sans-serif",
                        fontSize: 11,
                        color: 'var(--color-text-muted)',
                        marginTop: 6,
                        textAlign: 'center',
                      }}
                    >
                      Get notified about new features and updates
                    </p>
                  )}
                </div>
                )}

                {/* Share buttons */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {/* Row 1: Share the puzzle (no spoiler) + Share your path (spoiler) */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={handleSharePuzzle}
                      className="btn btn-primary flex-1 gap-2"
                      style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '0.95rem', letterSpacing: '0.08em' }}
                    >
                      {copiedPuzzle ? <><CheckIcon />COPIED!</> : <><ShareIcon />SHARE THE PUZZLE</>}
                    </button>
                    <button
                      onClick={handleShareSolution}
                      className="btn btn-secondary flex-1 gap-2"
                      style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '0.95rem', letterSpacing: '0.08em' }}
                    >
                      {copiedSolution ? <><CheckIcon />COPIED!</> : <><ShareIcon />SHARE YOUR PATH</>}
                    </button>
                  </div>
                  {/* Row 2: Play Again / Free Play CTA */}
                  {isFreePlay ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <button
                        onClick={handlePlayAgain}
                        className="btn btn-secondary"
                        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700 }}
                      >
                        Play Again
                      </button>
                      <button
                        onClick={() => setShowResult(false)}
                        className="btn btn-ghost"
                        aria-label="Close result"
                        style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <button
                        onClick={handlePlayAgain}
                        className="btn btn-secondary gap-2"
                        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: '0.95rem', letterSpacing: '0.06em' }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        Want more? Try Free Play
                      </button>
                      <button
                        onClick={() => setShowResult(false)}
                        className="btn btn-ghost"
                        aria-label="Close result"
                        style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}
                      >
                        Dismiss
                      </button>
                    </div>
                  )}
                </div>

                {/* Footer note */}
                <p
                  style={{
                    fontFamily: "'Barlow', sans-serif",
                    fontSize: 11,
                    color: 'var(--color-text-muted)',
                    textAlign: 'center',
                  }}
                >
                  {isFreePlay ? 'Free Play — no streak impact' : 'New puzzle at midnight UTC'}
                </p>
              </div>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ------------------------------------
// Shared chain display (user chain + optimal path)
// ------------------------------------

function ChainDisplay({ nodes, accent = false }: {
  nodes: Array<{
    id: string;
    type: string;
    name: string;
    edge_type?: string;
    connection_label?: string;
  }>;
  accent?: boolean;
}) {
  return (
    <div
      style={{
        background: 'var(--color-surface-2)',
        border: `1px solid ${accent ? 'var(--color-accent)' : 'var(--color-border)'}`,
        borderRadius: 4,
        padding: '8px 12px',
      }}
    >
      {nodes.map((node, idx) => {
        const edgeMeta = node.edge_type && node.edge_type in EDGE_TYPE_META
          ? EDGE_TYPE_META[node.edge_type as keyof typeof EDGE_TYPE_META]
          : null;
        return (
          <div key={node.id + idx}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '3px 0',
              }}
            >
              <div
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  flexShrink: 0,
                  backgroundColor: edgeMeta ? edgeMeta.color : 'var(--color-accent)',
                }}
              />
              <span
                style={{
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontWeight: 600,
                  fontSize: 13,
                  color: 'var(--color-text)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {node.name}
              </span>
            </div>
            {idx < nodes.length - 1 && edgeMeta && (
              <div style={{ paddingLeft: 14, paddingBottom: 1 }}>
                <span
                  style={{
                    fontFamily: "'Barlow', sans-serif",
                    fontSize: 11,
                    color: edgeMeta.color,
                  }}
                >
                  {edgeMeta.emoji} {node.connection_label ?? edgeMeta.label}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------
// Sub-components
// ------------------------------------

function ScoreStat({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      style={{
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-border)',
        borderRadius: 4,
        padding: '10px 8px',
        textAlign: 'center',
      }}
    >
      <div
        className="jersey-number"
        style={{
          fontSize: '1.75rem',
          color: highlight ? 'var(--color-accent)' : 'var(--color-text)',
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 600,
          fontSize: 10,
          letterSpacing: '0.1em',
          textTransform: 'uppercase' as const,
          color: 'var(--color-text-muted)',
          marginTop: 2,
        }}
      >
        {label}
      </div>
    </div>
  );
}

function ShareIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

