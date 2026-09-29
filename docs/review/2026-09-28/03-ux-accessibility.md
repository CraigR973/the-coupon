# 03 — UI/UX and accessibility (objective checks only)

_In progress — findings are written in as they are verified. Working notes, scripts and raw
output: `notes/03-ux/` (`progress.md` says where the pass is)._

## Method

The production bundle, built by `notes/03-ux/build_web.py`, served on `127.0.0.1:4330` against
the review harness's seeded scratch API on `127.0.0.1:8130` (`tests.e2e_server:app`, FakeBetfair,
`ODDS_PROVIDER=fake`, scheduler off, migration 026). Driven in real headless Chromium (Playwright
1.60, Node 24), `deviceScaleFactor: 1`, service workers blocked, theme and session written to
`localStorage` before first paint. axe-core 4.10.2 injected into the live page.

**The shared harness's bundle was unstyled.** `notes/harness/web.sh` runs `vite build <root>`
from outside `apps/web`, and `tailwind.config.ts` resolves its `content` globs against the process
working directory, so Tailwind emitted no utilities: the stylesheet was 9.1 KB against the gate's
45.8 KB and every page rendered as unstyled text. The first five captures of this pass were taken
against it and discarded. `build_web.py` runs the same build with `cwd=apps/web` (from Python, no
shell `cd`) and refuses to serve a stylesheet under 30 KB; every result below is from that build
(CSS 45,794 bytes, identical to the gate's). Lenses 02 and 05 have already marked their captures
from the first build as unstyled in `screenshots/INDEX.md`.

States were seeded in process with the app's own models (`notes/03-ux/seed_states.py`): Alice is
site admin and league admin of `the-coupon`, Bob a member (and admin of a second league,
`sunday-club`, with fixture scope, match odds only and a **locked** round), Carol a member, Dave
in no league, Erin a pending join request, an unclaimed invite, and a **2025/26 archive** season
(two settled rounds with won, lost and void picks). Loading states hold the page's main request
open; error states fulfil it with a 500; forced-empty states fulfil it with `[]`; offline drops the
network after load. The settled current round comes from the e2e server's own lock and settle
endpoints after real picks.

At 390 the viewport is 390×844 with a desktop user agent — the layout an installed PWA gets. The
mobile install gate is triggered by user agent, not width, so it is measured separately with an
Android UA.

## Prior findings

_Being re-driven._

## Register

_Being written._

## Checked and found nothing material

## Proposed batches

## Owner decisions

## Doc corrections

## What this pass did not do
