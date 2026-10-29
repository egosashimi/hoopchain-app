// ============================================================
// HOOPCHAIN — SearchInput Component
// Debounced player autocomplete — flat border, no glow on focus
// ============================================================

import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { PlayerSearchResult, ChainNode } from '../types';
import { searchApi } from '../api/client';

interface SearchInputProps {
  onSelect: (node: ChainNode) => void;
  disabled?: boolean;
  placeholder?: string;
  excludeIds?: string[];
  shake?: boolean;
}

export function SearchInput({
  onSelect,
  disabled = false,
  placeholder = 'Search for a player...',
  excludeIds = [],
  shake = false,
}: SearchInputProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [shaking, setShaking] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (shake) {
      setShaking(true);
      const t = setTimeout(() => setShaking(false), 500);
      return () => clearTimeout(t);
    }
  }, [shake]);

  const search = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }

    setLoading(true);
    try {
      const data = await searchApi.players(q, 10);
      const filtered = data.filter((p) => !excludeIds.includes(p.id));
      setResults(filtered);
      setOpen(filtered.length > 0);
      setActiveIndex(-1);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [excludeIds]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(query), 280);
    return () => clearTimeout(debounceRef.current);
  }, [query, search]);

  function handleSelect(result: PlayerSearchResult) {
    const node: ChainNode = {
      id: result.id,
      type: 'player',
      name: result.full_name,
      headshotUrl: result.headshot_url,
      teamName: result.team_name,
      yearsActive: result.seasons_active,
      isActive: result.is_active,
    };
    setQuery('');
    setResults([]);
    setOpen(false);
    setActiveIndex(-1);
    onSelect(node);
    inputRef.current?.focus();
  }

  useEffect(() => {
    if (activeIndex < 0 || !listRef.current) return;
    const item = listRef.current.querySelector<HTMLElement>(`#result-${activeIndex}`);
    item?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      if (!open) return;
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      if (!open) return;
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Enter') {
      if (open && results.length > 0) {
        e.preventDefault();
        handleSelect(results[activeIndex >= 0 ? activeIndex : 0]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  return (
    <div className="relative w-full max-w-lg">
      {/* Input wrapper */}
      <div
        className={`search-input-wrapper${shaking ? ' animate-shake' : ''}`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          background: 'var(--color-surface)',
          border: `2px solid ${shaking ? 'var(--color-error)' : focused ? 'var(--color-accent)' : 'var(--color-border)'}`,
          borderRadius: 4,
          opacity: disabled ? 0.5 : 1,
          cursor: disabled ? 'not-allowed' : undefined,
          backgroundColor: shaking ? 'rgba(239,68,68,0.06)' : 'var(--color-surface)',
          transition: 'border-color 150ms',
        }}
      >
        {/* Search icon */}
        <div style={{ paddingLeft: 14, color: 'var(--color-text-muted)', flexShrink: 0 }}>
          {loading ? (
            <Spinner />
          ) : (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          )}
        </div>

        {/* Text input */}
        <input
          ref={inputRef}
          id="player-search-input"
          className="search-input-field"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { setFocused(true); if (results.length > 0) setOpen(true); }}
          onBlur={() => {
            setFocused(false);
            setTimeout(() => setOpen(false), 150);
          }}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          style={{
            flex: 1,
            paddingTop: 12,
            paddingBottom: 12,
            paddingRight: 14,
            background: 'transparent',
            color: 'var(--color-text)',
            fontSize: 14,
            fontFamily: "'Barlow', sans-serif",
            fontWeight: 500,
            outline: 'none',
            border: 'none',
          }}
          placeholder-style={{ color: 'var(--color-text-muted)' }}
          aria-autocomplete="list"
          aria-controls="search-results-list"
          aria-activedescendant={activeIndex >= 0 ? `result-${activeIndex}` : undefined}
          aria-label="Search for a player"
          role="combobox"
          aria-expanded={open}
        />
      </div>

      {/* Dropdown results */}
      {open && results.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            zIndex: 50,
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
            overflow: 'hidden',
          }}
        >
          <ul
            ref={listRef}
            id="search-results-list"
            role="listbox"
            style={{ maxHeight: 280, overflowY: 'auto', padding: '4px 0' }}
          >
            {results.map((result, idx) => (
              <li
                key={result.id}
                id={`result-${idx}`}
                role="option"
                aria-selected={idx === activeIndex}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSelect(result);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  cursor: 'pointer',
                  background: idx === activeIndex ? 'var(--color-surface-2)' : 'transparent',
                  borderLeft: `3px solid ${idx === activeIndex ? 'var(--color-accent)' : 'transparent'}`,
                  transition: 'background-color 100ms',
                }}
              >
                {/* Headshot thumbnail — small square */}
                <PlayerThumbnail playerId={result.id} playerName={result.full_name} />

                {/* Info */}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 700,
                    fontSize: 13,
                    color: 'var(--color-text)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    letterSpacing: '0.01em',
                  }}>
                    {result.full_name}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 1 }}>
                    {result.team_name && (
                      <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: 'var(--color-text-muted)' }}>
                        {result.team_name}
                      </span>
                    )}
                    {result.seasons_active && (
                      <>
                        <span style={{ color: 'var(--color-border-2)', fontSize: 11 }}>·</span>
                        <span style={{ fontFamily: "'Barlow', sans-serif", fontSize: 11, color: 'var(--color-text-muted)' }}>
                          {result.seasons_active}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {result.is_active && (
                  <div
                    style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-success)', flexShrink: 0 }}
                    title="Active player"
                  />
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* No results */}
      {open && query.length >= 2 && results.length === 0 && !loading && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            zIndex: 50,
            background: 'var(--color-surface)',
            border: '2px solid var(--color-border)',
            borderRadius: 4,
            padding: '10px 14px',
          }}
        >
          <p style={{ fontFamily: "'Barlow', sans-serif", fontSize: 13, color: 'var(--color-text-muted)', textAlign: 'center' }}>
            No players found for "<span style={{ color: 'var(--color-text)' }}>{query}</span>"
          </p>
        </div>
      )}
    </div>
  );
}

// Small headshot for dropdown (rectangular, not circle)
function PlayerThumbnail({ playerId, playerName }: { playerId: string; playerName: string }) {
  const [failed, setFailed] = useState(false);
  const url = `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`;

  return (
    <div style={{ width: 32, height: 32, flexShrink: 0, overflow: 'hidden', borderRadius: 2, background: 'var(--color-surface-2)' }}>
      {!failed ? (
        <img
          src={url}
          alt={playerName}
          style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }}
          onError={() => setFailed(true)}
          loading="lazy"
        />
      ) : (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="20" height="20" viewBox="0 0 100 120" fill="none">
            <circle cx="50" cy="38" r="22" fill="var(--color-border-2)" />
            <ellipse cx="50" cy="105" rx="40" ry="32" fill="var(--color-border-2)" />
          </svg>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" strokeOpacity="0.2" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}
