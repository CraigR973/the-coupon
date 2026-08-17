import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { PredictionsRedirect } from '@/components/PredictionsRedirect';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const LEAGUES = [
  {
    slug: 'the-coupon',
    name: 'The Coupon',
    description: null,
    privacy: 'private',
    member_count: 4,
    max_members: null,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    slug: 'work-league',
    name: 'Work League',
    description: null,
    privacy: 'private',
    member_count: 8,
    max_members: null,
    created_at: '2026-01-01T00:00:00Z',
  },
];

/** Backs `localStorage` with a real store so the recency key can be seeded. */
function stubAuth(seed: Record<string, string> = {}): Record<string, string> {
  const store: Record<string, string> = {
    coupon_player: STORED_PLAYER,
    coupon_access: FAKE_JWT,
    ...seed,
  };
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  });
  return store;
}

function stubFetch(leagues: unknown[] = LEAGUES) {
  vi.stubGlobal('fetch', () =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(leagues) }),
  );
}

/** Reports the address the redirect settled on. */
function Landing() {
  const { pathname, search } = useLocation();
  return <span data-testid="landed">{`${pathname}${search}`}</span>;
}

function renderAt(entry: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route
                path="/predictions"
                element={
                  <PredictionsRedirect section="">
                    <span data-testid="rendered-in-place">Your pick</span>
                  </PredictionsRedirect>
                }
              />
              <Route
                path="/predictions/coupon"
                element={
                  <PredictionsRedirect section="/coupon">
                    <span data-testid="rendered-in-place">Combined coupon</span>
                  </PredictionsRedirect>
                }
              />
              <Route path="/leagues/:slug/predictions" element={<Landing />} />
              <Route path="/leagues/:slug/predictions/coupon" element={<Landing />} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
  stubFetch();
});

describe('PredictionsRedirect', () => {
  it('sends a slug-less coupon path to the bound league', async () => {
    stubAuth({
      [LAST_VIEWED_LEAGUE_KEY]: JSON.stringify({ slug: 'work-league', name: 'Work League' }),
    });
    renderAt('/predictions');

    expect((await screen.findByTestId('landed')).textContent).toBe(
      '/leagues/work-league/predictions',
    );
  });

  it('carries the gameweek through, so an old ?gw= link still opens that week', async () => {
    stubAuth({
      [LAST_VIEWED_LEAGUE_KEY]: JSON.stringify({ slug: 'work-league', name: 'Work League' }),
    });
    renderAt('/predictions/coupon?gw=gw-7');

    expect((await screen.findByTestId('landed')).textContent).toBe(
      '/leagues/work-league/predictions/coupon?gw=gw-7',
    );
  });

  it('waits for the leagues rather than bouncing through the default slug', () => {
    // The fetch never settles: nothing should have been decided yet.
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    renderAt('/predictions');

    expect(screen.getByLabelText('Loading page')).toBeTruthy();
    expect(screen.queryByTestId('landed')).toBeNull();
  });

  it('leaves a member of no league where they are, rather than at a league they do not play', async () => {
    stubFetch([]);
    renderAt('/predictions');

    expect(await screen.findByTestId('rendered-in-place')).toBeTruthy();
    expect(screen.queryByTestId('landed')).toBeNull();
  });
});
