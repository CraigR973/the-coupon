import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NetworkFirst } from 'workbox-strategies';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import { respectNoStore } from '@/lib/apiCachePolicy';

const API_URL = 'https://api.the-coupon.example/api/v1/leagues/the-coupon/standings';

/** The body a signed-in read returns — the thing SEC-13 is about not leaving behind. */
const STANDINGS = JSON.stringify([{ player: 'Alice', points: 19 }]);

function apiResponse(headers: Record<string, string>) {
  return new Response(STANDINGS, {
    status: 200,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

// ---------------------------------------------------------------------------
// A Cache Storage that records what was actually written.
// ---------------------------------------------------------------------------

interface FakeCache {
  entries: Map<string, Response>;
}

function installFakeCacheStorage(): FakeCache {
  const entries = new Map<string, Response>();
  const cache = {
    put: async (request: Request | string, response: Response) => {
      entries.set(typeof request === 'string' ? request : request.url, response);
    },
    match: async (request: Request | string) =>
      entries.get(typeof request === 'string' ? request : request.url),
    delete: async () => true,
    keys: async () => [...entries.keys()].map((url) => new Request(url)),
  };
  vi.stubGlobal('caches', {
    open: async () => cache,
    delete: async () => true,
    keys: async () => ['api-coupon'],
    match: async () => undefined,
  });
  return { entries };
}

/**
 * Runs the real `NetworkFirst` with the real plugins, because the question is whether the
 * *strategy* honours `respectNoStore` — calling `cacheWillUpdate` directly would only
 * prove the callback returns `null`, which was never in doubt.
 *
 * `ExpirationPlugin` is the one piece of `sw.ts`'s list left out. It writes timestamps to
 * IndexedDB from `cacheDidUpdate`, which jsdom does not implement, and the resulting
 * unhandled rejection fails the run while proving nothing: eviction is orthogonal to
 * whether a response is written at all. `CacheableResponsePlugin` is kept — it is the
 * plugin SEC-13 named as insufficient, and it is the one this has to run alongside.
 */
/**
 * jsdom defines none of the service-worker globals, and Workbox checks two of them:
 * `Strategy.handleAll` does `options instanceof FetchEvent`, and `StrategyHandler`
 * asserts `options.event instanceof ExtendableEvent`. Standing these in is what lets the
 * real strategy run here — the alternative is asserting on `cacheWillUpdate` alone,
 * which would not prove `NetworkFirst` honours it.
 */
class StubExtendableEvent {
  readonly pending: Promise<unknown>[] = [];
  waitUntil(promise: Promise<unknown>) {
    this.pending.push(promise);
  }
}

async function handleThroughRoute(response: Response) {
  vi.stubGlobal('FetchEvent', class FetchEvent {});
  vi.stubGlobal('ExtendableEvent', StubExtendableEvent);
  vi.stubGlobal('fetch', () => Promise.resolve(response));
  const strategy = new NetworkFirst({
    cacheName: 'api-coupon',
    networkTimeoutSeconds: 3,
    plugins: [respectNoStore, new CacheableResponsePlugin({ statuses: [200] })],
  });

  const request = new Request(API_URL);
  const event = new StubExtendableEvent();

  const handled = await strategy.handle({
    event: event as unknown as ExtendableEvent,
    request,
  });
  // The cache write happens in a `waitUntil` promise, so the assertion has to wait for
  // it — otherwise an empty cache proves only that the test looked too early.
  await Promise.all(event.pending);
  return handled;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('the /api/v1 route honours Cache-Control', () => {
  it('leaves nothing in Cache Storage for a no-store response', async () => {
    const store = installFakeCacheStorage();

    const handled = await handleThroughRoute(apiResponse({ 'Cache-Control': 'no-store' }));

    // The member still gets their data — this is about what is left behind, not about
    // breaking the read.
    expect(handled?.status).toBe(200);
    expect(store.entries.size).toBe(0);
  });

  it.each([
    ['no-store alone', 'no-store'],
    ['with no-cache', 'no-cache, no-store, must-revalidate'],
    ['capitalised', 'No-Store'],
    ['with private and max-age', 'private, max-age=0, no-store'],
  ])('leaves nothing behind when the header is %s', async (_label, directive) => {
    const store = installFakeCacheStorage();
    await handleThroughRoute(apiResponse({ 'Cache-Control': directive }));
    expect(store.entries.size).toBe(0);
  });

  // The guard has to read the directive rather than switch caching off wholesale, or a
  // response the API later declares storable would stay uncached forever with nothing
  // pointing at why.
  it('still caches a response the API did not mark no-store', async () => {
    const store = installFakeCacheStorage();

    await handleThroughRoute(apiResponse({ 'Cache-Control': 'max-age=300' }));

    expect(store.entries.size).toBe(1);
    expect(store.entries.has(API_URL)).toBe(true);
  });

  it('does not mistake no-cache for no-store — that one is revalidate, not forget', async () => {
    const store = installFakeCacheStorage();
    await handleThroughRoute(apiResponse({ 'Cache-Control': 'no-cache' }));
    expect(store.entries.size).toBe(1);
  });

  it('caches a response with no Cache-Control at all, as before', async () => {
    const store = installFakeCacheStorage();
    await handleThroughRoute(apiResponse({}));
    expect(store.entries.size).toBe(1);
  });
});
