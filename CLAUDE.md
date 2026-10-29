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

1. **The live game has no backend.** The frontend runs entirely in the browser on
   GitHub Pages: `frontend/src/engine/` does search, hop validation, BFS/GOAT,
   free play, scoring and share text from `frontend/public/data/graph.json` +
   `daily.json`. `src/api/client.ts` keeps the old endpoint-shaped interface but
   calls the engine — do not reintroduce HTTP calls to Railway without Kai asking.
2. **After rebuilding `backend/graph.pkl`, run `python data/etl/19_export_static_data.py`
   and commit both data files.** `daily.json` is append-only: never edit or
   regenerate existing dates (the script refuses to change its start date), and
   extend `SCHEDULE_END` before the schedule runs out (dates past it fall back to
   a date-seeded generator, so the game never breaks, but scheduled puzzles are better).
3. **Frontend deploys to GitHub Pages** from the public repo
   `egosashimi/hoopchain-app`: `.github/workflows/deploy-pages.yml` builds
   `frontend/` and force-pushes it to the `gh-pages` branch (Settings → Pages →
   Source: Deploy from a branch → `gh-pages` / root). The workflow skips private
   repos. The Vite `base` comes from `VITE_BASE_PATH`, set by the workflow — never
   hardcode root-absolute paths in `src/` (fetch data via `import.meta.env.BASE_URL`).
   Routing is hash-based (`#/admin`), so no SPA rewrites are needed. The repo is
   public: never commit secrets, and never put a secret in a `VITE_*` var (they
   are bundled into public JS).
4. **`backend/graph.pkl` is committed intentionally** (~21MB). It is the source
   for the static export (and for the dormant backend). Do not gitignore it.
5. **Seasons after 2024-25 come from `data/rosters/<season>.json`**, not graph.pkl.
   `.github/workflows/update-rosters.yml` (weekly + manual) runs
   `20_fetch_recent_rosters.py` (NBA.com CDN box scores → rosters by NBA Stats
   person ID) and the export, commits, and dispatches the Pages deploy. NBA.com
   is unreachable from the dev container — trigger the workflow instead of
   fetching locally. New players get teammate connections only (no draft/college
   data in box scores). Never hand-edit roster files; completed seasons are
   fetched once (delete the file to refetch).
6. **Server-only features are off**, behind `available: false` flags in
   `client.ts`: email signup (hidden in ResultModal), leaderboard, and the admin
   page (shows a notice). Stats and streaks live in localStorage (`userStore`).

### Dormant backend (Railway) — only if it is ever revived

The FastAPI backend in `backend/` is kept but unused by the live site. If it is
brought back: never add a pre-deploy command to `railway.toml`/dashboard (it can't
reach Postgres then); never use Railway `${{Postgres.*}}`/`${{Redis.*}}` references
(they resolve to localhost here — use the internal hostnames below);
`USE_MOCK_GRAPH=false` must stay set (the mock fallback is silent — verify
`/health` shows `mock_mode=false`); you cannot change Railway dashboard settings —
tell Kai exactly what to set. Railway deploys from the private `egosashimi/hoopchain`.

---

## Architecture

- **Frontend:** React + Vite → GitHub Pages (`frontend/`). State in Zustand
  (`gameStore.ts`, `userStore.ts`). `src/api/client.ts` → `src/engine/`
  (`graph.ts`: groups, connections, BFS, search; `puzzles.ts`: daily schedule,
  free play, scoring, share text).
- **Data files:** `graph.json` stores connections as groups (team-season rosters,
  draft classes, colleges, All-Star games, coach stints), not pairwise edges; two
  players connect when they share a group. Rebuilding rosters from labels also
  restores teammate pairs the pickle's simple graph overwrote with draft/college
  edges. Classic = teammate groups only, Wild = all. `daily.json` is
  `{start, puzzles: [[startId, endId], ...]}` indexed by day offset (UTC dates),
  built from famous/curated/high-score players with the weekday difficulty ramp
  (Mon–Tue easy, Wed–Fri medium, Sat–Sun hard; hard pairs are scarce, so they are
  spread out and the rest of the weekend days are medium).
- **ETL:** `data/etl/01..18_*.py` built the Postgres DB and `graph.pkl` (Kaggle
  nbadb base + Balldontlie/nba_api patches, through 2024-25);
  `19_export_static_data.py` builds the static data from graph.pkl + `data/rosters/`;
  `20_fetch_recent_rosters.py` fetches 2025-26+ rosters (Actions only). Source dataset is nbadb — we do NOT scrape Basketball-Reference.
- **Repos:** `egosashimi/hoopchain-app` (public) is canonical and hosts the Pages
  site; it began as a single clean commit with no history. `egosashimi/hoopchain`
  (private) holds the old history and the Railway deploy source.

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
# Local dev (no backend needed)
cd frontend && npm run dev           # http://localhost:5173

# Rebuild static game data after graph.pkl changes (needs networkx)
python data/etl/19_export_static_data.py

# Dormant backend only
docker-compose up -d                 # Postgres :5433, Redis :6379
cd backend && python -m uvicorn app.main:app --reload --port 8000

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
