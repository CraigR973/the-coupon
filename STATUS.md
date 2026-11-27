# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-10-10 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `d6826d9` (Batch 255: Fantasy's four European top flights) at migration `032` (27 Nov) |
| API deployment | Railway `07c6ee55-743c-488d-9a58-bc369dca614b` succeeded 00:32 UTC, one replica, `europe-west4` (27 Nov); rollback `c5feaaa2` (`a4728c3`) |
| Payments | `payments-production-0aa1.up.railway.app` serves `d6826d9` at `032`, Railway `4c8e213a-05b2-4d1a-aebb-04421620f78c` (27 Nov; rollback `56365aee`), one replica, `europe-west4`, no access log; **Monzo connected** at 21:32 UTC (owner's account, confidential client, webhook registered); payments count from 21:29 UTC (16 Oct); **2-1 Hibs moved to a new payment link and pot on 25 Nov**: link id `unipaylink_0000BCfe…` and the new Pay URL set at 09:55 UTC by a guarded database write at the owner's request (audited as `league_updated`); its first payment (09:50 UTC) was matched automatically by the 09:59 read, which also learned the new pot; payments through the old link no longer count, and the owner is closing it (25 Nov); before that, all 20 link payments from members were read and matched through the five-minute read in the 24 Oct observation; retained logs also prove a webhook-matched payment, and a 9 Nov probe confirms selective `400 bad_request.app_version_outdated` refusals; the owner's own top-ups into the pot are matched since Batch 216 (the pot's `pot_…` name learned from Monzo's filings), and the first one waits in the queue once; Monzo's approval lapses about 14 Jan 2027 (25 Oct) |
| Web | `the-coupon-production.vercel.app` builds every push to `main`; since 11:51 UTC on 26 Nov it serves `5647cff` (Batch 251) as bundle `index-Cv5lh-FH.js` (deployment `the-coupon-production-p6f7aptir`): a moved Fantasy price is confirmed on the row that was tapped ("Price moved: Home is now 3.25", Pick or Cancel). Earlier the same day: the moved price at 2 dp (Batch 250, 10:59 UTC) and, from Batch 249 (09:49 UTC), plain words on both game screens ("2 of 4 picked", "Waiting on …", "Your pick", "Copy for chat", "Waiting for results") and each Fantasy pick's price at 2 dp. On 25 Nov: Fantasy's picks as one card of six tiles with a slim bar, and Group's status card leading with the member's pick before one coupon card (Batch 246, 23:46 UTC); both games' fixtures as compact rows under open competitions with jump chips (Batch 245, 22:12 UTC), the game screens' week bar above the Group | Fantasy switch (Batch 244, 20:05 UTC), Home showing one football week per league, with a countdown, both games as rows, the week's £1 once and one button (Batch 243, 18:34 UTC), labels in the app font, colours that render on won and lost results and the bell in the top bar (Batch 242, 15:25 UTC), a paid week's payment strip on one line (Batch 247, 14:33 UTC) and badges that no longer fade (Batch 248, 14:06 UTC). Both games' fixtures show club form, position and competition names (Batch 235). The API has served the two-game screens to 2-1 Hibs since its activation at 17:08 UTC on 23 Nov. |
| Database | Supabase `pugujiiojitstkilphrz`, London, owned by `postgres`; RLS forced on 42 of 42 tables, no public-role table or schema grants; the two-game tables hold 2-1 Hibs' rollout, its four games and 12 dues since 17:08 UTC (23 Nov) |
| League data | 1 live league, 13 active accounts, 7 active push subscriptions (2026-09-24) |
| Odds | `odds-api.io` priced by **Betfair Sportsbook** since 10:36 UTC on 31 Oct (ADR 0002's 31 Oct amendment). Bet365 has been paid-only since 26 Oct, 19:00 UTC, and a free key gets a 403. Free key: 100 requests/hour and 500/day for the whole deployment. On the 31 Oct card it priced 78 of 85 fixtures, none in the Highland League (31 Oct). The owner chose to keep it rather than pay £49/mo for Bet365 (31 Oct). The 07:05 warm pass asks the provider nothing: the 50-request pick reserve withholds it because 06:05 discovery's requests are still inside the rolling hour, so it only reports prices left in memory (22 and 23 Nov) |
| Football data | FotMob, no key |
| Scheduler | on (`SCHEDULER_ENABLED=true`) |
| Avatars | built and off (`AVATAR_STORAGE=none`) |
| Backups | weekly off-site `pg_dump` to Backblaze B2 (EU), Mondays 04:00 London (Batch 95, switched on 21 Nov); first weekly run 23 Nov 04:00 UTC, 912,932 bytes; by hand before the flag 23 Nov 13:51 UTC, `production/the-coupon-20261123T135112Z.dump`, 912,317 bytes, 17,964 rows, restore-checked at 17:07 UTC from the owner's download: 42 of 42 tables and every row count identical, the `2115540` API ready on the copy (23 Nov). Runbook: `docs/runbooks/backup-restore.md` |
| Two-game format | `TWO_GAMES_ENABLED=true` on both services since 14:04 (API) and 14:07 (payments) UTC on 23 Nov. **2-1 Hibs is activated** from Sat 28 Nov (17:08:50 UTC, 23 Nov; rounds 17 and 18 retired untouched): its 28 Nov fantasy card (125 fixtures) is open and locks Sat 12:00, its group card (95 fixtures) opens Sat 03:00 and locks 14:30, and 12 members owe £1 for 28 Nov. At 00:31 UTC on 24 Nov the fantasy card showed a price on 44 of 125 fixtures: Premier League 7 of 9, Championship 9 of 11, League One 10 of 11, League Two 12 of 12, Scottish Premiership 6 of 6. None of the Scottish Cup (19), National League tiers (35), Lowland (9), Welsh (10) or Highland (3) fixtures shows one; of the 81 unpriced, Betfair Sportsbook returned 72 as unavailable and 9 were still to be asked. The 5 Dec cards are complete (group 93, fantasy 130, 16 priced). No picks or payments yet. Yer Leagues A Joke stays legacy; its round 3 settled under the flag at 21:00:35 UTC on 23 Nov, with no picks (24 Nov) |

`scripts/check-deploy-drift.sh` is the authority on what the API is running, never
`git log`: shipments have gone unrecorded before.

## Shipment state

- **Batch 255 is live** (27 Nov, `6cd8996`, API-only; API and payments released 00:31–00:35
  UTC at `d6826d9`, as the owner scheduled): Fantasy also plays LaLiga, Serie A, the Bundesliga
  and Ligue 1, for every two-game league, with no switch (owner, 26 Nov: "one rule and not have
  the switch … implement and enable this overnight"); Group and legacy rounds stay British.
  The weekend census keeps the four at no extra request. Live pre-flight on 26 Nov: 31 of their
  games in the 28 Nov Fantasy window, Betfair Sportsbook priced 10 of 10 sampled. Batch 256
  (their place in the card order) follows the shipment.
- **Batch 252 is live** (26 Nov, `a4728c3`, tests only; API and payments released
  17:37–17:42 UTC): a backend test pins that nobody sees another member's Fantasy picks
  before lock, and only totals and counts after it. Released straight after the push, as
  the owner chose, because the drift check counts any commit under `apps/api`; drift is in
  sync.
- **Batch 251 is live on the web** (26 Nov, `5647cff`, web-only, pushed 11:50 UTC): when a
  Fantasy save is refused because its price moved, the tapped row offers the new price ("Price
  moved: Home is now 3.25", Pick at 3.25, Cancel) in view, instead of only in the picks card
  (on a phone, the Review sheet or the foot of the page); until it is saved the row shows no
  tick or "Your pick". Found by the owner's first real picks; the owner chose it. No API
  change; drift in sync before the push.
- **Batch 250 is live on the web** (26 Nov, `8971554`, web-only, pushed 10:58 UTC): when a
  price moves during a Fantasy save, the slot says "The price changed to 3.25" and offers
  "Confirm odds 3.25 for slot 1", in the member's odds format, instead of 4 dp; the
  confirmation still sends the API's own price. The owner approved the five changed test
  lines (26 Nov). No API change; drift in sync before the push.
- **Batch 249 is live on the web** (26 Nov, `3e73a89`, web-only, pushed 09:49 UTC): plain
  words on both game screens. Group's status card says "N of M picked", "Waiting on …" and
  "Your pick: X", and the coupon's button "Copy for chat"; Fantasy's tiles show the price at
  2 dp in the member's odds format, without "Frozen odds", and "Waiting for results" with no
  points for a pick still to play; both games say "Waiting for results" for pending. The
  owner approved the 17 changed test lines (26 Nov). The badges and the price buttons'
  screen-reader names keep their words; the moved-price confirmation followed as Batch 250.
  No API change; drift in sync before the push.
- **Two-game mode passed an overnight test pass** (26 Nov, on `ce5deae`): all 30 two-game
  browser stories 4 runs in a row with no failures; a realistic league walked through a whole
  week (Wed, Sat morning and afternoon, results final, Monday) with no console or page errors
  and no 320px overflow; backend 2,106 and web 1,629 tests pass with the clock at Sat 28 Nov
  and Mon 30 Nov; production healthy (no server errors in 24 hours of API traffic). Report:
  `.local/overnight-2026-11-26/two-game-test-report.md`.
- **Batch 246 is live on the web** (25 Nov, `b243ac0`, web-only, pushed 23:45 UTC), the last
  batch of the redesign: Fantasy's picks are one "Your picks" card of six tiles (tap a held
  one to remove it, "+ Pick" goes to the fixtures) with a slim bar; Group's status card leads
  with the member's pick and Change, then a dot per member, and the coupon is one card with
  each leg's initials and the copy in its header. Plain words and 2 dp prices followed as
  Batch 249 (26 Nov). No API change; drift in sync before the push.
- **Batch 245 is live on the web** (25 Nov, `2f47e82`, web-only, pushed 22:12 UTC): each
  fixture on both games is a compact row (clubs with position and form, the kick-off between,
  Home, Draw and Away as three buttons), about 110px instead of about 400px; Group rows take
  the same shape, with both teams to score in a sheet (owner's choice). Competitions start
  open under sticky headers with jump chips; unpriced Fantasy fixtures fold into one row.
  The owner checked it on a phone (25 Nov). No API change; drift in sync before the push.
- **Batch 244 is live on the web** (25 Nov, `8454296`, web-only, pushed 20:04 UTC): both game
  screens open with a week bar, Home, ‹ week › and the archive, whose arrows step through the
  live weeks and the last five finished ones (a dot when next week's Fantasy is open), above
  the Group | Fantasy switch for that week; one status line, and the rules as one line with a
  "How it works" sheet. The Games tab opens this week until its results are final. The
  archive has no underlined links. The owner checked it on a phone (25 Nov). No API
  change; drift in sync before the push.
- **Batch 243 is live on the web** (25 Nov, `7ea6bfc`, web-only, pushed 18:33 UTC), the Home
  rebuild: each two-game league's card shows one football week, the earliest whose results
  are not final, with the soonest deadline as a countdown, Fantasy and Saturday Group as two
  rows, the week's £1 once as a chip and one button; next week's open Fantasy is one line until
  this week is final. The hero opens with the date and keeps the cross-league totals as one
  slim row; combined prices carry thousands separators. The owner checked it
  on a phone (25 Nov). No API change; drift in sync before the push.
- **Batch 242 is live on the web** (25 Nov, `3a78a50`, web-only, pushed 15:24 UTC), the first
  batch of the Home and Games redesign: one label style in the app font instead of spaced-out
  monospace capitals (60 labels), 21 dead `text-*-ink` colour names fixed (won and lost labels
  were uncoloured), the bell beside the avatar on every screen, the light/dark switch only in
  Settings, and price tiles that neither cut off their points line nor fade. No API change;
  drift in sync before the push.
- **Batch 247 is live on the web** (25 Nov, `b348150`, web-only, pushed 14:32 UTC): a paid
  week's payment strip is one line (a tick, "Paid through this week", and the status check
  and Details as icon buttons); owed, its text stacks above the buttons on a phone. Every paid
  member had seen it squeezed to a word a line at the top of both game screens since Batch 238.
  No API change; drift in sync before the push.
- **Batch 248 is live on the web** (25 Nov, `f59fd41`, web-only, pushed 14:05 UTC): the `Badge`
  base class no longer transitions colour. Muted competition chips (on every group fixture card
  since Batch 235) faded text and background together and crossed mid-fade, so the group
  story's light-theme axe scan failed 1 run in 5 on `main`; it then passed 10 repeats in a row.
  No API change; drift in sync before the push.
- **Batch 240 is shipped and verified** (24 Nov, `7205e84`, no migration; API `07b1640b`
  23:36 UTC, payments `733c3ae4` 23:38 UTC). Each minute's dues pass reads one snapshot without
  the league lock and takes the lock only when a member needs a membership interval or a due; the
  money rules are unchanged. The first passes took 0.23–0.34 s (were 3.9 s, up to 4.9 s), with no
  error. Still to observe: Monday 30 Nov's catch-up writing the 5 Dec dues.
- **Batch 239 is live on the web** (24 Nov, `6bac303`, web-only, pushed 21:41 UTC): the old home
  page is back for every member. The hero shows the season's points, picks won and win rate from
  the season table and the next thing that needs them, two-game entries included; each league
  has its old card again, and a two-game league's card holds that week's entries, its last
  result and run, and the Standings line. No API change; drift in sync before the push.
- **Batch 235 is live on the web** (24 Nov, `38d3f7f`, web-only, pushed 21:10 UTC): both games'
  fixture cards show club form, table position and the competition's own name (the group still
  unpriced); tapping your own pick again removes it through Batch 234's `DELETE`s; the Fill and
  Replace slot buttons are gone (a tap fills the fixture's slot or the first free one, each slot
  offers Remove, a full slip keeps Swap a pick); the group status card names who is still to
  pick. No API change; drift in sync before the push.
- **Batch 234 is shipped and verified** (24 Nov, `85fa1ae`, no migration; API `45ae5d94`
  17:13 UTC, payments `b994b98f` 17:15 UTC): competition names and club position and form on
  both games' fixtures, removing a fantasy slot or a group pick (`DELETE`, replayable, refused
  after the lock, while suspended and for others), and the group view naming who is still to
  pick. 17:13–19:22 UTC: settlement 1.2 s, dues 3.9 s, discovery 12 s a pass, no QueuePool error.
- **Batch 238 is live on the web** (24 Nov, `b1c089b`, web-only): a payment strip heads both
  game screens (Pay £1, one fee for both games, details folded), every competition starts
  folded unless the week has one, the group's status card and coupon come first on phones, the
  fantasy screen drops its recent weeks and refresh button, and the season table's money card
  folds. No API change; drift in sync before the push.
- **Batch 237 is shipped and verified** (24 Nov, `65cc0c9` with the IaC fix, no migration;
  API `77d0cf36` 15:09 UTC, payments `a07f7352` 15:11 UTC). Game reads take no league lock;
  discovery's setup holds none; the first passes took discovery 2.2–2.7 s, settlement 1.2–1.6 s
  and weekly dues 3.8–4.3 s (were 80–89 s, 80–89 s and the 10 s pool timeout), with no QueuePool
  error. The first preflight stopped on an IaC plan that would have deleted `TWO_GAMES_ENABLED`;
  `65cc0c9` preserves it. Still to observe: read times under member traffic and the first real
  fantasy PUT.
- **Batch 236 is live on the web** (23 Nov, `61a9700`, web-only, pushed 23:32 UTC): a group refresh
  that fails on the connection keeps the last view with a notice instead of "Group game
  unavailable"; a failed first load or a server refusal still shows that screen. No API change;
  drift in sync before the push.
- **Batch 233 is live on the web** (23 Nov, `5198ab5`, web-only, pushed 22:22 UTC): the Saturday
  group on the old coupon layout — status card, folded competitions, a game another member holds
  greyed as "Picked by <name>", the member's own as "Your game", and the coupon's legs, fold and
  Copy text. Same-time fixtures on both screens now run by home club. No API change; drift in
  sync before the push; revert is one push of `main`.
- **Batch 232 is live on the web** (23 Nov, `05cf820`, web-only, pushed 19:14 UTC): the fantasy
  week on the old coupon layout, each tapped price saved straight into the slip (the held
  fixture's slot, else the first free one; a seventh price asks which pick to swap), a Group |
  Fantasy switch on both game screens, and the Games tab opening the game that needs the
  member. No API change; drift in sync before the push. 2-1 Hibs' 28 Nov fantasy is open, so
  members meet it this week; revert is one push of `main`.
- **2-1 Hibs is on two games a week from Sat 28 Nov** (23 Nov, 17:08:50 UTC, owner's go 2:
  "Yes, after restore"). The 13:51 backup was restore-checked first (17:07, every table
  identical). A fresh preview matched the approved one; the apply retired rounds 17 and 18
  (untouched) and restarted nothing. Within a minute: four games, calendar `ready`, 12 dues of
  £1, the fantasy game open with the app's 12 notices; both 28 Nov cards complete at 17:17.
  The discovery-silence alarm fired once (admin push 17:09:45) until the first card filled.
  Recovery is forward-only or the 13:51 backup; the emergency stop is `suspend`, never the
  flag (`docs/runbooks/two-game-activation.md`).
- **`TWO_GAMES_ENABLED` is on for both services with no rollout row** (23 Nov, owner's go 1,
  moved to 14:03 UTC by the owner). A fresh backup came first (13:51 UTC, 912,317 bytes,
  counts identical before and after). API redeploy `fd64e4a4` succeeded 14:04:40, payments
  `d2faa3eb` 14:07:48, both `2115540` / `032`; drift in sync; the read-only audit matches 13:30
  exactly. The lossless 032 undo ends with the first row in a two-game table (the next
  odds-api.io request or membership change); recovery after that is a forward fix or the
  13:51 backup. Not an emergency stop: see `docs/runbooks/two-game-activation.md`.
- **The erasure-test fix is shipped and verified** (23 Nov, `2115540`, no migration,
  behaviour-neutral). It pins one weekly-fees test's clock, which had turned `main` red from
  00:47 to 12:40 UTC when the real date crossed Monday's fee week. The IaC apply and both
  uploads ran 13:19–13:26 UTC: API `add870dc`, payments `92a2821c`, both `2115540` / `032`;
  drift is in sync and the audit (run through the pooler, `railway ssh` refused) matches.
  Image rollback: API `95dad76c`, payments `07fdefcc` (both `eaf8ca7`). The lossless 032 undo
  still holds until `TWO_GAMES_ENABLED` goes on.
- **Batch 231 is shipped and verified with the format off** (23 Nov, `eaf8ca7`, no
  migration). The owner moved it from Tue 24 Nov to the night of 22–23 Nov. The IaC apply
  (the four reporting-only changes) and both uploads ran 00:20–00:27 UTC: API `bcf945c9`,
  payments `3d3fcc6e`, both `eaf8ca7` / `032`; drift is in sync and the read-only audit
  matches 22 Nov (RLS 42 of 42, no public-role grants, 37 rounds all `legacy`, the 15 new
  tables empty). Image rollback: API `fe1a286e`, payments `6b56c9ee` (both `874d89c`). The
  lossless 032 undo still holds until `TWO_GAMES_ENABLED` goes on.
- **Batches 219–228 are shipped and verified with the format off** (22 Nov, `874d89c`,
  migration `032`). API and payments went first (10:17 and 10:19 UTC), the web at 11:04 UTC;
  both services report `874d89c` / `032`, drift is in sync, and the read-only audit found RLS
  forced on 42 of 42 tables with no public-role grants, every round `legacy` and the 15 new
  tables empty. Until a league is activated, `docs/runbooks/migration-032-undo.sql` returns
  the database to `031` without losing legacy writes; afterwards recovery is forward-only
  (`docs/runbooks/migration-032-recovery.md`). Recovery point: the 22 Nov 10:03 UTC backup.
- **Batch 215 is shipped and verified** (9 Nov, `c18e81e`, no migration). Both services
  report `c18e81e` / `031`, readiness is `db: ok`, drift is in sync, and the catalogue audit
  found RLS forced on all 27 tables with no public-role table or schema grants. The exact
  listed transaction is recovered after `400 bad_request.app_version_outdated`; the
  five-minute read and matching are unchanged. The complete local gate and both exact-SHA
  CI runs passed (1,650 backend, 1,418 frontend, journey 1, zero skips). Both services
  restarted twice, clear of locks and settlement sweeps. Natural-payment acceptance
  remains open; no webhook was deliberately deregistered or re-registered.
- **Batch 205 is shipped and verified** (13 Oct, `9731776`). API health and database
  readiness report `028`, drift is in sync, and the read-only audit found RLS forced on all
  24 tables with no `anon`, `authenticated` or `PUBLIC` table or schema grants. The web alias
  is Ready on the same SHA. Pay to pick is inert until a site admin sets a league's fee.
- **Batch 217 is shipped and verified** (7 Nov, `0d00825`, no migration). Both services report
  `0d00825` / `031`, drift is in sync, and the read-only audit found RLS forced on 27 of 27
  tables with no public-role grants. A refused odds key or bookmaker now carries the
  provider's reason, holds the odds cache off for 15 minutes and tells the site admins.
  Shipped at 19:03 UTC, after the 7 Nov lock and clear of the settlement sweeps.
- **Batch 218 is live on the web** (7 Nov, `2fa77bd`, web-only). "Take <new price>" now sends
  that price, a moved price re-reads the round, and the member's own hourly pick limit is named
  instead of "API error 429". It went out at 17:27 UTC, after the 7 Nov lock: two members lost
  up to an hour of picking to the dead button that morning (06:58 and 11:53 UTC).
- **Batch 206 is live on the web** (13 Oct, `32a8aef`, web-only, exact-SHA CI green): the pay
  panel, the season pot, the site-admin fee fields and the Payments screen. No league has a
  fee, so no member sees any of it yet.
- **Batch 209 is shipped and verified** (14 Oct, `335e986`, no migration). Every member of a
  league with a fee gets the payment link with no 18+ step, and pick cards grey out while a
  member owes. Health reports `335e986` / `028`, drift is in sync, and the read-only audit found
  RLS forced on 24 of 24 tables with no `anon`, `authenticated` or `PUBLIC` grants. Vercel serves
  the same SHA. Still inert until a site admin sets a league's fee.
- **Batches 207 and 208 are shipped and verified** (16 Oct, `5dd1fbe`, migration `029`). Both
  services report `5dd1fbe` / `029`, drift is in sync for both, and the read-only audit found
  RLS forced on 25 of 25 tables with no `anon`, `authenticated` or `PUBLIC` grants.
  **Monzo is connected** (16 Oct): the owner created a new confidential client, sealed its id and
  secret, connected at 21:29 UTC and approved in the app; the service marked itself connected and
  registered its webhook at 21:32 UTC with no error. Payments count from 21:29 UTC. Nothing is
  read until a league has a `monzo_link_id`, which a site admin now sets in League settings
  (Batch 210). The connect's one-time OAuth code appeared in the payments access log once; it was
  spent, and since `bca0aaa` (shipped 17 Oct) the service writes no access log.
- **Batch 203 shipped unrecorded on 11 Oct** (Railway `de1b8aa8`, `5882b0f`), found from
  Railway's deployment list on 13 Oct and now in the L4 record.
- **Batch 216 is shipped and verified** (25 Oct, `b7a4d72`, no migration). Both services report
  `b7a4d72` / `031` and drift is in sync. The first read learned the pot's `pot_…` name from a
  link payment's filing and wrote nothing; the owner's two earlier moves fell before it.
- **The bookmaker switch is live** (31 Oct, API `205b3765`, no code change, no migration).
  Every pick in the 31 Oct round was refused until `ODDS_API_BOOKMAKER` moved from `Bet365`
  to `Betfair Sportsbook`. Health reports `b7a4d72` / `031` and drift is in sync. A refused
  fixture's live odds call now returns Betfair Sportsbook prices, and a member's pick then
  saved (`201`). The restart emptied the app's odds budget counter, so a `429` at 11:05
  refused picks again until about 11:10, and they have saved since. The payments service was
  not touched. Record: L4, 2026-10-31.
- **The 24 Oct round is settled by hand** (31 Oct, 17:33 UTC, no code change). The owner
  approved voiding the abandoned Cumbernauld Colts v Banks O'Dee tie, so its one pick scores
  nothing; the round's other 10 picks had already settled, and all 12 members were told. It
  ran the admin settle endpoint's own code from the owner's Mac, because Railway SSH was
  dropping connections; the audit row names the owner. Record: L4, 2026-10-31.
- **Batch 214 is shipped and verified** (25 Oct, `06d6070`, migration `031`). Both services
  report `06d6070` / `031`, drift is in sync, and the catalogue audit found RLS forced on 27 of 27
  tables with no public-role grants. The payments service learned 2-1 Hibs' pot from its link
  payments, but Monzo names that pot by a different id in pot deposits, so the owner's top-ups
  are still not matched (Batch 216). Migration `031` requires forward recovery:
  `docs/runbooks/migration-031-recovery.md`.
- **Batch 213 is shipped and verified** (18 Oct, `0a7457b`, migration `030`). Both services
  report `0a7457b` / `030`, drift is in sync, and the catalogue audit found RLS forced on 26 of 26
  tables with no public-role grants. The `payment_notices` job runs every ten minutes; its first
  run sent nothing. Migration `030` requires forward recovery:
  `docs/runbooks/migration-030-recovery.md`.
- **Migration `029` requires forward recovery.** It is additive, but the older images'
  boot checks cannot start against revision `029`. Use
  `docs/runbooks/migration-029-recovery.md` for forward repair. Production has no backup
  restore point, so do not describe a downgrade as a data-preserving rollback.

## Waiting on the owner

These are not batches; nothing here will happen unless the owner does it or authorises it.

- **The season-calendar backfill**, unblocked since Batch 188 shipped on 2026-10-04.
  Production's `season_calendars` table is empty
  (2026-09-24). `python -m src.backfill_season_calendar --dry-run`, review every move,
  then a separately authorised `--apply`; see `docs/backfills/2026-season-calendar.md`.
- **The local agent configuration** (review finding PIPE-01, by hand, not a batch).
  `.claude/settings.local.json` still enables the Supabase MCP server — bound to a
  different product — with its write-capable query tool allowed, a blanket shell allow,
  and delete rules for other repositories (checked 2026-09-24).
- **Avatars stay off** until the owner follows `docs/runbooks/avatar-storage.md`. They
  would share the Supabase project whose egress quota was exceeded.
- **Stop recording the owner's own £1 by hand** (2026-10-25). Since Batch 216 a move from the
  owner's account into the pot is read; the first one waits in "Waiting to be matched" once,
  and assigning it to the owner books every later one automatically.
- **Monzo needs approving again by about 14 Jan 2027.** Monzo makes the owner re-approve a
  developer app every 90 days, and the payments service was approved on 16 Oct; after
  that nothing is read until the owner connects again from the payments service. Batch 214
  adds a warning a week before (2026-10-24).
- **Delete the old Monzo spike's OAuth client** at developers.monzo.com (ADR 0009 launch
  step 1, still open). Its client secret, echoed into a transcript on 7 Sep, still works: a
  token refresh with it succeeded on 2026-10-24. Its data access lapsed the same day, and
  the payments service has its own client, so nothing needs it.

## Members

- **Member B has not been told their sign-in name changed** (2026-09-27, 10:45 BST). Batch
  74 renamed the owner and members A and B on 2026-08-26; the boot-time push reached the
  other two on 2026-08-30. Member B has no push subscription, but five live sessions, the
  latest issued 2026-09-26 06:11 UTC. Batch 148's in-app notice has been live since 09:42
  BST, so it reaches them on their next open; the API logs `rename notice seen in the app`
  when it does, and production then holds the third `display_name_changed` row.
- A rename releases the old sign-in name outright, so nothing reserves the three names
  Batch 74 released.

## Open batches

Batches **237–241** are the first two-game week's fixes (owner, 24 Nov: all of 237, 238, 234,
235 and 239 today, in that order, with a `/ship-prod` after 237 and after 234). 237 is closed
and owes `/ship-prod`; 240 (the dues pass's lock) and 241 (two order-dependent tests) were found
in 237 and wait for the owner.

Batches **232–235** put both two-game games on one coupon screen (owner, 23 Nov). 232 (fantasy
with a pick slip, `05cf820`) and 233 (the Saturday group, `5198ab5`) are closed and live on the
web (23 Nov), as is 236 (the group screen keeping its last view through a dropped connection,
found in 233, `61a9700`). 234 (API:
competition names, club form, removing a pick in either game, who is still to pick;
`/ship-prod` owed) and 235 (the screens using it) were amended and moved to 24 Nov by the owner.

Batches **219–228** are closed (22 Nov) and live with the two-game format off. Batch
**231** — activation, suspension and resume for one league, audited, from a site-admin
route or `python -m src.two_game_rollout` — is closed (22 Nov, `97c9555`) and shipped with
the format off (23 Nov, `eaf8ca7`). Nothing
activates without Batch 228's activation checkpoint and a separate owner decision naming
the league and its first Saturday (`docs/runbooks/two-game-activation.md`). The note kept
frozen during the 219–228 stack is in `session-log.md`.

Batches 170-203 are drafted from the 2026-09-28 review and every owner decision they needed
was answered on 30 Sep. Group AG is complete, shipped and verified. Group AA is complete
(172, 173, 174 and 170, closed 3 Oct; web-only, nothing to ship). Group AC is complete,
shipped and verified (180, 179, 181 and 182; shipped 3 Oct as `9be47cef`). Group AD's first
checkpoint shipped on 4 Oct as `bb09760b` (Batches 183 and 188), and its closing checkpoint
shipped on 5 Oct as `546db3f` (Batches 184-187 and fix `f0710b0`); Group AD is complete. Batch
204 (docs-only close-out fast path, owner-approved gate maintenance) is complete. Group AE is
complete, shipped and verified (Batches 189–193; shipped 7 Oct as `c530469`); Group AB is
complete (Batches 171, 175–178; web-only, closed 8 Oct); Group AF is complete, shipped
and verified (Batches 196, 195, 197 and 194; final shipment 10 Oct). Group AH: Batches 202
(web toolchain refresh) and 203 (pipeline and operations hygiene) are complete (11 Oct).
Batch 203 shipped on 11 Oct, unrecorded until 13 Oct.

Batches 205-209 are pay to pick in 2-1 Hibs (ADR 0009). Batch 205 — the API ledger, weekly
dues and the paid-up check, migration `028` — is complete and shipped (13 Oct, `9731776`).
Nothing changes for members until a site admin sets a league's fee. Batch 206 — the screens —
is complete and live on the web (13 Oct, `32a8aef`). Batch 209 — the link with no 18+ step,
and greyed pick cards while a member owes (ADR 0009 amended 13 Oct) — is complete (14 Oct,
`b53ddf9`) and shipped as `335e986`. Batch 207 — the `payments` Railway service declared and
switched off, with a boot that never migrates — is complete (14 Oct, `71a0c5a`); production's
service was switched on on 16 Oct (`8b26336`). Batch 208 — the payments service reads the
league's Monzo link payments into the ledger, migration `029` — is complete (16 Oct,
`22bc3cb`) and not shipped; one `/ship-prod` covers both. Batch 210 — the admin-screen half of
208 (the link-id field and link health) — is complete and live on the web (17 Oct, `1e12109`,
web-only). Batch 211 —
a least-privilege database login for `payments` — is open and deferred until after launch
(owner, 16 Oct). Batch 212 — members see the prize fund, both targets and everyone's status,
and the pay panel's earlier balance — is complete and shipped (17 Oct, `06a32f6`, shipped as
`88d8541`). Batch 213 — notifications for queued payments, Monzo link trouble and payments
received, migration `030` — is complete and shipped (18 Oct, `8797aa7`, shipped as `0a7457b`).
2-1 Hibs has its fee, link and link id, and members' link payments are read and matched (24
Oct); making sure every member is 18 or over stays the owner's check (ADR 0009). Batch 214 —
the owner's own top-ups into the pot, a warning before Monzo's 90-day approval lapses, and
the refused webhook re-reads logged, migration `031` — is complete and shipped (25 Oct,
`d4880b1`, shipped as `06d6070`). Batch 216 — the owner's top-ups matched by the pot's
`pot_…` name, learned from Monzo's filings, which are never counted — is complete (25 Oct,
`bbedccf`) and shipped (25 Oct, as `b7a4d72`). Batch 215 — why Monzo refuses every webhook
re-read — is complete and shipped (9 Nov, `c18e81e`): the exact refused id is recovered from recent authenticated account feeds; natural-payment acceptance remains open. Batch 217 — the odds provider's own reason on a refused request, a
quarter-hour hold-off after a refused key or bookmaker, and a notice to site admins when picks
are refused for odds — is complete (31 Oct, `4d28412`) and shipped (7 Nov, as `0d00825`). Batch 218 — "Take the new
price" sends the price it names — is complete and live on the web (7 Nov, `2fa77bd`, web-only).
Batch 229 — CI's three jobs pinned to Ubuntu 24.04, because GitHub's `ubuntu-latest` became
Ubuntu 26.04, where Playwright 1.60.0 cannot install Chromium — is complete (19 Nov, `bf9d5f5`,
tooling-only, nothing to ship). Batch 230 — moving CI back once Playwright supports the newer
image — is open and not urgent.

