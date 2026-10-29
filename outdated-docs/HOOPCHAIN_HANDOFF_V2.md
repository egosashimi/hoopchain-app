# HOOPCHAIN — COMPREHENSIVE HANDOFF DOCUMENT
# Version 2.0 | May 28, 2026
# For use as the primary reference in a new Claude Code project session
# ============================================================
# AGENT OPERATING RULES:
# 1. Read this entire document before taking any action
# 2. Do not ask Kai technical questions — make decisions and document them
# 3. Do not expose credentials in logs, commits, or chat output
# 4. Update the STATUS TRACKER section as work is completed
# 5. When in doubt about a decision, check this document first
# ============================================================

---

## WHAT HOOPCHAIN IS

Daily browser-based NBA trivia game. Two NBA players are shown (START and END). The user builds a chain connecting them through shared real-world relationships — teammates, coaches, college, draft class, All-Star appearances. Fewest hops wins. Daily puzzle, streak tracking, shareable emoji result.

**Creative direction owner: Kai.** Kai makes all visual, naming, and tone decisions. The agent makes all technical decisions independently.

**Live URLs:**
- Frontend: https://hoopchain-vite.vercel.app
- Backend: https://hoopchain-backend-production.up.railway.app
- Health check: https://hoopchain-backend-production.up.railway.app/health
- GitHub repo: https://github.com/egosashimi/hoopchain (PRIVATE)

---

## CURRENT STATE (as of May 28, 2026 evening)

### What is working
- Backend deployed on Railway, graph loads correctly: 4,832 nodes, 204,825 edges, real mode
- Daily puzzles seeded: 140 puzzles in `daily_puzzles` table
- Frontend deployed on Vercel at hoopchain-vite.vercel.app
- Game UI renders: HOOPCHAIN wordmark, player cards, chain builder, search input
- Graph integrity: LeBron↔Rondo, KG↔Pierce, Rondo↔LeBron all confirmed valid

### What is broken / in progress RIGHT NOW
- **Search returning empty arrays** — root cause: DATABASE_URL was pointing to localhost. Fix was just deployed (May 28 ~6PM EDT): DATABASE_URL changed to `postgresql+asyncpg://hoopchain:<redacted-db-password>@postgres.railway.internal:5432/hoopchain` and REDIS_URL changed to `redis://default:@redis.railway.internal:6379`. Railway redeploy was triggered via "Deploy Changes" button. VERIFY THIS WORKED by hitting `/search/players?q=kyrie` — should return Kyrie Irving.
- **Today's puzzle (May 28) may still show Allen Iverson** — stale Redis cache from mock era. Will self-resolve at midnight UTC when the key expires, OR flush manually once Redis is confirmed connected.
- **Vercel frontend not on latest code** — multiple backend fixes (search query fix, cache fix, config fixes) were pushed to GitHub but Vercel builds kept failing due to root directory misconfiguration. Root directory IS now correctly set to `frontend` in Vercel settings. Needs a fresh deploy triggered.

### What has never worked
- Victor Wembanyama and Cooper Flagg are NOT in the graph — nbadb dataset predates their NBA careers. Needs a data refresh (Phase 6 item).
- GitHub Actions CI/CD is deleted — Railway deploys directly from GitHub pushes to main. This is intentional.

---

## INFRASTRUCTURE

### Railway (Backend)
- Project URL: https://railway.com/project/<redacted-railway-id>
- Backend service ID: <redacted-railway-id>
- Postgres service ID: <redacted-railway-id>
- Redis service ID: <redacted-railway-id>
- Region: US West (California)
- Plan: Hobby ($5/mo)
- Auto-deploys: YES — pushes to `main` branch trigger Railway redeploy automatically
- Root directory: `backend`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Pre-deploy command: NONE (was removed — caused repeated failures)

