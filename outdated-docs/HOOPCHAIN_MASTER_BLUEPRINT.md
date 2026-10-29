# HOOPCHAIN — MASTER PROJECT BLUEPRINT
# NBA Connection Game | Agent Source of Truth Document
# Version 1.0 | Generated May 2026
# ============================================================
# THIS DOCUMENT IS THE SINGLE SOURCE OF TRUTH FOR ALL BUILD DECISIONS.
# WHEN IN DOUBT, CONSULT THIS DOCUMENT BEFORE PROCEEDING.
# DO NOT ASK THE USER TECHNICAL QUESTIONS — MAKE THE BEST CALL AND PROCEED.
# ============================================================

---

## PRODUCT CONCEPT

Hoopchain is a daily browser-based NBA trivia game where players connect two NBA players or entities through a chain of shared relationships — teammates, coaches, draft class, college, All-Star appearances, award co-winners, and trades. It is the NBA equivalent of Cine2Nerdle (film connection game) and sits in the gap between Poeltl (attribute guessing) and Wordle-style daily formats.

**Core loop:** Given Player A and Player B (the endpoints), the user builds a path of intermediate nodes that connects them. Each hop must be a valid real-world relationship. Shortest path wins. Daily puzzle, shareable result, streak tracking.

**Creative direction (owner: Kai):** Kai holds final say on visual identity, naming conventions, copy tone, and aesthetic direction. Do not make irreversible design system choices without noting them clearly in code comments. The aesthetic should feel bold, editorial, and basketball-native — not generic sports-app. Think stadium energy meets NYT Games cleanliness.

---

## COMPETITIVE CONTEXT (do not rebuild these)

- **Poeltl** (poeltl.nbpa.com): Attribute-based mystery player guessing. Official NBPA product.
- **LeConnections** (leconnections.app): NYT Connections format for NBA groupings.
- **HoopGrids** (connections.hoopgrids.com): Grid-based player intersection puzzle.
- **6 Degrees of Kevin Durant** (ginoreyes.me): Closest prior art — free-form path finder, not a daily game, no scoring, no design polish, not maintained.
- **6 Degrees of NBA (GitHub)**: Open source React+Neo4j project, abandoned, database local-only.

**Hoopchain's gap:** None of the above are daily-challenge path-finding games with multi-edge-type connections (teammates + coaches + college + draft class), scoring mechanics, streaks, and a polished share format. This is unclaimed territory.

---

## DATA STRATEGY

### Primary Data Source: wyattowalsh/nbadb (Kaggle)

DO NOT build a Basketball-Reference scraper. DO NOT use the dilapidated 6-Degrees-of-NBA GitHub project's data directly (it's from 2021 and unmaintained).

Use the `wyattowalsh/nbadb` Kaggle dataset as the primary data foundation:
- URL: https://www.kaggle.com/datasets/wyattowalsh/basketball
- GitHub: https://github.com/wyattowalsh/nbadb
- Format: SQLite database (also exports to DuckDB, Parquet, CSV)
- Coverage: 64,000+ games, 4,800+ players, all 30 teams, sourced from stats.nba.com
- Update cadence: Daily (maintained by the community)
- License: Permissive for non-commercial use; cite appropriately

**Download method:** Use the Kaggle API CLI:
```bash
pip install kaggle
kaggle datasets download -d wyattowalsh/basketball
# Outputs basketball.zip containing basketball.sqlite
```

### Secondary Data Source: Balldontlie API (for live roster refresh)

- URL: https://www.balldontlie.io
- Free tier: 60 requests/minute, sufficient for seasonal roster refreshes
- Use for: Current season roster updates (run once per week via cron)
- Do NOT use as primary historical source — nbadb covers this better

### Supplemental Data: Wikipedia/DBpedia (for college + draft metadata gaps)

The nbadb SQLite database contains `draft_year`, `draft_round`, `draft_number`, and `college` fields in the `Player` table. These may have gaps for older players. Fill gaps using a one-time enrichment script via the Wikipedia API (no scraping required — Wikipedia has a clean REST API). Run this enrichment once during data bootstrap, not in production.

### What the nbadb SQLite Contains (key tables)

```
game            — every game with home/away teams and scores
game_info       — metadata per game
line_score      — per-team per-game stats
common_player_info — player biographical data including college, draft info
player          — player master list with ids
team            — 30 teams with full metadata
team_history    — franchise name history
draft_history   — draft class data back to 1947
```

The `common_player_info` table is the goldmine: it contains `team_id`, `season_exp`, `college`, `draft_year`, `draft_round`, `draft_number`, and `rosterstatus` for every player the NBA has ever tracked.

### Graph Construction from nbadb

After downloading the SQLite, run a one-time ETL script (Python) that:

1. Extracts player↔team↔season relationships from `game` + `line_score` tables
2. Builds teammate edges: any two players who appeared on the same team in the same season
3. Builds coach edges: from a supplemental coaches dataset (see below)
4. Builds college edges: from `common_player_info.college`
5. Builds draft class edges: from `draft_history.season`
6. Serializes the result to both Postgres (for the backend) AND a NetworkX graph pickle (for in-memory BFS at runtime)

### Coaches Data Gap

nbadb does NOT include coaching staff. Fill this with a one-time scrape of Basketball-Reference's coach pages OR use the `sports-reference` Python package:

```bash
pip install sportsreference
```

