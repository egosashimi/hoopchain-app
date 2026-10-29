// ============================================================
// HOOPCHAIN — Header Component
// 70s Topps card aesthetic: flat wordmark, no gradients/glow
// ============================================================

import { useGame } from '../hooks/useGame';
import { useUserStore } from '../store/userStore';
import { useGameStore } from '../store/gameStore';

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export function Header() {
  const { setShowHowToPlay, setShowStats, setShowFreePlay } = useGame();
  const streak = useUserStore((s) => s.streak);
  const theme = useUserStore((s) => s.theme);
  const setTheme = useUserStore((s) => s.setTheme);
  const isFreePlay = useGameStore((s) => s.isFreePlay);
  const exitFreePlay = useGameStore((s) => s.exitFreePlay);

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  function handleLogoClick() {
    if (window.location.hash !== '') {
      window.location.hash = '';
    }
    if (isFreePlay) {
      exitFreePlay();
    }
  }

  return (
    <header
      className="sticky top-0 z-40 w-full"
      style={{
        background: 'var(--color-bg)',
        borderBottom: '2px solid var(--color-border)',
        height: 'var(--header-height)',
      }}
    >
      <div className="max-w-game h-full flex items-center justify-between">

        {/* Left — Stats + Data */}
        <div className="flex-1 flex items-center gap-1">
          <button
            onClick={() => setShowStats(true)}
            className="btn btn-ghost text-sm gap-2 h-9 px-3"
            aria-label="View your stats"
            id="stats-button"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3v18h18" />
              <path d="M18 17V9" />
              <path d="M13 17V5" />
              <path d="M8 17v-3" />
            </svg>
            <span className="hidden sm:inline" style={{ fontFamily: "'Barlow', sans-serif", fontWeight: 500 }}>Stats</span>
            {streak > 0 && (
              <span
                className="text-xs font-bold px-1.5 py-0.5"
                style={{
                  background: 'var(--color-surface-2)',
                  color: 'var(--color-accent)',
                  border: '1px solid var(--color-border-2)',
                  borderRadius: 2,
                  fontFamily: "'Barlow Condensed', sans-serif",
                  fontWeight: 700,
                }}
              >
                🔥 {streak}
              </span>
            )}
          </button>

          <a
            href="#/data"
            className="btn btn-ghost text-sm gap-1.5 h-9 px-3"
            aria-label="Data & coverage info"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
            </svg>
            <span className="hidden sm:inline" style={{ fontFamily: "'Barlow', sans-serif", fontWeight: 500 }}>Data</span>
          </a>
        </div>

        {/* Center — HOOPCHAIN wordmark + date (clickable → home) */}
        <button
          onClick={handleLogoClick}
          className="flex flex-col items-center gap-0"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          aria-label="Return to today's puzzle"
        >
          <h1
            className="header-wordmark leading-none tracking-wider"
            style={{
              fontFamily: "'Bebas Neue', sans-serif",
              fontSize: '1.75rem',
              letterSpacing: '0.08em',
            }}
          >
            <span style={{ color: 'var(--color-text)' }}>HOOP</span>
            <span style={{ color: 'var(--color-accent)' }}>CHAIN</span>
          </h1>
          <span
            className="uppercase"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 600,
              fontSize: '0.65rem',
              letterSpacing: '0.18em',
              color: 'var(--color-text-muted)',
            }}
          >
            {today}
          </span>
        </button>

        {/* Right — Free Play, How to Play, Theme toggle */}
        <div className="flex-1 flex items-center gap-1 justify-end">
          <button
            onClick={() => setShowFreePlay(true)}
            className="btn btn-ghost text-sm gap-1.5 h-9 px-3"
            aria-label="Free Play"
            id="free-play-button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            <span
              className="hidden sm:inline"
              style={{ color: 'var(--color-accent)', fontFamily: "'Barlow', sans-serif", fontWeight: 500 }}
            >
              Free Play
            </span>
          </button>

          <button
            onClick={() => setShowHowToPlay(true)}
            className="btn btn-ghost text-sm gap-2 h-9 px-3"
            aria-label="How to play"
            id="how-to-play-button"
          >
            <span className="hidden sm:inline" style={{ fontFamily: "'Barlow', sans-serif", fontWeight: 500 }}>How to Play</span>
            <span
              className="w-6 h-6 flex items-center justify-center"
              style={{
                border: '2px solid var(--color-border)',
                color: 'var(--color-text-muted)',
                fontSize: '0.875rem',
                fontWeight: 700,
                borderRadius: 2,
                fontFamily: "'Barlow Condensed', sans-serif",
              }}
            >
              ?
            </span>
          </button>

          {/* Theme toggle */}
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="btn btn-ghost h-9 w-9 px-0 flex items-center justify-center"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </header>
  );
}
