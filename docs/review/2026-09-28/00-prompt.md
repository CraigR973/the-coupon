# 00 — The prompt this review runs from

Written 2026-09-28, before the review started, and kept here so the register can
be read against what was actually asked. It builds on `docs/review/2026-08-22/`,
`docs/review/2026-08-26/` and `docs/review/2026-09-13/` rather than repeating them.

Why it is shaped this way:

- **Prove the fixes before looking for new faults.** Batches 120-168, plus 95 and
  115, all closed after the last review — 130 commits, ~23,000 lines since
  `2ce6f42` — and every one was built by an agent and pushed to production by
  automatic close-out with no human review first. "Held" therefore means
  re-driven against something running, not re-read.
- **The pipeline lens audits what the agents did, not only the rules.** Sampling
  diffs for weakened tests and trying to weaken the gate on a throwaway branch is
  the only way to know whether the guardrails worked across 49 unreviewed batches.
- **Resilience is written in.** The last review ran over seven days, was
  interrupted five times by usage limits, and lost its raw notes to a
  temporary-directory cleanup. Notes now live in the repository and are
  committed at every checkpoint, with a `PROGRESS.md` a cold session can resume
  from.
- **The unfinished half of the design lens is named.** The peripheral screens,
  the PWA polish pass, the ranked top-ten changes and the missing corpus states
  were left undone last time; captures must now be proven to show their state.
- **The last review's doc corrections were listed and left.** This time they are
  applied on the branch.