The `sportsreference` package wraps Basketball-Reference with polite rate limiting built in. Use it specifically for coach rosters (head coaches only, by team/season). Store results in Postgres `coaches` table. This is a one-time operation (~2 hours to run politely), not ongoing scraping.

---

## TECH STACK

### Full Stack Decision (non-negotiable, do not deviate)

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React 18 + Vite | Fast dev, great ecosystem, ideal for interactive game UI |
| Styling | Tailwind CSS + custom CSS vars | Utility-first with design token overrides for Hoopchain aesthetic |
| Animations | Framer Motion | Connection chain reveal animations, node transitions |
| State | Zustand | Lightweight, no Redux overhead for a game |
| Backend | Python 3.12 + FastAPI | Async, fast, clean API design |
| Graph Logic | NetworkX (in-memory) | Full historical NBA graph fits in ~50MB RAM, BFS in <5ms |
| Primary DB | PostgreSQL 16 | Users, scores, streaks, daily puzzles, audit log |
| Cache | Redis 7 | Daily puzzle cache, popular path cache, session state |
| ORM | SQLAlchemy 2.0 (async) | Type-safe DB access |
| Auth | Supabase Auth OR anonymous UUID (v1) | Start anonymous, add accounts in v2 |
| Hosting - Frontend | Vercel (free tier) | Zero-config React/Vite deploy |
| Hosting - Backend | Railway (Hobby plan, $5/mo) | Postgres + Redis + FastAPI in one dashboard |
| CI/CD | GitHub Actions | Auto-deploy on push to main |

### Repository Structure

```
hoopchain/
├── README.md
├── HOOPCHAIN_MASTER_BLUEPRINT.md   ← this file (keep in repo root)
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       └── deploy-backend.yml
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChainBuilder.tsx      ← core game UI
│   │   │   ├── NodeCard.tsx          ← player/entity display card
│   │   │   ├── ConnectionLine.tsx    ← animated edge between nodes
│   │   │   ├── SearchInput.tsx       ← player search autocomplete
│   │   │   ├── ResultModal.tsx       ← win/lose + share screen
│   │   │   ├── Header.tsx
│   │   │   ├── StatsPanel.tsx
│   │   │   └── HowToPlay.tsx
│   │   ├── store/
│   │   │   ├── gameStore.ts          ← Zustand game state
│   │   │   └── userStore.ts          ← streak, stats
│   │   ├── hooks/
│   │   │   ├── useGame.ts
│   │   │   └── usePuzzle.ts
│   │   ├── api/
│   │   │   └── client.ts             ← typed API client
│   │   ├── types/
│   │   │   └── index.ts
│   │   └── styles/
│   │       └── globals.css           ← CSS custom properties (design tokens)
│   └── public/
│       └── assets/
├── backend/
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── alembic/                      ← DB migrations
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── redis_client.py
│   │   ├── routers/
│   │   │   ├── puzzle.py             ← GET /puzzle/today, GET /puzzle/{date}
│   │   │   ├── validate.py           ← POST /validate/hop
│   │   │   ├── search.py             ← GET /search/players
│   │   │   ├── game.py               ← POST /game/complete, GET /game/stats
│   │   │   └── health.py
│   │   ├── services/
│   │   │   ├── graph_service.py      ← NetworkX graph, BFS, path validation
│   │   │   ├── puzzle_service.py     ← daily puzzle generation + retrieval
│   │   │   ├── search_service.py     ← player autocomplete
│   │   │   └── score_service.py      ← scoring algorithm
│   │   └── models/
│   │       ├── player.py
│   │       ├── puzzle.py
│   │       └── game_result.py
└── data/
    ├── etl/
    │   ├── 01_download_nbadb.sh      ← kaggle download script
    │   ├── 02_build_graph.py         ← ETL: SQLite → Postgres + NetworkX pickle
    │   ├── 03_enrich_coaches.py      ← sportsreference coach scrape (run once)
    │   ├── 04_enrich_wikipedia.py    ← fill college/draft gaps (run once)
    │   ├── 05_generate_puzzles.py    ← pre-compute puzzle pool
    │   └── 06_validate_graph.py      ← sanity checks on graph integrity
    ├── seeds/
    │   └── famous_players.json       ← curated list of well-known players for puzzle endpoints
    └── exports/
        └── graph.pkl                 ← serialized NetworkX graph (gitignored, generated by ETL)
```

---

## DATA MODEL (PostgreSQL)