### Railway Environment Variables (hoopchain-backend service)
```
DATABASE_URL=postgresql+asyncpg://hoopchain:<redacted-db-password>@postgres.railway.internal:5432/hoopchain
REDIS_URL=redis://default:@redis.railway.internal:6379
GRAPH_PICKLE_PATH=graph.pkl
USE_MOCK_GRAPH=false
ENVIRONMENT=production

CORS_ORIGINS=["https://hoopchain-vite.vercel.app","https://hoopchain.app","http://localhost:5173"]
```

**ACTION REQUIRED — CORS for hoopchain.app:** Once Kai registers hoopchain.app and connects it to Vercel, update `CORS_ORIGINS` in the Railway dashboard (hoopchain-backend service → Variables) to add `"https://hoopchain.app"` to the JSON array. Do NOT edit the code — set it directly in the Railway env var. The backend already reads and parses the JSON array from this variable.

Also add `VITE_ADMIN_PASSWORD` in Vercel → hoopchain-vite → Settings → Environment Variables. This is the admin page password (Kai picks it).

### CRITICAL RAILWAY NOTES
- `${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}` reference syntax does NOT work correctly in this project — both resolve to localhost. Always use hardcoded internal hostnames.
- Internal Postgres hostname: `postgres.railway.internal:5432`
- Internal Redis hostname: `redis.railway.internal:6379`
- External Postgres TCP proxy (for local ETL scripts): `<railway-tcp-proxy-host:port>`
- Postgres credentials: user=`hoopchain`, password=`<redacted-db-password>`, db=`hoopchain`
- The Railway CLI auth returns "Unauthorized" with the project token — use dashboard or direct DB connections instead
- Do NOT click "Apply X changes" in the Railway dashboard unless you explicitly made those changes — stale pending changes accumulate and cause bad redeploys
- Do NOT add a pre-deploy command — it will break every deploy

### Vercel (Frontend)
- Project: hoopchain-vite
- Dashboard: https://vercel.com/egosashimis-projects/hoopchain-vite
- Root directory: `frontend` (set in Build & Deployment settings — CONFIRM this is still set)
- Build command: `npm run build`
- Output directory: `dist`
- Framework: Vite
- Environment variable: `VITE_API_BASE_URL=https://hoopchain-backend-production.up.railway.app`
- Auto-deploys: YES from main branch (connected to GitHub)
- Node.js version: 24.x

### CRITICAL VERCEL NOTES
- Root directory MUST be set to `frontend` in Settings → Build and Deployment → Root Directory
- When redeploying, always uncheck "Use existing Build Cache"
- The repo has a `vercel.json` inside `frontend/` — do not add one at the repo root or it overrides settings
- There is a SEPARATE dead Next.js project at hoopchain.vercel.app — ignore it entirely, it is unrelated

---

## REPOSITORY STRUCTURE

