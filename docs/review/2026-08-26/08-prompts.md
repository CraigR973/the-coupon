# 08 — Commands and prompts for running the groups

The original copy-paste prompts for Groups A-H are retained below as the record
of how those completed groups were started. Current Groups I-M use the canonical
slash command, which reads `07-sequencing.md` and every batch row from a cold
session without the owner having to restate their constraints:

```text
/group-start I
/group-start J
/group-start K
/group-start L
/group-start M
```

## The rhythm inside a group

Build-batch close-out is **automatic** as of the owner's decision on 2026-08-27
(`AGENTS.md`). A green `scripts/ci-local.sh` gate flows straight into
`/phase-closeout` — commit, ff-merge `main`, strike the batch, session log,
`STATUS.md`, **and the push**. So the group command carries each batch from
unwritten to merged and deployed on the web, while preserving one branch and
one close-out per batch:

```
/group-start X           → batch 1 branch, gate, close-out and push
                         → repeat for each batch before the next checkpoint
/ship-prod               → explicit command at an API checkpoint
/group-start X           → verify drift, then resume after the checkpoint
```

**The push deploys.** Vercel releases the web app from `main` on every close-out,
so a batch's frontend reaches members minutes after it verifies — your review
window is now after the deploy, not before it. The one place this bites is a
batch that adds a web half calling a *new* API route: the page goes live, the
route doesn't exist until `/ship-prod`. Batch 94 is the clearest case, Batch 96
and possibly 97 the others; their group prompts below carry the warning.

**A red gate self-heals, within limits.** Failures the batch itself caused get
fixed and the gate reruns, up to three attempts per check. What stops the run and
comes back to you: a pre-existing red on `main` (that gets its own `fix/` branch
first), a fix that would breach the batch's scope, three exhausted attempts, or a
worktree holding more than the batch. And green is never reached by weakening a
check — no deleting, skipping, loosening or `xfail`-ing. See `AGENTS.md`, "A red
gate: fix it, but only in one direction."

For the historical A-H prompts below, the next-batch instruction was:

```
/batch-start <N>
```

If the session went cold mid-group, use this so the constraints come back:

```
Continuing <Group X> from docs/review/2026-08-26/07-sequencing.md.
Batches <done> are closed. Read that group's section, then /batch-start <N>.
```

For Groups I-M, rerun `/group-start <letter>` instead. Checked rows are treated
as resumable progress. The command never infers that a checked API batch has
shipped: it runs `scripts/check-deploy-drift.sh` at the checkpoint and stops for
`/ship-prod` again unless production is in sync.

---

## Group A — Security fixes · 82, 83, 84, 85 · API only

```
Starting Group A from docs/review/2026-08-26/07-sequencing.md — Batches 82, 83,
84, 85. API-only, one /ship-prod at the end of the group.

Read that group's section first for the ordering constraints (82 is the only
HIGH finding and goes first; 83 needs a migration), then /batch-start 82.

Close out each batch automatically on a green gate, and report what the drift
check says at the end of each one.
```

## Group B — Client hardening · 86, 88, 87 · web only

```
Starting Group B from docs/review/2026-08-26/07-sequencing.md — Batches 86, 88,
87. Web-only, so no /ship-prod is owed at the boundary.

Note 86 and 88 edit the same two files (LoginPage.tsx, RegisterPage.tsx) and are
deliberately adjacent — 86 adds the <main>/<h1> shell, 88 hardens the ?next=
guard inside it. Read that group's section, then /batch-start 86.

These are web-only, so each close-out's push puts the change in front of members
straight away — tell me what visibly changed as each one lands.
```

## Group C — The pick path · 89, 90 · API + web

```
Starting Group C from docs/review/2026-08-26/07-sequencing.md — Batches 89 and
90. These two are one user moment and must not be split: 89 introduces the
server-side refusal state ("too many picks being made right now") and 90 is the
client that renders exactly that state alongside offline and lost-the-race
outcomes.

Read that group's section, then /batch-start 89. When you implement it, be
precise about the refusal contract 90 will have to consume — name the shape and
the message in the batch's own notes so 90 has something exact to build against.

90's web half deploys on its close-out push while 89's refusal state waits for
/ship-prod, so tell me the moment 90 is closed — that gap is exactly the window
where the client can render a state the API cannot produce.
```

## Group D — Infrastructure and resilience · 99, 100, 101, 95 · API

```
Starting Group D from docs/review/2026-08-26/07-sequencing.md — Batches 99, 100,
101, then 95 last. API/infra only, one /ship-prod at the end.

Before 95: check whether the FEAT-A09 Supabase egress investigation has happened.
95 adds a full logical dump to a quota whose main consumer is still unattributed
and which already caused one production 402 — if that's still open, stop before
95 and tell me rather than shipping a backup job that may re-trigger the outage
it exists to prevent.

Also note 99 edits routers/auth.py, which Group A's Batch 83 also touched — build
on the merged result.

Read that group's section, then /batch-start 99. Close out each batch
automatically on a green gate.
```

## Group E — League governance · 91, 94, 93 · API + web

