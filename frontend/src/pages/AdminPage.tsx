// ============================================================
// HOOPCHAIN — Admin Page
// Password-protected puzzle management tool.
// Access at /#/admin — the password is the backend's API_SECRET_KEY,
// checked server-side (never bundled into the frontend).
// ============================================================

import { useState, useEffect, useCallback } from 'react';
import { adminApi, searchApi, type AdminPuzzleRow, type AdminSubscriberRow } from '../api/client';

export function AdminPage() {
  if (!adminApi.available) return <AdminUnavailable />;
  return <AdminLogin />;
}

// Admin tools edit the server's puzzle table; the static site has no server
function AdminUnavailable() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--color-bg)', padding: 24 }}>
      <div style={{ maxWidth: 360, textAlign: 'center', fontFamily: "'Barlow', sans-serif", color: 'var(--color-text)' }}>
        <h1 style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '1.5rem', letterSpacing: '0.08em', marginBottom: 12 }}>ADMIN</h1>
        <p style={{ fontSize: 14, color: 'var(--color-text-muted)', marginBottom: 16 }}>
          Admin tools need the Hoopchain server. This version of the site runs entirely in the
          browser, and daily puzzles come from the schedule in <code>public/data/daily.json</code>.
        </p>
        <a href="#/" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>← Back to game</a>
      </div>
    </div>
  );
}

function AdminLogin() {
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState(false);
  const [checking, setChecking] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setChecking(true);
    try {
      await adminApi.getPuzzles(password);
      setAuthed(true);
      setAuthError(false);
    } catch {
      setAuthError(true);
    } finally {
      setChecking(false);
    }
  }

  if (!authed) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--color-bg)',
        }}
      >
        <div
          style={{
            width: '100%',
            maxWidth: 320,
            padding: 24,
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
          }}
        >
          <h1
            style={{
              fontFamily: "'Bebas Neue', sans-serif",
              fontSize: '1.5rem',
              letterSpacing: '0.08em',
              color: 'var(--color-text)',
              marginBottom: 16,
              textAlign: 'center',
            }}
          >
            ADMIN
          </h1>
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input
              type="password"
              placeholder="Admin password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              style={{
                padding: '8px 12px',
                background: 'var(--color-surface-2)',
                border: `1px solid ${authError ? '#ef4444' : 'var(--color-border)'}`,
                borderRadius: 3,
                fontFamily: "'Barlow', sans-serif",
                fontSize: 14,
                color: 'var(--color-text)',
                outline: 'none',
              }}
            />
            {authError && (
              <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: '#ef4444' }}>
                Incorrect password
              </p>
            )}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={checking}
              style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: '1rem', letterSpacing: '0.08em' }}
            >
              {checking ? 'CHECKING…' : 'LOGIN'}
            </button>
          </form>
          <p style={{ marginTop: 12, textAlign: 'center' }}>
            <a href="#/" style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: 'var(--color-text-muted)' }}>
              ← Back to game
            </a>
          </p>
        </div>
      </div>
    );
  }

  return <AdminDashboard adminKey={password} />;
}

// ------------------------------------
// Admin Dashboard (authenticated)
// ------------------------------------