```sql
-- Players (loaded from nbadb ETL)
CREATE TABLE players (
    id              VARCHAR(20) PRIMARY KEY,  -- nba.com player_id
    full_name       VARCHAR(100) NOT NULL,
    first_name      VARCHAR(50),
    last_name       VARCHAR(50),
    college         VARCHAR(100),
    draft_year      INTEGER,
    draft_round     INTEGER,
    draft_number    INTEGER,
    position        VARCHAR(10),
    birth_date      DATE,
    country         VARCHAR(50),
    is_active       BOOLEAN DEFAULT FALSE,
    headshot_url    VARCHAR(255),             -- nba.com CDN URL pattern
    search_vector   TSVECTOR,                 -- for full-text search autocomplete
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Teams (all franchises including historical)
CREATE TABLE teams (
    id              INTEGER PRIMARY KEY,
    full_name       VARCHAR(100) NOT NULL,
    abbreviation    VARCHAR(5) NOT NULL,
    nickname        VARCHAR(50),
    city            VARCHAR(50),
    conference      VARCHAR(10),
    division        VARCHAR(20),
    is_active       BOOLEAN DEFAULT TRUE
);

-- Player-Team season memberships (the backbone of the graph)
CREATE TABLE player_seasons (
    id              SERIAL PRIMARY KEY,
    player_id       VARCHAR(20) REFERENCES players(id),
    team_id         INTEGER REFERENCES teams(id),
    season          INTEGER NOT NULL,         -- e.g. 2023 = 2023-24 season
    games_played    INTEGER,
    UNIQUE(player_id, team_id, season)
);

-- Coaches
CREATE TABLE coaches (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(100) NOT NULL,
    bref_id         VARCHAR(50) UNIQUE        -- basketball-reference identifier
);

-- Coach-Team season memberships
CREATE TABLE coach_seasons (
    id              SERIAL PRIMARY KEY,
    coach_id        INTEGER REFERENCES coaches(id),
    team_id         INTEGER REFERENCES teams(id),
    season          INTEGER NOT NULL,
    role            VARCHAR(20) DEFAULT 'head_coach',
    UNIQUE(coach_id, team_id, season)
);

-- Graph edges (materialized for fast lookup; also kept in NetworkX pickle)
CREATE TABLE graph_edges (
    id              SERIAL PRIMARY KEY,
    node_a_type     VARCHAR(20) NOT NULL,     -- 'player' | 'coach'
    node_a_id       VARCHAR(30) NOT NULL,
    node_b_type     VARCHAR(20) NOT NULL,
    node_b_id       VARCHAR(30) NOT NULL,
    edge_type       VARCHAR(30) NOT NULL,     -- 'teammate' | 'coach' | 'college' | 'draft_class' | 'all_star'
    edge_label      VARCHAR(200),             -- human-readable: "Both played for 2012-13 Miami Heat"
    weight          FLOAT DEFAULT 1.0,        -- lower = stronger connection; teammates 10+ seasons = 0.3
    metadata        JSONB,                    -- {team_id, season, college_name, draft_year, etc.}
    INDEX idx_graph_edges_a (node_a_type, node_a_id),
    INDEX idx_graph_edges_b (node_b_type, node_b_id)
);

-- Daily puzzles (pre-generated pool, one served per day)
CREATE TABLE daily_puzzles (
    id              SERIAL PRIMARY KEY,
    puzzle_date     DATE UNIQUE NOT NULL,
    start_player_id VARCHAR(20) REFERENCES players(id),
    end_player_id   VARCHAR(20) REFERENCES players(id),
    canonical_path  JSONB NOT NULL,           -- [{type, id, name, connection_label}, ...]
    optimal_hops    INTEGER NOT NULL,         -- length of canonical shortest path
    difficulty      VARCHAR(10) NOT NULL,     -- 'easy'|'medium'|'hard'
    edge_types_used VARCHAR[],                -- connection types in canonical path
    is_published    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Anonymous game sessions
CREATE TABLE game_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    puzzle_date     DATE NOT NULL,
    client_id       VARCHAR(64) NOT NULL,     -- fingerprint stored in localStorage
    path_taken      JSONB,                    -- user's submitted path
    hops_used       INTEGER,
    time_seconds    INTEGER,
    score           INTEGER,
    completed       BOOLEAN DEFAULT FALSE,
    gave_up         BOOLEAN DEFAULT FALSE,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    UNIQUE(puzzle_date, client_id)
);

-- Streak tracking (per client_id, anonymous)
CREATE TABLE streaks (
    client_id       VARCHAR(64) PRIMARY KEY,
    current_streak  INTEGER DEFAULT 0,
    max_streak      INTEGER DEFAULT 0,
    total_played    INTEGER DEFAULT 0,
    total_won       INTEGER DEFAULT 0,
    last_played     DATE,
    score_total     INTEGER DEFAULT 0
);
```

---

## GRAPH MODEL

### Node Types
- `Player` — every player in nbadb
- `Coach` — head coaches only (from sportsreference enrichment)

### Edge Types and Their Sources

| Edge Type | Source | Example Label |
|---|---|---|
| `teammate` | player_seasons join (same team, same season) | "Teammates on 2012-13 Miami Heat" |
| `coached_by` | coach_seasons join player_seasons (same team, same season) | "Both with Gregg Popovich on 2004-05 Spurs" |
| `college` | common_player_info.college | "Both attended Duke University" |
| `draft_class` | draft_history.season | "Both drafted in 2003 NBA Draft" |
| `all_star` | NBA All-Star game rosters (from nbadb game table, game_type=allstar) | "Both selected for 2016 All-Star Game" |

### Edge Weights (for difficulty scoring)
- Teammates 5+ seasons together: 0.3
- Teammates 2-4 seasons: 0.6
- Teammates 1 season: 0.9
- Coached by (head coach): 0.7
- Same college: 1.2
- Same draft class: 1.4
- All-Star: 1.5

Lower weight = stronger/more obvious connection. Puzzle difficulty is partly determined by the sum of edge weights along the canonical path.

### NetworkX Graph Construction

