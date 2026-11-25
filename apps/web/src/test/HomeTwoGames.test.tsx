import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { GameNavigationContext, HomeGameStatusContext } from '@/hooks/useGameIntents';
import { DashboardPage } from '@/pages/DashboardPage';
import type { CrossLeagueSummary, PerLeagueSummary } from '@/lib/types';
import type { GameCard, LeagueGames } from '@/lib/twoGameTypes';

/**
 * Batch 239 (owner, 24 Nov 2026): the old home page comes back for two-game leagues. The
 * hero and its season figures return, and each two-game league gets the old card — state,
 * position, form, last result — with its entries inside it, in the same list as every
 * legacy league. The legacy-only page is `DashboardPage.test.tsx`, unchanged.
 */
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
        number: 6,
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

// ── Batch 239: the old home page for two-game leagues ────────────────────────────────

const HOUR = 3_600_000;
const inHours = (hours: number) => new Date(Date.now() + hours * HOUR).toISOString();

function twoGameCard(
  week: { id: string; label: string },
  kind: GameCard['game_kind'],
  extra: Partial<GameCard> = {},
): GameCard {
  const destination = `/leagues/hibs-id/weeks/${week.id}/${kind}`;
  return {
    league_id: 'hibs-id',
    week_id: week.id,
    game_id: `${week.id}-${kind}`,
    game_kind: kind,
    week_label: week.label,
    week_number: '1',
    destination,
    opens_at: inHours(-48),
    locks_at: inHours(kind === 'fantasy' ? 25 : 27),
    entry_state: 'open',
    purpose: 'entry',
    archived: false,
    coverage_state: 'complete',
    result_version: 0,
    progress: {},
    result: { final: false },
    fee: {
      league_id: 'hibs-id',
      week_id: week.id,
      week_label: week.label,
      billing_starts_at: '2026-11-23T00:00:00Z',
      billing_ends_at: '2026-11-30T00:00:00Z',
      obligation_pence: 100,
      amount_owed_pence: 0,
      paid_through: true,
      pooled_credit_pence: 0,
      payment_url: null,
      destination: `${destination}#payment`,
      obligations: [],
    },
    ...extra,
  };
}

const THIS_WEEK = { id: 'w-now', label: '2026-11-28' };
const LAST_WEEK = { id: 'w-prev', label: '2026-11-21' };

/** This week open with no group pick and two fantasy slots; last week final. */
function hibsGames(extra: Partial<LeagueGames> = {}): LeagueGames {
  return {
    league_id: 'hibs-id',
    slug: 'hibs',
    name: '2-1 Hibs',
    two_games_enabled: true,
    suspended: false,
    server_now: new Date().toISOString(),
    games: [
      twoGameCard(LAST_WEEK, 'group', {
        opens_at: inHours(-200),
        locks_at: inHours(-140),
        entry_state: 'locked',
        purpose: 'results',
        archived: true,
        progress: { picked_count: 3, member_count: 3 },
        result: { status: 'won', final: true },
        my_entry: {
          league_id: 'hibs-id',
          week_id: LAST_WEEK.id,
          game_id: 'w-prev-group',
          game_kind: 'group',
          revision: 1,
          operation_id: null,
          pick: {
            id: 'g1',
            fixture_id: 'f1',
            player_id: 'p1',
            market: 'MATCH_ODDS',
            outcome: 'HOME',
            runner_name: 'Hibernian',
            revision: 1,
            operation_id: 'op-1',
            result: 'won',
          },
        },
      }),
      twoGameCard(LAST_WEEK, 'fantasy', {
        opens_at: inHours(-200),
        locks_at: inHours(-142),
        entry_state: 'locked',
        purpose: 'results',
        archived: true,
        progress: { slots_filled: 6 },
        result: {
          final: true,
          provisional: false,
          entry_result: 'scored',
          weekly_points: 22,
          won: 1,
          slots_filled: 6,
        },
      }),
      twoGameCard(THIS_WEEK, 'group', {
        progress: { picked_count: 1, member_count: 3 },
        result: { status: 'pending', final: false },
      }),
      twoGameCard(THIS_WEEK, 'fantasy', {
        progress: { slots_filled: 2 },
        result: { final: false, provisional: true, weekly_points: 0 },
      }),
    ],
    legacy_rounds: [],
    next_cursor: null,
    next_game_state: 'known',
    next_game_opens_at: null,
    season_stats: { total_points: 52, rank: 1 },
    weekly_form: [],
    ...extra,
  };
}

