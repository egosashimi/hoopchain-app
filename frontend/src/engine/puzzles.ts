// ============================================================
// HOOPCHAIN — In-browser puzzles, scoring and share text
// Ports of backend puzzle_service / free_play_service / score_service.
// Daily puzzles come from public/data/daily.json (append-only schedule);
// dates past its end are generated deterministically from the date.
// ============================================================

import type { Difficulty, GameMode, Puzzle } from '../types';
import { headshotUrl, loadGraph, type HoopGraph } from './graph';

const PUZZLE_EPOCH = Date.UTC(2026, 0, 1);
const DAY_MS = 86_400_000;

const PLAYABLE_MODES: GameMode[] = ['classic', 'wild'];

// Mirrors data/etl/19_export_static_data.py (0=Monday): ramps easy → hard through the week
const DAILY_DIFFICULTY_BY_WEEKDAY: Difficulty[] = ['easy', 'easy', 'medium', 'medium', 'medium', 'hard', 'hard'];

// GOAT dribble-count bands (dribbles = intermediate players)
const DIFFICULTY_BANDS: Record<Difficulty, [number, number]> = {
  easy: [1, 1],
  medium: [2, 2],
  hard: [3, 999],
};
const MAX_SAMPLE_ATTEMPTS = 100;
const DIFFICULTY_RELAX_AT = 60;

const ERA_ORDER = ['2020s', '2010s', '2000s', '1990s', '1980s', 'pre1980'];
const ERA1_WEIGHTS = [0.35, 0.35, 0.15, 0.10, 0.04, 0.01];

// ------------------------------------
// Dates
// ------------------------------------

/** Today's puzzle date (UTC, matching the old backend and userStore). */
export function todayDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function parseDate(d: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) throw new Error('Invalid date format. Use YYYY-MM-DD.');
  return Date.parse(`${d}T00:00:00Z`);
}

export function shiftDate(d: string, days: number): string {
  return new Date(parseDate(d) + days * DAY_MS).toISOString().slice(0, 10);
}

function weekday(d: string): number {
  return (new Date(parseDate(d)).getUTCDay() + 6) % 7; // 0=Monday
}

// ------------------------------------
// Randomness
// ------------------------------------

type Rng = () => number;

