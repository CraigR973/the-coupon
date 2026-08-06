/**
 * Batch 19 — stale-chunk recovery.
 *
 * Acceptance:
 *  - A failed dynamic import is recognised across engine wordings, and app
 *    errors that merely mention modules are not.
 *  - A stale chunk reloads the page once; a second failure inside the cooldown
 *    falls through to the boundary instead of looping.
 *  - Offline never reloads — the chunk cannot arrive either way.
 *  - A non-chunk error from the loader reaches the boundary untouched.
 *  - The boundary tells a stale chunk apart from a render crash.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Suspense } from 'react';
import { isChunkLoadError, lazyRoute } from '@/lib/lazyRoute';
import { ErrorBoundary } from '@/components/ErrorBoundary';

// Chrome's wording, the one the owner's report reproduces as.
const CHUNK_MESSAGE =
  'Failed to fetch dynamically imported module: https://example.test/assets/CouponPickPage-CGRBdxPc.js';

const reload = vi.fn();

function renderRoute(load: () => Promise<{ default: () => JSX.Element }>) {
  const Route = lazyRoute(load);
  return render(
    <ErrorBoundary>
      <Suspense fallback={<span>loading</span>}>
        <Route />
      </Suspense>
    </ErrorBoundary>,
  );
}

beforeEach(() => {
  reload.mockClear();
  window.sessionStorage.clear();
  vi.stubGlobal('location', { ...window.location, reload });
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  // The boundary logs the failure by design; keep the run readable.
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ─── isChunkLoadError ────────────────────────────────────────────────────────

describe('isChunkLoadError', () => {
  it.each([
    ['Chrome', CHUNK_MESSAGE],
    ['Firefox', 'error loading dynamically imported module: https://example.test/assets/a.js'],
    ['Safari', 'Importing a module script failed.'],
    ['Safari, older', 'Module script failed to load.'],
    ['Vite CSS preload', 'Unable to preload CSS for /assets/index-abc.css'],
  ])('recognises the %s wording', (_engine, message) => {
    expect(isChunkLoadError(new Error(message))).toBe(true);
  });

  it.each([
    new TypeError("Cannot read properties of undefined (reading 'toFixed')"),
    new Error('API error 404'),
    new Error('Failed to fetch'),
  ])('leaves an application error alone: %s', (error) => {
    expect(isChunkLoadError(error)).toBe(false);
  });

  it('handles a thrown non-Error', () => {
    expect(isChunkLoadError(CHUNK_MESSAGE)).toBe(true);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

// ─── lazyRoute ───────────────────────────────────────────────────────────────

describe('lazyRoute', () => {
  it('reloads the page when a route chunk is gone', async () => {
    renderRoute(() => Promise.reject(new Error(CHUNK_MESSAGE)));

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    // The promise never settles, so the route stays suspended rather than
    // flashing the boundary while the page goes away.
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('does not reload twice inside the cooldown', async () => {
    renderRoute(() => Promise.reject(new Error(CHUNK_MESSAGE)));
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());

    renderRoute(() => Promise.reject(new Error(CHUNK_MESSAGE)));
    await screen.findAllByText('The Coupon has been updated');
    expect(reload).toHaveBeenCalledOnce();
  });

  it('reloads again once the cooldown has passed', async () => {
    window.sessionStorage.setItem('coupon_chunk_reload_at', String(Date.now() - 60_000));

    renderRoute(() => Promise.reject(new Error(CHUNK_MESSAGE)));

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
  });

  it('does not reload while offline', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);

    renderRoute(() => Promise.reject(new Error(CHUNK_MESSAGE)));

    await screen.findByText('The Coupon has been updated');
    expect(reload).not.toHaveBeenCalled();
  });

  it('passes an application error through to the boundary', async () => {
    renderRoute(() => Promise.reject(new Error('boom')));

    await screen.findByText('Something went wrong');
    expect(reload).not.toHaveBeenCalled();
  });

  it('renders the route normally when the chunk loads', async () => {
    renderRoute(() => Promise.resolve({ default: () => <p>the coupon</p> }));

    await screen.findByText('the coupon');
    expect(reload).not.toHaveBeenCalled();
  });
});

// ─── ErrorBoundary ───────────────────────────────────────────────────────────

describe('ErrorBoundary', () => {
  function Boom({ error }: { error: Error }): JSX.Element {
    throw error;
  }

  it('offers only a reload for a stale chunk', async () => {
    render(
      <ErrorBoundary>
        <Boom error={new Error(CHUNK_MESSAGE)} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('The Coupon has been updated')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    // Resetting the boundary cannot re-attempt a rejected lazy payload.
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('keeps the generic message for a render crash', () => {
    render(
      <ErrorBoundary>
        <Boom error={new TypeError('x.toFixed is not a function')} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