const HIBS_ENTRY: PerLeagueSummary = {
  slug: 'hibs',
  name: '2-1 Hibs',
  member_count: 3,
  rank: 1,
  total_points: 52,
  picks_played: 9,
  picks_won: 4,
  recent_form: [
    {
      gameweek_id: LAST_WEEK.id,
      starts_on: LAST_WEEK.label,
      status: 'scored',
      points: 22,
      format: 'two_game',
      game_kind: 'fantasy',
      slots_filled: 6,
      destination: '/leagues/hibs-id/weeks/w-prev/fantasy',
    },
  ],
  // The summary reads legacy rounds only: on a two-game league this is the last legacy
  // round, settled, and never this week.
  current_round: {
    gameweek_id: 'legacy-14',
    starts_on: '2026-11-14',
    number: 5,
    status: 'settled',
    locks_at_utc: '2026-11-14T14:30:00Z',
    picks_open_at_utc: null,
    leg_count: 3,
    combined_odds: 8.2,
    my_pick: null,
  },
  last_result: {
    gameweek_id: 'legacy-14',
    starts_on: '2026-11-14',
    number: 5,
    leg_count: 3,
    picks_won: 2,
    combined_odds: 8.2,
    all_won: false,
    my_pick: null,
  },
};

const HIBS_SUMMARY: CrossLeagueSummary = {
  total_points: 52,
  picks_played: 9,
  picks_won: 4,
  win_rate_pct: 44,
  leagues_count: 1,
  per_league: [HIBS_ENTRY],
};

