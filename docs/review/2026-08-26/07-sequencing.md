# 07 — Sequencing: how Batches 82-102 group

The twenty-one batches this review produced, arranged into eight groups that
each run as a unit. Written 2026-08-27, after the owner's decisions in
`README.md`.

## What a "group" is in this repo

`/batch-start N` takes **one** batch number and makes one `feat/batch-N-slug`
branch. `/phase-closeout N` takes **one** batch, merges it to `main`, and pushes.
Neither command batches. So a group is not a command — it is a run of individual
start → closeout cycles with **one `/ship-prod` at the end**.

That is already the established pattern: `docs: specify Batches 78-80 from the
owner's three points` grouped the *specification*, then Batches 79, 80 and 81
each got their own `docs: close out Batch N` commit, and a single
`docs: record the 2026-08-26 shipment of Batches 79-81` closed the group.

Per group, the loop is:

```
/batch-start N      → implement on feat/batch-N-slug, verify
/batch-verify N     → the real gate (scripts/ci-local.sh)
/phase-closeout N   → commit, ff-merge main, strike, push
   ... repeat for each batch in the group ...
/ship-prod          → once, at the group boundary, if the group has an API half
```

**The group boundary matters because of the deploy asymmetry.** Every
`/phase-closeout` pushes `main`, and Vercel releases the web app from `main`
immediately. Railway does not move until `/ship-prod`. So a group whose web half
calls an API route the deployed image does not serve is broken in production for
the length of the group — that is the 2026-08-06 incident, and Batch 51 repeated
it. Groups below are cut so that never spans a boundary.

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
