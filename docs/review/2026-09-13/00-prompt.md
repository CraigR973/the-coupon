# 00 — The prompt this review runs from

Written 2026-09-13, before the review started, and kept here so the register can
be read against what was actually asked. It builds on `docs/review/2026-08-22/`
and `docs/review/2026-08-26/` rather than repeating them.

Why it is shaped this way:

- **Delta, not a restart.** Two full reviews and a table of owner decisions
  already exist; Batches 82-119 are what has changed since the last one.
- **The AI-engineering lens points at the delivery pipeline.** The app ships no
  LLM features, but agents build it and batch close-out pushes to production
  with no human review first.
- **"Optimal" and "premium" are made measurable.** Neither prior review did
  performance, and the design pass has to end in changes specific enough to batch.
- **This project's hazards are named up front.** Production trails `main`, a
  live odds probe spends the scheduler's budget, and the Supabase MCP and
  `apps/web/.env.local` both target a different product.

```text
Full-application review — The Coupon, 2026-09-13

This is the third standing review of The Coupon, following docs/review/2026-08-22/
and docs/review/2026-08-26/. Work as four specialists at once: a senior software
engineer, an application security engineer, an AI engineer responsible for this
repo's agent-driven delivery pipeline, and a product designer whose bar is set by
paid consumer sports apps. The review answers three questions: does the app do
what its spec says; does it do it safely and efficiently; and does it look and
feel like something people would pay for?

READ FIRST
- AGENTS.md, and follow it throughout (never cd; the gate is scripts/ci-local.sh;
  ODDS_PROVIDER=fake for anything automated).
- Both prior review READMEs in full: their registers and the 2026-08-27 owner
  decisions table. Also docs/review/2026-08-26/06-ux-design.md.
- STATUS.md "Now" and "Next"; the product and acceptance sections of
  docs/BUILD_PLAN.md.

SCOPE
The whole application, with effort in proportion to change. The last review was
at 3795854; Batches 82-119 have landed since. Spot-check that the prior registers'
"fixed" rows still hold. Do not re-audit from zero. Do not reopen recorded owner
decisions (text-only with no crests or imagery; display name + four-digit PIN
auth; SEC-14 accepted; FotMob terms accepted with an alert trigger; logical
backups instead of PITR) unless you find new facts. If you do, say what changed.

SETUP
1. Work on branch chore/review-2026-09-13, which already holds this prompt as
   docs/review/2026-09-13/00-prompt.md. Rebase it onto main if main has moved.
2. Run scripts/check-deploy-drift.sh. main is ahead of production (Batch 113,
   migration 025, has not shipped). Review main, and tag every finding
   "live" or "main-only".
3. Run scripts/ci-local.sh (full, then SKIP_PROD_BUNDLE=1) and record the
   baseline. If it is red on main, stop and report: per AGENTS.md that gets its
   own fix/ branch first.

LENSES (one document each)
01 Security. Build a route-by-route authorisation matrix from the routers
   (anonymous / member / league admin / site admin) and test for cross-league
   IDOR. Cover PIN brute force and lockout, the token lifecycle, every outbound
   call (SSRF), input validation, the service worker and client storage,
   production headers and CSP (read-only), secrets in the tree, history and
   logs, and a live OSV query against the current pins and the lockfile. Confirm
   SEC-01..SEC-13 still hold.
02 Correctness: does it work as expected. Judge against BUILD_PLAN acceptance,
   not intuition. Run the seeded app (tests/e2e_server.py, fake odds) and play at
   least two leagues with different windows, markets and pick_scope through
   open -> pick -> claim conflict -> lock -> settle -> standings -> season
   archive. Any single-league or single-window assumption is a bug. Priorities
   since the last review: the season calendar and season_week labels (113),
   stranded-round retirement (112), discovery budget and per-window commits
   (119), pricing (114), pick alerts (116), home's current round
   (105/106/117), football results and team season (109-111), notifications
   (107/108), the offline pick queue (90). Include DST weekends, London vs UTC,
   and concurrent claims on one selection.
03 UI/UX and accessibility: objective checks only. Run axe-core in real
   Chromium on every route in both themes at 390x844. Do a keyboard-only pass,
   check accessible names, 200% zoom, prefers-reduced-motion, and 44px targets
   on primary actions. Cover every state, not just the happy path: first run
   with no league, loading, empty, error, offline, locked, settled, archive,
   admin console.
04 Performance and operations. Neither prior review did performance, so state
   numbers. No load against production. Measure: production bundle size and
   route splitting; Lighthouse mobile (throttled) on the prod bundle served
   locally for home, coupon and standings; query counts, timings and EXPLAIN on
   the hot endpoints (home summary, current round/slate, leaderboard, combined
   coupon) at two data shapes, production's (5 leagues, largest 12 members) and
   a stress shape (a 50-member league with a full season of rounds);
   odds-api.io requests per scheduled job and per member action against the
   100/hour and 500/day plan; scheduler job duration and overlap; React
   re-render hot spots and TanStack Query key hygiene. Also re-check the gate,
   dependencies and deploy hygiene.
05 Feature gaps, briefly. What the spec promises that isn't closed (Batches 95
   and 115, LAUNCH_PLAN), and what a paying member would expect that is
   missing. Ground every point in actual routers and components.
06 Premium design: judgement, but concrete. Screenshot every screen and state
   from 03 at 390x844 and 1280x800 in both themes. Hold them against the finish
   of apps like FotMob, Sleeper, the official FPL app and Apple Sports, within
   the text-only constraint. Look at type scale and hierarchy, spacing rhythm,
   density, surface depth, tabular figures for odds and points, motion and
   feedback on the pick action, skeletons vs spinners, empty-state warmth, copy
   tone, icon consistency, PWA polish (icons, splash, theme-color, install
   prompt, safe areas in standalone mode) and cross-screen consistency.
   Output: per screen, what already works and what breaks the premium feel.
   Then the ten highest-leverage changes ranked by impact / effort, each
   specific enough to batch: token names and values, components to change, the
   "before" screenshot, and an HTML mockup where it helps. No recommendation may
   regress WCAG AA.
07 Agent delivery pipeline. The app ships no LLM features, so the AI
   engineering lens points at what does use AI: agents build this repo, and
   batch close-out pushes to production with no human review first. Review
   AGENTS.md, CLAUDE.md, docs/agent-commands/, .claude/commands/,
   .codex/hooks.json and ci-local.sh for:
   - contradictions or stale facts between them;
   - any route by which an agent could reach green by weakening the gate;
   - what an automatic push can break before CI reports;
   - whether STATUS.md (~1,900 lines) and BUILD_PLAN.md (~4,100 lines) still
     earn their cost as cold-start context;
   - which hazards are enforced by scripts and which only by prose.
   Propose an AI product feature only if you can name a concrete member problem
   it solves better than a non-AI fix. "None" is an acceptable answer.

GUARDRAILS
- Production is read-only: HTTPS headers, /api/v1/health, public pages. No
  writes, no load, no signing in as real members, no Railway or Supabase
  changes. Never use the Supabase MCP; it is bound to a different product.
- Never touch the owner's Betfair account. Do not call odds-api.io live: the
  scheduler shares the 100/hour budget, and a probe can 429 the refresh job.
- apps/web/.env.local targets another product's API; override it for every
  local browser run. The browser flow needs FRONTEND_ORIGIN=http://127.0.0.1:4173.
- Never pass DATABASE_URL to psql.
- Fix nothing. Doc-only corrections are allowed and must be listed.

EVIDENCE STANDARD
- Every finding has: id, severity, live/main-only, verified or plausible,
  evidence (file:line, command and output, HTTP exchange, axe result, or
  screenshot path), a one-sentence impact on a member, and a recommended fix.
- "Verified" means reproduced against something running. Code reading alone is
  "plausible".
- Before rating anything HIGH or above, try to disprove it and record what you
  tried.
- Severity. CRITICAL: picks, points or credentials are wrong, lost or exposed
  now. HIGH: the same under an unusual but reachable condition, or the Saturday
  flow can fail. MED: degraded correctness, security or efficiency with a
  workaround. LOW: hardening, hygiene, polish. INFO. Design findings use impact
  (high/med/low) instead.
- Don't pad. If a lens finds nothing material, say so and show what was checked.

DELIVERABLES: docs/review/2026-09-13/
- 00-prompt.md (this prompt) already exists; leave it as written.
- README.md in the house format: how it was produced, baseline, register
  ordered by what to act on first, what's already excellent (so nobody churns
  it), owner decisions needed (each with options and a recommendation), where
  the review was wrong, and what it did not do.
- 01-security, 02-correctness, 03-ux-accessibility, 04-performance-operations,
  05-feature-gaps, 06-premium-design, 07-agent-pipeline, 08-sequencing;
  screenshots/ alongside.
- New unchecked batch rows in docs/BUILD_PLAN.md, in the existing row format,
  from Batch 120, for every finding ready to build. 08-sequencing groups them
  into deployment-safe runs (web-only / API-carrying / migration) the way the
  2026-08-26 sequencing did.
- Commit on the branch. Do not merge, push, /ship-prod or /batch-start anything;
  I will review the register first.

You may run the lenses as parallel subagents. Give each one these guardrails
and its slice of the prior registers. You own verification and the README.

End with a summary of 15 lines or fewer: baseline, counts by severity, the top
five actions, and the decisions you need from me.
```