function AdminDashboard({ adminKey }: { adminKey: string }) {
  const [puzzles, setPuzzles] = useState<AdminPuzzleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overrideDate, setOverrideDate] = useState('');
  const [overrideMsg, setOverrideMsg] = useState<string | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [overrideLoading, setOverrideLoading] = useState(false);
  const [subscribers, setSubscribers] = useState<AdminSubscriberRow[]>([]);
  const [subscribersLoading, setSubscribersLoading] = useState(true);
  const [subscribersError, setSubscribersError] = useState<string | null>(null);

  // Player search for override form
  const [startQuery, setStartQuery] = useState('');
  const [endQuery, setEndQuery] = useState('');
  const [startResults, setStartResults] = useState<Array<{ id: string; full_name: string }>>([]);
  const [endResults, setEndResults] = useState<Array<{ id: string; full_name: string }>>([]);
  const [selectedStart, setSelectedStart] = useState<{ id: string; full_name: string } | null>(null);
  const [selectedEnd, setSelectedEnd] = useState<{ id: string; full_name: string } | null>(null);

  const fetchPuzzles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.getPuzzles(adminKey);
      setPuzzles(data);
    } catch (err: unknown) {
      setError((err as { message?: string })?.message ?? 'Failed to load puzzles');
    } finally {
      setLoading(false);
    }
  }, [adminKey]);

  const fetchSubscribers = useCallback(async () => {
    setSubscribersLoading(true);
    setSubscribersError(null);
    try {
      const data = await adminApi.getSubscribers(adminKey, 500);
      setSubscribers(data);
    } catch (err: unknown) {
      setSubscribersError((err as { message?: string })?.message ?? 'Failed to load subscribers');
    } finally {
      setSubscribersLoading(false);
    }
  }, [adminKey]);

  useEffect(() => {
    fetchPuzzles();
    fetchSubscribers();
  }, [fetchPuzzles, fetchSubscribers]);

  // Debounced player search
  useEffect(() => {
    if (startQuery.length < 2) { setStartResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const results = await searchApi.players(startQuery, 6);
        setStartResults(results);
      } catch { setStartResults([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [startQuery]);

  useEffect(() => {
    if (endQuery.length < 2) { setEndResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const results = await searchApi.players(endQuery, 6);
        setEndResults(results);
      } catch { setEndResults([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [endQuery]);

  async function handleOverride(e: React.FormEvent) {
    e.preventDefault();
    if (!overrideDate || !selectedStart || !selectedEnd) return;
    setOverrideLoading(true);
    setOverrideMsg(null);
    setOverrideError(null);
    try {
      const result = await adminApi.overridePuzzle(adminKey, overrideDate, selectedStart.id, selectedEnd.id);
      setOverrideMsg(`✓ Saved: ${selectedStart.full_name} → ${selectedEnd.full_name} (${result.difficulty}, ${result.optimal_hops} hops)`);
      setOverrideDate('');
      setSelectedStart(null);
      setSelectedEnd(null);
      setStartQuery('');
      setEndQuery('');
      fetchPuzzles();
    } catch (err: unknown) {
      setOverrideError((err as { message?: string })?.message ?? 'Override failed');
    } finally {
      setOverrideLoading(false);
    }
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', padding: '24px 16px' }}>
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <h1
            style={{
              fontFamily: "'Bebas Neue', sans-serif",
              fontSize: '1.75rem',
              letterSpacing: '0.08em',
              color: 'var(--color-text)',
            }}
          >
            HOOPCHAIN ADMIN
          </h1>
          <a
            href="#/"
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 700,
              fontSize: 12,
              letterSpacing: '0.1em',
              color: 'var(--color-text-muted)',
              textDecoration: 'none',
            }}
          >
            ← BACK TO GAME
          </a>
        </div>

        {/* Override form */}
        <div
          style={{
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
            padding: 20,
            marginBottom: 24,
          }}
        >
          <h2
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 700,
              fontSize: 14,
              letterSpacing: '0.1em',
              color: 'var(--color-text)',
              marginBottom: 14,
              textTransform: 'uppercase' as const,
            }}
          >
            Override Puzzle
          </h2>
          <form onSubmit={handleOverride} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Date */}
            <div>
              <label style={labelStyle}>Date</label>
              <input
                type="date"
                value={overrideDate}
                min={today}
                onChange={(e) => setOverrideDate(e.target.value)}
                required
                style={inputStyle}
              />
            </div>

            {/* Start player */}
            <div style={{ position: 'relative' }}>
              <label style={labelStyle}>Start Player</label>
              {selectedStart ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text)' }}>
                    {selectedStart.full_name}
                  </span>
                  <button
                    type="button"
                    onClick={() => { setSelectedStart(null); setStartQuery(''); }}
                    style={{ ...ghostBtnStyle }}
                  >
                    ✕
                  </button>
                </div>
              ) : (
                <>
                  <input
                    type="text"
                    placeholder="Search player..."
                    value={startQuery}
                    onChange={(e) => setStartQuery(e.target.value)}
                    style={inputStyle}
                  />
                  {startResults.length > 0 && (
                    <div style={dropdownStyle}>
                      {startResults.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => { setSelectedStart(p); setStartQuery(''); setStartResults([]); }}
                          style={dropdownItemStyle}
                        >
                          {p.full_name}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* End player */}
            <div style={{ position: 'relative' }}>
              <label style={labelStyle}>End Player</label>
              {selectedEnd ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text)' }}>
                    {selectedEnd.full_name}
                  </span>
                  <button
                    type="button"
                    onClick={() => { setSelectedEnd(null); setEndQuery(''); }}
                    style={{ ...ghostBtnStyle }}
                  >
                    ✕
                  </button>
                </div>
              ) : (
                <>
                  <input
                    type="text"
                    placeholder="Search player..."
                    value={endQuery}
                    onChange={(e) => setEndQuery(e.target.value)}
                    style={inputStyle}
                  />
                  {endResults.length > 0 && (
                    <div style={dropdownStyle}>
                      {endResults.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => { setSelectedEnd(p); setEndQuery(''); setEndResults([]); }}
                          style={dropdownItemStyle}
                        >
                          {p.full_name}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {overrideMsg && (
              <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: '#22c55e' }}>{overrideMsg}</p>
            )}
            {overrideError && (
              <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 12, color: '#ef4444' }}>{overrideError}</p>
            )}

            <button
              type="submit"
              disabled={overrideLoading || !selectedStart || !selectedEnd || !overrideDate}
              className="btn btn-primary"
              style={{
                fontFamily: "'Bebas Neue', sans-serif",
                fontSize: '1rem',
                letterSpacing: '0.08em',
                opacity: (!selectedStart || !selectedEnd || !overrideDate) ? 0.5 : 1,
              }}
            >
              {overrideLoading ? 'Saving…' : 'SAVE OVERRIDE'}
            </button>
          </form>
        </div>

        {/* Upcoming puzzles table */}
        <div
          style={{
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--color-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <h2
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: '0.1em',
                color: 'var(--color-text)',
                textTransform: 'uppercase' as const,
              }}
            >
              Next 30 Days ({puzzles.length} puzzles)
            </h2>
            <button
              onClick={fetchPuzzles}
              className="btn btn-ghost"
              style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: 11 }}
            >
              Refresh
            </button>
          </div>

          {loading && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
              Loading…
            </p>
          )}
          {error && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: '#ef4444' }}>{error}</p>
          )}
          {!loading && !error && puzzles.length === 0 && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
              No puzzles scheduled for the next 30 days.
            </p>
          )}
          {!loading && puzzles.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: 'var(--color-surface-2)' }}>
                    {['Date', 'Start Player', 'End Player', 'Difficulty', 'Hops', 'Modes', 'Preview'].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '8px 12px',
                          textAlign: 'left',
                          fontFamily: "'Barlow Condensed', sans-serif",
                          fontWeight: 700,
                          fontSize: 10,
                          letterSpacing: '0.12em',
                          textTransform: 'uppercase' as const,
                          color: 'var(--color-text-muted)',
                          borderBottom: '1px solid var(--color-border)',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {puzzles.map((p, i) => {
                    const isToday = p.puzzle_date === today;
                    return (
                      <tr
                        key={p.puzzle_date}
                        style={{
                          background: isToday ? 'rgba(255,107,53,0.06)' : i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)',
                          borderBottom: '1px solid var(--color-border)',
                        }}
                      >
                        <td style={tdStyle}>
                          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, color: isToday ? 'var(--color-accent)' : 'var(--color-text)' }}>
                            {p.puzzle_date}{isToday ? ' ★' : ''}
                          </span>
                        </td>
                        <td style={tdStyle}>{p.start_player_name}</td>
                        <td style={tdStyle}>{p.end_player_name}</td>
                        <td style={tdStyle}>
                          <span style={{ color: diffColor(p.difficulty) }}>{p.difficulty}</span>
                        </td>
                        <td style={tdStyle}>{p.optimal_hops}</td>
                        <td style={tdStyle}>{(p.available_modes ?? []).join(', ')}</td>
                        <td style={tdStyle}>
                          <a
                            href={`#/preview/${p.puzzle_date}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              fontFamily: "'Barlow Condensed', sans-serif",
                              fontWeight: 700,
                              fontSize: 11,
                              letterSpacing: '0.06em',
                              color: 'var(--color-accent)',
                              textDecoration: 'none',
                            }}
                          >
                            Preview →
                          </a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Subscribers table */}
        <div
          style={{
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
            overflow: 'hidden',
            marginTop: 24,
          }}
        >
          <div
            style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--color-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <h2
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: '0.1em',
                color: 'var(--color-text)',
                textTransform: 'uppercase' as const,
              }}
            >
              Email Subscribers ({subscribers.length})
            </h2>
            <button
              onClick={fetchSubscribers}
              className="btn btn-ghost"
              style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: 11 }}
            >
              Refresh
            </button>
          </div>

          {subscribersLoading && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
              Loading…
            </p>
          )}
          {subscribersError && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: '#ef4444' }}>{subscribersError}</p>
          )}
          {!subscribersLoading && !subscribersError && subscribers.length === 0 && (
            <p style={{ padding: 20, fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)' }}>
              No subscribers yet.
            </p>
          )}
          {!subscribersLoading && subscribers.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: 'var(--color-surface-2)' }}>
                    {['Email', 'Signed Up'].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '8px 12px',
                          textAlign: 'left',
                          fontFamily: "'Barlow Condensed', sans-serif",
                          fontWeight: 700,
                          fontSize: 10,
                          letterSpacing: '0.12em',
                          textTransform: 'uppercase' as const,
                          color: 'var(--color-text-muted)',
                          borderBottom: '1px solid var(--color-border)',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {subscribers.map((s, i) => (
                    <tr
                      key={s.id}
                      style={{
                        background: i % 2 === 0 ? 'transparent' : 'var(--color-surface-2)',
                        borderBottom: '1px solid var(--color-border)',
                      }}
                    >
                      <td style={{ ...tdStyle, fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600 }}>{s.email}</td>
                      <td style={tdStyle}>{formatSignedUp(s.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------
// Helpers
// ------------------------------------

function diffColor(d: string) {
  return d === 'easy' ? '#22c55e' : d === 'hard' ? '#ef4444' : '#eab308';
}

function formatSignedUp(timestamp: string | null) {
  if (!timestamp) return '—';
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return timestamp;
  return parsed.toLocaleString();
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontFamily: "'Barlow Condensed', sans-serif",
  fontWeight: 700,
  fontSize: 10,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'var(--color-text-muted)',
  marginBottom: 4,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  background: 'var(--color-surface-2)',
  border: '1px solid var(--color-border)',
  borderRadius: 3,
  fontFamily: "'Barlow', sans-serif",
  fontSize: 13,
  color: 'var(--color-text)',
  outline: 'none',
  boxSizing: 'border-box',
};

const dropdownStyle: React.CSSProperties = {
  position: 'absolute',
  top: '100%',
  left: 0,
  right: 0,
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 3,
  zIndex: 100,
  maxHeight: 180,
  overflowY: 'auto',
};

const dropdownItemStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  padding: '7px 12px',
  textAlign: 'left',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  fontFamily: "'Barlow', sans-serif",
  fontSize: 13,
  color: 'var(--color-text)',
  borderBottom: '1px solid var(--color-border)',
};

const ghostBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  color: 'var(--color-text-muted)',
  fontSize: 12,
  padding: '2px 6px',
};

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontFamily: "'Barlow', sans-serif",
  fontSize: 12,
  color: 'var(--color-text)',
  verticalAlign: 'middle',
};