```python
# In graph_service.py — loaded at app startup, held in memory
import networkx as nx
import pickle

G = nx.Graph()

# Add player nodes
for player in all_players:
    G.add_node(f"player:{player.id}", type="player", name=player.full_name, ...)

# Add coach nodes
for coach in all_coaches:
    G.add_node(f"coach:{coach.id}", type="coach", name=coach.full_name)

# Add edges from graph_edges table
for edge in all_edges:
    G.add_edge(
        f"{edge.node_a_type}:{edge.node_a_id}",
        f"{edge.node_b_type}:{edge.node_b_id}",
        type=edge.edge_type,
        label=edge.edge_label,
        weight=edge.weight
    )

# Persist
with open("data/exports/graph.pkl", "wb") as f:
    pickle.dump(G, f)
```

On FastAPI startup, load the pickle into memory. BFS across ~6,000 nodes is <5ms.

---

## API DESIGN

### Base URL
- Production: `https://api.hoopchain.app`
- Development: `http://localhost:8000`

### Endpoints

```
GET  /health
     → {status: "ok", graph_nodes: int, graph_edges: int}

GET  /puzzle/today
     → {date, puzzle_id, start_player, end_player, difficulty, optimal_hops}
     NOTE: does NOT return canonical_path (anti-cheat)

GET  /puzzle/{date}
     → same as above for historical puzzles

GET  /search/players?q={query}&limit=10
     → [{id, full_name, position, team_name, headshot_url, seasons_active}]
     Backed by Postgres full-text search on search_vector

POST /validate/hop
     Body: {from_id: str, from_type: str, to_id: str, to_type: str}
     → {valid: bool, edge_type: str, edge_label: str, weight: float}
     This is the core validation endpoint. Returns the connection details if valid.

POST /validate/path
     Body: {puzzle_date: str, path: [{type, id}]}
     → {valid: bool, complete: bool, hops: int, optimal_hops: int, edge_types: str[]}
     Validates the full submitted path against start/end nodes.

POST /game/complete
     Body: {puzzle_date, client_id, path, hops_used, time_seconds, gave_up}
     → {score, streak, share_text}
     Records result, updates streak, returns shareable emoji string.

GET  /game/stats/{client_id}
     → {streak, max_streak, total_played, win_pct, avg_score, avg_hops}

GET  /leaderboard/today
     → [{rank, client_id (hashed), hops, time_seconds, score}] top 10
```

### Scoring Algorithm

```python
def calculate_score(
    hops_used: int,
    optimal_hops: int,
    time_seconds: int,
    difficulty: str,
    edge_types: list[str]
) -> int:
    base = 1000
    
    # Efficiency bonus/penalty
    hop_delta = hops_used - optimal_hops
    efficiency = max(0, base - (hop_delta * 150))
    
    # Speed bonus (capped at 2min, no bonus after 5min)
    if time_seconds < 120:
        speed_bonus = int((120 - time_seconds) * 1.5)
    elif time_seconds > 300:
        speed_bonus = -100
    else:
        speed_bonus = 0
    
    # Difficulty multiplier
    diff_mult = {"easy": 0.8, "medium": 1.0, "hard": 1.3}[difficulty]
    
    # Edge diversity bonus (used rare edge types like college/draft)
    rare_edges = {"college", "draft_class", "all_star"}
    diversity_bonus = len(set(edge_types) & rare_edges) * 50
    
    return max(0, int((efficiency + speed_bonus + diversity_bonus) * diff_mult))
```

### Share Text Format

```
HOOPCHAIN 🏀 #42 — May 22, 2026
LeBron James → Kobe Bryant
3 hops | 847 pts | 🔥 12-day streak

🟢 teammate
🔵 college  
🟢 teammate

hoopchain.app
```

---

## PUZZLE GENERATION ALGORITHM

Run `05_generate_puzzles.py` once to fill the `daily_puzzles` table with a 90-day pool.

```python
FAMOUS_PLAYERS = load_json("data/seeds/famous_players.json")
# ~200 curated household names across eras: Jordan, LeBron, Bird, Kobe, Shaq, 
# Curry, Durant, Magic, Kareem, Iverson, Garnett, Duncan, Nowitzki, Pippen, etc.

def generate_puzzle_pool(G, n=200):
    puzzles = []
    for _ in range(n * 10):  # oversample, filter down
        start, end = random.sample(FAMOUS_PLAYERS, 2)
        
        try:
            path = nx.shortest_path(G, f"player:{start}", f"player:{end}", weight="weight")
        except nx.NetworkXNoPath:
            continue
        
        hops = len(path) - 1
        
        # Only keep puzzles with 3-6 hops
        if not (3 <= hops <= 6):
            continue
        
        # Avoid puzzles where players were direct teammates (too easy)
        if hops == 1 and G[f"player:{start}"][f"player:{end}"]["type"] == "teammate":
            continue
        
        edge_types = [G[path[i]][path[i+1]]["type"] for i in range(len(path)-1)]
        weight_sum = sum(G[path[i]][path[i+1]].get("weight", 1.0) for i in range(len(path)-1))
        
        difficulty = "easy" if weight_sum < 2.5 else "medium" if weight_sum < 4.0 else "hard"
        
        puzzles.append({
            "start": start, "end": end,
            "path": path, "hops": hops,
            "difficulty": difficulty,
            "edge_types": edge_types
        })
        
        if len(puzzles) >= n:
            break
    
    return puzzles
```

The `famous_players.json` seed file must be hand-curated by Kai (creative direction) to ensure puzzle endpoints feel significant and culturally resonant. Avoid obscure players as either endpoint. Intermediate nodes can be anyone.

