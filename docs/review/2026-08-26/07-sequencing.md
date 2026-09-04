# 07 — Sequencing: how Batches 82-111 group

The batches from this review and its later owner-review addenda, arranged into
deployment-safe groups. First written 2026-08-27, after the owner's decisions in
`README.md`; extended on 2026-08-30 and 2026-09-03.

## What a "group" is in this repo

`/batch-start N` still takes **one** batch number and makes one
`feat/batch-N-slug` branch. `/phase-closeout N` still takes **one** verified
batch, merges it to `main`, ticks it, logs it and pushes. A group never changes
that isolation.

For current Groups I-M, `/group-start X` is the orchestration command around
those one-batch workflows. It runs the group's unchecked batches in order, each
on its own branch and through its own full gate and automatic close-out. It
stops at every documented API checkpoint and asks for the separately explicit
`/ship-prod`; rerunning the same group after shipping verifies deployment drift
before it resumes. It never deploys production itself.

That is already the established pattern: `docs: specify Batches 78-80 from the
owner's three points` grouped the *specification*, then Batches 79, 80 and 81
each got their own `docs: close out Batch N` commit, and a single
`docs: record the 2026-08-26 shipment of Batches 79-81` closed the group.

The underlying loop remains:

```
/group-start X      → /batch-start N on its own branch and full gate
                    → automatic /phase-closeout N and push
                    → repeat only until the next deployment checkpoint
/ship-prod          → explicit owner command at that checkpoint
/group-start X      → verify drift is in sync, then resume the group
```

**The group boundary matters because of the deploy asymmetry.** Every
`/phase-closeout` pushes `main`, and Vercel releases the web app from `main`
immediately. Railway does not move until `/ship-prod`. So a group whose web half
calls an API route the deployed image does not serve is broken in production for
the length of that gap — that is the 2026-08-06 incident, and Batch 51 repeated
it. Groups below therefore use internal checkpoints where a later web batch
depends on a new API contract; a group no longer implies only one ship at its
end.

## The groups

### Group A — Security fixes · Batches 82, 83, 84, 85 · **API only** → `/ship-prod`

The highest-severity work, and all of it server-side, so nothing reaches members
early and there is no asymmetry risk inside the group.

| batch | why here |
| --- | --- |
| 82 | the only HIGH security finding — authenticated SSRF via push subscribe |
| 83 | registration race; touches `routers/auth.py` |
| 84 | DST window validation; `routers/leagues.py` validators |
| 85 | notification mute gate; sits beside 82's notification surface |

82 first — it is the one finding an outsider could act on today. 82 and 85 both
live in the notification code, so they share context; 83 and 84 are both
input-validation fixes in routers.

Note: 83 needs a migration (functional unique index on `lower(display_name)`).

### Group B — Client hardening · Batches 86, 87, 88 · **web only** → no ship needed

Three small, independent frontend fixes. Web-only, so each reaches members on
its own close-out push and no `/ship-prod` is owed at the boundary.

**86 and 88 touch the same two files** (`LoginPage.tsx`, `RegisterPage.tsx`), so
run them adjacent — 86 adds the `<main>`/`<h1>` shell, 88 hardens the `?next=`
guard inside it. Doing them apart means touching the same components twice.

88 also unblocks Group H.

### Group C — The pick path under pressure · Batches 89, 90 · **API + web** → `/ship-prod`

These two are one user moment and should not be split. 89 introduces a new
server-side refusal state ("too many picks being made right now"); 90 is the
client that has to render exactly that state alongside offline and lost-the-race
outcomes. Built apart, either 89 ships a message nothing displays, or 90 handles
a message that does not exist yet.

This group carries FEAT-B01 — the review's highest-value product finding — so it
is worth doing early despite being more work than Groups A and B.

**Ship promptly at the boundary.** 90's web half reaches members on push; 89's
refusal state does not exist until the ship.

### Group D — Infrastructure and resilience · Batches 99, 100, 101, 95 · **API/infra** → `/ship-prod`

The standing-risk work from the owner decisions. All server-side.

| batch | why here |
| --- | --- |
| 99 | durable login/PIN-reset limiters (migration) |
| 100 | single-replica guard on migration-on-boot |
| 101 | FotMob failure trigger and alert |
| 95 | durable off-box logical backups |

**95 goes last in this group, and is soft-blocked.** A full logical dump adds
Supabase egress to a quota whose main consumer is still unattributed (FEAT-A09,
which already caused one production 402). Attribute that consumer before 95
lands, or the backup job may re-trigger the outage it exists to protect against.