## Toolchain

Checked 2026-10-03.

- **The gate is `scripts/ci-local.sh`**: twelve checks and no skips, the twelfth being the seeded
  coupon journey (2026-09-30). GitHub's `coupon-journey` job runs the same runner through
  `ci-local.sh --journey-only`. The `gate` job runs the same trusted-main guard, ratchets and
  zero-skip checks as local close-out. A full green run stamps the exact Git tree; close-out reuses
  that stamp when only `docs/BUILD_PLAN.md`, `session-log.md` and `STATUS.md` changed, otherwise it
  reruns the gate, and waits for both pushed SHAs to pass CI before the group continues. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 2,087, frontend 1,505, journey 1; checked 2026-11-22). 13m04s on this Mac
  with the journey (2026-09-30), and 38 minutes when macOS's storage scan loads it
  (2026-09-25). Without a database the backend suite is 800 passed and 550 skipped at
  1,350 tests (2026-09-29) — not the gate.
- **Backend** runs from the gate's own venv, `~/.cache/the-coupon/ci-local-venv`, built from
  `apps/api/requirements-dev.txt`: Python 3.12, FastAPI 0.141.1, ruff 0.5.4. app-starter's
  venv cannot import the suite.
- **Frontend** is Node 24.21.0 through nvm, with pnpm 9.15.0 from corepack; the gate refuses
  any other pnpm. CI and the Vercel build are Node 24 too (`apps/web` pins `24.x`). The
  ambient `node` is too old for the tooling, and nvm's default alias is still 20. Since Batch
  202 (2026-10-11): Vite 8 (Rolldown), Vitest 5, Tailwind 4 reading `tailwind.config.ts`
  through `@config`, ESLint 10 with `apps/web/eslint.config.js`; OSV finds no npm advisory.
  `index.css` holds the rules that keep Tailwind 3's rendering — change them only with a
  before/after screenshot check. The guard does not yet protect `eslint.config.js`.