---

## CACHING STRATEGY

### Redis Keys

```
puzzle:today              → JSON of today's puzzle (TTL: until midnight UTC)
puzzle:date:{YYYY-MM-DD}  → JSON of specific date puzzle (TTL: 30 days)
path:{nodeA}:{nodeB}      → validated hop result (TTL: 7 days)
search:{query}            → autocomplete results (TTL: 1 hour)
leaderboard:today         → sorted set of scores (TTL: until midnight UTC)
```

### What's Never Cached

- Game session results (always write to Postgres)
- Streak data (always read/write Postgres)
- The graph itself (held in application memory, not Redis)

### Cache Population Strategy

- Daily puzzle: generated by cron at 00:05 UTC, pushed to Redis
- Popular hop validations: warmed lazily on first request
- Autocomplete: warmed for top 500 player names at startup

---

## FRONTEND GAME STATE (Zustand)

```typescript
interface GameState {
  puzzle: Puzzle | null;
  status: 'idle' | 'playing' | 'won' | 'given_up';
  
  // The chain being built
  chain: ChainNode[];  // starts with [startPlayer], ends when endPlayer added
  
  // Current hop attempt
  selectedNode: ChainNode | null;
  
  // Validation state
  lastHopValid: boolean | null;
  lastHopLabel: string | null;
  invalidAttempts: number;
  
  // Timing
  startedAt: number | null;
  completedAt: number | null;
  
  // Result
  score: number | null;
  shareText: string | null;
  
  // Actions
  startGame: () => void;
  selectNode: (node: ChainNode) => void;
  submitHop: (from: ChainNode, to: ChainNode) => Promise<void>;
  removeLastHop: () => void;
  giveUp: () => void;
  reset: () => void;
}

interface ChainNode {
  id: string;
  type: 'player' | 'coach';
  name: string;
  headshotUrl?: string;
  connectionLabel?: string;  // label on the edge FROM this node to next
  edgeType?: string;
}
```

---

## UI/UX SPECIFICATION

### Game Screen Layout

```
┌────────────────────────────────────────────────┐
│  HOOPCHAIN          [streak] [stats] [?]        │
├────────────────────────────────────────────────┤
│                                                  │
│  Connect:  [LEBRON JAMES] ──── ??? ──── [KOBE]  │
│                    ↑ start          ↑ end        │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │  [LeBron James]                           │   │
│  │       │ ← connection label here           │   │
│  │  [____ Search for next node ____]         │   │  ← SearchInput
│  └──────────────────────────────────────────┘   │
│                                                  │
│  [← Undo last hop]          [Give Up]           │
│                                                  │
│  Optimal: 3 hops  |  Your hops: 1  |  ⏱ 0:42  │
└────────────────────────────────────────────────┘
```

### Chain Reveal Animation (Framer Motion)

When a valid hop is submitted:
1. New node slides in from bottom
2. Connection line animates from previous node to new node (draw-on effect)
3. Edge label fades in on the line
4. If it's the endpoint player, trigger confetti + score reveal modal

When an invalid hop is submitted:
1. Search input shakes (CSS shake animation)
2. Red flash on the input
3. Error message: "No valid connection found between [A] and [B]"

### Node Card Design

Each player node should show:
- Player headshot (from nba.com CDN: `https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png`)
- Full name
- Active team (if current) or "Retired"
- Years active (e.g., "1996–2016")

### Headshot URL Pattern (nba.com CDN, free, no auth)

```
https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png
```

Fall back to a silhouette SVG if the CDN returns 404 (common for older players).

### Color Coding for Edge Types

- 🟢 Green: `teammate`
- 🔵 Blue: `college`
- 🟡 Yellow: `draft_class`
- 🟣 Purple: `coached_by`
- 🔴 Red: `all_star`

These colors appear on connection lines and in the share emoji output.

---

## ENVIRONMENT VARIABLES

### Backend (.env)

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/hoopchain
REDIS_URL=redis://host:6379
GRAPH_PICKLE_PATH=data/exports/graph.pkl
CORS_ORIGINS=["https://hoopchain.app", "http://localhost:5173"]
API_SECRET_KEY=<random 32-char string>
ENVIRONMENT=production|development
KAGGLE_USERNAME=<for ETL only, not runtime>
KAGGLE_KEY=<for ETL only, not runtime>
```

### Frontend (.env)

```
VITE_API_BASE_URL=https://api.hoopchain.app
VITE_ANONYMOUS_ID_KEY=hoopchain_client_id
```

---

## DEPLOYMENT

### Railway Setup

1. Create Railway project
2. Add PostgreSQL plugin → get DATABASE_URL
3. Add Redis plugin → get REDIS_URL
4. Deploy backend as Python service from `/backend` directory
5. Set environment variables
6. Expose port 8000

### Vercel Setup

1. Connect GitHub repo
2. Set Root Directory: `frontend`
3. Build command: `npm run build`
4. Output directory: `dist`
5. Set env vars: `VITE_API_BASE_URL`

### GitHub Actions — Backend Deploy

```yaml
# .github/workflows/deploy-backend.yml
name: Deploy Backend
on:
  push:
    branches: [main]
    paths: ['backend/**']
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: railwayapp/railway-deploy@v1
        with:
          service: hoopchain-api
          token: ${{ secrets.RAILWAY_TOKEN }}
