# 05 — Feature gaps

Two questions, grounded in the routers and components: what the spec and launch plan
promise that is not built or not reachable (Part A, `FEAT-A`), and what a paying member of
a weekly friends' game would expect that is missing (Part B, `FEAT-B`). Every claim that
something is missing was looked for; the route inventory is in the notes.

## Method

- **Route inventory.** Every FastAPI route (84) matched against every `/api/v1/` literal in
  `apps/web/src` outside tests, in both directions
  (`notes/05-features/route_inventory.py` → `route_inventory.txt`; reverse check in
  `drive-addendum.txt`). Eight routes have no web caller (two are health checks); no web call
  lacks a route.
- **Scratch stack, HTTP and in process.** `notes/harness/stack.py` on port 8150 with
  `PUBLIC_SIGNUP_ENABLED=false`, FakeBetfair odds, scheduler off. `drive.py` →
  `drive-output.txt` played two leagues with different rules — league A (`selection` scope,
  both markets, four members) and league B (`fixture` scope, Match Odds only, created over
  HTTP by an ordinary member) — through pick → lock → settle, by **both** settle paths: the
  real `run_settle_gameweeks` sweep and the admin's hand-entered results. Sends were counted
  by replacing `send_notification` with a recorder; routes that needed the recorder ran
  through an in-process ASGI client on the same database.
- **Real Chromium.** The production bundle (built with `VITE_API_URL` at the stack) served
  from the API's own origin by Playwright route fulfilment, so no second port was bound
  (`browser.mjs` → `browser-output.txt`, `browser-output-2.txt`). The stylesheet did not
  apply under that harness, so the six captures are functional evidence only and are named
  `*-unstyled-*` in `screenshots/INDEX.md`.
- **Production:** not touched by this pass. Deployment state is the lead's (every finding
  on `main` is live).

## Prior findings