Note: 99 touches `routers/auth.py`, which Group A's Batch 83 also edits. Group A
lands first, so 99 builds on the merged result — no conflict, but worth knowing
the order is deliberate.

### Group E — League governance · Batches 91, 94, 93 · **API + web** → `/ship-prod`

Three batches about who controls and can see into a league.

| batch | why here |
| --- | --- |
| 91 | privacy default → invite-only |
| 94 | league-scoped audit log (new API route **and** new screen) |
| 93 | one-time notification to the three renamed members |

**94 is the asymmetry risk in this whole plan** — a new `GET /leagues/{slug}/audit-log`
plus a page that calls it. The page reaches production on close-out; the route
does not exist until `/ship-prod`. Put 94 last in the group and ship immediately
after, or the page 404s exactly the way Football Stats did after Batch 51.

93 depends on the notification path being correct, so it comes after Group A's
Batch 85.

### Group F — Season boundary · Batch 96 · **API + web** → `/ship-prod`

Alone, deliberately. It changes what every standings figure means, touches
`services/scoring.py` and the screens that draw it, and interacts with Batch 80's
`recent_form` window. One batch, one gate, one ship — nothing else moving
underneath it.

### Group G — The visual pass · Batches 98, 97, 92 · **mostly web** → ship only if 97 needs an API half

The "does this feel premium" work, and the only group whose output is judged by
eye rather than by a test.

| batch | why here |
| --- | --- |
| 98 | solid-fill avatars — clears the AA failure, changes how every list looks |
| 97 | home layout: content **and** scale |
| 92 | share a settled result |

98 before 97: the avatar treatment appears on home, standings and every roster,
so settling it first means 97's layout work is done against final components
rather than being redone.

**Why this group is late.** Groups E and F add new screens (audit log) and change
what standings show (season boundary). Styling before those land means restyling
after. If the visual result matters more to you than the rework — a fair call,
given it is the thing a stranger judges first — pull this group ahead of E and F
and accept a second pass.

**Check whether 97 needs new API data.** "The member's other leagues" and a
next-round countdown may be servable from the existing `PerLeagueSummary`
(Batch 81 already extended it) or may need a route. If it needs a route, this
group gets a `/ship-prod` and 97 must be last in it.

### Group H — Framework migration · Batch 102 · **web only** → no ship needed

react-router 6 → 7, alone, because it touches routing everywhere and its blast
radius is its own.

**One real sequencing choice.** Placed last, the migration has to carry every web
batch built before it. Placed right after Group B — as soon as Batch 88 closes
the guard gap — every subsequent web batch (90, 91, 92, 97, 98) is written
against the version you are keeping, and only three batches exist for the
migration to carry.

Later is the safer default and is what this document recommends. Earlier is the
better engineering if you are confident about the v7 migration, and it is worth
considering precisely because so much of the remaining work is frontend.

## Suggested order

```
A  82 83 84 85   API      → /ship-prod
B  86 88 87      web      → (no ship)          88 unblocks H
C  89 90         API+web  → /ship-prod         highest product value
D  99 100 101 95 API      → /ship-prod         95 blocked on FEAT-A09
E  91 94 93      API+web  → /ship-prod         94 last, ship immediately
F  96            API+web  → /ship-prod         alone
G  98 97 92      web      → ship if 97 needs a route
H  102           web      → (no ship)
```

Two independent things sit outside the batch flow entirely and can happen at any
point: closing launch gate **L5** retroactively via `/launch-closeout L5`, and
the **FEAT-A09 egress investigation**, which should precede Batch 95.

---

## Addendum, 2026-08-30 — batches added after this document was written

The groups above cover Batches 82-102, which is what the 2026-08-26 review produced. Two
later batches came out of doing the work rather than out of the review, so this addendum
places them as Groups I and J:

### Group I — The other privacy dropdown · Batch 103 · **web only** → no ship needed

Batch 91 was scoped to `CreateLeaguePage` and left `LeagueSettingsPage` carrying the same
unexplained control, over a league that already has members and a pending-request queue that
a save can silently auto-approve or discard. Web-only, so it reaches members on its own
close-out push and owes nothing.

**Run it near Group G.** It lifts Batch 91's options table into `lib/leagues.ts`, and Group
G's Batch 97 reworks home layout; doing them in the same stretch keeps the shared-copy
module settling once. It does not depend on Group G and can go earlier if the pending-request
surprise matters more than the visual pass.

### Group J — The Railway config migration · Batch 104 · **API + infra** → `/ship-prod`, alone

