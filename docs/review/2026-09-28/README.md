# Full-application review — 2026-09-28

The fourth standing review of The Coupon, at `main` `eb18bcb`, following
`docs/review/2026-08-22/`, `2026-08-26/` and `2026-09-13/`. Four lenses at once: senior
engineer, application security engineer, the AI engineer responsible for the agent-driven
delivery pipeline, and a product designer holding the app to a paid consumer sports app.
Its first job: prove that Batches 120-168, 95 and 115 — 49 batches, 130 commits and ~23,000
lines, every one built by an agent and deployed by automatic close-out with no human review
first — actually fixed the 2026-09-13 register.

**In one line: the agents fixed most of what they were given, and did not cheat to get there,
but "ticked" is not "fixed" — a quarter of the prior register is only partly fixed, four new
defects came in with the fixes, and production still has no backup.**

## How this was produced

Seven specialist passes run as subagents, three at a time, each briefed in writing
(`notes/briefs/`) with the guardrails and its slice of the prior register, keeping its notes in
`notes/<lens>/` and committing at every checkpoint. The lead built and smoke-tested a shared
local harness (`notes/harness/`: scratch PostgreSQL, the seeded API with fake odds, the
production bundle), verified every HIGH finding personally, reconciled every finding against the
source (`10-reconciliation.md`), and wrote the batch rows.

- **Backend** — scratch PostgreSQL at migration 026, the seeded API on the production odds path
  onto a counting fake, pushes captured. Four leagues with different windows, markets and claim
  scopes played open → pick → conflict → lock → settle → standings → coupon → archive; lock and
  settle advanced by the scheduler's own jobs. The backup job ran against a local fake S3 and was
  restored. No live provider was called.
- **Security** — 73 routes × 7 roles probed, cross-league ID substitution, a live OSV query over
  62 Python and 838 npm pins, a secret scan of every added line in 543 commits.
- **Frontend** — the production bundle in real Chromium: 354 axe-core runs over 38 paths in both
  themes at 390×844 and 1280×800, a keyboard walk, focus measured from pixels, and a corpus of 526
  captures, each hash-checked and its state confirmed by opening it. The 14 duplicate hashes are
  all accounted for: 8 are UX-25's evidence (an error state identical to loading or empty) and 6
  are lens 06 re-captures identical to lens 03's.
- **Performance** — statement counts and EXPLAIN at production's shape and a 50-member,
  full-season stress shape; provider spend at one, three and five windows; bundle and precache.
- **Pipeline** — every commit since `2ce6f42` scanned hunk by hunk for weakened tests; the
  guardrail and close-out guard replayed as they stood at each commit; 24 attempts to weaken the
  gate on a throwaway worktree (never pushed); CI history read with `gh`.
- **Production** — read-only: response headers, `/api/v1/health`, public pages. Nothing written,
  no load, no member session, no database read.

**It ran over two days, not one, and was stopped by the usage limit four times.** The notes
survived every stop because they lived in the repository; each pass resumed from its own
`progress.md`. After the second stop the lead cut parallelism from six passes to three, because
every resume re-sends a whole transcript. The record is in `PROGRESS.md`.

## Baseline

Green on `main` `eb18bcb`, run twice:

| gate | result |
| --- | --- |
| `scripts/ci-local.sh` | **PASS, 11 checks, 11m18s** |
| `SKIP_PROD_BUNDLE=1` | **PASS, 10 checks, 10m37s** |
| backend | **1,350 passed, 0 skipped** — equal to the ratchet |
| frontend | **1,204 passed, 0 skipped** — equal to the ratchet |
| pytest without a database | 800 passed, 550 skipped (29 Sep) |
| versions | python 3.12.13 · fastapi 0.141.1 · starlette 1.6.0 · ruff 0.5.4 · Node 24.21.0 |

