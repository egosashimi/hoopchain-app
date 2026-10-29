# CLAUDE.md — Hoopchain

Daily browser-based NBA connection game. Players build a chain between two NBA
players through shared real-world relationships (teammates, coaches, college,
draft class, All-Star). Modeled after Cine2Nerdle.

**Roles.** Kai is creative director — all visual, naming, and tone calls are his.
You make all technical decisions independently: decide, implement, document. Do
not ask Kai technical questions. Never print credentials in logs, commits, or
output.

**Source of truth.** This file holds the invariants. Current state, architecture
detail, known bugs, and roadmap live in `HOOPCHAIN_HANDOFF_V2.md` — read it at the
start of any non-trivial session. Append a one-line entry to `CHANGELOG.md` at the
end of every session describing what changed. `HOOPCHAIN_MASTER_BLUEPRINT.md` and
`.next_steps.md` are HISTORICAL — ignore them.

---

## Golden rules (violating these breaks prod)

1. **Never add a pre-deploy command** to `railway.toml` or the Railway dashboard.
   It cannot reach Postgres during that phase and breaks every deploy. The DB is
   already migrated.
2. **Never use Railway `${{Postgres.*}}` / `${{Redis.*}}` variable references** —
   they resolve to localhost in this project. Always use hardcoded internal
   hostnames (below).
3. **`USE_MOCK_GRAPH=false` must stay set** in Railway. Without it the app
   silently falls back to a 27-player mock graph with no error. The mock fallback
   never raises — a broken DB connection returns mock data silently, so verify
   `/health` returns `graph_nodes≈4832, mock_mode=false` after any infra change.
4. **`backend/graph.pkl` is committed intentionally** (~21MB). Railway needs it at
   build time. Do not gitignore it. Default `GRAPH_PICKLE_PATH=graph.pkl` resolves
   to `/app/graph.pkl` in the container — do not change it.
5. **Frontend deploys to GitHub Pages** from the public repo
   `egosashimi/hoopchain-app`: `.github/workflows/deploy-pages.yml` builds
   `frontend/` and force-pushes it to the `gh-pages` branch (Settings → Pages →
   Source: Deploy from a branch → `gh-pages` / root). The workflow skips private
   repos. The Vite `base` comes from `VITE_BASE_PATH`, set by the workflow — never hardcode
   root-absolute asset paths in `src/`. Routing is hash-based (`#/admin`), so no
   SPA rewrites are needed. The repo is public: never commit secrets, and never
   put a secret in a `VITE_*` var (they are bundled into public JS).
6. **You cannot change Railway dashboard settings** (token lacks permission). When
   a dashboard change is required, stop and tell Kai exactly what to set; he does
   it. Never click "Apply N changes" with stale pending changes queued.

---

## Architecture

- **Frontend:** React + Vite → GitHub Pages (`frontend/`). State in Zustand
  (`gameStore.ts`, `userStore.ts`). API client in `src/api/client.ts`.
- **Backend:** FastAPI → Railway (`backend/`). Routers: puzzle, validate, search,
  game, health, admin, subscribe. Services: graph (NetworkX BFS + hop validation),
  search (Postgres FTS + ILIKE fallback), puzzle (Redis-cached daily), score.
- **Data:** PostgreSQL + Redis on Railway. Graph is NetworkX in-memory, loaded
  from `backend/graph.pkl` at startup (~4,832 nodes / ~204,825 edges).
- **ETL:** `data/etl/01..08_*.py` (Kaggle nbadb base + Balldontlie current-season
  patch). Source dataset is nbadb — we do NOT scrape Basketball-Reference.
- **Repos:** `egosashimi/hoopchain-app` (public) is canonical and hosts the
  Pages site; it began as a single clean commit with no history.
  `egosashimi/hoopchain` (private) holds the old history and is still what
  Railway deploys the backend from until Kai repoints Railway (dashboard) — until
  then, push backend changes to both repos' `main`.
- **Deploy:** push to `main` → Railway auto-deploys the backend; the
  `deploy-pages.yml` GitHub Action builds and publishes the frontend.

---

## Infra reference

**Railway internal hosts (runtime env vars, already set in dashboard — do not
swap for `${{...}}` refs):**
- Postgres: `postgresql+asyncpg://hoopchain:<password>@postgres.railway.internal:5432/hoopchain`
- Redis: `redis://default:@redis.railway.internal:6379`

**Production DB access for local/one-off scripts (external TCP proxy):**
- Read the full connection string (TCP proxy host/port, user `hoopchain`, db
  `hoopchain`) from the gitignored `data/etl/.env` — do NOT commit the host,
  port, or password; scripts read `DATABASE_URL` from the environment.

**Player headshots:** `https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_stats_player_id}.png`
(no auth; falls back to silhouette on 404). Requires the **NBA Stats** player ID —
Balldontlie IDs will NOT resolve.

---

## Common commands

```bash
# Local dev
docker-compose up -d                 # Postgres :5433, Redis :6379
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev           # http://localhost:5173

# Health check (prod)
curl https://hoopchain-backend-production.up.railway.app/health
# expect: {"graph_nodes":4832,"mock_mode":false,...}

# Prod DB scripts: load connection string from data/etl/.env, then e.g.
python data/etl/07_seed_players_table.py
```

---

## Known-bad patterns — do not reintroduce

- `plainto_tsquery("english", q)` passing "english" as a bound param — Postgres
  rejects it (needs regconfig). Use `literal_column("'english'")`.
- Caching invalid hops in Redis — only cache valid hops; never cache
  `{valid:false}`. Flush `path:*` if the graph edge count changes on startup.
- Per-`(player, season)` dedup in the teammate edge build — it collapses traded
  players to one team and drops co-roster pairs. Build teammate edges by grouping
  on `(team_id, season)` and pairing every roster member.
- Adding patched players under Balldontlie IDs — always reconcile to the NBA Stats
  ID, or you create duplicate, headshot-less nodes whose edges orphan.
- Gating the admin page on a `VITE_*` password — it ships in the public bundle.
  Admin auth is the backend's `X-Admin-Key` check against `API_SECRET_KEY`.

---

## Identity / data integrity (read before touching the graph)

Player identity must be reconciled across the nbadb base, the Balldontlie patch,
and the materialized `graph_edges` table. Duplicate nodes (e.g. a second Chet
Holmgren with no headshot) and "missing" in-era connections (e.g. Wade↔Butler
2003-04 Heat, Kobe↔Boozer 2014-15 Lakers) are usually the SAME root cause: a
player exists as two nodes, or the teammate edge build dropped the pair. A data
refresh does NOT fix in-era gaps — fix the build/identity, rebuild `graph.pkl`,
recommit. Diagnose before changing: confirm roster rows exist, then check for the
edge, before assuming anything.