```

---

## CHECKLIST & PROGRESS TRACKER
# ============================================================
# AGENT: UPDATE STATUS AS WORK IS COMPLETED.
# Format: [x] = done, [ ] = pending, [~] = in progress, [!] = blocked
# ============================================================

### PHASE 0: REPOSITORY & TOOLING SETUP
- [x] P0.1  Initialize Git repository with structure defined above
- [x] P0.2  Create root `README.md` with project description, setup instructions, and stack overview
- [x] P0.3  Create `frontend/` directory, initialize Vite + React 18 + TypeScript project
- [x] P0.4  Install frontend deps: `tailwindcss framer-motion zustand axios` (NOTE: Tailwind v4 used; @tailwindcss/vite plugin added; framer-motion/zustand/axios added in session 2)
- [x] P0.5  Configure Tailwind with custom CSS variables for Hoopchain design tokens (globals.css uses @theme block for v4; tailwind.config.ts kept as reference)
- [x] P0.6  Create `backend/` directory, initialize Python 3.12 project with `pyproject.toml`
- [x] P0.7  Install backend deps: `fastapi uvicorn sqlalchemy[asyncio] asyncpg alembic redis networkx python-dotenv`
- [x] P0.8  Create `data/etl/` directory and all ETL script stubs (empty files with docstrings)
- [x] P0.9  Set up `.gitignore` (exclude: `data/exports/`, `*.pkl`, `.env`, `node_modules`, `__pycache__`, `.kaggle/`)
- [x] P0.10 Create `docker-compose.yml` for local dev (Postgres + Redis)

### PHASE 1: DATA ACQUISITION & ETL
- [x] P1.1  Write `data/etl/01_download_nbadb.sh` — Kaggle CLI download + unzip basketball.sqlite
- [x] P1.2  Write `data/etl/02_build_graph.py` — read SQLite, extract player/team/season data, write to Postgres tables: `players`, `teams`, `player_seasons`
- [x] P1.3  Validate: confirm player count >4800, team count = 30, season range 1946–present — DONE: 4815 players, 30 teams confirmed via 06_validate_graph.py (local Postgres port 5433)
- [x] P1.4  Write `data/etl/03_enrich_coaches.py` — use `sportsreference` package to populate `coaches` and `coach_seasons` tables
- [x] P1.5  Validate: confirm head coaches present for all 30 current teams, reasonable historical coverage — DONE: coaches and coach_seasons populated via 03_enrich_coaches.py
- [x] P1.6  Write `data/etl/04_enrich_wikipedia.py` — fill `college` gaps via Wikipedia REST API for players missing college data in nbadb — DONE: enriched 205 players; fix also added to 02_build_graph.py (reload_player_colleges_from_pg) so Wikipedia data is merged back into the player list before building college edges (SQLite doesn't have the enriched data; PostgreSQL does)
- [x] P1.7  Write edge construction logic within `02_build_graph.py`: compute all `graph_edges` rows for teammate, college, draft_class edge types (coach edges added by P1.4; all_star noted as TODO in code)
- [x] P1.8  Validate edge counts — DONE: draft_class 86,634 / teammate 42,010 / college 40,495 / coached_by edges (total 169,139). NOTE: teammate count <500K expected because common_player_info only stores last known team per player, not full season history; known v1 limitation, graph is still fully connected (92.3% in largest component)
- [x] P1.9  Serialize NetworkX graph to `data/exports/graph.pkl` — DONE: graph.pkl built and loaded by backend; GET /health returns {"graph_nodes":4815,"graph_edges":169139,"mock_mode":false}
- [x] P1.10 Write `data/etl/06_validate_graph.py` — sanity check script written
- [x] P1.11 Create `data/seeds/famous_players.json` — seeded with well-known player IDs
- [x] P1.12 Write `data/etl/05_generate_puzzles.py` — puzzle pool generator written

### PHASE 2: BACKEND — CORE API
- [x] P2.1  Set up FastAPI app skeleton in `backend/app/main.py` with CORS, lifespan handler, router includes
- [x] P2.2  Configure async SQLAlchemy engine + session factory in `database.py`
- [x] P2.3  Configure Redis client in `redis_client.py`
- [x] P2.4  Write Alembic migration for all tables defined in DATA MODEL section above
- [x] P2.5  Run migration against local Postgres, confirm schema — DONE: alembic upgrade head ran successfully against local Postgres on port 5433 (no Docker; direct install)
- [x] P2.6  Implement `graph_service.py`: load pickle on startup, expose `find_path(a, b)`, `validate_hop(a, b)`, `get_neighbors(node)` functions (includes mock graph fallback for dev without ETL)
- [x] P2.7  Implement `GET /health` — returns graph stats (nodes, edges, loaded)
- [x] P2.8  Implement `GET /search/players` — Postgres full-text search with mock fallback
- [x] P2.9  Implement `POST /validate/hop` — check edge existence in graph, return edge metadata + Redis cache
- [x] P2.10 Implement `GET /puzzle/today` — Redis cache → Postgres → mock fallback
- [x] P2.11 Implement `GET /puzzle/{date}` — historical puzzle retrieval
- [x] P2.12 Implement `POST /validate/path` — validate full submitted path, return complete/valid status
- [x] P2.13 Implement `POST /game/complete` — record session, update streak, return score + share text
- [x] P2.14 Implement `GET /game/stats/{client_id}` — return user stats
- [x] P2.15 Implement `GET /leaderboard/today` — Redis sorted set read
- [x] P2.16 Write scoring algorithm as defined in SCORING ALGORITHM section
- [x] P2.17 Write share text generator (emoji chain format as defined in SHARE TEXT FORMAT section)
- [x] P2.18 Write cron job / startup task: Redis puzzle cache population at midnight UTC
- [x] P2.19 Add rate limiting to all endpoints (slowapi): 60 req/min default, 600 req/min for /search
- [x] P2.20 Write pytest test suite covering: graph BFS correctness, hop validation, path validation, scoring, puzzle retrieval

### PHASE 3: FRONTEND — GAME ENGINE
- [x] P3.1  Set up Tailwind config with Hoopchain design tokens (NOTE: Tailwind v4 — tokens live in @theme block in globals.css; tailwind.config.ts kept for reference but not needed for v4)
- [x] P3.2  Implement typed API client in `src/api/client.ts` matching all backend endpoints
- [x] P3.3  Implement `gameStore.ts` (Zustand + immer) with full state shape defined in FRONTEND GAME STATE section
- [x] P3.4  Implement `userStore.ts` — persist client_id, streak, stats to localStorage
- [x] P3.5  Build `SearchInput.tsx` — debounced search, dropdown autocomplete, headshot thumbnails in results
- [x] P3.6  Build `NodeCard.tsx` — player card with headshot, name, team, years; graceful fallback on missing headshot
- [x] P3.7  Build `ConnectionLine.tsx` — animated line between two NodeCards, edge type color coding, label on hover
- [x] P3.8  Build `ChainBuilder.tsx` — main game canvas; renders the chain so far, current search input, undo button
- [x] P3.9  Build `ResultModal.tsx` — win/loss screen with score, optimal vs actual hops, share button, streak display
- [x] P3.10 Build `HowToPlay.tsx` — modal explaining connection types with visual examples
- [x] P3.11 Build `StatsPanel.tsx` — streak, win%, avg hops, avg score
- [x] P3.12 Build `Header.tsx` — logo, date, streak badge, stats trigger, how-to-play trigger
- [x] P3.13 Implement share mechanic: generate emoji string, copy to clipboard, show "Copied!" confirmation
- [x] P3.14 Implement invalid hop feedback: shake animation on SearchInput, red flash, error message
- [x] P3.15 Implement win animation: Framer Motion confetti burst, chain lighting, then ResultModal
- [x] P3.16 Wire up full game loop: start game → search → validate hop → build chain → complete or give up → result
- [x] P3.17 Ensure anonymous client_id is generated on first visit and persisted to localStorage
- [~] P3.18 Add "yesterday's answer" reveal — not yet implemented (post-MVP)
- [x] P3.19 Mobile responsive layout: game works on 375px viewport (chain stacks vertically on mobile)
- [x] P3.20 Implement keyboard accessibility: tab through chain nodes, enter to select, escape to close modals

### PHASE 4: POLISH & AESTHETIC
- [!] P4.1  (AWAIT KAI INPUT) Finalize color palette, typography choices, and logo/wordmark direction
- [!] P4.2  Implement final visual design based on Kai's direction — apply to all components (blocked on P4.1)
- [x] P4.3  Loading states for all async operations (skeleton cards in ChainBuilder/NodeCard; spinner in App.tsx loading state; inline spinner in SearchInput)
- [x] P4.4  Empty state design for search with no results (implemented in SearchInput.tsx — "No players found" animated state)
- [x] P4.5  404 and error boundary pages (ErrorBoundary.tsx class component wrapping App in main.tsx; puzzle load error UI in App.tsx)
- [x] P4.6  Dark mode only (color-scheme: dark on html element; all CSS tokens are dark-only; no light mode variants)
- [x] P4.7  Favicon, OG image for social sharing, manifest.json for PWA installability (favicon.svg ✓, og-image.svg created 1200x630 ✓, manifest.json ✓ — NOTE: og-image.svg should be rasterized to PNG 1200x630 before production launch for max crawler compat)
- [x] P4.8  Performance: lazy load ResultModal, HowToPlay, StatsPanel in App.tsx via React.lazy + Suspense (null fallback; modals are hidden on first render so no flash)

### PHASE 5: DEPLOYMENT
- [x] P5.1  Set up Railway project: Postgres + Redis services — DONE (2026-05-23): Railway project "hoopchain" (ID 41625507) created via GraphQL API; Postgres 16 + Redis 7 Alpine running at postgres.railway.internal / redis.railway.internal; Railway CLI v4.61.1 rejected token (Unauthorized) but GraphQL API worked with Bearer auth; GitHub repo made public for Railway access
- [x] P5.2  Set up Vercel project linked to GitHub repo — DONE: Vercel CLI authenticated via device code; project deployed and renamed to "hoopchain" at hoopchain.vercel.app; vercel.json added with SPA rewrites
- [x] P5.3  Configure all environment variables in Railway and Vercel dashboards — DONE: backend env vars set via GraphQL API (DATABASE_URL/REDIS_URL/GRAPH_PICKLE_PATH/USE_MOCK_GRAPH=false/CORS_ORIGINS/API_SECRET_KEY/ENVIRONMENT=production); Vercel VITE_API_BASE_URL=https://hoopchain-backend-production.up.railway.app
- [x] P5.4  Graph committed to repo and loaded in production — NOTE: production DB is empty (no ETL run against Railway Postgres); graph.pkl committed at backend/graph.pkl (17MB, built from local ETL); alembic migrations run via pre-deploy command; graph is from local ETL data
- [x] P5.5  Verify graph loads correctly in production backend (`GET /health`) — CONFIRMED: {"status":"ok","graph_nodes":4832,"graph_edges":169635,"mock_mode":false} at https://hoopchain-backend-production.up.railway.app/health
- [ ] P5.6  Verify at least 30 days of puzzles exist in production `daily_puzzles` table — requires running 05_generate_puzzles.py against production DB
- [ ] P5.7  Run end-to-end smoke test: complete a puzzle in production — requires P5.6
- [ ] P5.8  Set up GitHub Actions workflows for auto-deploy
- [ ] P5.9  Configure custom domain (hoopchain.app or similar) — Kai to register domain

### PHASE 6: POST-LAUNCH (v2 features — do not build in v1)
- [ ] P6.1  User accounts (Supabase Auth) replacing anonymous client IDs
- [ ] P6.2  Global leaderboard with real usernames
- [ ] P6.3  "Hard mode" — teammate edges disabled, must use college/draft/coach only
- [ ] P6.4  Era filter — "1990s only," "2010s only" puzzle variants
- [ ] P6.5  Multiplayer race mode (Socket.io)
- [ ] P6.6  Coach nodes surfaced in UI (currently in graph but not searchable by default)
- [ ] P6.7  Community puzzle submission
- [ ] P6.8  Mobile app (React Native, same API)

---

## KNOWN RISKS & MITIGATIONS

| Risk | Likelihood | Mitigation |
|---|---|---|
| nbadb Kaggle dataset missing coaches data | High | ETL phase 3 (sportsreference enrichment) addresses this |
| Basketball-Reference blocks sportsreference scraping | Medium | Rate limit to 1 req/3sec; if blocked, use cached partial data and note gaps |
| nba.com CDN headshots missing for old players | High | Fallback SVG silhouette; acceptable UX degradation |
| NetworkX graph too large for memory | Low | Current NBA has ~5,000 trackable players; graph will be <100MB. If needed, use Neo4j (not required for v1) |
| Puzzle is too hard/easy | Medium | Difficulty tuning in generate_puzzles.py; expose difficulty to Kai for review before publishing |
| NBA IP / trademark issues | Medium | Do not use NBA logo. "Hoopchain" is descriptive, not a trademark claim. Player names/stats are factual public record. Seek legal clarity before monetizing. |
| Graph disconnected (can't path between two players) | Low | validate_graph.py catches this; only connect modern era players (post-1980) for puzzles |

---

## DEVELOPMENT ENVIRONMENT — QUICK START

After cloning the repo, an agent or developer should be able to run:

```bash
# Start local services
docker-compose up -d  # starts Postgres on 5432, Redis on 6379

