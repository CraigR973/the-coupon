import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { ResultsPage } from '@/pages/ResultsPage';
import type { GameweekResult, SeasonSummary } from '@/lib/types';

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
    season_week: '45b',
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

const SEASONS: SeasonSummary[] = [
  { season: 2026, label: '2026/27', is_current: true, rounds_settled: 1 },
  { season: 2025, label: '2025/26', is_current: false, rounds_settled: 2 },
];

let requested: string[] = [];

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

function stubFetch({
  results = RESULTS,
  seasons = [],
}: { results?: GameweekResult[]; seasons?: SeasonSummary[] } = {}) {
  requested = [];
  vi.stubGlobal('fetch', (url: string) => {
    requested.push(String(url));
    if (String(url).includes('/results')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(results) });
    }
    if (String(url).includes('/seasons')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(seasons) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

/** Reports the address a row tap landed on, fragment included. */
function CouponProbe() {
  const { pathname, search, hash } = useLocation();
  return <span data-testid="landed">{`${pathname}${search}${hash}`}</span>;
}

function renderPage(initial = '/leagues/the-coupon/predictions/results') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/predictions/results" element={<ResultsPage />} />
              <Route path="/leagues/:slug/predictions" element={<CouponProbe />} />
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
  it('shows only the current season and filters an older API that ignores the query', async () => {
    stubFetch({
      seasons: SEASONS,
      results: [{ ...RESULTS[0], gameweek_id: 'gw-current', starts_on: '2026-07-01' }, ...RESULTS],
    });
    renderPage();

    expect(await screen.findByTestId('result-gw-current')).toBeInTheDocument();
    expect(screen.queryByTestId('result-gw-2')).toBeNull();
    expect(screen.getByTestId('season-strip')).toBeInTheDocument();
    expect(requested.filter((url) => url.includes('/results'))[0]).not.toContain('season=');
  });

  it('opens an archived season from the selector and from a direct link', async () => {
    stubFetch({
      seasons: SEASONS,
      results: [{ ...RESULTS[0], gameweek_id: 'gw-current', starts_on: '2026-07-01' }, ...RESULTS],
    });
    renderPage();
    await screen.findByTestId('result-gw-current');
    fireEvent.click(screen.getByRole('button', { name: 'Show the 2025/26 season' }));
    expect(await screen.findByTestId('result-gw-2')).toBeInTheDocument();
    expect(screen.queryByTestId('result-gw-current')).toBeNull();
    expect(requested.some((url) => url.includes('/results?season=2025'))).toBe(true);

    renderPage('/leagues/the-coupon/predictions/results?season=2025');
    await waitFor(() => expect(screen.getAllByTestId('result-gw-2')).toHaveLength(2));
  });

  it('lists settled gameweeks newest first with their winner and points', async () => {
    renderPage();
    const list = await screen.findByTestId('results-list');
    const rows = list.querySelectorAll('li');
    expect(rows[0].textContent).toContain('Bob won');
    expect(rows[0].textContent).toContain('21 pts');
    expect(rows[1].textContent).toContain('Alice, Carol tied');
    expect(rows[0].textContent).toContain('Gameweek 45b');
  });

  it('shows the combined-coupon outcome badge', async () => {
    renderPage();
    const row = await screen.findByTestId('result-gw-1');
    expect(row.textContent).toContain('Coupon won');
    const other = await screen.findByTestId('result-gw-2');
    expect(other.textContent).toContain('Coupon lost');
  });

  it('marks an astronomical combined price instead of printing false precision', async () => {
    stubFetch({
      results: [{ ...RESULTS[0], combined_odds: 1.1399982514331652e26 }],
    });
    renderPage();
    const row = await screen.findByTestId('result-gw-2');
    expect(row.textContent).toContain('1,000,000+');
    expect(row.textContent).not.toContain('e+');
  });

  it('opens that week\'s combined coupon on tap, at this league\'s address', async () => {
    renderPage();
    const row = await screen.findByTestId('result-gw-1');
    fireEvent.click(row);
    // A gameweek id is league-scoped, so the link has to carry the league too —
    // otherwise it resolves against whichever league the reader happens to be on.
    // Batch 105 moved the destination into the round itself, at its copy section.
    expect((await screen.findByTestId('landed')).textContent).toBe(
      '/leagues/the-coupon/predictions?gw=gw-1#coupon',
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

  it('says how many legs were void, since the price beside it leaves them out (Batch 186)', async () => {
    stubFetch({ results: [{ ...RESULTS[0], leg_count: 4, void_leg_count: 2, combined_odds: 7.13 }] });
    renderPage();
    const row = await screen.findByTestId('result-gw-2');
    expect(row.textContent).toContain('2 of 4 landed·2 void');
    expect(row.textContent).toContain('7.13');
  });

  it('says nothing about voids when there were none, or the API does not say', async () => {
    renderPage();
    // Neither row carries `void_leg_count`: one predates it, one simply had no voids.
    const list = await screen.findByTestId('results-list');
    expect(list.textContent).not.toContain('void');
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