**Deployment drift: none.** Production's API serves `b08a47f3` at migration 026, and none of the
14 later commits reaches the image; the web app serves `4121cf0` (its stylesheet carries Batch
149's last change). **Every finding below is live.**

## Did the fixes work? The prior-register scorecard

81 items from 2026-09-13 (SEC-24 was withdrawn there), each re-driven against something running:

| verdict | count | which |
| --- | --- | --- |
| **held** | **46** | the claim race, the stray round's scoring, the lockout push, join codes, site-admin writes, CSP, logout storage, void win rate, extra weeks and the anchor, the DST reminder, rank removed, landmarks, contrast, the toast live regions, every provider-budget fix, compression, indexes, the precache, the animation library, the countdown, Node 24, the migration recovery note, alarm routing, account deletion and export, the settle notice, the rename notice, the gate's port and ratchet, the cold-start trim, the name redaction |
| **partial** | **21** | SEC-15, SEC-18, SEC-20, CORR-14, CORR-15, void legs, UX-14, UX-15, UX-20, PERF-16, FEAT-A10, PIPE-02, 04, 05, 06, DES-01, 02, 03, 05, 06, 08 |
| **not fixed** | **11** | CORR-13 and PERF-17 (ticked by 121 and 164, not fixed); UX-18, OPS-17, OPS-18 (never batched); SEC-22, OPS-15 (dropped between the plan and Batch 127); FEAT-A12, FEAT-B09 (held back); OPS-13 backups, PIPE-01 local config (owner actions) |
| **regressed** | **0** | — |
| accepted / by decision | 2 | CORR-16, PERF-02 |
| pending | 1 | PERF-14 (Lighthouse on standings) — see "What this review did not do" |

**The pattern in the partials** is one shape repeated: a fix covers the exact case the finding
described and misses its neighbour. The admin guard stops a reset of a current admin but not of
one demoted a second earlier (SEC-27); the source backoff is charged but never checked (SEC-28);
completion is re-checked on leave but not on self-deletion, which a later batch added (CORR-19);
void legs left the coupon but not results or home (CORR-21). Each batch's own tests encoded its
own case, so each passed.

**Four new defects came in with the fixes:** dark-mode toasts made illegible by Batch 149's last
commit (DES-10), the tab bar's marker two tabs off from Batch 164 (UX-26), the zoomed header
overflowing from Batch 168 (UX-27), and a pick burst exhausting the pool — Batch 162's background
fan-out holding the connections Batch 146 halved (PERF-20).

**The agents themselves behaved well.** Across 55 code commits there is no new skip, xfail or
`.only`; every changed expectation was specified by its row and reported; the one oracle change
(Batch 131) stopped for the owner as planned. What is weak is the machinery around them (PIPE-10
to PIPE-14).

## Register — ordered by what to act on first

New ids continue the 2026-09-13 numbering. Severity for engineering findings; impact
(high/med/low) for design.

| id | sev | finding | batch |
| --- | --- | --- | --- |
| OPS-13 | HIGH (carried) | **Production has had no backup for 56 days** — the job is built and switched off | owner action |
| DES-10 | high | Every toast is illegible in dark mode, the default — 1.01-1.07:1, since 28 Sep | 169 |
| SEC-32 | **HIGH** | A league admin can take over any member of their league, and every other league that member plays in; the member is told nothing | 179 |
| PERF-19 | **HIGH** | Combined odds overflow at 30-50 members: home and results return 500 for the whole league, permanently for history | 183 |
| PIPE-10 | MED | The gate is judged by the branch's own copy; `exit 0` or a new config file switches checks off — six weakenings at once passed | 198 |
| PIPE-11 | MED | The protected smoke script changed three times on 22 Sep on branches the guardrail refuses, with no record | 198 |
| UX-31 | MED | Offline mid-session, tapping a pick gives an endless spinner and no "queued" message (= DES-16) | 172 |
| UX-25 | MED | Six screens show a failure as empty — the coupon says "No coupon this week yet" | 172 |
| SEC-28 | MED | The per-source login backoff never stops a lock: one address still locks any number of members | 180 |
| SEC-27 | MED | Demote a co-admin, then reset their PIN: takeover | 179 |
| CORR-20 | MED | After a window change, a round that can never settle still takes picks, pending for ever | 184 |
| CORR-13 | MED (carried) | Two rounds in one football week still share a label | 184 |
| CORR-19 | MED | Self-deletion completes a round silently and credits the next picker | 185 |
| PERF-20 | MED | A pick burst in a big league exhausts the pool: 500s, and 294 alerts dropped | 191 |
| CORR-24 / PERF-21 | MED | Discovery is priced at the raw pool (36 vs 23 walked); the refresh has no budget — 118/hour at five windows | 189 |
| PERF-23 | MED | One pick bucket for the whole deployment: 50 an hour, 100 a day, changes of mind included | 190 |
| PIPE-12 | MED | 8 of 72 CI runs on `main` failed; Batches 120-122 pushed on red; nothing reads CI | 199 |
| PIPE-13 | MED | The only end-to-end journey is outside the gate; it rotted for five days | 200 |
| PIPE-14 | MED | The split-half refusal is cleared by a flag with no record; a two-batch split passes | 201 |
| DES-11 | high | Every translucent colour compiles to nothing (53 utilities, 126 uses) — the header and tab bar have no fill | 171 |
| DES-13 | high | Navigation fills the first phone screen; the first price is 351 px below the fold | 175 |
| UX-28 | MED | Keyboard focus lands behind the tab bar and header | 174 |
| UX-30, UX-22 | MED | Escape on five dialogs drops focus; the install gate has no landmark | 174 |
| UX-18, UX-21 | MED (UX-18 carried) | Lost picks dimmed below AA on the coupon and profile | 173 |
| FEAT-A13 | MED | Pick correction needs a database read to use and fixes one pick per fixture | 187 |
| FEAT-B10 | MED | Notifications leave no record; ~half the league has no push | 194 |
| PERF-18 | MED | The pick screen runs two queries per competition — 56 statements | 192 |
| OPS-17 | MED (carried) | A job due while the worker is busy is dropped (1 s misfire grace) | 193 |
| SEC-29 | LOW-MED | A per-league name can copy someone outside the league; no screen sets one | 181 |
| DES-12, 14, 15, 17, 18 | med | Z-order rankings at 1280; prices at caption size; settled rounds read as a price board; first-run copy while loading; the installed shell does not match | 176, 175, 173, 172, 178 |
| CORR-21, 22, 23, 25, 26, 27 | LOW | Void legs on two more surfaces; silent corrections; unpicked rounds never settle; the backfill counts deleted leagues; "4 of 3"; departed members hold claims | 186, 187, 188, 173, 185 |
| UX-23, 24, 26, 27, 29, 32, 33 | LOW | Tab bar marker and label, clipped labels, zoomed header, focus details | 170, 174 |
| SEC-30, SEC-31, OPS-19, PERF-22 | LOW | Toolchain advisories 17 → 32; an over-long hint is a 500; operator CLIs on Node 20; a dead dependency | 202, 182, 203 |
| FEAT-A12, A14, A15, B09, B11, B12 | LOW | Closed sign-ups are a dead end; corrections invisible to leagues; routes with no screen; history across seasons; mute granularity; members can't share the code | 195, 187, 179/181, 196, 194 |
| PIPE-15-18, PIPE-19 | LOW / INFO | Follow-ups nobody owns; tautological tests; the hook fires at the wrong moment; closed rows in the open head (fixed on this branch); dormant machinery | 203 |
| DES-19-23 | low | Football tables closed; "Former" as a name; off-palette offline banner; admin tabs overlap; anonymous invites | 177, 173, 197 |
| PIPE-01 | HIGH (carried) | Local agent config still binds a write-capable database tool to another product | owner action |

**New findings: 2 HIGH, 23 MED, 25 LOW, 1 INFO**, plus design **3 high, 5 med, 5 low**. No
CRITICAL. Eleven prior items carried as not fixed. Every surviving finding has a batch (169-203),
an owner action, or an explicit acceptance.

## What is already excellent — do not churn it

- **The agents' test discipline.** No skipped, xfailed or deleted tests to reach green in 55 code
  commits; every expectation change was specified and reported.
- **The claim race is solid.** 4 × 12 simultaneous submissions in both scopes: one 201, eleven
  409s with CORS, zero 500s.
- **Access control holds.** 73 routes × 7 roles with no unexpected access; cross-league ID
  substitution scoped everywhere; no live secret in 543 commits; the API's headers exemplary; the
  web CSP's `script-src` strict (one hash, no `unsafe-inline`).
- **Anonymisation keeps history exactly.** After an erasure, every other member's points, win
  rate and summary were byte-identical, and the erased member's settled points still sum.
- **The backup works.** Run against a local fake S3, it dumped, uploaded and restored
  byte-identically, and failed safely on every misconfiguration tried. Only switching it on remains.
- **The provider budget is honest now.** The counter equals a counting fake in every simulated
  hour; three windows went from 145/hour and 527/day to 72 and 337.
- **The web client got lighter.** 823.6 → 697.3 KiB of JS, no animation library, no admin chunks
  in the precache, the countdown no longer re-renders the screen, no text under 12 px.
- **Time is right.** Reminders across both 2026/27 clock changes fire once per round; London, New
  York and Sydney members see correct lock times.
- **Accessibility basics are complete.** Zero unnamed controls, zero 24 px target failures,
  reduced motion works everywhere, failures announced assertively, toasts clear the tab bar with
  a real safe-area inset.
- **The pick refusals read right** — conflict, price moved, busy each get their own variant and
  the action that follows (once the toasts are legible).

## Owner decisions needed

Numbered so you can answer "1) yes 2) b …". Each names the batch it unblocks.

1. **League-admin PIN resets (SEC-32, Batch 179).** Options: (a) retire the league-scoped route —
   no screen uses it — so every reset goes through your site console, and notify the member on
   reset and on PIN set; (b) keep it for members in no other league, refuse anyone demoted inside
   the 24-hour window, and notify; (c) accept. **Recommend (a):** it closes the takeover and the
   cross-league reach outright, costs league admins nothing they can do today, and the register
   screen's promise is then corrected rather than kept. Cost: one API batch.
2. **A departed member's unlocked picks (CORR-27, Batch 185).** (a) keep, as now — the claim blocks
   that selection all week; (b) delete picks on rounds not yet locked, keep locked and settled.
   **Recommend (b):** your 2026-09-22 "keep history" was about history; an unlocked pick is not
   history yet.
3. **Picks on a round the settle guard refuses (CORR-20, Batch 184).** (a) void them — the member
   sees "void, no points"; (b) leave pending. **Recommend (a),** and stop offering such rounds.
4. **Correcting a wrong result (FEAT-A13, Batch 187).** (a) per fixture, across every league, from
   the admin Results screen; (b) a screen over today's per-pick route. **Recommend (a):** one wrong
   result touches every pick on that match. Cost: the largest batch here, `max` effort.
5. **Per-league display names (SEC-29, Batch 181).** (a) remove the route — nothing in the app sets
   one; (b) harden it. **Recommend (a).**
6. **Should close-out wait for CI? (PIPE-12, Batch 199).** It reverses the written "Do not poll
   CI". **Recommend yes:** ~7-8 minutes per batch, and three batches have already pushed on red.
7. **Gate-maintenance approval** for Batches 198-201 and 203, which edit protected files, recorded
   in the guardrail as for 127 and 153. **Recommend yes, 198 first** — the gate can currently be
   switched off from inside a branch.
8. **Toolchain refresh (SEC-30, OPS-15, Batch 202).** (a) refresh, one major at a time; (b) record
   an acceptance. **Recommend (a),** after the gate batches: 32 build-tool advisories and four
   majors behind.
9. **Notification history (FEAT-B10, Batch 194).** Build it (a small table, a bell on home) or
   accept push-only. **Recommend build:** STATUS counts 7 push subscriptions for 13 accounts, so roughly half the
   league gets none of the five announcements. Cost: the review's
   only migration.
10. **Closed sign-ups (FEAT-A12, Batch 195).** A public `signup-status` route, and let an invite
    create an account while sign-ups are closed. **Recommend yes** — today there is no way in at
    all when closed, and the state is already public.
11. **Brand colour for the installed app (DES-18, Batch 178).** (a) move the icon, splash and
    status bar to the app's palette; (b) adopt navy as an app token; (c) leave. **Recommend (a).**
12. **May an invite link name the league and inviter before sign-in? (DES-23, Batch 197).**
    **Recommend yes** — the token is already a secret the inviter chose to share.
13. **Site admins editing leagues they have not joined** (settings, invites, resets — all
    audited). Keep, read-only, or none. **Recommend keep,** recorded as Batch 125's deliberate
    scope; the harm SEC-17 named is closed.

**And the owner actions that are not batches:** switch on the backup (`docs/runbooks/backup-restore.md`
— 56 days without one); rescope the local agent configuration (PIPE-01); do not run the
season-calendar backfill until Batch 188 ships; close launch gate L5 retroactively (FEAT-A01); and
attribute the storage-egress consumer (FEAT-A09), which the backup's bucket choice still depends on.

## Where this review was wrong

- **The lead's harness built an unstyled bundle.** `web.sh` ran Vite outside `apps/web`, so
  Tailwind emitted 9 KB of CSS; nine captures from lenses 02 and 05 are unstyled. Lens 03 caught
  it; it was fixed and those captures relabelled as text-only evidence. No finding depended on
  their styling.
- **26 of lens 03's captures were taken offline.** Lens 06 caught it; the rows are marked and the
  screens re-captured. No finding rests on them, but axe may have under-reported on those six
  screens in that state.
- **A pass copied a redacted member's name into its notes** (a scan of historical test diffs).
  Lens 01 caught it; it was replaced and this unpushed branch's history rewritten so no commit
  carries it. `main`'s history is untouched, per your decision.
- **SEC-32 was first recorded as an owner decision** and raised by the lead on reconciliation: the
  2026-08-23 decision it seemed to fall under predates the league-scoped route.
- **DES-16 and UX-31 are the same defect**, found by two lenses; merged.
- **A first CI count read 6 failures, not 8**: `gh run list --branch main` silently returns 16 of
  72 runs.
- **The 2026-09-13 review was wrong in two places this one found.** Its "no N+1 anywhere" missed
  the pick screen (PERF-18) — its round spanned one competition, so the count never moved. And its
  plan let four items fall through: SEC-22 "folded into 127" (which left it out), and UX-18, OPS-17
  and OPS-18 given no batch at all.

## What this review did not do

- **Lighthouse and the wall-clock timings** (PERF-14 and lens 04's timing rows) were staged for a
  quiet machine and were still running when this README was written; `04-performance-operations.md`
  records their state at the final commit.
- **No real device or screen reader.** WebKit will not install on this Mac, so iOS standalone
  rendering is judged from files and geometry (DES-18).
- **Pushes were not observed** — the harness has no VAPID keys; who is targeted was counted.
- **The cross-league half of SEC-32 was not driven as its own probe** (the script was stopped by
  a safety classifier and not retried by another route); it follows from the code.
- **The name-redaction check derived 5 of the 11 names** from Batch 155's diff; the tree is clean
  of those five.
- **No production reads** beyond headers, health and public pages; the backup state, push counts
  and member B's rename notice come from `STATUS.md`.

## Doc corrections applied on this branch

Listed in `notes/lead/doc-corrections.md`: the stale gate figures (800 passed / 550 skipped),
the push is close-out step 9, Group Z exists, batch-verify's single-file commands use the gate's
venv, STATUS says what the 481 budget omits and what the web serves, LAUNCH_PLAN records Batch
95, the SEC-22 note in the 2026-09-13 sequencing, a note on Batch 123's row, and the seven ticked
rows moved out of the build plan's open head. **`phase-closeout.md` is a protected file**, so
`ci-local.sh` run on this branch fails its guardrail until merged.

## The documents

| file | covers |
| --- | --- |
| [01-security.md](01-security.md) | the matrix, the reset and lockout residues, headers, OSV, secrets |
| [02-correctness.md](02-correctness.md) | four leagues through the whole loop; races, calendar, budget, backup, backfill |
| [03-ux-accessibility.md](03-ux-accessibility.md) | 354 axe runs, focus from pixels, keyboard, reflow, states |
| [04-performance-operations.md](04-performance-operations.md) | before → after at two shapes; provider spend; bundle; scheduler; deploy |
| [05-feature-gaps.md](05-feature-gaps.md) | spec versus built; what a paying member expects |
| [06-premium-design.md](06-premium-design.md) | did the visual pass land; peripheral screens; PWA; the top ten with mockups |
| [07-agent-pipeline.md](07-agent-pipeline.md) | what the agents did; the gate attacked; CI; cold start |
| [08-sequencing.md](08-sequencing.md) | Batches 169-203 in deployment-safe groups |
| [09-prompts.md](09-prompts.md) | need, effort and the copy-paste run order |
| [10-reconciliation.md](10-reconciliation.md) | every finding re-checked against the source |
| [screenshots/](screenshots/) | 526 captures, indexed by `INDEX.md` |
| [PROGRESS.md](PROGRESS.md) | how the run went, including the four interruptions |