```
hoopchain/                          ← repo root (github.com/egosashimi/hoopchain, PRIVATE)
├── HOOPCHAIN_MASTER_BLUEPRINT.md   ← original v1 blueprint (reference only)
├── .next_steps.md                  ← may contain stale instructions, ignore
├── .github/
│   └── workflows/                  ← deploy-backend.yml was DELETED (caused failures)
├── frontend/                       ← Vite React app → Vercel
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── vercel.json                 ← SPA rewrite rules
│   └── src/
│       ├── components/
│       │   ├── ChainBuilder.tsx    ← core game canvas
│       │   ├── NodeCard.tsx        ← player card with headshot
│       │   ├── SearchInput.tsx     ← debounced autocomplete
│       │   ├── ResultModal.tsx     ← win/loss + share (lazy loaded)
│       │   ├── HowToPlay.tsx       ← rules modal (lazy loaded)
│       │   ├── StatsPanel.tsx      ← streak stats (lazy loaded)
│       │   ├── ConnectionLine.tsx  ← animated edge between nodes
│       │   ├── Header.tsx
│       │   └── ErrorBoundary.tsx
│       ├── store/
│       │   ├── gameStore.ts        ← Zustand game state
│       │   └── userStore.ts        ← streak, localStorage persistence
│       ├── api/client.ts           ← typed API client
│       ├── types/index.ts
│       └── styles/globals.css      ← design tokens (dark theme, orange accent)
├── backend/                        ← FastAPI app → Railway
│   ├── graph.pkl                   ← 21MB NetworkX graph (COMMITTED, not gitignored)
│   ├── railway.toml                ← Railway config (NO preDeployCommand)
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── alembic/                    ← DB migrations
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       └── 002_drop_fk_constraints.py
│   ├── scripts/
│   │   └── seed_puzzles.py         ← seeds daily_puzzles table, idempotent
│   └── app/
│       ├── main.py                 ← FastAPI entrypoint, lifespan handler
│       ├── config.py               ← pydantic settings, reads env vars
│       ├── database.py             ← async SQLAlchemy engine
│       ├── redis_client.py         ← Redis connection
│       ├── routers/
│       │   ├── puzzle.py           ← GET /puzzle/today, GET /puzzle/{date}
│       │   ├── validate.py         ← POST /validate/hop, POST /validate/path
│       │   ├── search.py           ← GET /search/players
│       │   ├── game.py             ← POST /game/complete, GET /game/stats
│       │   └── health.py           ← GET /health
│       └── services/
│           ├── graph_service.py    ← NetworkX graph, BFS, hop validation
│           ├── search_service.py   ← Postgres full-text search + ILIKE fallback
│           ├── puzzle_service.py   ← daily puzzle retrieval + Redis cache
│           └── score_service.py    ← scoring + share text generation
└── data/
    ├── etl/
    │   ├── 01_download_nbadb.sh    ← Kaggle download (requires KAGGLE creds)
    │   ├── 02_build_graph.py       ← SQLite → Postgres + NetworkX graph
    │   ├── 03_enrich_coaches.py    ← sportsreference coach data
    │   ├── 04_enrich_wikipedia.py  ← fill college/draft gaps
    │   ├── 05_generate_puzzles.py  ← generate puzzle pool (local use)
    │   ├── 06_validate_graph.py    ← graph sanity checks
    │   └── 07_seed_players_table.py ← seeds players table from graph.pkl
    └── seeds/
        └── famous_players.json     ← 81 curated player IDs for puzzle endpoints
```

---

## GRAPH DATA

### Stats
- Nodes: 4,832 players
- Edges: 204,825 relationships
- Largest connected component: 4,622 nodes (96.0%)
- Isolated nodes: 189 (all obscure pre-1960s or one-game players — expected)
- File: `backend/graph.pkl` (21MB, committed to git)

### Edge Types
| Type | Count (approx) | Source | Example Label |
|---|---|---|---|
| `teammate` | ~120,000 | player_seasons join | "Teammates on 2012-13 Miami Heat" |
| `college` | ~40,992 | common_player_info.college | "Both attended Duke University" |
| `coached_by` | ~30,000 | coach_seasons | "Both with Pop on 2005 Spurs" |
| `draft_class` | ~10,000 | draft_history.season | "Both drafted in 2003 NBA Draft" |
| `all_star` | ~3,000 | All-Star game rosters | "Both in 2016 All-Star Game" |

### Edge Weights (lower = stronger/more obvious)
- Teammates 5+ seasons: 0.3
- Teammates 2-4 seasons: 0.6
- Teammates 1 season: 0.9
- Coached by: 0.7
- Same college: 1.2
- Same draft class: 1.4
- All-Star: 1.5

### Known Data Gaps
- **Victor Wembanyama**: NOT in graph — nbadb predates 2023-24 season
- **Cooper Flagg**: NOT in graph — 2025 draft, predates dataset entirely
- **Recent trades/signings**: Dataset refreshed manually via ETL, not automatic
- To add missing players: re-run ETL with updated nbadb download, rebuild graph.pkl, commit

### Confirmed Working Connections
- LeBron James → Rajon Rondo: 1 hop (2021-22 Lakers teammates)
- Rajon Rondo → Kevin Garnett: valid (Boston Celtics)
- Paul Pierce → Kevin Garnett: valid (Boston Celtics)
- LeBron James → Kobe Bryant: 3-4 hops

