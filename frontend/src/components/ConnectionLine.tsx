// ============================================================
// HOOPCHAIN — ConnectionLine Component
// Flat solid lines connecting NodeCards — no glow, no animation
// ============================================================

import type { EdgeType } from '../types';
import { EDGE_TYPE_META } from '../types';

interface ConnectionLineProps {
  edgeType?: EdgeType;
  edgeLabel?: string;
  animate?: boolean;
  orientation?: 'vertical' | 'horizontal';
}

export function ConnectionLine({
  edgeType,
  edgeLabel,
  orientation = 'vertical',
}: ConnectionLineProps) {
  const meta = edgeType ? EDGE_TYPE_META[edgeType] : null;
  const color = meta?.color ?? 'var(--color-border-2)';
  const label = edgeLabel ?? meta?.label ?? '?';

  if (orientation === 'horizontal') {
    return (
      <div className="flex items-center gap-2 px-2">
        <div className="h-px flex-1" style={{ backgroundColor: color }} />
        {edgeType && (
          <div
            className="flex items-center gap-1.5 whitespace-nowrap"
            style={{
              padding: '2px 8px',
              background: 'var(--color-surface-2)',
              border: `1px solid ${color}`,
              borderRadius: 2,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <span
              style={{
                color,
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 700,
                fontSize: 10,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}
            >
              {label}
            </span>
          </div>
        )}
        <div className="h-px flex-1" style={{ backgroundColor: color }} />
      </div>
    );
  }

  // Vertical (default — stacked mobile layout)
  return (
    <div className="flex flex-col items-center" style={{ gap: 2, paddingTop: 2, paddingBottom: 2 }}>
      <div style={{ width: 2, height: 14, backgroundColor: color }} />
      {edgeType ? (
        <div
          className="flex items-center gap-1.5 whitespace-nowrap"
          style={{
            padding: '2px 8px',
            background: 'var(--color-surface-2)',
            border: `1px solid ${color}`,
            borderRadius: 2,
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: color }}
          />
          <span
            style={{
              color,
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 700,
              fontSize: 10,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {label}
          </span>
        </div>
      ) : (
        <div
          style={{
            padding: '2px 8px',
            background: 'var(--color-surface-2)',
            border: '1px dashed var(--color-border-2)',
            borderRadius: 2,
          }}
        >
          <span style={{ color: 'var(--color-text-muted)', fontSize: 10 }}>···</span>
        </div>
      )}
      <div style={{ width: 2, height: 14, backgroundColor: color }} />
    </div>
  );
}

// ------------------------------------
// PendingConnectionLine — search state
// Dashed line with SEARCH NEXT prompt in Bebas Neue
// ------------------------------------

export function PendingConnectionLine() {
  return (
    <div className="flex flex-col items-center" style={{ gap: 2, paddingTop: 2, paddingBottom: 2 }}>
      <div
        style={{
          width: 2,
          height: 14,
          borderLeft: '2px dashed var(--color-border-2)',
        }}
      />
      <div
        style={{
          padding: '2px 10px',
          background: 'var(--color-surface)',
          border: '1px dashed var(--color-border-2)',
          borderRadius: 2,
        }}
      >
        <span
          style={{
            fontFamily: "'Bebas Neue', sans-serif",
            fontSize: 12,
            letterSpacing: '0.12em',
            color: 'var(--color-accent)',
          }}
        >
          SEARCH NEXT
        </span>
      </div>
      <div
        style={{
          width: 2,
          height: 14,
          borderLeft: '2px dashed var(--color-border-2)',
        }}
      />
    </div>
  );
}