Railway is retiring `railway.toml` in favour of `.railway/railway.ts`, with existing files
working **until 2026-12-01**. Alone, and for the same reason Group F is alone: it changes
what production is built from, and three separate checks — the gate's `tomllib` assertions,
`nixpacks.toml`'s `DEPLOY_REPLICA_COUNT`, and `test_migration_guard.py` — all read the file
it replaces. Nothing else should be moving underneath it, and the ship follows immediately
so the deployed manifest can be verified against the new config.

**This one has an external deadline, which nothing else in this plan does.** Everything above
can slip by a week at the owner's discretion; this cannot slip past 2026-12-01 without the
deploy config becoming whatever Railway defaults to — including the `numReplicas = 1` that
Batch 100's migration guard exists to protect.

### 2026-08-30 order at the time

```
F  96            API+web  → /ship-prod         alone
G  98 97 92      web      → ship if 97 needs a route
I  103           web      → (no ship)          near G; shares lib/leagues.ts
J  104           API+infra→ /ship-prod         alone; hard deadline 2026-12-01
```

Groups A-E and H are complete. D is complete but for Batch 95, which remains soft-blocked on
the FEAT-A09 egress investigation.

---

## Addendum, 2026-09-03 — Coupon, home, notifications and Football Stats review

The owner reviewed the product as a software-engineering, football-analysis and
UI/UX exercise, then chose the larger Coupon consolidation, notification
completion only for the final-pick special case, concise fixes on both the
combined screen and copied text, and the full selected season for team results
and fixtures. Those decisions produce Batches 105-111.

The concern that the application feels a little bland does not become a generic
colour batch. Groups K and M first fix hierarchy and repetition, then introduce
restrained, meaning-bearing accents for action state, active dates,
competitions and outcomes without recolouring large surfaces.

### Group K — One weekly Coupon and a truthful home · Batches 105, 106 · **web only** → no ship needed

Batch 105 consolidates `Your pick` and `Combined coupon` into one state-aware
**Current round** surface, keeps **Season** as the historical destination, fixes
clipped/repetitive rows and copy, and preserves old deep links. Batch 106 then
applies the same temporal discipline to home: the primary card owns the current
or next action, while old picks and odds live only under `Last result`. It also
contains the hero corner glows.

Run 105 before 106 because home's Coupon destination and state language should
point at the settled navigation model. Both are web-only and use existing API
data, so each close-out push is complete in itself and no `/ship-prod` is owed.

### Group L — Pick progress and all-picks completion · Batches 107, 108 · **API then web**

```
107  API/data  → /ship-prod checkpoint → 108  web
```

Batch 107 makes pick pushes concise, adds `X/Y picked`, creates a durable,
concurrency-safe all-picked event, includes the final picker, deep-links the
completion event to the exact gameweek's copy section, and exposes completion
progress in the pick response. Batch 108 consumes that contract for the final
picker's in-app hand-off and makes opt-in and Settings copy describe the events
that actually exist. Batch 105 is a prerequisite because it establishes that
canonical copy-section destination.

The checkpoint is mandatory. Batch 108 must not reach Vercel while production
Railway still serves a pick response without the progress fields it consumes.
`/group-start L` therefore closes 107 and stops; after the owner runs
`/ship-prod`, rerun `/group-start L` to verify drift and continue with 108.

### Group M — Matchday navigation and complete team seasons · Batches 109, 110, 111 · **web, API, web**

```
109  web → 110  API/data → /ship-prod checkpoint → 111  web
```

Batch 109 is independent and turns Football Results into an addressable,
one-result-day-at-a-time carousel. Batch 110 expands provider-neutral ingestion
and the database read contract to retain and return every match in a team's
selected league season, including future and non-final statuses. Batch 111 then
makes table teams clickable and presents that full season.

The order keeps the small, existing-data interaction separate from the larger
data contract. The checkpoint after 110 is mandatory because 111's route cannot
work against the currently deployed API. `/group-start M` pauses there and
resumes only after an explicit `/ship-prod` leaves deployment drift in sync.

### Current order

```
I  103           web       → (no ship)
J  104           API+infra → /ship-prod         alone; hard deadline 2026-12-01
K  105 106       web       → (no ship)
L  107           API/data  → /ship-prod → 108 web
M  109 110       web+API   → /ship-prod → 111 web
```

Expanded batch order:

```
103 → 104 → /ship-prod → 105 → 106 → 107 → /ship-prod → 108
    → 109 → 110 → /ship-prod → 111
```

Batch 95 remains outside this wave in the unfinished tail of Group D. Its
FEAT-A09 egress and off-platform-storage decisions remain soft blockers; neither
`/group-start I-M` nor the newer UX work bypasses them.
