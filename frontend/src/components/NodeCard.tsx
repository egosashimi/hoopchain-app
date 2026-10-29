// ============================================================
// HOOPCHAIN — NodeCard Component
// 70s Topps basketball card: portrait layout, flat, no shadows
// ============================================================

import { useState } from 'react';
import type { ChainNode } from '../types';
import { EDGE_TYPE_META } from '../types';

// ------------------------------------
// Silhouette fallback SVG (inline)
// ------------------------------------
function SilhouetteSVG() {
  return (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 100 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <circle cx="50" cy="38" r="22" fill="var(--color-border-2)" />
      <ellipse cx="50" cy="105" rx="40" ry="32" fill="var(--color-border-2)" />
    </svg>
  );
}

// ------------------------------------
// Headshot with graceful fallback
// ------------------------------------
interface HeadshotProps {
  playerId: string;
  playerName: string;
  size?: number;
  className?: string;
}

export function Headshot({ playerId, playerName, size = 56, className = '' }: HeadshotProps) {
  const [failed, setFailed] = useState(false);
  const url = `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`;

  if (failed) {
    return (
      <div
        className={`flex items-center justify-center overflow-hidden ${className}`}
        style={{ width: size, height: size, background: 'var(--color-surface-2)' }}
        aria-label={`${playerName} silhouette`}
      >
        <SilhouetteSVG />
      </div>
    );
  }

  return (
    <div
      className={`overflow-hidden ${className}`}
      style={{ width: size, height: size, background: 'var(--color-surface-2)' }}
    >
      <img
        src={url}
        alt={playerName}
        width={size}
        height={size}
        className="w-full h-full object-cover object-top"
        onError={() => setFailed(true)}
        loading="lazy"
      />
    </div>
  );
}

// ------------------------------------
// NodeCard — portrait trading card design
// ------------------------------------

const CARD_WIDTH = 152;
const CARD_HEADSHOT_HEIGHT = 104;   // ~65% of card
const CARD_INFO_HEIGHT = 52;        // ~35% of card

interface NodeCardProps {
  node: ChainNode;
  isEndpoint?: boolean;
  isStart?: boolean;
  isEnd?: boolean;
  isLatest?: boolean;
  animate?: boolean;
  className?: string;
}

export function NodeCard({
  node,
  isStart = false,
  isEnd = false,
  isLatest = false,
  animate = true,
  className = '',
}: NodeCardProps) {
  const edgeMeta = node.edgeType ? EDGE_TYPE_META[node.edgeType] : null;
  const [failed, setFailed] = useState(false);
  const url = `https://cdn.nba.com/headshots/nba/latest/1040x760/${node.id}.png`;

  const topBorderColor = edgeMeta?.color ?? null;

  const card = (
    <div
      className={`relative flex-shrink-0 node-card ${className}`}
      style={{
        width: CARD_WIDTH,
        border: '2px solid var(--color-border)',
        borderRadius: 4,
        overflow: 'hidden',
        opacity: isLatest ? 1 : undefined,
      }}
    >
      {/* Colored top edge — shows edge type when connection exists */}
      {topBorderColor && (
        <div style={{ height: 3, background: topBorderColor }} />
      )}

      {/* START / END badge — flat rectangular in Bebas Neue */}
      {(isStart || isEnd) && (
        <div
          className="absolute z-10 node-card__badge"
          style={{
            top: topBorderColor ? 7 : 4,
            left: 4,
            padding: '1px 6px',
            background: isStart ? 'var(--color-accent)' : '#ef4444',
            borderRadius: 2,
            fontFamily: "'Bebas Neue', sans-serif",
            fontSize: 13,
            letterSpacing: '0.08em',
            color: 'white',
            lineHeight: 1.3,
          }}
        >
          {isStart ? 'START' : 'END'}
        </div>
      )}

      {/* Headshot — fills top portion of card */}
      <div
        className="node-card__headshot"
        style={{
          height: CARD_HEADSHOT_HEIGHT,
          overflow: 'hidden',
          background: 'var(--color-surface-2)',
          position: 'relative',
        }}
      >
        {failed ? (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <SilhouetteSVG />
          </div>
        ) : (
          <img
            src={url}
            alt={node.name}
            style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top center', display: 'block' }}
            onError={() => setFailed(true)}
            loading="lazy"
          />
        )}
      </div>

      {/* Info strip — bottom portion */}
      <div
        className="node-card__info"
        style={{
          height: CARD_INFO_HEIGHT,
          background: 'var(--color-surface-2)',
          borderTop: '1px solid var(--color-border)',
          padding: '5px 7px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        <div
          className="node-card__name"
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 700,
            fontSize: 12,
            color: 'var(--color-text)',
            lineHeight: 1.2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            letterSpacing: '0.01em',
          }}
        >
          {node.name}
        </div>
        {node.teamName && (
          <div
            className="node-card__team"
            style={{
              fontFamily: "'Barlow', sans-serif",
              fontWeight: 400,
              fontSize: 10,
              color: 'var(--color-text-muted)',
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginTop: 2,
            }}
          >
            {node.teamName}
          </div>
        )}
      </div>
    </div>
  );

  if (animate && isLatest) {
    return (
      <div
        style={{
          animation: 'fadeIn 0.25s ease-out',
        }}
      >
        {card}
      </div>
    );
  }

  return card;
}

// ------------------------------------
// SkeletonNodeCard — loading state
// ------------------------------------

export function SkeletonNodeCard() {
  return (
    <div
      style={{
        width: CARD_WIDTH,
        height: CARD_HEADSHOT_HEIGHT + CARD_INFO_HEIGHT,
        border: '2px solid var(--color-border)',
        borderRadius: 4,
        overflow: 'hidden',
      }}
    >
      <div className="skeleton" style={{ height: CARD_HEADSHOT_HEIGHT }} />
      <div style={{ height: CARD_INFO_HEIGHT, background: 'var(--color-surface-2)', borderTop: '1px solid var(--color-border)', padding: '6px 7px' }}>
        <div className="skeleton" style={{ height: 10, width: '75%', borderRadius: 2, marginBottom: 4 }} />
        <div className="skeleton" style={{ height: 8, width: '55%', borderRadius: 2 }} />
      </div>
    </div>
  );
}
