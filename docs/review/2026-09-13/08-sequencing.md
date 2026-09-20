# 08 — Sequencing: how Batches 120-140 group

The same discipline as the 2026-08-26 sequencing: `/batch-start N` still takes
one batch, on its own branch, through its own gate, with its own automatic
close-out. A group never changes that isolation; it only decides the order and
where a production shipment has to fall.

**The deploy asymmetry still governs everything.** Every close-out pushes `main`
and Vercel releases the web app from it; Railway does not move until
`/ship-prod`. A group whose web half calls an API route the deployed image does
not serve is broken in production for the length of that gap.

**Start from behind.** A shipment is already owed — migration 025, Batch 113 —
and its web half is live against an API that 404s (PIPE-05). **Ship that before
starting Group N**, or the first close-out push stacks a second undeployed half
on top of the first.

## Group N — The Saturday defects · Batches 120, 121, 122 · **API-carrying** → `/ship-prod`

The findings a member can actually be hurt by this weekend. All server-side, so
nothing reaches members early and there is no asymmetry inside the group.

| batch | finding | why here |
| --- | --- | --- |
| 120 | CORR-08 | the claim-race 500 — the Saturday land-grab path |
| 121 | CORR-09, CORR-13 | the stray round that scores |
| 122 | SEC-15 | league-admin account takeover |

120 first: it is the one a member meets every time two friends reach for the same
selection. 121 next because its fix changes retirement *and* settlement, and
nothing else should be moving underneath it. 122 is the highest-severity security
finding but is not time-of-week sensitive.

## Group O — The rest of the security register · Batches 123, 124, 125, 126 · **API + web** → `/ship-prod`

| batch | finding |
| --- | --- |
| 123 | SEC-18 targeted lockout (web half first, then the API half) |
| 124 | SEC-16 join code survives removal and skips approval |
| 125 | SEC-17 site-admin write bypass |
| 126 | SEC-20 display-name impersonation |

**123 has a web half that helps on its own** — trying a token refresh before
falling back to a PIN prompt fixes the common case with no API change — so it can
close out and reach members immediately; its API half (per-source backoff and a
lockout notification) follows in the same group.

## Group P — Operations and the things that have been open too long · Batches 127, 128, 129 · **infrastructure** → `/ship-prod`

| batch | finding |
| --- | --- |
| 127 | OPS-11 Node 20 is past end-of-life |
| 128 | OPS-12 a migrating shipment leaves no rollback target |
| 129 | OPS-14 alarms that reach a person |

**Batch 95 is not renumbered and still sits outside this plan**: it remains
soft-blocked on the storage-egress attribution (FEAT-A09), and OPS-13 is what it
costs to leave open. The attribution is an owner action, not a batch, and it is
the cheapest unblock in this review.

127 goes first: it changes the toolchain the other two are verified on.

## Group Q — Correctness follow-ups · Batches 130, 131, 132, 133 · **API-carrying** → `/ship-prod`

| batch | finding |
| --- | --- |
| 130 | CORR-14 completion by attrition |
| 131 | CORR-10 void picks and win rate — **changes an oracle test, so report it** |
| 132 | CORR-11, CORR-12 calendar guards and the anchor (both main-only) |
| 133 | CORR-15 discovery's own budget |

132's two findings only exist once migration 025 ships, so this group must follow
that shipment.

## Group R — What a member expects · Batches 134, 135, 136 · **API + web** → `/ship-prod`

| batch | finding |
| --- | --- |
| 134 | FEAT-A10 correcting a mis-settled pick |
| 135 | FEAT-B08 a settlement notification |
| 136 | FEAT-B07 account deletion and export — **needs the owner decision first** |

134 is the one with a precedent: it has already been needed once and was done with
a script against production.

## Group S — The web pass · Batches 137, 138, 139, 140 · **web-only** → no shipment owed

Everything here reaches members on its own close-out push.

| batch | finding |
| --- | --- |
| 137 | UX-12 four public screens outside the shell |
| 138 | UX-13 opacity below AA |
| 139 | DES-02, DES-03 the pick screen opens closed; one red toast for every outcome |
| 140 | DES-01 a real desktop layout |

137 and 138 are small and independent. 139 pairs naturally with Batch 120 — the
same member moment, one fixing the response and the other how it reads. 140 is
the largest piece of visual work in the review and should be taken on its own.

## Held back deliberately

- **The pipeline batches** (PIPE-01 to PIPE-09) are tooling-only and deploy
  nothing, so they can be taken at any point. PIPE-01 should be done by the owner
  by hand, today, because it is a local configuration that contradicts the
  project's own rule.
- **DES-04 to DES-09** and the remaining feature gaps (FEAT-A11, FEAT-A12,
  FEAT-B09) are real but small; they belong in whichever group next touches
  those files rather than as batches of their own.
- **The unfinished lenses** (below) come before any of this if the owner wants
  the register complete first.

## What this review did not finish

Three passes were cut short by usage limits and are worth completing before the
register is treated as closed:

1. **The manual accessibility pass** — keyboard-only walk, focus-ring contrast,
   accessible names from the live tree, 200% zoom and 320px reflow, reduced
   motion, and 44px target measurement. The axe sweep and the screenshot corpus
   are done; this is the other half of lens 03.
2. **The web performance pass** — bundle size and route splitting, Lighthouse on
   the production bundle for home, coupon and standings, requests per screen and
   per idle minute, re-render hot spots and query-key hygiene.
3. **The odds-budget and scheduler pass** — requests per scheduled job and per
   member action, the hour-by-hour Saturday budget against 100/hour and 500/day,
   job durations and overlap, and event-loop blocking from the synchronous push
   sends. Note the correctness lens already found the three-window cliff
   (CORR-15) from the cost model.

Also unfinished: the peripheral design screens and the PWA polish pass
(manifest, maskable icons, splash, safe-area insets in standalone mode), and the
ranked top-ten design changes with mockups.

## Documentation corrections to apply

These are doc-only and were **not** applied by this review; they are listed so
the owner can take them in one pass.

| file | from | to |
| --- | --- | --- |
| `AGENTS.md` | "509 passed, 151 skipped" | 734 passed, 438 skipped (measured 2026-09-13; re-run for today's count) |
| `docs/agent-commands/batch-verify.md` | "ten checks" (full gate) | eleven checks; `SKIP_PROD_BUNDLE=1` leaves ten |
| `docs/agent-commands/batch-verify.md` | "It is `509 passed, 151 skipped`" | 734 passed, 438 skipped |
| `docs/agent-commands/batch-verify.md` | "It is 88 seconds. Run it." | roughly five minutes with a database (4m48s measured) |
| `docs/agent-commands/phase-closeout.md` | "509 passed, 151 skipped" | as above |
| `docs/LAUNCH_PLAN.md` | the nightly backup "still runs and still logs a successful dump" | no scheduled backup is registered; Batch 75 removed the job |
| `apps/api/src/routers/me.py` | docstring claiming nine queries | fifteen |
| `.claude/settings.json`, `.codex/hooks.json` | "only when the user asks" | **owner to decide** — it contradicts automatic close-out |