---

## DATABASE SCHEMA

### Key Tables
```sql
players           -- 4,815 rows, seeded from graph.pkl via 07_seed_players_table.py
teams             -- 30 teams
player_seasons    -- player↔team↔season memberships
coaches           -- head coaches
coach_seasons     -- coach↔team↔season memberships
graph_edges       -- materialized edges (also in graph.pkl)
daily_puzzles     -- 140 rows seeded, puzzle_date UNIQUE
game_sessions     -- anonymous game results (client_id from localStorage)
streaks           -- per client_id streak tracking
```

### Daily Puzzles Table
- 140 puzzles seeded covering ~4 months from May 28, 2026
- Today's puzzle (May 28): player `201950` vs `203932`, easy, 2 hops
- Puzzle generation: `backend/scripts/seed_puzzles.py` — idempotent, skips existing dates
- To generate more: run `seed_puzzles.py` with production DATABASE_URL via TCP proxy

### Migrations
- `001_initial_schema`: All tables created
- `002_drop_fk_constraints`: Dropped FK constraints from daily_puzzles (player_id FKs caused INSERT failures when players table was empty)

---

## API ENDPOINTS

All at: `https://hoopchain-backend-production.up.railway.app`

```
GET  /health
     → {status, graph_nodes, graph_edges, mock_mode}
     EXPECTED: graph_nodes=4832, mock_mode=false

GET  /puzzle/today
     → {puzzle_id, puzzle_date, start_player, end_player, difficulty, optimal_hops}
     NOTE: does NOT return canonical_path (anti-cheat)

GET  /puzzle/{date}
     → same for historical dates (YYYY-MM-DD format)

GET  /search/players?q={query}&limit=10
     → [{id, full_name, position, team_name, headshot_url, is_active}]
     Uses Postgres FTS with ILIKE fallback. Unicode normalized.
     TEST: /search/players?q=kyrie should return Kyrie Irving

POST /validate/hop
     Body: {from_id, from_type, to_id, to_type}
     → {valid, edge_type, edge_label, weight}

POST /validate/path
     Body: {puzzle_date, path: [{type, id}]}
     → {valid, complete, hops, optimal_hops, edge_types}

POST /game/complete
     Body: {puzzle_date, client_id, path, hops_used, time_seconds, gave_up}
     → {score, streak, share_text}

GET  /game/stats/{client_id}
     → {streak, max_streak, total_played, win_pct, avg_score}

GET  /leaderboard/today
     → top 10 scores for today's puzzle
```

---

## KNOWN BUGS & HISTORY

### Recurring Issues (do not reintroduce)

**1. Pre-deploy command on Railway**
Any pre-deploy command (`alembic upgrade head`, `seed_puzzles.py`) breaks Railway deploys because it can't connect to Postgres during that phase. The DB is already migrated. DO NOT add a pre-deploy command to railway.toml or the Railway dashboard.

**2. graph.pkl path**
The graph must be at `backend/graph.pkl`. Old default was `../data/exports/graph.pkl` which resolved to `/data/exports/graph.pkl` in the Railway container (wrong). Config now defaults to `graph.pkl` which resolves to `/app/graph.pkl` (correct). Do not change this.

**3. Railway variable references not working**
`${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}` both resolve to localhost in this project. Always use hardcoded internal hostnames. See INFRASTRUCTURE section for correct values.

**4. Mock mode fallback**
The app has a 27-player mock graph for local dev without real data. `USE_MOCK_GRAPH=false` must be set in Railway. The search service falls back to mock if Postgres connection fails — so a broken DATABASE_URL silently returns mock data without erroring.

**5. plainto_tsquery type error**
`plainto_tsquery("english", query)` passes "english" as a bound parameter which Postgres rejects (needs regconfig type). Fixed using `literal_column("'english'")`. Do not revert this.