| id | batch | state | evidence |
| --- | --- | --- | --- |
| FEAT-A10 no way to correct a pick | 134 | **partial** | The API holds: site admin corrected Bob lost → won 38; the repeat returned `changed: false`; a member got 403 (`drive-output.txt`, and 02's CORR table). But it cannot be used from the app and it corrects one pick, not the result — **FEAT-A13** |
| FEAT-B07 no deletion or export | 136 | **held** | Chromium: Carol found Settings → Your data, downloaded `the-coupon-my-data-2026-09-29.json` (7 sections, her one pick, her own name only), entered her PIN and deleted her account → landed on `/login` with "Your account has been deleted." (`browser-output.txt`). Over HTTP: wrong PIN 403, sole admin of a league others play in 409, site admin 409, each with a plain reason. The anonymised-points sum is 01/02's check, not re-driven here |
| FEAT-A11 rename notice can never arrive | 148 | **held** | A profile seeded with the third renamed id (`39faae39…`): `GET /me/rename-notice` returned the notice, Chromium showed the dialog on sign-in, "Got it" posted `seen` (204), and a reload did not show it again; a non-renamed member gets `null`. Member B's production state not checked, per the brief |
| FEAT-B08 settlement is silent | 135 | **held** | Sweep: league A settled, 3 sends — Alice "won 19 points", Dave "won 24", Bob "lost" — and **none to Carol, who had muted league A**; a second sweep sent 0. Hand entry: league B settled, 3 sends including Dave's "You had no pick this round." Residuals are 02's CORR-22 (a correction is silent) and CORR-23 (a round nobody picked never settles) |
| FEAT-A12 register ignores the kill switch | carried | **not fixed, and sharper** | Chromium with sign-ups closed: the full form, no notice; refused only after a name and a PIN twice (`browser-output-2.txt`). See below |
| FEAT-B09 results have no season filter | carried | **not fixed** | With a settled May 2026 round added: `/results` lists 1 Aug 2026 **and** 2 May 2026 and ignores `?season=`; `/seasons` lists 2026/27 and 2025/26; `/standings` splits correctly (38 vs 20 for Bob). The page is titled "Season" (`ResultsPage.tsx:75`); the route takes no season (`routers/coupon.py:64`). First visible at next season's first settled round |
| FEAT-A01 launch gate L5 | — | **not fixed** | `docs/LAUNCH_PLAN.md:30` unticked; `launch-log.md` has L0-L4 only. The gate's substance (a first live gameweek settled correctly) has been met for weeks; the owner's 2026-08-27 "close it retroactively" is still not actioned |
| FEAT-A02 / OPS-13 no backup | 95 | **not fixed — built, switched off** | From `STATUS.md` (2026-09-26); production could not be read, and `/health` says nothing about backups. **Open since production launched on 4 Aug: 56 days on 29 Sep**; members' picks have had no second copy since the first live Saturday on 22 Aug (38 days); first raised as FEAT-A02 on 26 Aug (34 days). The fix has been live and off since 26 Sep |
| FEAT-A09 egress consumer | owner | **not done** | `STATUS.md` and `docs/runbooks/backup-restore.md` step 5 both say it was never identified. Recorded facts point away from this project: the avatars bucket holds nothing, Supabase meters egress per organisation, and the organisation has four other projects |

**What the owner must do to have a backup** (all in `docs/runbooks/backup-restore.md`,
"Switching it on"): create an EU-jurisdiction R2 bucket; add a 30-day bucket lock and a
90-day expiry on `production/`; create a key scoped to that bucket; check Supabase egress
headroom (each run moves about 17 MB); set the four `BACKUP_S3_*` variables and then
`BACKUP_STORAGE=s3` on the Railway production API service; confirm the boot log is clean;
run it once by hand over `railway ssh`:

```
/opt/venv/bin/python -m src.run_scheduled offsite-backup
```

Tally: **3 held, 1 partial, 5 not fixed** (A12, B09, A01, A02/OPS-13, A09 — the last three
are owner actions, not code).

## Register

| id | sev | deploy | status | finding |
| --- | --- | --- | --- | --- |
| FEAT-A13 | MED | live | verified | Pick correction needs a production database read to use, and fixes one pick while every other pick on the same match keeps the wrong result |
| FEAT-B10 | MED | live | verified (absence) / plausible (reach) | Notifications leave no record in the app, so the members without push — about half — get none of them |
| FEAT-A12 | LOW | live | verified | *(carried, sharper)* With sign-ups closed there is no way in at all, and the screen says to ask for an invite that cannot work |
| FEAT-A14 | LOW | live | verified | A league cannot see that its results were corrected or hand-settled |
| FEAT-B11 | LOW | live | plausible | Notifications can be muted per league or not at all — not per kind |
| FEAT-B12 | LOW | live | verified | Only league admins can invite, though every member already holds the join code |
| FEAT-A15 | LOW | live | verified | Four routes have no screen, and the register screen promises a PIN reset no league admin can perform |
| FEAT-B09 | LOW | live | verified | *(carried)* The Season list runs across seasons |

## FEAT-A13 · MED · live · verified — the correction tool cannot be used as a tool

Batch 134 built `POST /admin/picks/{pick_id}/correct` (`routers/admin.py:1348`) and it
scores correctly. Three things stop the owner using it on a Saturday night:

1. **No screen.** The route has no web caller (`route_inventory.txt`); the session log
   records "API only, as the row specified". It needs a site-admin bearer token in curl.
2. **Nothing returns the pick id.** A member's pick id is served only to that member
   (`routers/picks.py:188`). Seventeen reads available to a site admin who is also the
   league's admin — league detail, round, coupon, standings, results, profiles, members,
   audit log, every admin console read, the cross-league summary, their own export — were
   searched for Bob's pick id: **0 of 17** contain it (`drive-output.txt`). The member's
   own data export does not carry it either (`drive-addendum.txt`). The only source is a
   production database read.
3. **It corrects a pick, not a result.** Correcting Bob's Draw to the "true" 1-1 made him
   won 38 — while Alice's Arsenal-win pick on the **same fixture** still read won 19. One
   match now has two contradictory winners on the table, and the same fixture sits in
   every league's round. Nothing lists the other picks on a fixture.

*Considered for HIGH and rejected:* the wrong result is the provider's, not the tool's;
correcting every affected pick by id restores consistency, so a workaround exists; and the
trigger — a mis-settled fixture — has happened once since launch.

**Member impact:** when a result is wrong, members wait for an engineer with database
access, and a partial fix leaves the table contradicting itself.

**Fix:** a site-admin action on the admin Results screen — pick a settled fixture, enter the
true score or void and a reason — that re-scores **every** settled pick on that fixture in
every league through `resolve_pick`, writes one audit row per league (with `league_slug`,
as 01 recommends), and sends 02's CORR-22 per-member line. API + web, no migration.

## FEAT-B10 · MED · live — notifications leave no record

There are now five member-facing push types (picks open, reminder, pick made or moved, all
picked, round settled) plus the admin alerts. Every one is fire-and-forget: the
notification models are `PushSubscription`, `NotificationPreferences` and `AuditLog`
(`models/notification.py`) — no message table, no inbox route, no screen. `STATUS.md`
(2026-09-24) records **7 active push subscriptions for 13 active accounts**, and on iPhone
push needs the installed PWA. So roughly half the league never learns that picks opened,
that the deadline is near, or what their pick scored — Batch 135's payoff reaches seven.
Batch 148 built a one-off in-app channel for exactly this problem, for one notice.

**Member impact:** a member without push has to open the app and go looking for every
event the product announces.

**Fix:** record each league notification per member when it is sent (a small table, 30
days) and show it behind a bell on home, marking read on view. Migration + API + web.

## FEAT-A12 · LOW · live · verified — closed sign-ups are a dead end *(carried)*

Still true that the register screen has no knowledge of the switch. Two new facts:

- **The advice is impossible.** The refusal says "Ask a league admin for an invite", but
  claiming an invite requires an account (`league_memberships.py:63`, verified 401 without
  one) and no route creates one. With the switch off, nobody new can join by any path.
- **The state is already public.** Registration checks the switch before it validates
  the name (`routers/auth.py:426`): a one-character name still gets the 403 (verified). So
  the reason `GET /config` is authenticated — "nothing unauthenticated needs it", and it
  describes the deployment — does not apply to this one bit.

**Fix:** a separate unauthenticated `GET /api/v1/auth/signup-status` → `{open}` (leaves the
`/config` decision alone), a closed notice in place of the form, and copy that tells the
visitor what actually works. API + web.

## FEAT-A14 · LOW · live · verified — corrections and hand settlements are invisible to the league

After the correction, league A's audit log held **0** entries; league B's admin saw his
three membership rows but not the site admin's hand settlement of his round. Both audit
rows exist (the site-admin dashboard lists them by id, without reason or league), but
`_league_audit_scope` (`leagues.py:1358`) matches only `target_id = league` or
`changes.league_slug`, and both writers record neither (`admin.py:1286`, `:1432`). The pick
itself carries no "corrected" field. 01 recorded the correction half as INFO; the hand
settlement is the same gap. **Fix:** in FEAT-A13's batch, add `league_slug` to both rows and
a `corrected` flag with the reason on the member's pick.

## FEAT-B11 · LOW · live — mute is all or nothing per league

Preferences are a global mute, quiet hours and a per-league mute (`notifications.py:115`).
A pick in a twelve-member league pushes to the other eleven; a member who wants the
reminder and the result but not that chatter must mute the league and lose both. The
owner chose per-pick sends over a digest (`notification_triggers.py`, `notify_pick_made`);
choosing *which kinds* is a different question. **Fix:** per-kind toggles (picks and moves;
reminders; results) — best done with FEAT-B10's migration.

## FEAT-B12 · LOW · live · verified — only admins can invite

Every member receives the league's join code (`leagues.py:1151`; verified for an ordinary
member), but the only screen that shows or shares it is the admin invites page
(`App.tsx:264`, `lib/invite.ts:73`). Since Batch 124 a code respects approval-gated leagues,
so letting members share it opens nothing. **Fix:** an "Invite a friend" share action for
members on the league screen, reusing `shareInvite`. Web-only.

