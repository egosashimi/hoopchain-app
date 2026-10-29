// ============================================================
// HOOPCHAIN — Shared TypeScript Types
// ============================================================

// ------------------------------------
// Core Domain Types
// ------------------------------------

export type EdgeType = 'teammate' | 'college' | 'draft_class' | 'coached_by' | 'all_star';
export type NodeType = 'player' | 'coach';
export type Difficulty = 'easy' | 'medium' | 'hard';
export type GameStatus = 'idle' | 'playing' | 'won' | 'given_up';
// Modes: Classic = teammates only, Wild = all edge types, Coach = coached_by only
export type GameMode = 'classic' | 'wild' | 'coach';

// ------------------------------------
// Player / Search
// ------------------------------------

export interface Player {
  id: string;
  full_name: string;
  first_name?: string;
  last_name?: string;
  position?: string;
  college?: string;
  draft_year?: number;
  is_active: boolean;
  headshot_url?: string;
  team_name?: string;
  seasons_active?: string;
}

export interface PlayerSearchResult {
  id: string;
  full_name: string;
  position?: string;
  team_name?: string;
  headshot_url?: string;
  seasons_active?: string;
  is_active?: boolean;
}

// ------------------------------------
// Chain / Graph Node
// ------------------------------------

export interface ChainNode {
  id: string;
  type: NodeType;
  name: string;
  headshotUrl?: string;
  teamName?: string;
  yearsActive?: string;
  isActive?: boolean;
  // Edge FROM this node to the next node
  connectionLabel?: string;
  edgeType?: EdgeType;
}

// ------------------------------------
// Puzzle
// ------------------------------------

export interface Puzzle {
  puzzle_id: number;
  puzzle_date: string;           // YYYY-MM-DD
  start_player: PuzzleEndpoint;
  end_player: PuzzleEndpoint;
  difficulty: Difficulty;
  optimal_hops: number;
  available_modes: GameMode[];                              // modes with valid paths
  optimal_hops_by_mode?: Partial<Record<GameMode, number>>; // unweighted BFS per mode
}

export interface PuzzleEndpoint {
  id: string;
  full_name: string;
  headshot_url?: string;
  team_name?: string;
  is_active?: boolean;
}

// ------------------------------------
// API Responses
// ------------------------------------

export interface HealthResponse {
  status: string;
  graph_nodes: number;
  graph_edges: number;
  mock_mode: boolean;
}

export interface HopValidationRequest {
  from_id: string;
  from_type: NodeType;
  to_id: string;
  to_type: NodeType;
  mode?: GameMode;
}

export interface HopValidationResponse {
  valid: boolean;
  edge_type?: EdgeType;
  edge_label?: string;
  weight?: number;
  reason?: string;  // 'wrong_edge_type' when mode filtering rejects a valid edge
}

export interface PathValidationRequest {
  puzzle_date: string;
  path: Array<{ type: NodeType; id: string }>;
  mode?: GameMode;
}

export interface PathValidationResponse {
  valid: boolean;
  complete: boolean;
  hops: number;
  optimal_hops: number;
  edge_types: EdgeType[];
}

export interface GameCompleteRequest {
  puzzle_date: string;
  client_id: string;
  path: ChainNode[];
  hops_used: number;
  time_seconds: number;
  gave_up: boolean;
  mode?: GameMode;
}

export interface OptimalPathNode {
  id: string;
  type: string;
  name: string;
  headshot_url?: string;
  edge_type?: EdgeType;
  connection_label?: string;
}

export interface GameCompleteResponse {
  score: number;
  streak?: number;   // absent for free play
  share_text: string;
  optimal_path?: OptimalPathNode[];
}

export interface GameStats {
  streak: number;
  max_streak: number;
  total_played: number;
  win_pct: number;
  avg_score: number;
  avg_hops: number;
  last_played?: string;
}

export interface LeaderboardEntry {
  rank: number;
  client_id_hash: string;
  hops: number;
  time_seconds: number;
  score: number;
}

// ------------------------------------
// Zustand Store Interfaces
// ------------------------------------

export interface GameState {
  puzzle: Puzzle | null;
  status: GameStatus;
  mode: GameMode;
  isFreePlay: boolean;

  chains: Record<string, ChainNode[]>;  // per-mode chains; active = chains[mode]
  seenFreePlayPuzzleIds: number[];      // puzzle_ids seen this session, sent as exclude_ids

  selectedNode: ChainNode | null;

  lastHopValid: boolean | null;
  lastHopLabel: string | null;
  lastHopEdgeType: EdgeType | null;
  invalidAttempts: number;
  errorMessage: string | null;

  startedAt: number | null;
  completedAt: number | null;

  score: number | null;
  shareText: string | null;
  optimalPath: OptimalPathNode[] | null;

  isValidating: boolean;
  showResult: boolean;
  showHowToPlay: boolean;
  showStats: boolean;
  showFreePlay: boolean;
}

export interface UserState {
  clientId: string;
  streak: number;
  maxStreak: number;
  totalPlayed: number;
  totalWon: number;
  avgScore: number;
  avgHops: number;
  lastPlayed: string | null;
  scoreTotal: number;
  theme: 'dark' | 'light';
}

// ------------------------------------
// Mode Metadata
// Classic = teammates only | Wild = all edges | Coach = coached_by only
// ------------------------------------

export const MODE_META: Record<GameMode, { label: string; color: string; shortLabel: string }> = {
  classic: { label: 'Classic', shortLabel: 'Classic', color: '#e8520a' },  // burnt orange
  wild:    { label: 'Wild',    shortLabel: 'Wild',    color: '#d4a017' },  // mustard yellow
  coach:   { label: 'Coach',   shortLabel: 'Coach',   color: '#7c4daa' },  // muted purple
};

// ------------------------------------
// Edge Type Metadata
// ------------------------------------

export const EDGE_TYPE_META: Record<EdgeType, { label: string; color: string; emoji: string; cssClass: string }> = {
  teammate:    { label: 'Teammate',    color: '#22c55e', emoji: '🟢', cssClass: 'edge-teammate' },
  college:     { label: 'College',     color: '#3b82f6', emoji: '🔵', cssClass: 'edge-college' },
  draft_class: { label: 'Draft Class', color: '#eab308', emoji: '🟡', cssClass: 'edge-draft' },
  coached_by:  { label: 'Coach',       color: '#7c4daa', emoji: '🟣', cssClass: 'edge-coach' },
  all_star:    { label: 'All-Star',    color: '#ef4444', emoji: '🔴', cssClass: 'edge-allstar' },
};

// ------------------------------------
// Utility
// ------------------------------------

export function formatElapsedTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function getHeadshotUrl(playerId: string): string {
  return `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`;
}

export function generateClientId(): string {
  return `hc-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