**6. Stale Redis cache**
When the graph was rebuilt (169k → 204k edges), Redis had cached `{valid: False}` for hops that now exist. Fix: only cache valid hops, never cache invalid results. On startup, if edge count changed, flush `path:*` keys. This is already implemented.

**7. Vercel root directory**
Vercel must have Root Directory set to `frontend`. If it gets reset, builds fail with "package.json not found". Check Settings → Build and Deployment → Root Directory after any Vercel project changes.

**8. Wrong player IDs in mock/puzzle data**
Several mock players had crossed IDs (KG=947 was Allen Iverson, Duncan=708 was KG, etc.). These are fixed. The famous_players.json seed file had similar issues (Ray Allen was Chris Paul's ID). If headshots look wrong, check player IDs against nba.com CDN: `https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png`

**9. Git index corruption**
A previous session crashed mid-git-operation. If git behaves strangely, run:
```bash
rm .git/index.lock
rm .git/index
git read-tree HEAD
```

---

## PLAYER HEADSHOTS

NBA CDN URL pattern (free, no auth):
```
https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png
```

Falls back to silhouette SVG if 404 (common for pre-1980s players).

Key player IDs (verified correct):
- LeBron James: 2544
- Kobe Bryant: 977
- Michael Jordan: 893
- Kevin Garnett: 708
- Allen Iverson: 947
- Tim Duncan: 1495
- Shaquille O'Neal: 406
- Magic Johnson: 1425
- Larry Bird: 1449
- Steve Nash: 959
- Ray Allen: 951
- Vince Carter: 1713
- Chris Paul: 101108

---

## LOCAL DEVELOPMENT SETUP

```bash
# Prerequisites: Python 3.12, Node 18+, Docker

# 1. Start local services
docker-compose up -d   # Postgres on 5433, Redis on 6379

# 2. Backend
cd backend
pip install -e ".[dev]"
cp .env.example .env   # set DATABASE_URL, REDIS_URL, USE_MOCK_GRAPH=false
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

# 3. ETL (run once to build real graph locally)
cd data/etl
# Set KAGGLE_USERNAME and KAGGLE_KEY in environment
bash 01_download_nbadb.sh
python 02_build_graph.py
python 03_enrich_coaches.py
python 05_generate_puzzles.py
python 06_validate_graph.py
# Copy graph to backend
cp ../exports/graph.pkl ../../backend/graph.pkl

# 4. Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Production DB Access (for one-off scripts)
```bash
# External TCP proxy for local → production Postgres
DATABASE_URL="postgresql://hoopchain:<redacted-db-password>@<railway-tcp-proxy-host:port>/hoopchain"
python data/etl/07_seed_players_table.py
```

---

## IMMEDIATE NEXT ACTIONS (in priority order)

### P1 — Verify the May 28 Railway redeploy worked
```bash
curl https://hoopchain-backend-production.up.railway.app/health
# Expected: {"graph_nodes":4832,"graph_edges":204825,"mock_mode":false}

curl "https://hoopchain-backend-production.up.railway.app/search/players?q=kyrie"
# Expected: returns Kyrie Irving with real data
```
If search still returns empty, DATABASE_URL didn't take effect. Re-check Railway variables.

### P2 — Flush stale Redis puzzle cache for today
If `/puzzle/today` still returns Allen Iverson, the May 28 puzzle key is stale in Redis.
Options:
- Wait until midnight UTC (key expires naturally)
- Or: connect to Redis via the TCP proxy (create one in Railway Redis service → Settings → Networking → TCP Proxy) and run `DEL puzzle:date:2026-05-28`

### P3 — Deploy latest frontend to Vercel
Multiple backend fixes were never reflected in the Vercel build because of the root directory issue. Now that root directory is correctly set to `frontend`, trigger a fresh deploy:
- Go to Vercel → hoopchain-vite → Deployments → Redeploy latest → uncheck Build Cache
- OR push any trivial change to `frontend/` to trigger auto-deploy

### P4 — Kai's visual design direction (P4.1/P4.2 from blueprint)
Current design: dark slate background, electric orange accent (#FF6B35 approx), HOOPCHAIN wordmark. Kai to confirm or redirect. Agent should not finalize typography or color system without Kai's input.

### P5 — Custom domain (P5.9)
Register hoopchain.app or similar. Connect to Vercel. Update CORS_ORIGINS in Railway to include new domain.

### P6 — Data refresh for modern players
Wembanyama, Cooper Flagg, and other post-2023 players are missing. Re-run ETL with fresh nbadb download, rebuild graph.pkl, commit.

### P7 — GitHub Actions (P5.8)
Optional: add a workflow that runs pytest on PRs only (not deployment). Deployment is handled by Railway's GitHub integration directly.

---

## PHASE COMPLETION STATUS

| Phase | Status | Notes |
|---|---|---|
| P0: Repo & tooling | ✅ Complete | |
| P1: Data acquisition & ETL | ✅ Complete | 204,825 edges, 96% connectivity |
| P2: Backend API | ✅ Complete | All endpoints implemented |
| P3: Frontend UI | ✅ Complete | All components built |
| P4.1: Kai visual direction | ⏳ Awaiting Kai | Placeholder design in place |
| P4.2: Apply final design | ⏳ Blocked by P4.1 | |
| P4.3-P4.8: Polish | ✅ Complete | Lazy loading, error boundary, OG image, dark mode |
| P5.1-P5.5: Deploy infra | ✅ Complete | Railway + Vercel live |
| P5.6: Seed daily puzzles | ✅ Complete | 140 puzzles in production |
| P5.7: Smoke test | ⚠️ Partial | Search broken as of May 28, fix deployed but unverified |
| P5.8: GitHub Actions | ❌ Deleted | Railway handles deploys directly, GHA deleted |
| P5.9: Custom domain | ❌ Pending | Kai to register domain |

---

## DESIGN TOKENS (current placeholder)

```css
/* from frontend/src/styles/globals.css */
--color-bg: #0a0a0f;           /* near-black background */
--color-surface: #13131a;      /* card/panel background */
--color-surface-2: #1c1c26;    /* elevated surface */
--color-accent: #ff6b35;       /* electric orange — HOOPCHAIN brand */
--color-accent-2: #ff9a5c;     /* lighter orange for hover */
--color-text: #f0f0f5;         /* primary text */
--color-text-muted: #8888a0;   /* secondary text */
--color-border: #2a2a38;       /* subtle borders */

/* Edge type colors */
--color-teammate: #22c55e;     /* green */
--color-college: #3b82f6;      /* blue */
--color-draft-class: #eab308;  /* yellow */
--color-coached-by: #a855f7;   /* purple */
--color-all-star: #ef4444;     /* red */
```

**KAI NOTE:** These are placeholders. The wordmark HOOPCHAIN with HOOP in white and CHAIN in orange is the current design. Full visual identity direction is pending Kai's input (blueprint item P4.1).

---

## SECURITY NOTES

- Old Railway token `<redacted-revoked-railway-token>` is REVOKED. Do not use.
- This token appears in `.next_steps.md` in the repo — clean it up but it's harmless since revoked.
- Production credentials are in Railway environment variables only, never in committed code.
- `data/etl/.env` is gitignored — Kaggle credentials stored there locally only.
- `backend/graph.pkl` IS committed (21MB) — intentional, Railway needs it at build time.
- The repo is PRIVATE on GitHub.

---

## CONTACTS & ACCOUNTS

- GitHub: egosashimi (private repo: egosashimi/hoopchain)
- Railway: project ID <redacted-railway-id>
- Vercel: egosashimi's projects / hoopchain-vite
- Kaggle: credentials in local data/etl/.env (not in repo)

---

*Document version: 2.0 | Last updated: May 28, 2026*
*Agent: read this entire document at the start of each session before taking any action.*
*Kai: update P4.1 when you have visual direction ready.*