```text
Full-application review — The Coupon, 2026-09-28

This is the fourth standing review of The Coupon, following docs/review/2026-08-22/,
docs/review/2026-08-26/ and docs/review/2026-09-13/. Work as four specialists at
once: a senior software engineer, an application security engineer, an AI engineer
responsible for this repo's agent-driven delivery pipeline, and a product designer
whose bar is set by paid consumer sports apps. The review answers four questions:
did the fixes from the last review work; does the app do what its spec says; does
it do it safely and efficiently; and does it look and feel like something people
would pay for?

WHY THIS ONE IS DIFFERENT
Batches 120-168, plus 95 and 115, all closed after the last review: 130 commits and
about 23,000 lines since 2ce6f42. Every one of them was built by an agent and pushed
to production by automatic close-out with no human review first. The first job is
to prove the 2026-09-13 register is actually fixed, not just ticked.

READ FIRST
- AGENTS.md, and follow it throughout (never cd; the gate is scripts/ci-local.sh;
  ODDS_PROVIDER=fake for anything automated).
- docs/review/2026-09-13/ in full, especially README.md (the register, the
  2026-09-22 owner decisions and "Where this review was wrong"),
  09-reconciliation.md and 08-sequencing.md ("What this review did not finish").
  Skim the two earlier READMEs for their registers and decisions.
- STATUS.md in full (it is short now), and the product contract and open rows at
  the head of docs/BUILD_PLAN.md.

SCOPE
The whole application, with effort in proportion to change. Do not re-audit from
zero. Do not reopen recorded owner decisions unless you find new facts, and if you
do, say what changed. These decisions include: text-only with no crests; display
name + four-digit PIN; SEC-14 accepted; FotMob terms accepted; logical backups, not
PITR; account deletion anonymises and keeps history; cryptography held at 48.0.1;
void legs excluded from the combined coupon; no rank across leagues; name
redaction in the working tree only, with no history rewrite.

SETUP
1. Check `date` before stamping anything (this Mac's clock has moved backwards).
2. Create branch chore/review-2026-09-28 from main. Save this prompt verbatim as
   docs/review/2026-09-28/00-prompt.md under a short "why it is shaped this way"
   header, in the style of 2026-09-13/00-prompt.md. Commit it.
3. Run scripts/check-deploy-drift.sh. Review main, and tag every finding "live" or
   "main-only" against what production actually serves.
4. Run scripts/ci-local.sh (full, then SKIP_PROD_BUNDLE=1) and record the baseline
   against the ratchets in scripts/ci-test-counts.env. If main is red, stop and
   report: per AGENTS.md, that gets its own fix/ branch first.

RESILIENCE (the last review lost its working notes)
The last review ran over seven days, was interrupted five times by usage limits,
and lost its raw notes to a temporary-directory cleanup. This time:
- Keep all working notes in docs/review/2026-09-28/notes/, never in /tmp or a
  scratchpad. Commit after each lens and at every natural checkpoint.
- Keep docs/review/2026-09-28/PROGRESS.md current: which lenses are done, which are
  in flight, and the exact next step. A cold session must be able to resume from
  it alone.

LENSES (one document each). Each one opens with a "Prior findings" table covering
its slice of the 2026-09-13 register: id, batch, held / regressed / partial, and
the evidence. "Held" means re-driven against something running, not re-read.

01 Security. Rebuild the route-by-route authorisation matrix (anonymous / member /
   league admin / site admin) including every route added since 2ce6f42, and test
   for cross-league IDOR. Re-drive SEC-15..SEC-2x: the PIN takeover (122), lockout
   (123), join-code rotation (124), the site-admin write bypass (125), name
   impersonation (126). New surfaces: account deletion and data export (136),
   admin pick correction (134), settle and rename notifications (135, 148),
   extra-week endpoints (132), and the CSP and framing headers (141), read-only on
   production. Also: a live OSV query over current pins and the lockfile, secrets
   in the tree and history, and a check that SEC-01..SEC-13 still hold.
02 Correctness. Judge against BUILD_PLAN acceptance, not intuition. Run the seeded
   app (tests/e2e_server.py, fake odds). Play at least two leagues with different
   windows, markets and pick_scope through open -> pick -> claim conflict -> lock
   -> settle -> standings -> season archive. Any single-league or single-window
   assumption is a bug. Priorities: the claim race (120), stranded rounds (121), a
   round completed by someone leaving (130), void win rate (131), extra weeks
   (132), the discovery and slate budgets (115, 133, 159, 161), pick correction
   (134), whether settled points still sum after anonymisation (136), the DST
   reminder (147), void legs (156), no cross-league rank (157), and the backup job
   (95) against a local fake target. Run the season-calendar backfill dry-run
   against the scratch database only. Include DST weekends, London vs UTC, and
   concurrent claims on one selection.
03 UI/UX and accessibility: objective checks only. Run axe-core in real Chromium
   on every route in both themes at 390x844 AND 1280x800, since there is now a
   desktop layout (140). Do a keyboard-only pass, visible focus on every control
   (158), accessible names, 200% zoom (168), reflow (167), prefers-reduced-motion,
   and 44px targets. Cover every state: first run (150), loading/skeletons, empty,
   error vs empty (149), offline, locked, settled, archive, admin console, toasts
   against the tab bar. Re-run any violation before recording it: the last review
   withdrew one that was a capture artefact.
04 Performance and operations. Re-take the 2026-09-13 measurements the same way at
   the same two data shapes (production's, and a 50-member league with a full
   season) and report before -> after: bundle size and route splitting,
   service-worker precache (163), the animation library (164), Lighthouse mobile
   (throttled) on the prod bundle served locally for home, coupon and standings,
   countdown re-renders (165), the standings main-thread cost (166), query counts
   and EXPLAIN on the hot endpoints (144, 146), pick submit latency with push
   fan-out (162), odds-api.io requests per job and per member action against
   100/hour and 500/day (the certified worst day is 481), and scheduler duration
   and overlap. No load against production. Also cover deploy and rollback hygiene
   (128), the alarm routing (129), and the fact that production still has no
   backup.
05 Feature gaps, briefly. What the spec and LAUNCH_PLAN promise that is not built
   (including FEAT-A12 and FEAT-B09, carried over), and what a paying member would
   expect that is missing. Ground every point in actual routers and components.
06 Premium design: judgement, but concrete. First judge the visual pass that just
   shipped (Batches 139, 140, 149, 150, 151, 158, 168): did it land? Then finish
   what 2026-09-13 left undone: the peripheral screens (auth family, settings,
   admin console, football), and the PWA polish pass (manifest, maskable icons,
   splash, theme-color, install prompt, safe-area insets in standalone mode).
   Fill the corpus gaps: a genuine settled-results screen, a settled combined
   coupon, and the four pick-feedback states. Prove every capture shows the state
   it is named for: hash for duplicates and open a sample. Last time, "loading",
   "error" and "feedback" captures were all the idle screen. Hold everything
   against FotMob, Sleeper, the official FPL app and Apple Sports, within the
   text-only constraint. Output: per screen, what works and what breaks the
   premium feel. Then the ten highest-leverage changes, ranked by impact / effort
   and specific enough to batch: token names and values, components, the "before"
   screenshot, and an HTML mockup where it helps. No regression of WCAG AA.
07 Agent delivery pipeline. 49 batches shipped with no human review, so audit what
   the agents did, not just the rules:
   - Sample the batch diffs for tests weakened alongside code: loosened
     assertions, new skips or xfails, deleted cases, and ratchets raised without
     matching tests.
   - Try to weaken the gate on a throwaway local branch (never pushed), and
     confirm assert-quality-guardrails.sh and the gate repair (152, 153) catch it.
   - What an automatic push can break before CI reports.
   - Contradictions or stale facts across AGENTS.md, CLAUDE.md,
     docs/agent-commands/, .claude/commands/, .codex/hooks.json and ci-local.sh.
   - Cold-start cost after Batch 154: BUILD_PLAN.md is 5,122 lines, more than
     before the restructure. Measure it and say whether closed rows should move
     out.
   - Which hazards are enforced by scripts and which only by prose.
   Propose an AI product feature only if it solves a concrete member problem
   better than a non-AI fix. "None" is an acceptable answer.

GUARDRAILS
- Production is read-only: HTTPS headers, /api/v1/health and public pages. No
  writes, no load, no signing in as real members, no production database reads,
  and no Railway, Vercel or Supabase changes. Never use the Supabase MCP; it is
  bound to a different product.
- Never touch the owner's Betfair account. Do not call odds-api.io live: the
  scheduler shares the 100/hour budget, and a probe can 429 the refresh job.
- apps/web/.env.local targets another product's API; override it for every local
  browser run. The browser flow needs FRONTEND_ORIGIN=http://127.0.0.1:4173.
  Use Chromium; WebKit will not install on this Mac.
- Never pass DATABASE_URL to psql.
- Fix nothing. Doc-only corrections are allowed, but list them and APPLY them on
  this branch (last time they were listed and left).

EVIDENCE STANDARD
- Every finding has: id, severity, live/main-only, verified or plausible, evidence
  (file:line, command and output, HTTP exchange, axe result, or screenshot path),
  a one-sentence impact on a member, and a recommended fix.
- "Verified" means reproduced against something running. Code reading alone is
  "plausible".
- Before rating anything HIGH or above, try to disprove it and record what you
  tried.
- Do not put unverified claims in a subagent's brief. Last time a lead's grep
  wrongly told a pass there was no route splitting.
- Severity. CRITICAL: picks, points or credentials are wrong, lost or exposed now.
  HIGH: the same under an unusual but reachable condition, or the Saturday flow
  can fail. MED: degraded correctness, security or efficiency with a workaround.
  LOW: hardening, hygiene, polish. INFO. Design findings use impact
  (high/med/low) instead.
- Don't pad. If a lens finds nothing material, say so and show what was checked.

DELIVERABLES: docs/review/2026-09-28/
- 00-prompt.md, as written in setup.
- README.md in the house format: how it was produced, baseline, the prior-register
  scorecard (held / regressed / partial counts), the new register ordered by what
  to act on first, what's already excellent (so nobody churns it), owner decisions
  needed (each with options and a recommendation), where the review was wrong,
  and what it did not do.
- 01-security, 02-correctness, 03-ux-accessibility, 04-performance-operations,
  05-feature-gaps, 06-premium-design, 07-agent-pipeline; screenshots/ with
  INDEX.md.
- 08-sequencing: new unchecked batch rows in docs/BUILD_PLAN.md, in the existing
  row format, from Batch 169, for every finding ready to build. Group them into
  deployment-safe runs (web-only / API-carrying / migration).
- 09-prompts: need (Deep / Standard / Light) and effort for each new batch, using
  the table in 2026-09-13/09-prompts.md, plus the copy-paste run order.
- 10-reconciliation: before writing the README, re-check every finding against
  the source at the final commit, line by line, and record any withdrawn or
  refined findings.
- Commit on the branch. Do not merge, push, /ship-prod or /batch-start anything;
  I will review the register first. Send me README.md when it is done.

You may run the lenses as parallel subagents. Give each one these guardrails,
its slice of the prior register and the notes/ path. You own verification, the
reconciliation and the README.

End with a summary of 15 lines or fewer: baseline, prior-register scorecard, new
counts by severity, the top five actions, and the decisions you need from me.
```