function renderWithGames(
  games: LeagueGames[],
  status: Partial<{ isError: boolean; isLoading: boolean }> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <LeagueProvider>
            <HomeGameStatusContext.Provider
              value={{
                isError: false,
                isLoading: false,
                error: null,
                refetch: () => {},
                ...status,
              }}
            >
              <GameNavigationContext.Provider value={games}>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                </Routes>
              </GameNavigationContext.Provider>
            </HomeGameStatusContext.Provider>
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

describe('the old home page for two-game leagues (Batch 239)', () => {
  it('brings back the hero, its figures from the season table, for a two-game member', async () => {
    stubFetch(HIBS_SUMMARY);
    renderWithGames([hibsGames()]);
    const summary = await screen.findByTestId('home-season-summary');
    const hero = screen.getByTestId('home-hero');
    expect(hero).toHaveTextContent('Hi Alice');
    expect(summary).toHaveTextContent('Points52');
    expect(summary).toHaveTextContent('Picks won4/9');
    expect(summary).toHaveTextContent('Win rate44%');
    expect(screen.queryByRole('heading', { name: 'Hello, Alice' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Your games' })).toBeNull();
    // The fantasy entry locks first, so the hero's link opens it, not a legacy coupon.
    expect(within(hero).getByText('1 league needs a pick')).toBeInTheDocument();
    expect(within(hero).getByRole('link', { name: /2-1 Hibs locks in/ })).toHaveAttribute(
      'href',
      '/leagues/hibs-id/weeks/w-now/fantasy',
    );
  });

  it('puts the league’s entries inside its old card, with position, form and the last result', async () => {
    stubFetch(HIBS_SUMMARY);
    renderWithGames([hibsGames()]);
    const card = await screen.findByTestId('two-game-home');
    const scope = within(card);
    expect(scope.getByRole('heading', { name: '2-1 Hibs' })).toBeInTheDocument();
    expect(within(scope.getByTestId('home-state-hibs')).getByText('Pick required')).toBeVisible();
    expect(scope.getByRole('link', { name: 'Saturday Group · 28 Nov' })).toHaveAttribute(
      'href',
      '/leagues/hibs-id/weeks/w-now/group',
    );
    expect(scope.getByRole('link', { name: 'Fantasy · 28 Nov' })).toHaveAttribute(
      'href',
      '/leagues/hibs-id/weeks/w-now/fantasy',
    );
    expect(scope.getByText('Group pick needed')).toBeVisible();
    expect(scope.getByText(/^2 of 6 slots/)).toBeVisible();
    // Last week is final, and later than the legacy round the summary reports.
    const last = scope.getByTestId('last-result');
    expect(last).toHaveTextContent('Last result · Sat 21 Nov');
    expect(last).toHaveTextContent('Fantasy: 22 pts · 1 of 6 won');
    expect(last).toHaveTextContent('Group coupon won · Your pick: Hibernian');
    expect(within(last).getByTestId('pick-form')).toBeInTheDocument();
    const standings = scope.getByRole('link', { name: /Standings/ });
    expect(standings).toHaveAttribute('href', '/leagues/hibs/leaderboard');
    expect(standings).toHaveTextContent('#1of 3·52 pts');
    expect(scope.getByRole('link', { name: 'Game archive' })).toHaveAttribute(
      'href',
      '/leagues/hibs-id/games',
    );
    // The archived week is a result, not an entry.
    expect(scope.queryByRole('link', { name: 'Saturday Group · 21 Nov' })).toBeNull();
  });

  it('reports the last legacy round until the first two-game week is final', async () => {
    stubFetch(HIBS_SUMMARY);
    const league = hibsGames();
    renderWithGames([{ ...league, games: league.games.filter((card) => !card.archived) }]);
    const last = within(await screen.findByTestId('two-game-home')).getByTestId('last-result');
    expect(last).toHaveTextContent('2 of 3 picks landed');
    expect(last).not.toHaveTextContent('Fantasy:');
  });

  it('lists legacy and two-game leagues in one list, each in its old card, and counts both', async () => {
    stubFetch({
      ...SUMMARY,
      leagues_count: 3,
      per_league: [HIBS_ENTRY, ...SUMMARY.per_league],
    });
    renderWithGames([hibsGames()]);
    const list = await screen.findByTestId('home-league-cards');
    // The summary's order (by name), with 2-1 Hibs in it rather than in a list of its own.
    expect(list.children).toHaveLength(3);
    expect(list.children[0]).toContainElement(screen.getByTestId('two-game-home'));
    expect(within(list).getByTestId('home-card-the-coupon')).toBeInTheDocument();
    expect(within(list).getByTestId('home-card-work-league')).toBeInTheDocument();
    expect(screen.getByText('3 in play')).toBeInTheDocument();
    // Work League's open round has no pick, and 2-1 Hibs has two open entries: two leagues.
    expect(within(screen.getByTestId('home-hero')).getByText('2 leagues need a pick')).toBeVisible();
  });

  it('says the picks are in once every open entry has the member’s pick', async () => {
    stubFetch(HIBS_SUMMARY);
    const league = hibsGames();
    const [, , group, fantasy] = league.games;
    renderWithGames([
      {
        ...league,
        games: [
          ...league.games.slice(0, 2),
          { ...group!, my_entry: league.games[0]!.my_entry },
          { ...fantasy!, progress: { slots_filled: 6 } },
        ],
      },
    ]);
    const card = await screen.findByTestId('two-game-home');
    expect(within(card).getByText('Pick submitted')).toBeVisible();
    expect(within(card).getByText('Your pick: Hibernian')).toBeVisible();
    expect(within(screen.getByTestId('home-hero')).getByText('All open picks are in')).toBeVisible();
  });

  it('draws no league card until /me/games has said which leagues play two games', async () => {
    stubFetch(HIBS_SUMMARY);
    renderWithGames([], { isLoading: true });
    // Let the summary land: the cards and the hero's next action still wait for the games,
    // so 2-1 Hibs is never drawn as a legacy card for a moment.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByLabelText('Loading your leagues')).toBeInTheDocument();
    expect(screen.getByText(/all in one place/i)).toBeInTheDocument();
    expect(screen.queryByTestId('home-card-hibs')).toBeNull();
    expect(screen.queryByTestId('two-game-home')).toBeNull();
  });

  it('keeps the old legacy cards, with a notice, when /me/games fails', async () => {
    stubFetch();
    renderWithGames([], { isError: true });
    expect(await screen.findByTestId('home-card-the-coupon')).toBeInTheDocument();
    expect(screen.getByText("Couldn't load game status")).toBeVisible();
    expect(screen.getByTestId('home-hero')).toHaveTextContent('Hi Alice');
    expect(screen.queryByTestId('two-game-home')).toBeNull();
  });

  it('still draws a two-game card from its games when the summary fails', async () => {
    stubFetch(null);
    renderWithGames([hibsGames()]);
    expect(await screen.findByText("Couldn't load your leagues")).toBeVisible();
    const card = screen.getByTestId('two-game-home');
    expect(within(card).getByRole('link', { name: /Standings/ })).toHaveTextContent('#1·52 pts');
    expect(within(card).getByRole('link', { name: 'Fantasy · 28 Nov' })).toBeVisible();
  });
});

// ── Batch 243: one football week at a time, then the season ─────────────────────────

describe('Batch 243: Home shows this week, then the season', () => {
  beforeEach(() => {
    stubAuth();
    stubFetch(HIBS_SUMMARY);
  });

  it('names the week, counts down to its soonest lock and shows the £1 once', async () => {
    renderWithGames([hibsGames()]);
    const card = await screen.findByTestId('two-game-home');
    expect(within(card).getByText('This week · Sat 28 Nov')).toBeTruthy();
    expect(within(card).getByText('Fantasy locks in')).toBeTruthy();
    expect(within(card).getAllByText(/£1 paid/)).toHaveLength(1);
    expect(card.textContent).not.toMatch(/Entry open|Opening announced|Provisional|Paid through this week/);
  });

  it('offers one button for the most urgent thing', async () => {
    renderWithGames([hibsGames()]);
    const card = await screen.findByTestId('two-game-home');
    const action = within(card).getByRole('link', { name: 'Pick 4 more for Fantasy' });
    expect(action.getAttribute('href')).toBe('/leagues/hibs-id/weeks/w-now/fantasy');
  });

  it('asks for the week’s £1 first when it is owed', async () => {
    const owed = hibsGames();
    owed.games = owed.games.map((game) =>
      game.week_id === THIS_WEEK.id
        ? { ...game, fee: { ...game.fee, paid_through: false, amount_owed_pence: 100 } }
        : game,
    );
    renderWithGames([owed]);
    const card = await screen.findByTestId('two-game-home');
    expect(within(card).getByRole('link', { name: 'Pay £1 to play' }).getAttribute('href')).toBe(
      '/leagues/hibs-id/weeks/w-now/fantasy#payment',
    );
    expect(within(card).getByRole('link', { name: '£1 owed' })).toBeTruthy();
  });

  it('keeps this week on screen, and next week’s open Fantasy is one line', async () => {
    const next = { id: 'w-next', label: '2026-12-05' };
    const games = hibsGames();
    games.games = games.games.map((game) =>
      game.week_id === THIS_WEEK.id && game.game_kind === 'fantasy'
        ? {
            ...game,
            entry_state: 'locked',
            purpose: 'results',
            locks_at: inHours(-1),
            result: { final: false, provisional: true, weekly_points: 15 },
          }
        : game,
    );
    games.games.push(
      twoGameCard(next, 'fantasy', { opens_at: inHours(-1), locks_at: inHours(160) }),
    );
    renderWithGames([games]);
    const card = await screen.findByTestId('two-game-home');
    expect(within(card).getByText('This week · Sat 28 Nov')).toBeTruthy();
    expect(within(card).getByRole('link', { name: 'Fantasy · 28 Nov' })).toBeTruthy();
    expect(card.textContent).toContain('15 pts so far');
    const line = within(card).getByRole('link', { name: 'Fantasy · 5 Dec' });
    expect(line.closest('p')?.textContent).toContain('Next week’s Fantasy is open');
    expect(within(card).queryByRole('link', { name: 'Saturday Group · 5 Dec' })).toBeNull();
  });

  it('moves on to next week once this week’s results are final', async () => {
    const next = { id: 'w-next', label: '2026-12-05' };
    const games = hibsGames();
    games.games = games.games.map((game) =>
      game.week_id === THIS_WEEK.id
        ? {
            ...game,
            entry_state: 'locked',
            purpose: 'results',
            locks_at: inHours(-30),
            result: { ...game.result, final: true },
          }
        : game,
    );
    games.games.push(
      twoGameCard(next, 'fantasy', { opens_at: inHours(-40), locks_at: inHours(100) }),
      twoGameCard(next, 'group', {
        entry_state: 'not_open',
        purpose: 'upcoming',
        opens_at: inHours(90),
        locks_at: inHours(102),
      }),
    );
    renderWithGames([games]);
    const card = await screen.findByTestId('two-game-home');
    expect(within(card).getByText('This week · Sat 5 Dec')).toBeTruthy();
    expect(within(card).getByRole('link', { name: 'Fantasy · 5 Dec' })).toBeTruthy();
    expect(within(card).queryByRole('link', { name: 'Fantasy · 28 Nov' })).toBeNull();
    expect(card.textContent).toMatch(/Saturday Group.*Opens /s);
  });
});
