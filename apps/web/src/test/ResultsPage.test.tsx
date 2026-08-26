import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { ResultsPage } from '@/pages/ResultsPage';
import type { GameweekResult } from '@/lib/types';

const MOCK_LEAGUE = {
  slug: 'the-coupon',
  name: 'The Coupon',
  description: null,
  privacy: 'private',
  member_count: 2,
  max_members: null,
  created_at: '2026-01-01T00:00:00Z',
};

// Far-future exp so apiFetch's ensureFreshToken never tries to refresh.
const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const RESULTS: GameweekResult[] = [
  {
    gameweek_id: 'gw-2',
    starts_on: '2026-05-09',
    winner_names: ['Bob'],
    winner_points: 21,
    leg_count: 3,
    combined_odds: 12.5,
    all_won: false,
    picks_won: 2,
  },
  {
    gameweek_id: 'gw-1',
    starts_on: '2026-05-02',
    winner_names: ['Alice', 'Carol'],
    winner_points: 19,
    leg_count: 2,
    combined_odds: 5.89,
    all_won: true,
  },
];

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function stubFetch({ results = RESULTS }: { results?: GameweekResult[] } = {}) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/results')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(results) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

/** Reports the address a row tap landed on. */
function CouponProbe() {
  const { pathname, search } = useLocation();
  return <span data-testid="landed">{`${pathname}${search}`}</span>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/leagues/the-coupon/predictions/results']}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/predictions/results" element={<ResultsPage />} />
              <Route
                path="/leagues/:slug/predictions/coupon"
                element={<CouponProbe />}
              />
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

describe('ResultsPage', () => {
  it('lists settled gameweeks newest first with their winner and points', async () => {
    renderPage();
    const list = await screen.findByTestId('results-list');
    const rows = list.querySelectorAll('li');
    expect(rows[0].textContent).toContain('Bob won');
    expect(rows[0].textContent).toContain('21 pts');
    expect(rows[1].textContent).toContain('Alice, Carol tied');
  });

  it('shows the combined-coupon outcome badge', async () => {
    renderPage();
    const row = await screen.findByTestId('result-gw-1');
    expect(row.textContent).toContain('Coupon won');
    const other = await screen.findByTestId('result-gw-2');
    expect(other.textContent).toContain('Coupon lost');
  });

  it('opens that week\'s combined coupon on tap, at this league\'s address', async () => {
    renderPage();
    const row = await screen.findByTestId('result-gw-1');
    fireEvent.click(row);
    // A gameweek id is league-scoped, so the link has to carry the league too —
    // otherwise it resolves against whichever league the reader happens to be on.
    expect((await screen.findByTestId('landed')).textContent).toBe(
      '/leagues/the-coupon/predictions/coupon?gw=gw-1',
    );
  });

  it('explains an empty results list', async () => {
    stubFetch({ results: [] });
    renderPage();
    expect(await screen.findByText('No results yet')).toBeTruthy();
  });

  // ── Batch 29: league identity ─────────────────────────────────────────────

  it('names the bound league in the header', async () => {
    renderPage();
    await screen.findByTestId('results-list');
    expect(screen.getByText(/the coupon/i, { selector: 'p' })).toBeTruthy();
  });

  it('says how many legs landed, not only whether every one did (Batch 79)', async () => {
    renderPage();
    const row = await screen.findByTestId('result-gw-2');
    expect(row.textContent).toContain('2 of 3 landed');
  });

  it('renders the row unchanged against an API that does not send the count', async () => {
    renderPage();
    // `gw-1` carries no `picks_won`, the shape a deployed API predating Batch 79 sends.
    const row = await screen.findByTestId('result-gw-1');
    expect(row.textContent).toContain('Alice, Carol tied');
    expect(row.textContent).not.toContain('landed');
  });

  it('shows the no-league state and skips the results query for a member of no league', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByText("You're not in a league yet")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/results'))).toBe(false);
  });
});
