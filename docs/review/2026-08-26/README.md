# Full-application review — 2026-08-26

A follow-up to `docs/review/2026-08-22/` at commit `3795854` (Batches 1-81
closed, `main` caught up to production — confirmed via
`scripts/check-deploy-drift.sh` before this review started: production was one
docs-only commit behind, nothing to ship). Requested scope: security, code
quality, feature completeness against both the product's own spec and outside
product judgment, and UI/UX including a visual "does this look premium" pass —
covering the whole application, not just what changed, but built to avoid
re-deriving the 24 findings the last review already worked through.

## How this was produced

Five passes, run in parallel, each told to spot-check the relevant slice of the
2026-08-22 register rather than re-audit it from zero, then spend its real
effort on the 79 commits (Batches 54-81) that landed since:

- **Security** (`01-security.md`) — spot-checked all nine "fixed" 2026-08-22
  findings still hold (they do), confirmed SEC-09's deferred framework upgrade
  actually shipped (Batch 61), re-derived SEC-10's void against the real
  advisory mechanism, and audited everything new — public self-signup (Batch
  63), the notification system (Batches 76-77), and the admin/league surfaces
  added since. A live OSV query, production headers over HTTPS, and the
  `pywebpush` source were pulled and read directly rather than trusted from
  advisory titles.
- **Correctness** (`02-correctness.md`) — re-examined the two still-open
  findings (one turned out to have been a review error; the other's
  reachability genuinely changed since Batch 63), then read the business
  logic added since — the notification triggers, the standings "recent form"
  work (Batches 78-81), and the registration flow.
- **UI/UX and accessibility** (`03-ux-accessibility.md`) — the real app,
  seeded, played through a full pick → lock → settle cycle so the newer
  result/form surfaces had content, axe-core 4.10.2 injected live across 10
  screens × 2 themes (20 runs), including `/login` and `/register`, which
  didn't exist as a public route at the last review.
- **Visual design** (`06-ux-design.md`) — a separate, human pass over the
  same 20 screenshots, judging the app against a "professional product"
  bar per the owner's brief. Not automated; this is the one document in this
  review that is a judgement call rather than a verified fact.
- **Operations** (`04-operations.md`) — spot-checked the two still-open items
  (both unchanged), re-ran the dependency advisory scan against current pins,
  confirmed the CI gate still runs everything it claims to, and checked
  deploy docs against what actually shipped.
- **Feature gaps** (`05-feature-gaps.md`) — two separate questions: what the
  product's own spec (`BUILD_PLAN.md`, `LAUNCH_PLAN.md`) promises that isn't
  fully closed out (Part A), and what an outside product reviewer would flag
  as missing for what this product actually is — a private, points-only
  friends' game — grounded in the actual routers/components rather than
  invented (Part B).

## Baseline

Unchanged from `docs/review/2026-08-22/` at the top-level gate: `scripts/ci-local.sh`
passes clean, zero skips, run twice this session (with and without
`SKIP_PROD_BUNDLE`). Test count has grown from 1,047 (last review) to
whatever `ci-local.sh` reports today as Batches 54-81 each shipped with their
own tests per the project's convention.

## Register

Ordered by what I would act on first. "Batch N" means a new, unchecked batch
was drafted into `docs/BUILD_PLAN.md` on this branch — nothing has shipped,
each still needs `/batch-start N`. "Owner decision" means the finding needs a
call only the owner can make before it's batchable — same disposition the
prior review used for the contrast tokens and the empty-home-screen note, and
the same discipline applies: recorded as a decision, not a silent gap.

