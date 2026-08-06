/**
 * Route-level `lazy()` that survives a deployment.
 *
 * Every route in `App.tsx` is code-split, so moving between them fetches a
 * hashed chunk on demand. Those hashes change on every build and the old files
 * do not survive the deploy: Vercel serves each deployment on its own, and the
 * `vercel.json` rewrite excludes `assets/`, so a chunk from the previous build
 * is a plain 404. The service worker makes the window wider rather than
 * narrower — `sw.ts` calls `skipWaiting()` and `clientsClaim()`, so a new
 * worker takes over an open tab immediately and drops the previous precache,
 * while that tab carries on running the *old* JavaScript with the old chunk
 * names baked into it.
 *
 * The result is a tab held open across a deploy that renders fine until the
 * member taps into a route they had not visited yet, at which point the
 * `import()` rejects, `React.lazy` re-throws, and `ErrorBoundary` shows
 * "Something went wrong" — the Batch 19 report. Recovery is a full page load,
 * which fetches the current `index.html` and with it the current chunk names.
 *
 * So that is what this does: catch the failed import, reload once, and let the
 * boundary handle anything that is not a stale chunk. React caches a rejected
 * `lazy` payload permanently, so the retry has to happen inside the loader —
 * by the time the boundary's "Try again" runs, the payload only re-throws.
 */

import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

/**
 * How each engine words a dynamic import it could not fetch or parse. Matched
 * case-insensitively as substrings because the URL is appended to most of them.
 *
 * Both production failure shapes land here: a 404 (Vercel, where `assets/` is
 * excluded from the SPA rewrite) and an `index.html` body served under a `.js`
 * URL (any host whose fallback is broader), since a module script with an HTML
 * content type is rejected the same way.
 */
const CHUNK_ERROR_PATTERNS = [
  'failed to fetch dynamically imported module', // Chrome, Edge
  'error loading dynamically imported module', // Firefox
  'importing a module script failed', // Safari
  'module script failed to load', // Safari, older wording
  'unable to preload css', // Vite's CSS preload helper
];

/** True when `error` is a chunk that could not be loaded, not app code throwing. */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  const lower = message.toLowerCase();
  return CHUNK_ERROR_PATTERNS.some((pattern) => lower.includes(pattern));
}

/** Timestamp of this tab's last recovery reload. Session-scoped so it survives it. */
const RELOAD_MARKER_KEY = 'coupon_chunk_reload_at';

/**
 * How long a recovery reload suppresses the next one.
 *
 * This is what stops a reload loop. A genuine stale chunk fails once and the
 * reload fixes it; a chunk that is broken for some other reason fails again
 * within a second or two of coming back, well inside this window, and falls
 * through to the boundary instead of reloading again.
 */
const RELOAD_COOLDOWN_MS = 30_000;

function reloadedRecently(now: number): boolean {
  try {
    const at = Number(window.sessionStorage.getItem(RELOAD_MARKER_KEY));
    return Number.isFinite(at) && at > 0 && now - at < RELOAD_COOLDOWN_MS;
  } catch {
    // Storage can throw in private modes; treat it as "no reload yet".
    return false;
  }
}

function markReloaded(now: number): void {
  try {
    window.sessionStorage.setItem(RELOAD_MARKER_KEY, String(now));
  } catch {
    // Without the marker we lose loop protection, not correctness — the
    // boundary still catches a second failure.
  }
}

/**
 * Reload to recover a stale chunk, or re-throw so the boundary can explain.
 *
 * Declines to reload when offline — the chunk cannot arrive either way, and a
 * reload would trade a readable message for a blank shell — and when this tab
 * has already reloaded inside the cooldown.
 *
 * On the reload path it returns a promise that never settles, so React holds
 * the route's `Suspense` fallback for the moment the page takes to go away
 * rather than flashing the boundary on the way out.
 */
function recoverFromStaleChunk(error: unknown): Promise<never> {
  const now = Date.now();
  if (!window.navigator.onLine || reloadedRecently(now)) throw error;

  markReloaded(now);
  window.location.reload();
  return new Promise<never>(() => {});
}

// React's own `lazy` signature is written against `ComponentType<any>`; matching
// it keeps every call site's props inference intact.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComponent = ComponentType<any>;

/**
 * `React.lazy` with stale-chunk recovery. Use it for every code-split route so
 * the recovery covers the whole app rather than the one screen that reported it.
 */
export function lazyRoute<T extends AnyComponent>(
  load: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  return lazy(() =>
    load().catch((error: unknown) => {
      if (!isChunkLoadError(error)) throw error;
      return recoverFromStaleChunk(error);
    }),
  );
}