```
Starting Group E from docs/review/2026-08-26/07-sequencing.md — Batches 91, 94,
93, in that order.

Batch 94 is the biggest deploy-asymmetry risk in this whole plan: it adds a new
API route AND a page that calls it. With close-out automatic, that page is live
to members the moment 94 verifies, while the route waits for /ship-prod — so 94
goes last in the group and **stop and tell me immediately when it closes**, in
the first line of your report, not buried in the drift output. That gap is how
Football Stats 404'd after Batch 51.

Read that group's section, then /batch-start 91.
```

## Group F — Season boundary · 96 · API + web

```
Starting Group F from docs/review/2026-08-26/07-sequencing.md — Batch 96 alone.

It changes what every standings figure means, touches services/scoring.py and the
screens that draw it, and interacts with Batch 80's recent_form window — check
that the form run doesn't silently span the new season boundary.

Read that group's section and the Batch 96 row, then /batch-start 96. It changes
both halves at once, so its web side deploys on close-out while the scoring
change waits — flag that in the first line of your report so I can ship straight
away.
```

## Group G — The visual pass · 98, 97, 92 · mostly web

```
Starting Group G from docs/review/2026-08-26/07-sequencing.md — Batches 98, 97,
92, in that order. This is the "does it feel premium" work and it's judged by eye,
not just by tests.

98 goes before 97 deliberately: the avatar treatment appears on home, standings
and every roster, so settling it first means 97's layout work is done against
final components.

For 97, first check whether the content it needs ("the member's other leagues",
a next-round countdown) is servable from the existing PerLeagueSummary — Batch 81
already extended it — or needs a new route. If it needs a route, tell me, because
then this group owes a /ship-prod and 97 has to go last.

Read that group's section, then /batch-start 98. Include screenshots at 390x844
in both themes with each batch's report — these deploy to members on close-out,
so the screenshots are how I see what shipped.
```

## Group H — Framework migration · 102 · web only

```
Starting Group H from docs/review/2026-08-26/07-sequencing.md — Batch 102 alone,
react-router 6 to 7.

Confirm Batch 88 is closed first — it fixes the app's own ?next= backslash guard
and shouldn't wait on this migration. Batch 88's redirect tests must still be
green on the new major.

Read that group's section, then /batch-start 102. Routing is exactly what this
changes and the close-out push deploys it, so the Playwright deep-link smoke
against the prod bundle must be part of the gate — if it isn't green, stop and
report rather than closing out.
```

---

## Current groups I-M

### Group I — Settings privacy consequences · 103 · web only

```text
/group-start I
```

Implements and closes Batch 103, then checks deployment drift and reports the
web-only group complete without deploying the API.

### Group J — Railway configuration migration · 104 · API + infra

```text
/group-start J
/ship-prod
/group-start J
```

The first invocation closes Batch 104 and stops. The owner explicitly ships it;
the second invocation verifies production is in sync and completes the group.

### Group K — Coupon and home hierarchy · 105, 106 · web only

```text
/group-start K
```

Runs 105 then 106 as separate batch branches and close-outs. No API shipment is
part of this group.

### Group L — Notification progress and completion · 107, 108 · API then web

```text
/group-start L
/ship-prod
/group-start L
```

The first invocation closes Batch 107 and stops at its API checkpoint. After the
explicit ship, the second verifies drift before it starts Batch 108.

### Group M — Football matchdays and team seasons · 109, 110, 111 · web, API, web

```text
/group-start M
/ship-prod
/group-start M
```

The first invocation closes web Batch 109 and API Batch 110 separately, then
stops. After the explicit ship, the second verifies drift before it starts the
dependent team-season UI in Batch 111.

---

## Closing a group

At each API checkpoint shown in `07-sequencing.md`, use the explicit command:

```
/ship-prod
```

Then rerun the matching `/group-start` command. It confirms deployment drift is
in sync before it crosses the checkpoint. For web-only groups there is nothing
to ship — Vercel already released each batch on its close-out push — and
`/group-start` runs the drift check only to report whether some unrelated API
shipment remains owed.

## The two items outside the batch flow

Neither is a batch; both can happen at any point, and the second should precede
Batch 95.

**Launch gate L5** — the owner's decision was to close it retroactively:

```
Close launch gate L5 retroactively per docs/review/2026-08-26/README.md
(owner decision, 2026-08-27). The events L5 asks you to watch have already
played out in production, so tick its seven sub-items from the evidence already
in STATUS.md and the Batch 68/74 backfill narrative rather than waiting for
another Saturday. Show me what you'd write before running /launch-closeout L5.
```

**FEAT-A09 — the Supabase egress consumer:**

```
Investigate FEAT-A09 from docs/review/2026-08-26/05-feature-gaps.md: something is
consuming the Supabase egress quota on the-coupon-production and it's still
unattributed — STATUS.md notes it may not be this project at all. It already
caused one production 402 (exceed_egress_quota) that took avatar storage down
while Postgres kept answering.

Pull the usage breakdown by service and date, read-only, and tell me what the
actual consumer is. This blocks Batch 95, which would add a full nightly dump to
the same quota. Do not attach production Supabase to MCP (see ship-prod.md).
```