| id | sev | finding | disposition |
| --- | --- | --- | --- |
| SEC-12 | HIGH | push-subscription `endpoint` unvalidated — authenticated SSRF via open self-registration | **Batch 82** |
| FEAT-B01 | HIGH | pick submission (the app's core action) has zero offline resilience | **Batch 90** |
| CORR-06 | MED | registration's case-insensitive uniqueness has a case-sensitive DB backstop — concurrent race creates duplicate identities | **Batch 83** |
| OPS-08 | MED | `?next=` redirect guard misses the backslash open-redirect bypass (no fix in react-router 6.x) | **Batch 88** |
| UX-07 | MODERATE (a11y) | login/register render outside the page shell — no landmark, no `<h1>` | **Batch 86** |
| OPS-10 | MED (re-flagged) | aggregate pick-submission rate limit still unbounded; public signup + 50-member leagues make it a live 5x overshoot | **Batch 89** |
| FEAT-B02 / FEAT-A05 | MED | new leagues default fully open with no explanatory copy, in a product whose premise is "private" | **Batch 91** — default changed to invite-only per 2026-08-27 |
| FEAT-B04 | MED | league admins have no audit-trail visibility into their own league | **Batch 94** |
| CORR-05 | LOW | DST-boundary local-time construction; now reachable by any self-registered member, not just the owner | **Batch 84** |
| CORR-07 | LOW | one notification trigger skips the per-league mute gate its own batch added everywhere else | **Batch 85** |
| SEC-13 | LOW | service worker caches authenticated JSON for up to an hour despite `Cache-Control: no-store` | **Batch 87** |
| FEAT-B06 | LOW | no share surface for a settled result or standing (only the pre-lock coupon has one) | **Batch 92** |
| FEAT-A08 | LOW | three renamed members were never notified; their old names are now registrable by strangers | **Batch 93** |
| SEC-09 | ~~HIGH~~ | framework advisories | **fixed** — Batch 61 shipped 2026-08-25; register was stale, corrected here |
| CORR-04 | ~~LOW~~ | pick_scope mid-round change | **corrected** — the 2026-08-22 review missed the existing guard; there was never a live gap |
| SEC-10 | MED | react-router-dom open-redirect advisory | **void** in this tree, but no 6.x patch exists → **Batch 102** (migrate to react-router 7) |
| SEC-14 | LOW | registration's 409 is a username-enumeration oracle | **void** — accepted 2026-08-27; no lower-information failure exists without an email field, and the UX cost of a vague error is real |
| UX-08 | SERIOUS (a11y) | avatar palette uses fill tokens as text colour; bronze fails AA and a token swap alone doesn't clear it | **Batch 98** — solid fill + high-contrast text, clears AA by construction |
| UX-09 | — | home and standings end far short of the viewport on every screenshot captured | **Batch 97** — content *and* scale pass on home; standings excluded (test-seed artifact) |
| UX-10 | — | no team crests, competition badges, or any football imagery anywhere in the app | **declined** 2026-08-27 — app stays text-only; visual effort goes to UX-09 instead |
| FEAT-A01 | HIGH | launch gate L5 is the only phase never walked/closed, despite real Saturdays having already played out | **owner process action** — close retroactively from existing evidence via `/launch-closeout L5` |
| FEAT-A02 | HIGH | no managed backup or PITR — explicitly the largest standing risk, deferred by owner 2026-07-30 | **Batch 95** — durable off-box logical backups; managed PITR considered and set aside |
| FEAT-A03 | MED | rate-limit counters live in process memory, cleared on every redeploy | **Batch 99** — login + PIN-reset limiters move to Postgres; provider-budget stays in memory |
| FEAT-B03 | MED | no season boundary anywhere in scoring — standings never reset, no season-to-season or league-vs-league comparison | **Batch 96** — real season boundary + archive; cross-league comparison not taken |
| FEAT-A04 | LOW | migration-on-boot runs inside the web process | **Batch 100** — enforce the single-replica precondition in code rather than in a note |
| FEAT-A07 | LOW | FotMob terms-of-service risk backs three shipped features with no monitoring trigger | **Batch 101** — define the trigger and alert on it; fallback adapter not built |
| FEAT-A09 | INFO | unknown Supabase egress-quota consumer — already caused one production 402 | **owner/operational investigation** — attribute the consumer; **blocks Batch 95**, which adds egress |
| FEAT-B05 | LOW | no search or filter over round/member history | **backlog** — low impact at current scale |
| UX-11 | — | Settings is a flat, undifferentiated stack with no visual grouping | **backlog** — cheap, low priority |
| OPS-07 | MED (info) | `cryptography` advisories unreachable but capped below their fix by a macOS-wheel constraint | **doc fix only** — cross-reference added to `requirements.in` |
| OPS-09 | LOW | `AGENTS.md` undercounts the CI gate by one check | **doc fix only** — corrected |
| FEAT-A06 | LOW | `BUILD_PLAN.md`'s architecture section still names the superseded football provider | **doc fix only** — corrected |

**Twenty-one new batches drafted (82-102), three doc-only fixes made directly on
this branch, one register correction (SEC-09, already fixed by Batch 61), and one
review-error correction (CORR-04, never a live gap).** Nothing has shipped; every
batch still needs `/batch-start N`.

## Owner decisions — 2026-08-27

The thirteen items this review left as owner calls were put to the owner the day
after it was written. All thirteen were answered; eight became batches, one was
declined outright, one was voided, and three became process or operational
actions. Recorded here so the reasoning survives the way SEC-09's deferral did,
rather than being re-derived by the next review.

| item | decision | why it matters |
| --- | --- | --- |
| FEAT-A02 backup | **durable logical backups**, not managed PITR | Batch 95. Interacts with FEAT-A09 — a full dump adds egress to a quota with an unattributed consumer, so the investigation should land first |
| FEAT-A01 launch gate L5 | **close retroactively** | the events L5 asks you to watch have already played out in production; the gate document is what was never walked |
| FEAT-B03 season boundary | **add a real one**, with past seasons archived | Batch 96. Cross-league/season-vs-season comparison was *not* taken |
| UX-10 football imagery | **declined — stays text-only** | makes UX-09 the whole of the visual lever; no crest licensing exposure taken on |
| UX-09 home layout | **both** more content and a scale pass | Batch 97, and now the primary visual work rather than one of two options |
| UX-08 avatar contrast | **solid fill, high-contrast text** | Batch 98. Clears AA on all six palette slots by construction instead of tuning six colours against a tint |
| FEAT-B02 league privacy | **default to invite-only** | Batch 91. Existing leagues untouched — production's `test` league stays `public_open` |
| Batch 89 empty budget | **refuse with a clear reason** | keeps the frozen-odds invariant; no queueing, no cached price |
| FEAT-A03 rate limits | **security limiters durable, provider budget not** | Batch 99. Postgres, not Redis — no new infrastructure |
| FEAT-A04 migration-on-boot | **guard the precondition in code** | Batch 100. Migrations stay in the web process; a separate release step was set aside |
| FEAT-A07 FotMob terms | **define a trigger and alert** | Batch 101. The TheSportsDB fallback adapter is *not* being built yet |
| FEAT-A09 Supabase egress | **investigate and attribute** | operational action, and a soft blocker on Batch 95 |
| SEC-14 enumeration oracle | **void — accepted** | with no email field there is no low-information failure that isn't worse UX for a legitimate signup |
| SEC-10 react-router | **migrate to v7** | Batch 102. Batch 88 lands first — it fixes the app's own guard gap regardless of framework version |

## The documents

| file | covers |
| --- | --- |
| [01-security.md](01-security.md) | auth, sessions, the new push-notification surface, dependency advisories |
| [02-correctness.md](02-correctness.md) | game rules, races, the DST edge case, notification/standings logic added since Batch 54 |
| [03-ux-accessibility.md](03-ux-accessibility.md) | live axe-core sweep, 10 screens × 2 themes, objective findings only |
| [06-ux-design.md](06-ux-design.md) | the subjective "does this look premium" pass, from the same screenshots |
| [04-operations.md](04-operations.md) | the gate, dependencies, deploy hygiene, the aggregate rate-limit gap |
| [05-feature-gaps.md](05-feature-gaps.md) | spec-vs-built (Part A) and independent product judgement (Part B) |
| [07-sequencing.md](07-sequencing.md) | how Batches 82-111 group into deployment-safe runs, including the 2026-08-30 and 2026-09-03 addenda |
| [08-prompts.md](08-prompts.md) | `/group-start` invocations for current Groups I-M and the historical A-H kickoff prompts |

## Two things this review did not do

Same boundary as the prior one, for the same reasons:

- **No load or performance testing.** Still true; still worth its own exercise
  before a Saturday with meaningfully more members than today, especially
  given FEAT-A03 (in-memory limiters) and OPS-10 (aggregate rate limit) both
  point at the same underlying question — what happens when a league is
  larger than the ones this app has been tested against.
- **No live provider verification.** `AGENTS.md` reserves the real slate and
  pricing check for the owner; honoured throughout, including the local-only
  seeded instance used for `03-ux-accessibility.md`/`06-ux-design.md`.
- **OPS-08's redirect bypass was not click-tested live** — documented from the
  code and the advisory's own fix commit, flagged as plausible rather than
  confirmed-exploited, and batched anyway because the fix is cheap regardless.