## FEAT-A15 · LOW · live · verified — built but unreachable

| route | since | note |
| --- | --- | --- |
| `PUT /leagues/{slug}/members/me/display-name` (`league_memberships.py:394`) | never had a screen | SEC-20 and SEC-29 are both findings on this curl-only surface |
| `POST /leagues/{slug}/members/{id}/reset-pin` (`:577`) | never had a screen | yet the register screen says "Forget it and a league admin has to set you a new one" (`RegisterPage.tsx:139`), and a forgot-PIN request pages site admins only (`routers/auth.py:734`) |
| `GET /me/profile` (`me.py:64`) | — | superseded by `/auth/me` |
| `GET /push/vapid-public-key` | — | the web reads `VITE_VAPID_PUBLIC_KEY` at build |

`DELETE /auth/players/{id}/avatar` is also unused, but avatars are off by decision.
**Fix:** remove the last two; decide the first two (owner decision 4).

## FEAT-B09 · LOW · live · verified — the Season list runs across seasons *(carried)*

As in the table. **Fix:** the leaderboard's season selector on the Season list, filtering
by `starts_on` against the July rollover (`football_provider.py:50`). Web-only.

## Checked and found nothing material

- **Who hasn't picked** — the round lists members yet to pick (`PickRow.tsx:128`).
- **Changing a pick before lock** — a re-submit moves it and frees the old selection
  (`pick_changed`). There is no withdraw, and none is needed: no pick scores nothing.