- **Scratch PostgreSQL** is pip `pgserver`, started and discarded by the gate.
- **Protected files**: `scripts/ci-local.sh` runs `main`'s guard and owner-approval table, not the
  branch's. The guard protects gate, close-out, CI, lint, type and test-discovery configuration by
  pattern; it also refuses recorded skip, suppression and weakened-oracle forms. An approved
  gate-maintenance batch must have its exact file list quoted in its open row on `main`.
- **Production reads**: use `railway run` with the explicit production selectors and a local
  asyncpg script. The direct Supabase hostname did not resolve locally on 2026-10-01, so the
  read-only audit used the exact project's London session-pooler route in memory; `railway ssh`
  worked on 2026-09-26. Probe rather than trusting either route. The Railway CLI's default
  link is staging, and the Supabase MCP here is a different product — never read Coupon data
  through it.
- **Operator CLIs**: Railway 5.64.2 and Vercel 54.6.1 are verified with Node 24.21.0 on
  `PATH`; the legacy Node 20 installation supplies their shims only. Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`. Close-out refuses API+web work, and web work over existing API debt, until the
  owner schedules the shipment; its durable verdict records who scheduled it and the UTC time.
- **CI runners**: all three Quality jobs run on `ubuntu-24.04`, not `ubuntu-latest` (Batch 229,
  19 Nov). On GitHub's Ubuntu 26.04 image Playwright 1.60.0 cannot install Chromium, so both
  browser jobs failed at install on every push from about 18 Nov. Batch 230 moves back.

**Next:** `/ship-prod` for Batch 237 on the owner's go, then confirm from production logs that
game reads take about 1 s, both jobs' passes stay inside their minute, no QueuePool error
recurs and a real fantasy PUT saves. Then Batches 238, 234 (`/ship-prod`), 235 and 239 today.
The 24 Nov morning check found no legacy request or refusal; discovery's background allowance
(120 a day) ran out at 06:57 UTC and parks background price refreshes until 17:09 UTC, about
12 h of each day, while saves still price fresh. Fri ~12:30, recheck the Saturday card's
prices; Sat 28 Nov, the first two-game round (group opens 03:00, fantasy locks 12:00, group
14:30). Before activating Yer Leagues A Joke, stop the silence alarm firing between activation
and the first complete card. Next week, on its own fix branch: the test-data leak that turns
`main` red from 24 Dec to 6 Jan (`.local/date-sweep/README.md`). Confirm a natural payment on
the organiser's Payments screen. Batch 211 stays deferred; the season-calendar backfill remains
owner-gated, unblocked since 4 Oct.
