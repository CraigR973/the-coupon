import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider, useLeague } from '@/contexts/LeagueContext';
import { useRouteLeague } from '@/hooks/useRouteLeague';
import { DashboardPage } from '@/pages/DashboardPage';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';
import type { CrossLeagueSummary } from '@/lib/types';

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

const FAR_FUTURE = new Date(Date.now() + 3 * 86_400_000).toISOString();

const SUMMARY: CrossLeagueSummary = {
  avg_rank: 2.0,
  avg_rank_leagues: 2,
  total_points: 57,
  picks_played: 5,
  picks_won: 3,
  win_rate_pct: 60,
  leagues_count: 2,
  per_league: [
    {
      slug: 'the-coupon',
      name: 'The Coupon',
      member_count: 4,
      rank: 1,
      total_points: 38,
      picks_played: 3,
      picks_won: 2,
      current_round: {
        gameweek_id: 'gw-a',
        starts_on: '2026-08-22',
        status: 'open',
        locks_at_utc: FAR_FUTURE,
        picks_open_at_utc: null,
        leg_count: 3,
        combined_odds: 12.5,
        my_pick: {
          fixture_id: 'f-1',
          home: 'Arsenal',
          away: 'Chelsea',
          market: 'MATCH_ODDS',
          outcome: 'HOME',
          runner_name: 'Arsenal',
          odds: 1.9,
          status: 'pending',
        },
      },
    },
    {
      slug: 'work-league',
      name: 'Work League',
      member_count: 8,
      rank: 3,
      total_points: 19,
      picks_played: 2,
      picks_won: 1,
      current_round: {
        gameweek_id: 'gw-b',
        starts_on: '2026-08-22',
        status: 'open',
        locks_at_utc: FAR_FUTURE,
        picks_open_at_utc: null,
        leg_count: 2,
        combined_odds: 4.56,
        my_pick: null,
      },
    },
  ],
};

function stubAuth() {
  const store: Record<string, string> = {
    coupon_player: STORED_PLAYER,
    coupon_access: FAKE_JWT,
  };
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: vi.fn(),
  });
  return store;
}

function stubFetch(summary: CrossLeagueSummary | null = SUMMARY) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/me/cross-league-summary')) {
      return summary === null
        ? Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(summary) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(LEAGUES) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

/**
 * Reports where a tap landed, and which league the coupon screens are bound to.
 *
 * Stands in for a real coupon surface, `useRouteLeague` and all: since Batch 30 the
 * destination is what binds the league, so a probe that did not call it would not
 * be exercising the mechanism the card relies on.
 */
function CouponProbe() {
  const { pathname } = useLocation();
  const { slug } = useRouteLeague();
  const { activeSlug } = useLeague();
  return (
    <div>
      <span data-testid="pathname">{pathname}</span>
      <span data-testid="route-slug">{slug}</span>
      <span data-testid="active-slug">{activeSlug}</span>
    </div>
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/leagues/:slug/predictions" element={<CouponProbe />} />
              <Route path="/leagues/:slug/leaderboard" element={<CouponProbe />} />
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

describe('DashboardPage', () => {
  it('renders one card per league, not just the active one', async () => {
    renderPage();
    const cards = await screen.findByTestId('home-league-cards');
    expect(cards.querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByTestId('home-card-the-coupon')).toBeTruthy();
    expect(screen.getByTestId('home-card-work-league')).toBeTruthy();
  });

  it("carries each league's own pick and standing", async () => {
    renderPage();
    const mine = await screen.findByTestId('home-card-the-coupon');
    expect(mine.textContent).toContain('Arsenal');
    expect(mine.textContent).toContain('1.90');
    expect(mine.textContent).toContain('3-fold');
    expect(mine.textContent).toContain('#1');
    expect(mine.textContent).toContain('of 4');
    expect(mine.textContent).toContain('38 pts');

    // The second league is a different week entirely — no pick yet, its own table.
    const other = screen.getByTestId('home-card-work-league');
    expect(other.textContent).toContain('haven’t grabbed a selection');
    expect(other.textContent).toContain('#3');
    expect(other.textContent).toContain('19 pts');
  });

  it("opens that league's coupon in one tap, binding the coupon screens to it", async () => {
    renderPage();
    const card = await screen.findByTestId('home-card-work-league');
    fireEvent.click(card.querySelector('button')!);

    // Batch 30: the tap names the league in the URL, and the destination is what
    // binds the context — the card no longer has to do it on the way out.
    expect(screen.getByTestId('pathname').textContent).toBe('/leagues/work-league/predictions');
    expect(screen.getByTestId('route-slug').textContent).toBe('work-league');
    await waitFor(() => {
      expect(screen.getByTestId('active-slug').textContent).toBe('work-league');
    });
  });

  it("links each card's standings line to that league's table", async () => {
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(card.querySelector('a')?.getAttribute('href')).toBe('/leagues/the-coupon/leaderboard');
  });

  it('remembers the league a card opened, so a reload stays there', async () => {
    const store = stubAuth();
    stubFetch();
    renderPage();
    const card = await screen.findByTestId('home-card-work-league');
    fireEvent.click(card.querySelector('button')!);

    await waitFor(() => {
      expect(JSON.parse(store[LAST_VIEWED_LEAGUE_KEY]!).slug).toBe('work-league');
    });
  });

  it('counts down to the opening on a round whose picks have not opened (Batch 27)', async () => {
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...SUMMARY.per_league[1], // the league where the caller has no pick yet
          current_round: {
            ...SUMMARY.per_league[1].current_round!,
            status: 'scheduled',
            picks_open_at_utc: FAR_FUTURE,
          },
        },
      ],
    });
    renderPage();

    const card = await screen.findByTestId('home-card-work-league');
    expect(card.textContent).toContain('Picks haven’t opened yet');
    expect(card.textContent).toContain('Opens in');
    // Not "Locked" — the round is ahead of the member, not behind them.
    expect(card.textContent).not.toContain('Locked');
  });

  it('says when a league has published no coupon yet', async () => {
    stubFetch({
      ...SUMMARY,
      per_league: [{ ...SUMMARY.per_league[0], current_round: null }],
    });
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(card.textContent).toContain('No coupon published yet');
  });

  it('points a member with no leagues at the discovery page', async () => {
    stubFetch({
      avg_rank: null,
      avg_rank_leagues: 0,
      total_points: 0,
      picks_played: 0,
      picks_won: 0,
      win_rate_pct: null,
      leagues_count: 0,
      per_league: [],
    });
    renderPage();
    expect(await screen.findByText("You're not in a league yet")).toBeTruthy();
    expect(screen.getByRole('link', { name: /find a league/i }).getAttribute('href')).toBe(
      '/leagues/discover',
    );
  });
});
