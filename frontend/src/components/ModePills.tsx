// ============================================================
// HOOPCHAIN — ModePills
// Flat rectangular tabs: Classic / Wild / Coach
// Active: solid fill. Inactive: outline only.
// ============================================================

import { useGame } from '../hooks/useGame';
import { MODE_META, type GameMode } from '../types';

// Supported launch modes — COACH deferred until coach-edge enrichment is complete (W4).
const SUPPORTED_MODES: GameMode[] = ['classic', 'wild'];

const MODE_TOOLTIPS: Record<string, string> = {
  classic: 'Connect through shared teammates only',
  wild:    'Connect through teammates, college, draft class, and more.',
};

export function ModePills() {
  const { puzzle, mode, chains, isFinished, setMode } = useGame();

  if (!puzzle) return null;

  // Intersect payload modes with the supported set — single source of truth, no hardcoded 3-mode list.
  const available = puzzle.available_modes ?? ['classic'];
  const orderedModes = SUPPORTED_MODES.filter((m) => available.includes(m));

  if (orderedModes.length < 2) return null;

  return (
    <div className="w-full overflow-x-auto mb-5" style={{ WebkitOverflowScrolling: 'touch' }}>
      <div style={{ display: 'flex', flexWrap: 'nowrap', gap: 6, padding: '0 4px 4px', width: 'max-content', margin: '0 auto' }}>
        {orderedModes.map((m) => {
          const meta = MODE_META[m];
          const isActive = m === mode;
          const modeChain = chains[m] ?? [];
          const isComplete = puzzle && modeChain.length > 1 &&
            modeChain[modeChain.length - 1].id === puzzle.end_player.id;

          return (
            <button
              key={m}
              onClick={() => !isActive && setMode(m)}
              disabled={isActive && isFinished}
              aria-pressed={isActive}
              className="mode-pill"
              title={MODE_TOOLTIPS[m]}
              style={{
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                padding: '5px 16px',
                borderRadius: 2,
                border: `2px solid ${isActive ? meta.color : 'var(--color-border)'}`,
                background: isActive ? meta.color : 'transparent',
                color: isActive ? 'white' : 'var(--color-text-muted)',
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 700,
                fontSize: 11,
                letterSpacing: '0.12em',
                textTransform: 'uppercase' as const,
                cursor: (isActive && isFinished) ? 'not-allowed' : 'pointer',
                transition: 'background-color 150ms, border-color 150ms, color 150ms',
              }}
            >
              {meta.shortLabel}
              {isComplete && (
                <span style={{ fontSize: 10, opacity: isActive ? 1 : 0.6 }} aria-label="completed">✓</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
