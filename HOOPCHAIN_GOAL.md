# HOOPCHAIN — SOFT-LAUNCH GOAL
**Standing objective + single source of truth for planning. Work top-down.**
Version 1.2 · Target: soft launch ASAP (Finals window — Game 1 was 2026-06-03).

---

## Operating model (read first)

- **Sources of truth:** this file (`HOOPCHAIN_GOAL.md`) = the plan, decisions, and
  do-NOTs. `CLAUDE.md` = hard infra invariants. `CHANGELOG.md` = append-only history
  (one line per session). Nothing else is authoritative; `HANDOFF_V2`,
  `MASTER_BLUEPRINT`, and `.next_steps.md` are archived/ignored.
- **Prompt template** (every task prompt uses this shell so context isn't re-explained):
  > Task: [WX — name]. Read CLAUDE.md + HOOPCHAIN_GOAL.md first; don't relitigate
  > decisions or do-NOTs; constraints per CLAUDE.md.
  > Do: [spec + acceptance criteria].
  > Verify: extend `data/tests/test_count_consistency.py` with any new known-answer
  > assertions and run it.
  > Report: brief — files changed, test result, decisions needed. Append a CHANGELOG line.
- **Review by exception:** the agent self-verifies via the regression test and the
  workstream's acceptance criteria, and reports briefly. Escalate to Kai only on a
  failed check or a decision that needs his call — not for every green report.
- **Roles:** Kai = creative director (visual/naming/tone/scope). Agent = all technical
  architecture and implementation; decide and document, don't ask.

---

## Standing decisions (do not relitigate)

- **Ship ASAP** to catch Finals traffic. Soft launch at ~90%; iterate live.
- **Multiplayer battles / battle royale are the headline feature.** Do NOT over-invest
  in single-player balance (all-star/coach tuning, perfect difficulty curves). Get the
  daily + free play good enough, launch, then build the multiplayer differentiator.
- **COACH mode removed** (too sparse, thin as a standalone). Modes = CLASSIC + WILD.
- **Difficulty = unweighted GOAT (hop count).** For "hard", sample famous-but-distant
  endpoints (e.g. a legend ↔ a modern star) and keep the recognizability floor on both
  ends — do NOT reach for obscure players to manufacture length.

---

## Product

Daily browser NBA connection game: build a chain from START → END through shared
relationships; fewest hops ("dribbles") wins; par = "GOAT". Modes: CLASSIC (teammates)
and WILD (all connection types). Vite/React → Vercel; FastAPI → Railway; Postgres +
Redis; NetworkX graph from `backend/graph.pkl`.

## Definition of done (soft launch)

1. Gameplay correct: no phantom or missing in-era connections; GOAT = true minimum for
   the mode, counted as **connections (edges), not players**.
2. Give-up AND win reveal an optimal path, from any chain state (incl. empty).
3. Mode pills consistent, payload-driven, supported/solvable modes only.
4. Free play varied (rare repeats).
5. Nav/layout/logo behave per W5.
6. Analytics capturing from day one.

## Principles (hard-won)

- Phantom edges are worse than missing ones — prefer correctness over coverage.
- Verify, don't assume.
- Dribbles = intermediates (`len(path)−2` = edges−1): the players you actually guessed, excluding start and end. Direct teammates = 0 dribbles.
- Canonical NBA Stats IDs everywhere (dedup + headshots depend on them; no Balldontlie
  IDs).
- Rosters from box scores / play-by-play, not CPI year ranges.
- No Basketball-Reference scraping. The data source isn't the problem; the pipeline is.
- Self-verify with known-answer tests (shift QA off Kai).

## Practices

- **Regression test** `data/tests/test_count_consistency.py`: known-answer dribble counts
  (Wade↔Butler classic=0, Kobe↔Boozer classic=0, Klay↔Jokic classic=1, MJ↔LeBron classic=1),
  pills derive only from `available_modes`, Give Up works from empty chain. Extend on every
  correctness fix; run at end of correctness sessions.
- **ETL rebuild order (mandatory):** on any future data refresh, always run
  `16_patch_midseason_stints.py` before `rebuild_graph_from_pg.py`. Mid-season stints
  (trade deadline + hardship signings) must be patched into `player_seasons` first or
  the graph loses legitimate teammate edges for traded players.

---

## Workstreams

- **W1 — Data foundation · DONE.** player_seasons re-derived from PBP+inactive_players;
  Balldontlie patch retired (12_topup via nba_api for 2023-25); 5,025 nodes / 239,065
  edges / 97% connectivity; all checks pass. Watch (low risk): PBP can miss a zero-minute
  rostered player in PBP-less games; draft fallback may add rare pre-1996 draft-night
  phantoms.
- **W2 — Per-mode GOAT + reveal · DONE.** Unweighted per-mode BFS; `optimal_hops_by_mode`
  in payload; reveal auto on give-up + toggle on win; ⚡ removed.
- **W2.1 — Post-W2 fixes · DONE.** Off-by-one fixed (reveal uses `optimalPath.length−1`);
  Give Up works from idle; COACH removed; pills payload-only; tooltips added; regression
  test created.
- **W3 — Free-play variety · DONE.** On-the-fly generation from a 430-player
  recognizability pool; transient `free:` puzzles; live BFS GOAT; bands easy=1 (66%),
  medium=2 (18%), hard=3+ (11%); 0% repeats, no daily_puzzles writes.
- **W3.1 — Hard-mode endpoints · ACTIVE FAST-FOLLOW.** Replace the
  isolated-1980s hard source with famous-but-distant pairing (legend ↔ modern star, both
  above the recognizability floor, reachable). GOAT stays the metric; era-distance is the
  sampling heuristic. Real-world example of the problem: Whiteside↔Camby — two big men
  from different eras who share no direct teammate edge, producing a valid hard puzzle
  that rewards basketball knowledge over randomness.
- **W4 — COACH · DONE** (removed; see Standing decisions).
- **W5 — UI polish · NEXT (launch-blocking).** Nav: Stats+Data left, Free Play+How to
  Play right, logo centered. Difficulty badge on its own row below the matchup names.
  Logo click returns to the daily/home puzzle from any state.
- **W6 — Share aesthetics · ACTIVE** Keep the copyable text block; add a
  generated share image + tighten the modal. Awaiting visual direction from kai's prompt.
- **W7 — Favicon · DONE.** Monogram, reversed colors: hoop orange, chain white/gray.
- **W8 — Docs hygiene · ONGOING.** Keep CHANGELOG append-only. Archive HANDOFF_V2 /
  MASTER_BLUEPRINT / .next_steps.md. Move any live secret out of committed docs into
  gitignored env.
- **W9 — Analytics · DONE.** Vercel Analytics added (`@vercel/analytics/react`); no-op in dev, auto-activates on Vercel. Custom dashboard is post-launch.

## Do-NOTs

- Don't count dribbles as edges; dribbles = intermediates (edges−1 = `len(path)−2`).
- Don't apply the edge-overwrite "skip teammate" fix (breaks CLASSIC; teammate-wins is
  correct).
- Don't reintroduce COACH until reworked.
- Don't use proprietary (Balldontlie) IDs; don't scrape Basketball-Reference.
- Don't weight GOAT (unweighted hop count; weights are for puzzle selection only).
- Don't return path/canonical_path in `/puzzle/*` payloads (anti-cheat).
- Don't re-add a Railway pre-deploy command, swap hardcoded hostnames for `${{...}}`
  refs, or unset `USE_MOCK_GRAPH=false` (see CLAUDE.md).

## Sequencing to launch

W1✓ → W2✓ → W2.1✓ → W3✓ → **W5 (last launch-blocker)** → W9 analytics + smoke test →
**SOFT LAUNCH**. Fast-follow after launch: W3.1, W6 (when Kai's direction lands), W7.
Then begin the multiplayer feature (the headline).
