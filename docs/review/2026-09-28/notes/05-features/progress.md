# Lens 05 — feature gaps — progress

Resume from this file alone. Brief: `../briefs/common.md` + `../briefs/05-features.md`.
Deliverable: `docs/review/2026-09-28/05-feature-gaps.md`. Port: API 8150 only (no web
port was allocated — drive the bundle with Playwright `page.route` fulfilment from the
built files on a fake origin instead of binding a second port).

## Done

- 28 Sep 22:53 read briefs, 00-prompt, 2026-09-13 README + 05 doc, STATUS, AGENTS
- 28 Sep 23:00 route inventory (`route_inventory.py` → `route_inventory.txt`)
- 28 Sep 23:04 code reading of the whole prior slice (findings below) — interrupted
- 29 Sep 08:40 resumed

## Code-reading findings so far (plausible until driven)

Prior slice:
- FEAT-A10: `POST /admin/picks/{pick_id}/correct` exists (admin.py:1348), site admin,
  no web caller (inventory). No API route returns *another* member's pick id
  (PickResponse.id only on own pick, picks.py:188; CouponLeg, GameweekMember,
  SettledPick, MyPick have no pick id) → admin needs a DB read to use it. Audit row has
  `league_id` not `league_slug` and target_id=pick.id → `_league_audit_scope`
  (leagues.py:~1356) cannot see it: invisible to the league audit log. No push to the
  member. Session log Batch 134 says "no screen for it yet — API only".
- FEAT-B07: `GET /me/export`, `POST /me/delete` (me.py:597/623); YourDataSection mounted
  on SettingsPage (SettingsPage.tsx:633). Looks held — drive it.
- FEAT-A11: RenameNotice in Layout (Layout.tsx:23), routes me.py:678/687, ids hard-coded
  in services/rename_notice.py RENAMED_PROFILE_IDS. Drive by inserting a profile with id
  39faae39-29a9-4c47-8905-109b2773f31b.
- FEAT-B08: `announce_round_settled` called from admin settle (admin.py:1313) and the
  sweep (scheduler.py:703). `/__e2e/settle` calls settle_gameweek_via_provider directly
  (NOT the sweep) — drive the sweep in process with a counting send_notification.
- FEAT-A12: not fixed. RegisterPage has no signup check; `/config` is authenticated
  (routers/config.py docstring: "Authenticated, because nothing unauthenticated needs
  it"). Sharper: refusal says "Ask a league admin for an invite" but claim-invite needs
  CurrentUser (league_memberships.py:63) and no route creates an account → with the
  switch off there is no way in. The state is already public: register checks the switch
  before name validation (auth.py:426).
- FEAT-B09: not fixed. `/results` takes no season (coupon.py:64), ResultsPage has no
  selector and is titled "Season".
- FEAT-A01: L5 unticked (LAUNCH_PLAN.md:30), no L5 entry in launch-log.md.
- FEAT-A02/OPS-13: Batch 95 built off (STATUS "Backups none yet"); health exposes nothing
  about backup. Production live since L4 2026-08-04; first live Saturday 22 Aug.
- FEAT-A09: never attributed (STATUS, runbook step 5); memory note says avatars bucket
  empty, Supabase egress is per organisation, four other projects in the org.

New candidates:
- No in-app notification history: pushes are fire-and-forget, no table
  (models/notification.py has only PushSubscription, NotificationPreferences, AuditLog);
  STATUS: 13 active accounts, 7 push subscriptions.
- Mute is per league or global only; no per-type control (notifications.py
  PreferencesOut); pick-made pushes 11 per pick in a 12-member league.
- Built but unreachable: per-league display name PUT (league_memberships.py:394), league
  admin reset-pin (league_memberships.py:577), GET /me/profile, GET /push/vapid-public-key,
  DELETE /auth/players/{id}/avatar (avatars off). None ever had a web caller (git -S).
- Join code returned to every member (leagues.py:1151) but shown only on the admin
  invites page → ordinary members cannot invite.
- Forgot-PIN pages site admins only (auth.py:734); league admin not told.
- Season end: no end-of-season moment; rollover month 7 (football_provider.py:50).

Not a gap (checked present): who-hasn't-picked list (PickRow.tsx:128), move pick before
lock (pick_changed), invite share sheet for admins (lib/invite.ts:73), settled-result
share, reminder ~3h before lock (scheduler.py:844).

## Next

1. Commit this file.
2. Start stack on 8150 (PUBLIC_SIGNUP_ENABLED=false in env for the A12 run later, or a
   second run), write `drive.py` (HTTP + in-process) to verify A10, B07 API, A11, B08
   both paths, A12, B09, audit-log invisibility, pick-id discoverability. Save output
   to `drive-output.txt`.
3. Browser: build bundle with VITE_API_URL=http://127.0.0.1:8150 into scratchpad, then
   Playwright page.route on http://review05.localhost serving files; stack origin
   must be that origin. Check Settings → Your data, rename dialog, register form.
4. Write the lens document; stop the stack; commit; reply ≤40 lines.
