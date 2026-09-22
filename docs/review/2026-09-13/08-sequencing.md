# 08 — Sequencing: how Batches 120-157 group

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

## The decided order (owner, 2026-09-22)

1. **`/ship-prod`** — migration 025, owed since 13 September.
2. **The three unfinished passes** — manual accessibility, web performance,
   odds budget and scheduler. The owner chose to complete the register before
   building.
3. **Batch 152** — the gate repair, taken out of order.
4. **Group N onward** as laid out below.

Steps 2 and 3 both delay Group N, which holds the live Saturday defects. That is
the owner's call, recorded here rather than argued with.

Also decided: hold the cryptography pin at 48.0.1 (Batch 142 documents the
advisories as unreachable instead of bumping); anonymise on account deletion
(Batch 136); exclude void legs from the combined coupon (**Batch 156**, new);
drop the cross-league average rank (**Batch 157**, new); redact names in the
working tree only (Batch 155); realign the stop-hook text (Batch 153); do the
storage-egress attribution next, then Batch 95. PIPE-01 is the owner's own
two-minute fix and is not a batch.

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

## Group T — Security hardening · Batches 141, 142, 143 · **web + API** → `/ship-prod` at the end

| batch | finding |
| --- | --- |
| 141 | SEC-19 no CSP, and the app can be framed (web-only, reaches members on its own push) |
| 142 | SEC-21 cryptography pin, SEC-23 web-push timeout and port |
| 143 | SEC-25 logout leaves a league name, SEC-26 invite to a deleted league |

142 carries a live decision inside it: the fix version is past the point where
macOS wheels stop, which the local gate deliberately fails on. Decide there
rather than working around it.

## Group U — The measured performance work · Batches 144, 145, 146 · **API-carrying** → `/ship-prod`

| batch | finding |
| --- | --- |
| 144 | PERF-01 the labelling helper reads every round, twice (+ OPS-16 docstring) |
| 145 | PERF-03 an 84 KB slate served uncompressed |
| 146 | PERF-04 (as corrected) and PERF-05 — indexes and pool sizing |

**144 is worth taking before the 025 shipment if it can be**, because that
shipment is what makes it live. 146 is the only migration in this half of the
plan.

## Group V — The remaining member-facing gaps · Batches 147, 148 · **API + web** → `/ship-prod`

| batch | finding |
| --- | --- |
| 147 | CORR-17 the reminder skips the repeated DST hour |
| 148 | FEAT-A11 a renamed member with no push can never be told |

147 is low priority but cheap, and the October clock change is the deadline that
makes it worth doing now rather than next year.

## Group W — Finishing the visual pass · Batches 149, 150, 151 · **web-only** → no shipment owed

| batch | finding |
| --- | --- |
| 149 | DES-04, DES-05, DES-06 — toasts, skeletons, error states |
| 150 | DES-07 first-run home |
| 151 | DES-08, DES-09 — one statistic component, and a type scale |

151 raises font sizes and unifies a component; it touches the most files of the
three, so it goes last.

## Group X — The pipeline · Batches 152, 153, 154, 155 · **tooling-only, deploys nothing**

| batch | finding |
| --- | --- |
| 152 | PIPE-03, PIPE-04, PIPE-05 — the gate can test the wrong server, records no counts, and the drift check runs after the push |
| 153 | PIPE-06, PIPE-02 — stale gate numbers, and a hook that contradicts the policy |
| 154 | PIPE-07 — 106k tokens of cold-start reading |
| 155 | PIPE-08 — real names in a public repository |

**Take 152 early, out of order if necessary.** Every other batch in this plan is
verified by the gate it repairs, and 152 is what makes "green" mean something
before an automatic push deploys it. 153's hook change and 155's redaction both
need the owner first.

**PIPE-01 is not a batch.** The local agent configuration binds a write-capable
database tool to the wrong project with a blanket shell allow; it is a file on
the owner's machine, outside the repository, and should be corrected by hand
rather than by an agent that the same configuration governs.

## Accepted with no action

- **CORR-16** — the season-rollover week split across two calendars. No league
  plays that boundary; revisit if one does.
- **SEC-22** — seventeen advisories confined to the build toolchain, none
  reachable in production. Folded into Batch 127's toolchain refresh as hygiene.
- **SEC-14**, and the other decisions recorded on 2026-08-27, are unchanged.
- **CORR-18** (average rank across leagues) and the combined coupon's treatment
  of a void leg are **owner decisions**, not batches — see the README. If the
  owner drops the rank field, it is a one-line change to fold into any web batch.

## Held back deliberately

- **FEAT-A12** (the register screen ignores the signup kill switch) and
  **FEAT-B09** (the history has no season filter) are small and web-only; they
  belong in whichever batch next touches those screens rather than alone. Note
  FEAT-A12 needs the configuration route readable unauthenticated, which reverses
  a documented decision — raise it if it is taken.
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
