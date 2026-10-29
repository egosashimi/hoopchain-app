// ============================================================
// HOOPCHAIN — ChainBuilder Component
// Mobile: vertical stack (unchanged)
// Desktop (≥768px): three-column — [START] [chain+search] [END]
// ============================================================

import React, { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useGame } from '../hooks/useGame';
import { NodeCard, SkeletonNodeCard } from './NodeCard';
import { ConnectionLine, PendingConnectionLine } from './ConnectionLine';
import { SearchInput } from './SearchInput';
import { MODE_META } from '../types';
import type { ChainNode } from '../types';

export function ChainBuilder() {
  const {
    puzzle,
    chain,
    status,
    currentNode,
    hopsUsed,
    isPlaying,
    isFinished,
    isValidating,
    lastHopValid,
    errorMessage,
    startedAt,
    isFreePlay,
    mode,
    startGame,
    submitHop,
    removeLastHop,
    giveUp,
    dismissError,
    exitFreePlay,
  } = useGame();

  const chainEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chainEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [chain.length]);

  function handleSelect(candidate: ChainNode) {
    if (!isPlaying && !isFinished) startGame();
    submitHop(candidate);
  }

  if (!puzzle) {
    return <ChainBuilderSkeleton />;
  }

  const optimalDribbles = puzzle.optimal_hops_by_mode?.[mode] ?? puzzle.optimal_hops;
  const excludeIds = chain.map((n) => n.id);
  const modeMeta = MODE_META[mode];
  const isWon = status === 'won';

  // Derived nodes for desktop layout
  const startNode = chain[0];
  // Center nodes = intermediates between start and end (end excluded when won)
  const centerNodes: ChainNode[] = isWon
    ? chain.slice(1, chain.length - 1)
    : chain.slice(1);
  // End node for display in right column
  const endNodeDisplay: ChainNode = isWon
    ? chain[chain.length - 1]
    : {
        id: puzzle.end_player.id,
        type: 'player',
        name: puzzle.end_player.full_name,
        headshotUrl: puzzle.end_player.headshot_url,
        teamName: puzzle.end_player.team_name,
      };

  // ---- Shared sub-renders ----

  const freePlayBanner = isFreePlay && (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        padding: '6px 10px 6px 14px',
        border: `2px solid ${modeMeta.color}`,
        borderRadius: 4,
        background: 'var(--color-surface)',
      }}
    >
      <span
        style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 700,
          fontSize: 11,
          letterSpacing: '0.1em',
          textTransform: 'uppercase' as const,
          color: modeMeta.color,
        }}
      >
        FREE PLAY — results don't count toward your streak
      </span>
      <button
        onClick={exitFreePlay}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 700,
          fontSize: 11,
          letterSpacing: '0.08em',
          textTransform: 'uppercase' as const,
          color: 'var(--color-text-muted)',
          padding: '2px 4px',
          flexShrink: 0,
        }}
        aria-label="Return to daily puzzle"
      >
        ← Daily
      </button>
    </div>
  );

  const searchArea = !isFinished && (
    <div className="flex flex-col gap-3 w-full">
      <label
        style={{
          fontFamily: "'Barlow Condensed', sans-serif",
          fontWeight: 700,
          fontSize: 11,
          letterSpacing: '0.14em',
          textTransform: 'uppercase' as const,
          color: 'var(--color-text-muted)',
          textAlign: 'center',
          display: 'block',
        }}
        className="search-next-label"
      >
        Connect {currentNode?.name ?? '...'} to...
      </label>

      <SearchInput
        onSelect={handleSelect}
        disabled={isValidating || isFinished}
        placeholder="Search for an NBA player..."
        excludeIds={excludeIds}
        shake={lastHopValid === false}
      />

      <AnimatePresence>
        {errorMessage && (
          <motion.div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 14px',
              background: 'rgba(239,68,68,0.08)',
              border: '2px solid rgba(239,68,68,0.4)',
              borderRadius: 4,
              fontSize: 13,
              color: '#ef4444',
              fontFamily: "'Barlow', sans-serif",
            }}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <span style={{ flex: 1 }}>{errorMessage}</span>
            <button
              onClick={dismissError}
              style={{ color: 'rgba(239,68,68,0.6)', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  const controls = !isFinished && (
    <div className="controls-bar flex items-center justify-between gap-4 w-full">
      <button
        onClick={removeLastHop}
        disabled={chain.length <= 1 || isValidating}
        className="btn btn-ghost text-sm gap-2"
        aria-label="Undo last dribble"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m9 14-5-5 5-5" />
          <path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />
        </svg>
        Undo
      </button>

      <div
        className="controls-stat-text flex items-center gap-3"
        style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: 13, color: 'var(--color-text-muted)', fontWeight: 600 }}
      >
        <span>GOAT: <span style={{ color: 'var(--color-text)', fontWeight: 700 }}>{optimalDribbles}</span></span>
        <span style={{ color: 'var(--color-border-2)' }}>|</span>
        <span>Dribbles: <span style={{ color: 'var(--color-text)', fontWeight: 700 }}>{hopsUsed}</span></span>
        {startedAt && (
          <>
            <span style={{ color: 'var(--color-border-2)' }}>|</span>
            <ElapsedTimer startedAt={startedAt} />
          </>
        )}
      </div>

      <button
        onClick={giveUp}
        disabled={isValidating}
        className="btn btn-danger text-sm"
        aria-label="Give up and reveal answer"
      >
        Give Up
      </button>
    </div>
  );

  const validatingIndicator = isValidating && (
    <div
      className="flex items-center justify-center gap-2"
      style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}
    >
      <Spinner />
      Checking connection...
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      {freePlayBanner}

      {/* ======================================================
          MOBILE LAYOUT — vertical stack (unchanged)
          Hidden on md+ screens
          ====================================================== */}
      <div className="md:hidden flex flex-col items-center w-full">
        <AnimatePresence mode="popLayout">
          {chain.map((node, idx) => {
            const isStart = idx === 0;
            const isEnd = node.id === puzzle.end_player.id;
            const isLatest = idx === chain.length - 1 && idx > 0;
            const hasConnection = idx < chain.length - 1;

            return (
              <motion.div
                key={node.id + idx}
                className="flex flex-col items-center w-full"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                layout
              >
                <NodeCard
                  node={node}
                  isEndpoint={isStart || isEnd}
                  isStart={isStart}
                  isEnd={isEnd}
                  isLatest={isLatest}
                  animate={isLatest}
                />
                {hasConnection && (
                  <ConnectionLine
                    edgeType={node.edgeType}
                    edgeLabel={node.connectionLabel}
                    animate={isLatest}
                    orientation="vertical"
                  />
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>

        {!isFinished && (
          <>
            <PendingConnectionLine />
            <div style={{ opacity: 0.38 }}>
              <NodeCard
                node={{
                  id: puzzle.end_player.id,
                  type: 'player',
                  name: puzzle.end_player.full_name,
                  headshotUrl: puzzle.end_player.headshot_url,
                  teamName: puzzle.end_player.team_name,
                }}
                isEndpoint
                isEnd
                animate={false}
              />
            </div>
          </>
        )}

        <div ref={chainEndRef} />
      </div>

      {/* Mobile search + controls */}
      <div className="md:hidden flex flex-col gap-3">
        {searchArea}
      </div>
      <div className="md:hidden">
        {controls}
      </div>

      {/* ======================================================
          DESKTOP LAYOUT — three-column grid
          [START 200px] [center 1fr] [END 200px]
          Hidden on mobile, shown on md+ screens
          ====================================================== */}
      <div
        className="hidden md:grid"
        style={{
          gridTemplateColumns: '176px 1fr 176px',
          columnGap: 12,
          rowGap: 0,
          width: '100%',
          alignItems: 'start',
        }}
      >
        {/* LEFT COLUMN — START card */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 4 }}>
          {startNode && (
            <NodeCard
              node={startNode}
              isEndpoint
              isStart
              animate={false}
            />
          )}
        </div>

        {/* CENTER COLUMN — intermediate nodes + search + controls */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
          {/* Top connection: from start down into center.
              minHeight matches desktop card height (220 headshot + 70 info = 290px)
              so the search input never visually overlaps the side player card images
              when no intermediate nodes exist yet. */}
          <div style={centerNodes.length === 0 ? { minHeight: 290, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end' } : undefined}>
            {chain.length === 1 ? (
              <PendingConnectionLine />
            ) : (
              <ConnectionLine
                edgeType={startNode?.edgeType}
                edgeLabel={startNode?.connectionLabel}
                orientation="vertical"
              />
            )}
          </div>

          {/* Intermediate nodes */}
          {centerNodes.map((node, idx) => {
            const isLatest = !isWon && idx === centerNodes.length - 1;
            const isLastCenter = idx === centerNodes.length - 1;
            return (
              <React.Fragment key={node.id + idx}>
                <NodeCard
                  node={node}
                  isLatest={isLatest}
                  animate={isLatest}
                />
                {/* Connection after this node */}
                {!isLastCenter ? (
                  <ConnectionLine
                    edgeType={node.edgeType}
                    edgeLabel={node.connectionLabel}
                    orientation="vertical"
                  />
                ) : isWon ? (
                  // Last intermediate → end (right col)
                  <ConnectionLine
                    edgeType={node.edgeType}
                    edgeLabel={node.connectionLabel}
                    orientation="vertical"
                  />
                ) : (
                  // Not yet finished → pending down to end
                  <PendingConnectionLine />
                )}
              </React.Fragment>
            );
          })}

          {/* Search input + error — only when playing */}
          {!isFinished && (
            <div style={{ width: '100%', marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {searchArea}
            </div>
          )}

          {/* Controls row */}
          <div style={{ width: '100%', marginTop: 12 }}>
            {controls}
          </div>
        </div>

        {/* RIGHT COLUMN — END card */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 4 }}>
          <div style={{ opacity: isWon ? 1 : 0.38, transition: 'opacity 0.3s ease' }}>
            <NodeCard
              node={endNodeDisplay}
              isEndpoint
              isEnd
              animate={false}
            />
          </div>
        </div>
      </div>

      {/* Validating indicator — shown on both layouts */}
      {validatingIndicator}
    </div>
  );
}

// ------------------------------------
// Elapsed timer styled as shot clock
// ------------------------------------

function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = React.useState(0);

  useEffect(() => {
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;

  return (
    <span className="shot-clock" style={{ fontSize: '0.85rem', padding: '1px 7px' }}>
      {m}:{s.toString().padStart(2, '0')}
    </span>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" strokeOpacity="0.2" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}

// ------------------------------------
// Skeleton
// ------------------------------------

function ChainBuilderSkeleton() {
  return (
    <div className="flex flex-col items-center gap-4 animate-fade-in">
      <SkeletonNodeCard />
      <div style={{ height: 12, width: 2, background: 'var(--color-border)' }} />
      <div className="skeleton" style={{ height: 50, width: '100%', maxWidth: 480, borderRadius: 4 }} />
      <div style={{ height: 12, width: 2, background: 'var(--color-border)' }} />
      <SkeletonNodeCard />
    </div>
  );
}
