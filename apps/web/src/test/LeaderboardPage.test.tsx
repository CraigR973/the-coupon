import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { LeaderboardPage } from '@/pages/LeaderboardPage';
import { buildStandingsShareText } from '@/lib/share';
import type { SeasonSummary, Standing } from '@/lib/types';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/**
 * Batch 96 — the standings archive on the leaderboard.
 *
 * The table is bounded by season now, so this screen has two jobs it did not have: say
 * which season is on it, and let a member open a past one. The third job is the one that
 * is easy to forget — behave exactly as before against an API that has never heard of a
 * season, because close-out deploys this app to members while the API waits for
 * `/ship-prod`.
 */

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

const SEASONS: SeasonSummary[] = [
  { season: 2026, label: '2026/27', is_current: true, rounds_settled: 2 },
  { season: 2025, label: '2025/26', is_current: false, rounds_settled: 38 },
];

function standing(name: string, points: number, rank: number): Standing {
  return {
    player_id: `p-${name}`,
    display_name: name,
    total_points: points,
    picks_played: 4,
    picks_won: 2,
    rank,
  };
}

const THIS_SEASON: Standing[] = [standing('Alice', 34, 1), standing('Bob', 12, 2)];
const LAST_SEASON: Standing[] = [standing('Carol', 480, 1), standing('Alice', 260, 2)];

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

/** Every request the page makes, newest last — the assertion surface for the season. */
let requested: string[] = [];

function stubFetch({ seasonsStatus = 200 }: { seasonsStatus?: number } = {}) {
  requested = [];
  vi.stubGlobal('fetch', (url: string) => {
    const address = String(url);
    requested.push(address);
    const ok = (body: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

    // `/leagues/mine` first: LeagueProvider dereferences `leagues[0].slug` and throws
    // before the page under test mounts if it is not stubbed.
    if (address.includes('/leagues/mine')) return ok([MOCK_LEAGUE]);
    if (address.includes('/seasons')) {
      if (seasonsStatus !== 200) {
        return Promise.resolve({
          ok: false,
          status: seasonsStatus,
          json: () => Promise.resolve({ detail: 'Not Found' }),
        });
      }
      return ok(SEASONS);
    }
    if (address.includes('/standings')) {
      return ok(address.includes('season=2025') ? LAST_SEASON : THIS_SEASON);
    }
    if (address.includes('/leagues/the-coupon')) return ok(MOCK_LEAGUE);
    return ok({});
  });
}

function renderPage(initial = '/leagues/the-coupon/leaderboard') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/leaderboard" element={<LeaderboardPage />} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LeaderboardPage — the season archive', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    stubAuth();
  });

  it('opens on the season being played, and asks for it without a query string', async () => {
    stubFetch();
    renderPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('2026/27 standings')).toBeInTheDocument();

    const standingsCalls = requested.filter((url) => url.includes('/standings'));
    expect(standingsCalls).toHaveLength(1);
    expect(standingsCalls[0]).not.toContain('season=');
  });

  it('copies the current table in the existing plain-text convention', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    stubFetch();
    renderPage();

    await screen.findByText('Alice');
    await userEvent.click(screen.getByRole('button', { name: 'Copy standings' }));

    const expected = buildStandingsShareText(
      'The Coupon',
      '2026/27 standings',
      THIS_SEASON,
    );
    expect(expected).toBe(
      [
        'The Coupon: The Coupon — 2026/27 standings',
        '',
        '#1 Alice - 34 pts - 2/4 picks won',
        '#2 Bob - 12 pts - 2/4 picks won',
      ].join('\n'),
    );
    expect(writeText).toHaveBeenCalledWith(expected);
  });

  it('opens a past season, and says the table is finished', async () => {
    stubFetch();
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId('season-strip');
    await user.click(screen.getByRole('button', { name: 'Show the 2025/26 season' }));

    expect(await screen.findByText('Carol')).toBeInTheDocument();
    expect(requested.some((url) => url.includes('/standings?season=2025'))).toBe(true);
    expect(screen.getByText(/A completed season/)).toBeInTheDocument();
    expect(screen.getByText('2025/26 standings')).toBeInTheDocument();
    // The season is named for a screen reader as an action, not as a bare year, and the
    // current entry's "now" badge does not run into its label.
    expect(
      screen.getByRole('button', { name: 'Show 2026/27, the season being played' }),
    ).toBeInTheDocument();
  });

  it('reads the season straight out of the address, so an archived link is shareable', async () => {
    stubFetch();
    renderPage('/leagues/the-coupon/leaderboard?season=2025');

    expect(await screen.findByText('Carol')).toBeInTheDocument();
    expect(requested.some((url) => url.includes('/standings?season=2025'))).toBe(true);
  });

  it('copies only the archived table and label when that is the screen being viewed', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    stubFetch();
    renderPage('/leagues/the-coupon/leaderboard?season=2025');

    await screen.findByText('Carol');
    await userEvent.click(screen.getByRole('button', { name: 'Copy standings' }));

    expect(writeText).toHaveBeenCalledWith(
      buildStandingsShareText('The Coupon', '2025/26 standings', LAST_SEASON),
    );
    expect(writeText.mock.calls[0][0]).not.toContain('Bob');
  });

  it('draws the table as before when the API has no seasons endpoint yet', async () => {
    // The deploy gap: Vercel releases this app on merge, the API waits for `/ship-prod`.
    // A 404 on `/seasons` must cost the member nothing — no strip, no error, no blank
    // screen, and the standings request still goes out.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    stubFetch({ seasonsStatus: 404 });
    renderPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    await waitFor(() => expect(requested.some((url) => url.includes('/seasons'))).toBe(true));
    expect(screen.queryByTestId('season-strip')).not.toBeInTheDocument();
    expect(screen.queryByText(/Couldn’t load standings/)).not.toBeInTheDocument();
    expect(screen.getByText('Season standings')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Copy standings' }));
    expect(writeText).toHaveBeenCalledWith(
      buildStandingsShareText('The Coupon', 'Season standings', THIS_SEASON),
    );
  });

  it('hides the strip for a league that has only ever played one season', async () => {
    requested = [];
    vi.stubGlobal('fetch', (url: string) => {
      const address = String(url);
      requested.push(address);
      const ok = (body: unknown) =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      if (address.includes('/leagues/mine')) return ok([MOCK_LEAGUE]);
      if (address.includes('/seasons')) return ok([SEASONS[0]]);
      if (address.includes('/standings')) return ok(THIS_SEASON);
      return ok(MOCK_LEAGUE);
    });
    renderPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(screen.queryByTestId('season-strip')).not.toBeInTheDocument();
  });
});
