# Lens 05 — Feature gaps (brief)

Output: `docs/review/2026-09-28/05-feature-gaps.md`. Notes: `docs/review/2026-09-28/notes/05-features/`.
Port: API **8150** only if you need a running stack. New ids start at **FEAT-A13** (spec
gaps) and **FEAT-B10** (member expectations).

Keep it brief and grounded: every point cites the actual router, service or
component (file:line), and anything you call "missing" you have looked for.

## Your slice of the prior registers

| id | then | batch / decision | check |
| --- | --- | --- | --- |
| FEAT-A10 | HIGH | 134 | pick correction exists — site-admin API only? Is there any UI, or is it curl-only? Does the owner have a way to use it on a Saturday night from a phone? |
| FEAT-B07 | MED-HIGH | 136 | self-service deletion + export exist, reachable from the UI |
| FEAT-A11 | MED | 148 | in-app rename notice exists (STATUS says member B has not yet opened the app — do not try to confirm that against production) |
| FEAT-B08 | MED | 135 | settlement notification exists, per member, both settle paths |
| FEAT-A12 | LOW | carried, no batch | the register screen still ignores the signup kill switch? (Needs the config route readable unauthenticated, which reverses a documented decision — say so) |
| FEAT-B09 | LOW | carried, no batch | results history still has no season filter? |
| FEAT-A01 | — | launch gate L5 | still open? (`docs/LAUNCH_PLAN.md`, `launch-log.md`) |
| FEAT-A02 / OPS-13 | HIGH | 95 built, **switched off** | STATUS says production has no backup: record how long it has been open, and what exactly the owner must do (STATUS "Waiting on the owner") |
| FEAT-A09 | — | owner action | storage-egress consumer attributed? |

## What to do

1. Spec gaps: read the product contract and `docs/LAUNCH_PLAN.md`; list what they
   promise that is not built or not reachable by a member, with evidence.
2. Member expectations: what a paying member of a weekly friends' game would
   expect from FotMob / Sleeper / FPL-class apps that is missing — only things
   that fit this product (text-only, no wagering, private leagues). Check
   routers and components before calling anything missing. Examples to check,
   not assume: an in-app notification history/inbox now that there are several
   push types; a way to see *why* a pick was voided or corrected; league
   invitations by share sheet; what happens at season end; pick reminders
   control; editing a pick before lock; a "who hasn't picked" nudge.
3. Anything built but unreachable (an API route with no UI, a UI with no route).
   Diff routers against `apps/web/src/lib/api*` callers.
4. Keep it to what changes a decision. "Not a gap" list for things checked and
   present.
