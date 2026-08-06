# ADR 0005 — Recover a stale route chunk by reloading, not by pinning old builds

Status: **accepted, 2026-08-06.** Scoped as Batch 19, which was a timeboxed
diagnosis of the owner's "Something went wrong" report on the coupon page. The
diagnosis landed, so the batch ships the fix as well as the finding.

## Context

The owner reported the coupon page rendering `ErrorBoundary`'s "Something went
wrong". The batch row recorded why it could not be specified as a code change:
reconciliation had cleared the whole render path — `CouponPickPage`,
`CouponCombinedPage`, `CouponSubNav`, `GameweekNav`, `MemberRoster`, `PickCard`,
`FormLine`, `CombinedAccaView`, `lib/coupon.ts`, `useGameweekHistory` — and the
API models behind it, where every field the frontend dereferences without a
guard (`CouponLeg.odds`, `Coupon.combined_odds`, `Standing.form`) is
non-nullable. Typecheck, the Vitest suite and a production build all passed. The
throw was not in the source, and the row's leading hypothesis was a stale lazy
chunk after a redeploy.

## The finding

The hypothesis is right, and it reproduces exactly.

Against the real production bundle (`vite build` → `vite preview`) with a seeded
session, the dashboard was loaded, the built `assets/CouponPickPage-*.js` was
removed from disk — what a redeploy looks like to a tab that is still holding
the previous build's `index.html` — and the Coupon tab was tapped. The page
rendered "Something went wrong" inside an otherwise intact app shell, the
owner's screenshot, and the boundary's own log named the cause:

```text
render failed TypeError: Failed to fetch dynamically imported module:
  http://localhost:4173/assets/CouponPickPage-CGRBdxPc.js
    at Lazy
    at ... Layout ... Suspense ...
```

Restoring the file and reloading cleared it, with no other change.

The mechanism is the combination of three things that are each individually
correct:

1. **Every route is `lazy()`.** `App.tsx` code-splits eighteen route modules and
   the `Layout` shell, so moving to a screen this tab has not visited fetches a
   hashed chunk on demand.
2. **A deployment does not keep the previous build's chunks.** Hashes change on
   every build, Vercel serves the production domain from one deployment at a
   time, and since Batch 18 the `vercel.json` rewrite excludes `assets/` — so an
   old chunk URL is a plain 404 rather than an HTML body. Either shape rejects
   the `import()`; Chrome words both as `Failed to fetch dynamically imported
   module`.
3. **The service worker widens the window rather than narrowing it.** `sw.ts`
   calls `skipWaiting()` and `clientsClaim()` unconditionally, so a newly
   installed worker takes over an already-open tab immediately, and Workbox's
   precache drops the entries the new manifest no longer lists. Before that
   moment the old chunk would have been served from precache and nothing would
   have broken; after it, the tab is running old JavaScript against a worker
   that has only new chunks.

That last point is what makes the coupon page the reporter rather than a
coincidence. `UpdateBanner` does schedule an automatic reload, but only after
the new worker is detected, only when the tab is visible, only when predictions
are not dirty, and then after a five-second grace countdown. Reopening the
installed PWA and tapping straight into Coupon — the app's main screen, one tap
from the dashboard the tab was left on — lands inside that window. The dashboard
chunk is already in memory, so the crash appears on the *first route change*
after a deploy, not on the screen the tab was resumed to.

None of this is specific to the coupon. Any route that has not been visited yet
fails the same way; the coupon is simply the one members open first.

## Decision

**Catch the failed import at the `lazy()` boundary and reload the page once.**

`lib/lazyRoute.ts` wraps `React.lazy`, and `App.tsx` uses it for all eighteen
routes and the `Layout` shell. On a rejected import it matches the message
against the wordings Chrome, Firefox, Safari and Vite's CSS preload helper use;
anything else re-throws untouched, so an application error still reaches the
boundary as it does today. On a match it reloads, which fetches the current
`index.html` and with it the current chunk names.

Three properties make that safe:

- **The retry has to live inside the loader.** React caches a rejected `lazy`
  payload permanently, so the boundary's "Try again" re-throws the same error
  without re-attempting the import. Recovery after the throw is not available.
- **One reload, then stop.** A `sessionStorage` marker suppresses another
  recovery reload for thirty seconds. A genuine stale chunk fails once and is
  fixed; a chunk broken for any other reason fails again within a second of
  coming back, well inside the window, and falls through to the boundary. A
  reload loop is not reachable.
- **Offline never reloads.** The chunk cannot arrive either way, and reloading
  would trade a readable message for a blank shell.

The reload does not need to force a service-worker update first. A 404 on a
chunk means the precache no longer holds it, which means the new worker has
already activated and claimed the tab — so the reload is served the new
`index.html`, from precache or the network.

`ErrorBoundary` also learns the difference. When recovery declines to reload it
now says "The Coupon has been updated" and offers only Reload, dropping the
"Try again" button that cannot work for a rejected payload.

## What was rejected

- **Retrying the same import URL.** A deleted chunk stays deleted. It buys one
  more failed request in the case that actually happens.
- **Preloading every route chunk on entry.** It removes the failure by removing
  the code-splitting, and Batch 14 split these routes deliberately to keep
  framer-motion and recharts out of the unauthenticated `/login` entry.
- **Keeping old deployments' assets reachable.** Vercel can serve prior
  deployments on their own URLs, but the production domain resolves to one
  deployment; making stale hashes resolve there means an origin the app does not
  control and a cache policy nobody wants to reason about on a Saturday.
- **Calling `event.preventDefault()` on Vite's `vite:preloadError`.** That makes
  the preload helper resolve with `undefined` rather than reject, which
  `React.lazy` then fails on with a worse message. Catching the rejection is the
  single path.
- **Blocking on `dirtyState` the way `UpdateBanner` does.** The failure only
  happens on a route *change*, which already abandons any in-progress pick; the
  reload returns to the route the member asked for.

## Consequences

- A member who keeps a tab or the installed PWA open across a deploy sees a
  reload instead of an error. The route they tapped is what they land on.
- The recovery covers every code-split route, not the coupon, because the cause
  was never in coupon code.
- `UpdateBanner`'s scheduled reload is unchanged and still the primary path;
  this is the net under it for the window the banner cannot cover.
- The offline and repeat-failure paths keep an explicit message rather than a
  silent retry, so a real regression is still visible rather than reloaded over.

## Follow-up not taken here

`sw.ts` precaches `index.html` and registers `precacheAndRoute` before the
`NavigationRoute`, so precache answers navigations and the `NetworkFirst`
navigation strategy below it is effectively unreachable. That is out of scope
for a diagnosis batch and does not affect this fix — the reload happens after
the new worker has claimed the tab — but it is worth a row of its own.