- **Pick reminder** — one push three hours before lock (`services/gameweek.py:1416`);
  02 verified it across both DST changes. Not member-configurable; not worth a batch.
- **Invites by share sheet** — present for admins (`lib/invite.ts:73`); see FEAT-B12.
- **Season end** — tables roll over on 1 July and the leaderboard's selector keeps the
  archive. There is no end-of-season moment (champion, final push); the first season ends
  in May 2027, so this is noted, not batched.
- **Why a pick was voided** — the settle push says "was void — no points" and the coupon
  marks void legs; the provider gives no reason to show. Corrections are FEAT-A13/A14.
- **Every web call reaches a route** — the reverse inventory's only misses are template
  suffixes and the service worker's path prefixes.

## Proposed batches

1. **A wrong result can be put right from the admin console, for every pick on the match,
   and the league can see it** (FEAT-A13, FEAT-A14, with 02's CORR-22 and 01's
   `league_slug`) — API + web, no migration.
2. **Members without push miss everything the app announces** (FEAT-B10, with FEAT-B11's
   per-kind choice) — migration + API + web.
3. **The register screen knows sign-ups are closed** (FEAT-A12) — API-carrying + web.
4. **Members can invite a friend** (FEAT-B12) — web-only.
5. **The Season list filters by season** (FEAT-B09) — web-only.
6. **Unreachable routes are built or removed, and the register copy tells the truth about
   PIN resets** (FEAT-A15) — API-carrying + web; after owner decision 4.

## Owner decisions

1. **Correction scope** — per fixture across leagues, or a screen over today's per-pick
   route? *Recommend per fixture:* a wrong result is a fact about a match, and it removes
   the need to find pick ids.
2. **Notification history** — build it, or accept push-only? *Recommend build:* about half
   the members have no push, and Batch 148 already paid for this gap once.
3. **Signup status** — a new unauthenticated `signup-status` route, or make `/config`
   public? *Recommend the new route:* it discloses nothing `POST /register` does not already
   reveal, and leaves the `/config` decision standing.
4. **Per-league names and league-admin PIN resets** — build screens or delete the routes?
   *Recommend* deleting the per-league name route (two security findings, no member asked
   for it) and settling the league-admin reset together with 01's SEC-15/SEC-27 decision;
   either way the register copy changes.
5. **Carried owner actions, not decisions:** switch on the backup (steps above), attribute
   the egress (FEAT-A09), and run `/launch-closeout L5` or delete the gate (FEAT-A01).

## Doc corrections

| file | from | to |
| --- | --- | --- |
| `docs/LAUNCH_PLAN.md:425-428` | "Backup completion is out of scope under the 2026-07-30 deferral. No backup is scheduled at all: Batch 75 removed the nightly dump, which wrote to an ephemeral path and produced no recovery artifact, and restoring one is Batch 95." | "No backup runs yet: Batch 75 removed the nightly `/tmp` dump, and Batch 95's weekly off-site backup (built 2026-09-25) is switched off until the owner follows `docs/runbooks/backup-restore.md`." |
| `docs/LAUNCH_PLAN.md:192` | "Revisit post-launch." | "Revisited: Batch 95 built weekly logical backups to R2 (2026-09-25), switched off pending the owner." |

## What this pass did not do

- **No production reads.** Backup and egress states are taken from `STATUS.md`; Member B
  was not checked.
- **No real push delivery.** The stack has no VAPID keys; the recorder counts who was
  targeted, which is what the triggers decide. Delivery and quiet hours were not exercised.
- **The captures are unstyled** (see Method) and are not design evidence.
- **Not tested on iPhone.** The export download is a blob link; whether it saves from an
  installed PWA on iOS is unverified, because WebKit will not install here.
- The anonymised-points sum after deletion was left to 01 and 02, which both drove it.
