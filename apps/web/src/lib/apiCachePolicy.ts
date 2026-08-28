import type { WorkboxPlugin } from 'workbox-core';

/**
 * Keeps the service worker's `/api/v1/*` cache in step with what the API says about
 * storing its responses.
 *
 * `CacheableResponsePlugin` decides on HTTP status alone — it never reads
 * `Cache-Control` — so a `NetworkFirst` route wrote every 200 into Cache Storage
 * regardless of the `no-store` that `SecurityHeadersMiddleware` puts on every API
 * response. Logout and identity-switch clear that cache (`clearApiCaches()`), but a
 * device that is merely *locked* — access token expired, refresh token still present —
 * kept up to an hour of the previous reader's league data readable by anything with
 * page-context JS, since Cache Storage is same-origin-scoped rather than
 * permission-scoped. That is SEC-13.
 *
 * Returning `null` from `cacheWillUpdate` is what stops the write; dropping
 * `CacheableResponsePlugin` would not have, because `NetworkFirst` persists by default
 * and that plugin only ever narrows what it persists.
 *
 * Today the API marks every response `no-store`, so in practice this caches nothing and
 * the route is network-with-a-timeout. That is the intended trade: a stale league table
 * is not what a flaky connection needs, and `OfflineBanner` already states the case
 * plainly. Reading the header rather than deleting the route means a response the API
 * later declares cacheable — a public config read, say — starts being cached again
 * without anyone having to remember this file exists.
 */
export const respectNoStore: WorkboxPlugin = {
  cacheWillUpdate: async ({ response }) => {
    const directive = response.headers.get('Cache-Control');
    if (directive && /(^|,)\s*no-store\s*(,|$)/i.test(directive)) return null;
    return response;
  },
};