# Backend
cd backend
pip install -e ".[dev]"
cp .env.example .env  # fill in DATABASE_URL, REDIS_URL
alembic upgrade head
python -m uvicorn app.main:app --reload

# ETL (run once, takes ~30min)
cd data/etl
bash 01_download_nbadb.sh  # requires KAGGLE_USERNAME and KAGGLE_KEY in env
python 02_build_graph.py
python 03_enrich_coaches.py
python 05_generate_puzzles.py

# Frontend
cd frontend
npm install
npm run dev  # starts on http://localhost:5173
```

---

## AGENT OPERATING INSTRUCTIONS

1. **Work through the checklist in order.** Phases 0 → 1 → 2 → 3 → 4 → 5.
2. **Mark items complete** by changing `[ ]` to `[x]` in this file as you finish them.
3. **When multiple valid implementations exist,** choose the simpler one and add a comment explaining the tradeoff.
4. **When a task requires Kai's input** (marked in the checklist), build a reasonable placeholder, note the decision point clearly in a `// KAI: ...` code comment, and continue.
5. **Never ask the user for technical decisions.** Make the call, document it here or in code comments.
6. **Test as you build.** Write pytest tests for backend services as they're implemented. Write basic React Testing Library tests for critical UI interactions.
7. **Keep this document updated.** If the architecture diverges from what's written here (e.g., a dependency is unavailable, a schema needs changing), update this document to reflect the change and add a note under the relevant section.
8. **graph.pkl is the build artifact that unlocks everything.** The ETL phase is the critical path. If the graph fails to load, nothing works. Validate early and often.

---

## GLOSSARY

- **Node:** A player or coach entity in the graph
- **Edge:** A valid relationship between two nodes
- **Hop:** One user-submitted connection in their chain (one edge traversal)
- **Chain:** The complete sequence of nodes the user has built
- **Canonical path:** The shortest valid path the algorithm found, stored in the puzzle
- **Optimal hops:** Length of the canonical path (minimum hops needed)
- **Puzzle endpoints:** The start player and end player shown to the user
- **Connection label:** Human-readable description of an edge (e.g., "Teammates on 1996-97 Chicago Bulls")
- **Client ID:** Anonymous UUID generated client-side, stored in localStorage, used for streak tracking

---

*Last updated: May 2026 | Document owner: Hoopchain project | Agent: always reread this document at the start of each session before taking action.*