/** Deterministic PRNG (mulberry32) seeded from a string. */
function seededRng(seed: string): Rng {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function choice<T>(items: T[], rng: Rng): T {
  return items[Math.floor(rng() * items.length)];
}

function weightedChoice<T>(items: T[], weights: number[], rng: Rng): T {
  const total = weights.reduce((s, w) => s + w, 0);
  let r = rng() * total;
  for (let i = 0; i < items.length; i++) {
    r -= weights[i];
    if (r < 0) return items[i];
  }
  return items[items.length - 1];
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

/** Deterministic positive-32-bit pair ID (order-independent CRC32), same as the backend's. */
export function pairId(startId: string, endId: string): number {
  const [a, b] = startId < endId ? [startId, endId] : [endId, startId];
  let crc = 0xffffffff;
  for (const byte of new TextEncoder().encode(`${a}:${b}`)) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return ((crc ^ 0xffffffff) >>> 0) & 0x7fffffff;
}

export function difficultyLabel(dribbles: number): Difficulty {
  if (dribbles <= 1) return 'easy';
  if (dribbles <= 2) return 'medium';
  return 'hard';
}

// ------------------------------------
// Puzzle payloads
// ------------------------------------

function endpoint(g: HoopGraph, i: number) {
  const n = g.nodes[i];
  return { id: n.id, full_name: n.name, headshot_url: headshotUrl(n.id), is_active: n.isActive };
}

function buildPuzzle(g: HoopGraph, a: number, b: number, puzzleDate: string, puzzleId: number, mode: GameMode = 'classic'): Puzzle {
  const hops = g.optimalHopsByMode(a, b, PLAYABLE_MODES);
  // Requested mode first, as the backend ordered it
  const available = PLAYABLE_MODES
    .filter((m) => hops[m] !== undefined)
    .sort((x, y) => Number(y === mode) - Number(x === mode));
  const modeHops = hops[mode] ?? hops.classic ?? 1;
  return {
    puzzle_id: puzzleId,
    puzzle_date: puzzleDate,
    start_player: endpoint(g, a),
    end_player: endpoint(g, b),
    difficulty: difficultyLabel(modeHops),
    optimal_hops: modeHops,
    available_modes: available,
    optimal_hops_by_mode: hops,
  };
}

// ------------------------------------
// Free play (port of free_play_service.generate_free_play_puzzle)
// ------------------------------------

function pickEras(difficulty: Difficulty | undefined, rng: Rng): [string, string] {
  if (difficulty === 'hard') return ['hard_modern', 'hard_classic'];
  if (difficulty === 'medium') {
    return [choice(['2020s', '2010s'], rng), weightedChoice(['1990s', '1980s', '2000s'], [0.55, 0.3, 0.15], rng)];
  }
  const era1 = weightedChoice(ERA_ORDER, ERA1_WEIGHTS, rng);
  const w2 = ERA1_WEIGHTS.map((w, i) => (ERA_ORDER[i] === era1 ? w * 0.2 : w));
  return [era1, weightedChoice(ERA_ORDER, w2, rng)];
}

function sampleFreePlay(
  g: HoopGraph,
  mode: GameMode,
  difficulty: Difficulty | undefined,
  excludeIds: Set<number>,
  rng: Rng,
): { a: number; b: number } | null {
  const flat = [...new Set(Object.values(g.pools).flat())];
  if (flat.length < 2) return null;

  for (let attempt = 0; attempt < MAX_SAMPLE_ATTEMPTS; attempt++) {
    const relaxed = attempt >= DIFFICULTY_RELAX_AT;
    // Hard keeps era-gap sampling when relaxed (only the GOAT band drops)
    const eraDifficulty = !relaxed || difficulty === 'hard' ? difficulty : undefined;
    const [era1, era2] = pickEras(eraDifficulty, rng);
    const list1 = g.pools[era1]?.length ? g.pools[era1] : flat;
    const list2 = g.pools[era2]?.length ? g.pools[era2] : flat;
    const a = choice(list1, rng);
    const b = choice(list2, rng);
    if (a === b) continue;
    if (excludeIds.has(pairId(g.nodes[a].id, g.nodes[b].id))) continue;

    const path = g.shortestPath(a, b, mode);
    if (!path) continue;
    const hops = path.length - 2;
    // Hard always needs ≥ 2 dribbles; otherwise reject direct teammates (GOAT 0)
    if (hops < (difficulty === 'hard' ? 2 : 1)) continue;
    if (difficulty && !relaxed) {
      const [lo, hi] = DIFFICULTY_BANDS[difficulty];
      if (hops < lo || hops > hi) continue;
    }
    return { a, b };
  }
  return null;
}

export async function getFreePlayPuzzle(mode: GameMode = 'classic', difficulty?: Difficulty, excludeIds: number[] = []): Promise<Puzzle | null> {
  const g = await loadGraph();
  const pick = sampleFreePlay(g, mode, difficulty, new Set(excludeIds), Math.random);
  if (!pick) return null;
  const [startId, endId] = [g.nodes[pick.a].id, g.nodes[pick.b].id];
  return buildPuzzle(g, pick.a, pick.b, `free:${startId}:${endId}`, pairId(startId, endId), mode);
}

// ------------------------------------
// Daily
// ------------------------------------

interface DailySchedule {
  start: string;
  puzzles: [string, string][];
}

let schedulePromise: Promise<DailySchedule> | null = null;

function loadSchedule(): Promise<DailySchedule> {
  schedulePromise ??= fetch(`${import.meta.env.BASE_URL}data/daily.json`)
    .then((r) => {
      if (!r.ok) throw new Error(`Couldn't load the puzzle schedule (HTTP ${r.status})`);
      return r.json() as Promise<DailySchedule>;
    })
    .catch((err) => {
      schedulePromise = null;
      throw err;
    });
  return schedulePromise;
}

export async function getDailyPuzzle(puzzleDate: string): Promise<Puzzle> {
  const [g, schedule] = await Promise.all([loadGraph(), loadSchedule()]);
  const puzzleId = Math.round((parseDate(puzzleDate) - PUZZLE_EPOCH) / DAY_MS) + 1;
  const offset = Math.round((parseDate(puzzleDate) - parseDate(schedule.start)) / DAY_MS);
  if (offset < 0) throw new Error('No puzzle for that date.');

  const scheduled = schedule.puzzles[offset];
  if (scheduled) {
    const a = g.indexOf('player', scheduled[0]);
    const b = g.indexOf('player', scheduled[1]);
    if (a !== undefined && b !== undefined) return buildPuzzle(g, a, b, puzzleDate, puzzleId);
  }

  // Past the schedule: same date → same seed → same puzzle for everyone
  const rng = seededRng(`hoopchain-daily-${puzzleDate}`);
  const difficulty = DAILY_DIFFICULTY_BY_WEEKDAY[weekday(puzzleDate)];
  const pick = sampleFreePlay(g, 'classic', difficulty, new Set(), rng) ?? sampleFreePlay(g, 'classic', undefined, new Set(), rng);
  if (!pick) throw new Error('Could not build a puzzle for that date.');
  return buildPuzzle(g, pick.a, pick.b, puzzleDate, puzzleId);
}

/** Puzzle metadata for scoring a finished game (daily date or "free:{start}:{end}"). */
export async function resolvePuzzle(puzzleDate: string, mode: GameMode): Promise<Puzzle> {
  if (!puzzleDate.startsWith('free:')) return getDailyPuzzle(puzzleDate);
  const [startId, endId] = puzzleDate.slice(5).split(':');
  const g = await loadGraph();
  const a = g.indexOf('player', startId);
  const b = g.indexOf('player', endId);
  if (a === undefined || b === undefined) throw new Error('Invalid puzzle_date.');
  const puzzle = buildPuzzle(g, a, b, puzzleDate, pairId(startId, endId), mode);
  // Free-play difficulty is graded on the classic GOAT, as the backend did
  puzzle.difficulty = difficultyLabel(puzzle.optimal_hops_by_mode?.classic ?? puzzle.optimal_hops);
  return puzzle;
}

// ------------------------------------
// Scoring + share text (port of score_service)
// ------------------------------------

const MODE_LABEL: Record<GameMode, string> = {
  classic: 'CLASSIC MODE',
  wild: 'WILD MODE',
  coach: 'COACH MODE',
};

export function calculateScore(hopsUsed: number, optimalHops: number, timeSeconds: number, difficulty: Difficulty, edgeTypes: string[]): number {
  const base = 1000;
  const efficiency = Math.max(0, base - (hopsUsed - optimalHops) * 150);
  const speedBonus = timeSeconds < 120 ? Math.trunc((120 - timeSeconds) * 1.5) : timeSeconds > 300 ? -100 : 0;
  const diffMult = { easy: 0.8, medium: 1.0, hard: 1.3 }[difficulty] ?? 1.0;
  const rare = new Set(['college', 'draft_class', 'all_star']);
  const diversityBonus = new Set(edgeTypes.filter((t) => rare.has(t))).size * 50;
  return Math.max(0, Math.trunc((efficiency + speedBonus + diversityBonus) * diffMult));
}

export function generateShareText(opts: {
  puzzleDate: string;
  startName: string;
  endName: string;
  hopsUsed: number;
  optimalHops: number;
  streak: number;
  gaveUp: boolean;
  mode: GameMode;
  isFreeplay: boolean;
}): string {
  let dateHeader = opts.puzzleDate;
  if (opts.isFreeplay) {
    dateHeader = 'FREE PLAY';
  } else if (/^\d{4}-\d{2}-\d{2}$/.test(opts.puzzleDate)) {
    const d = new Date(parseDate(opts.puzzleDate));
    const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
    dateHeader = `${month} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
  }

  const modeLabel = MODE_LABEL[opts.mode] ?? `${opts.mode.toUpperCase()} MODE`;
  const resultLine = opts.gaveUp
    ? `${modeLabel} | gave up ❌`
    : `${modeLabel} | ${opts.hopsUsed} ${opts.hopsUsed === 1 ? 'dribble' : 'dribbles'} (GOAT: ${opts.optimalHops})${opts.hopsUsed === opts.optimalHops ? ' 🎯' : ''}`;

  const lines = [`HOOPCHAIN 🏀 ${dateHeader}`, `${opts.startName} → ${opts.endName}`, resultLine];
  if (opts.streak >= 3) lines.push(`🔥 ${opts.streak}-day streak`);
  lines.push('', 'hoopchain.app');
  return lines.join('\n');
}
