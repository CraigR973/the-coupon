import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
  it('turns the cross-league season into a home summary', async () => {
    renderPage();
    const summary = await screen.findByTestId('home-season-summary');
    const hero = screen.getByTestId('home-hero');
    expect(hero.textContent).toContain('Hi Alice');
    expect(hero.textContent).toContain('2 leagues, one clear view of every round');

    expect(summary.textContent).toContain('Points57');
    expect(summary.textContent).toContain('Picks won3/5');
    expect(summary.textContent).toContain('Win rate60%');
  });

  it('puts the soonest independent league deadline in the hero', async () => {
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...SUMMARY.per_league[0],
          current_round: {
            ...SUMMARY.per_league[0].current_round!,
            my_pick: null,
            locks_at_utc: new Date(Date.now() + 2 * 86_400_000).toISOString(),
          },
        },
        {
          ...SUMMARY.per_league[1],
          current_round: {
            ...SUMMARY.per_league[1].current_round!,
            locks_at_utc: new Date(Date.now() + 86_400_000).toISOString(),
          },
        },
      ],
    });
    renderPage();
    const action = await screen.findByTestId('home-next-action');
    expect(action.textContent).toContain('2 leagues need a pick');
    expect(action.textContent).toContain('Work League locks in');
    expect(within(action).getByRole('link').getAttribute('href')).toBe(
      '/leagues/work-league/predictions',
    );
  });

  it('says when every open coupon already has the member’s pick', async () => {
    const ownPick = SUMMARY.per_league[0].current_round!.my_pick!;
    stubFetch({
      ...SUMMARY,
      per_league: [
        SUMMARY.per_league[0],
        {
          ...SUMMARY.per_league[1],
          current_round: { ...SUMMARY.per_league[1].current_round!, my_pick: ownPick },
        },
      ],
    });
    renderPage();
    expect((await screen.findByTestId('home-next-action')).textContent).toContain(
      'All open picks are in',
    );
  });

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
    // Batch 106: while picks are open the card carries this league's progress rather
    // than a fold that changes every time anybody in it claims anything.
    expect(mine.textContent).toContain('3 of 4 picked');
    expect(mine.textContent).not.toContain('3-fold');
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
    expect(screen.queryByTestId('home-season-summary')).toBeNull();
    expect(screen.getByRole('link', { name: /find a league/i }).getAttribute('href')).toBe(
      '/leagues/discover',
    );
  });
});

// ── Batch 79: the week just gone ──────────────────────────────────────────────

/** `SUMMARY`'s first league, with a settled week attached. */
function withResult(result: Partial<import('@/lib/types').LastResult> = {}): CrossLeagueSummary {
  const [first, ...rest] = SUMMARY.per_league;
  return {
    ...SUMMARY,
    per_league: [
      {
        ...first,
        last_result: {
          gameweek_id: 'gw-old',
          starts_on: '2026-08-22',
          number: 4,
          leg_count: 6,
          picks_won: 4,
          combined_odds: 22.5,
          all_won: false,
          my_pick: {
            fixture_id: 'f-9',
            home: 'Forfar',
            away: 'Brechin',
            market: 'MATCH_ODDS',
            outcome: 'HOME',
            runner_name: 'Forfar',
            odds: 3.5,
            status: 'won',
            points_awarded: 35,
          },
          rank_movement: 2,
          ...result,
        },
      },
      ...rest,
    ],
  };
}

describe('the week just gone', () => {
  it('says the pick came in, what it scored, and how many landed', async () => {
    stubFetch(withResult());
    renderPage();
    const panel = await screen.findByTestId('last-result');
    expect(panel.textContent).toContain('Gameweek 4');
    expect(panel.textContent).toContain('Your pick won');
    expect(panel.textContent).toContain('35 pts');
    expect(panel.textContent).toContain('4 of 6 picks landed');
  });

  it('reads a rise in words as well as in colour', async () => {
    stubFetch(withResult());
    renderPage();
    const movement = await screen.findByTestId('rank-movement');
    expect(movement.textContent).toContain('2');
    expect(movement.textContent).toContain('places gained');
  });

  it('leaves the movement out entirely when the member did not move', async () => {
    stubFetch(withResult({ rank_movement: 0 }));
    renderPage();
    await screen.findByTestId('last-result');
    expect(screen.queryByTestId('rank-movement')).toBeNull();
  });

  it('calls a void pick void rather than a loss', async () => {
    // A void fixture never ran. "Didn't come in" would be the same conflation the
    // leaderboard's two denominators exist to avoid.
    stubFetch(
      withResult({
        my_pick: {
          fixture_id: 'f-9',
          home: 'Forfar',
          away: 'Brechin',
          market: 'MATCH_ODDS',
          outcome: 'HOME',
          runner_name: 'Forfar',
          odds: 3.5,
          status: 'void',
          points_awarded: null,
        },
      }),
    );
    renderPage();
    const panel = await screen.findByTestId('last-result');
    expect(panel.textContent).toContain('Your pick was void');
    expect(panel.textContent).not.toContain('pts');
  });

  it('says so when the member did not pick that round', async () => {
    stubFetch(withResult({ my_pick: null }));
    renderPage();
    const panel = await screen.findByTestId('last-result');
    expect(panel.textContent).toContain('You didn’t pick this round');
  });

  it('renders exactly as it did before against an API that sends none of it', async () => {
    // Vercel deploys this app from `main` on merge while the API waits for /ship-prod.
    // For that window every Batch 79 field is absent, and the card must be untouched.
    stubFetch(SUMMARY);
    renderPage();
    await screen.findByTestId('home-card-the-coupon');
    expect(screen.queryByTestId('last-result')).toBeNull();
    expect(screen.queryByTestId('rank-movement')).toBeNull();
  });

  // ── Batch 81: the run reaches home ─────────────────────────────────────────

  it('draws the season\u2019s run of five inside the result panel', async () => {
    const [first, ...rest] = withResult().per_league;
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...first,
          recent_form: [
            { gameweek_id: 'g5', starts_on: '2026-08-22', status: 'won', points: 35 },
            { gameweek_id: 'g4', starts_on: '2026-08-15', status: 'void', points: 0 },
          ],
        },
        ...rest,
      ],
    });
    renderPage();
    const panel = await screen.findByTestId('last-result');
    // Oldest first on screen, whatever order the API sent.
    expect(within(panel).getByTestId('pick-form').textContent).toBe('VW35');
  });

  it('keeps the run out of the standings link\u2019s accessible name', async () => {
    // `PickFormLine` is a `role="img"` whose label spells the run out in words. Nested in
    // a link, that whole sentence is appended to the link's name — "Standings, #1 of 4,
    // 38 pts, last rounds oldest first: won 35 points, void".
    const [first, ...rest] = withResult().per_league;
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...first,
          recent_form: [
            { gameweek_id: 'g5', starts_on: '2026-08-22', status: 'won', points: 35 },
          ],
        },
        ...rest,
      ],
    });
    renderPage();
    await screen.findByTestId('pick-form');
    for (const link of screen.getAllByRole('link')) {
      expect(link.textContent ?? '').not.toContain('oldest first');
      expect(link.getAttribute('aria-label') ?? '').not.toContain('oldest first');
    }
  });

  it('draws no run at all against an API that sends none', async () => {
    stubFetch(withResult());
    renderPage();
    await screen.findByTestId('last-result');
    expect(screen.queryByTestId('pick-form')).toBeNull();
  });

  it('counts down to the next opening once the round has settled', async () => {
    const [first, ...rest] = withResult().per_league;
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...first,
          current_round: { ...first.current_round!, status: 'settled' },
          next_opens_at_utc: new Date(Date.now() + 2 * 86_400_000).toISOString(),
        },
        ...rest,
      ],
    });
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(card.textContent).toContain('Next opens in');
    expect(card.textContent).not.toContain('Settled');
  });
});

/**
 * Batch 106 — one explicit state per card, and one round per part of it.
 *
 * The defect these pin down was on the commonest Sunday shape in the product: a settled
 * round with a future opening printed last week's pick, fold and combined odds as the
 * card's body with `Next opens in 2d` beside them. Nothing said the two belonged to
 * different rounds, so the odds read as the price of the round being counted down to.
 */
describe('a league card’s state', () => {
  /** `SUMMARY`'s first league only, patched. */
  function onlyFirst(entry: Partial<CrossLeagueSummary['per_league'][number]>) {
    return {
      ...SUMMARY,
      leagues_count: 1,
      per_league: [{ ...SUMMARY.per_league[0], ...entry }],
    };
  }

  it('says a pick is required when the member holds none and the round is open', async () => {
    stubFetch();
    renderPage();
    const card = await screen.findByTestId('home-card-work-league');
    expect(within(card).getByText('Pick required')).toBeTruthy();
    expect(card.textContent).toContain('Locks in');
    expect(card.textContent).toContain('2 of 8 picked');
  });

  it('says the pick is submitted once the member is in', async () => {
    stubFetch();
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(within(card).getByText('Pick submitted')).toBeTruthy();
    expect(card.textContent).toContain('Locks in');
  });

  it('says a round is in progress once claiming has stopped', async () => {
    stubFetch(
      onlyFirst({
        current_round: {
          ...SUMMARY.per_league[0].current_round!,
          status: 'locked',
        },
      }),
    );
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(within(card).getByText('Round in progress')).toBeTruthy();
    // The fold is frozen now, so this is the one state where it is a fact about today.
    expect(card.textContent).toContain('3-fold');
    expect(card.textContent).toContain('12.50');
  });

  it('says a league is between rounds when its round has settled', async () => {
    stubFetch(
      onlyFirst({
        current_round: { ...SUMMARY.per_league[0].current_round!, status: 'settled' },
        next_opens_at_utc: FAR_FUTURE,
      }),
    );
    renderPage();
    const card = await screen.findByTestId('home-card-the-coupon');
    expect(within(card).getByText('Between rounds')).toBeTruthy();
  });

  /** The regression. A settled round, a future opening, and the two must not blur. */
  it('keeps a settled round’s pick and odds out of the primary card', async () => {
    stubFetch(
      onlyFirst({
        current_round: { ...SUMMARY.per_league[0].current_round!, status: 'settled' },
        next_opens_at_utc: FAR_FUTURE,
      }),
    );
    renderPage();

    const card = await screen.findByTestId('home-card-the-coupon');
    const primary = card.querySelector('button')!;
    expect(primary.textContent).toContain('Next opens in');
    // None of last round's figures may sit beside that clock.
    expect(primary.textContent).not.toContain('Arsenal');
    expect(primary.textContent).not.toContain('1.90');
    expect(primary.textContent).not.toContain('3-fold');
    expect(primary.textContent).not.toContain('12.50');
    expect(primary.textContent).not.toContain('picked');
  });

  it('moves that round’s pick, fold and odds under Last result instead', async () => {
    // No `last_result` in this response, which is the deploy-gap shape: an API that
    // predates Batch 79 sends none. The figures still have to land somewhere labelled.
    stubFetch(
      onlyFirst({
        current_round: { ...SUMMARY.per_league[0].current_round!, status: 'settled' },
        next_opens_at_utc: FAR_FUTURE,
      }),
    );
    renderPage();

    const panel = await screen.findByTestId('last-result');
    expect(panel.textContent).toContain('Last result');
    expect(panel.textContent).toContain('Arsenal');
    expect(panel.textContent).toContain('1.90');
    expect(panel.textContent).toContain('3-fold');
    expect(panel.textContent).toContain('12.50');
    // `current_round` cannot say how many legs landed, so that line is absent rather
    // than guessed at.
    expect(panel.textContent).not.toContain('landed');
  });

  it('names the last result’s own round, never the one being counted down to', async () => {
    stubFetch(withResult());
    renderPage();
    const panel = await screen.findByTestId('last-result');
    expect(panel.textContent).toContain('Last result · Gameweek 4');
  });

  it('reads each league’s window and progress from that league alone', async () => {
    // Two leagues, two different states, two different denominators. Nothing here may
    // come from a shared Saturday: one is open and short of picks, the other settled.
    stubFetch({
      ...SUMMARY,
      per_league: [
        {
          ...SUMMARY.per_league[0],
          current_round: { ...SUMMARY.per_league[0].current_round!, status: 'settled' },
          next_opens_at_utc: FAR_FUTURE,
        },
        SUMMARY.per_league[1],
      ],
    });
    renderPage();

    const settled = await screen.findByTestId('home-card-the-coupon');
    const open = screen.getByTestId('home-card-work-league');
    expect(within(settled).getByText('Between rounds')).toBeTruthy();
    expect(within(open).getByText('Pick required')).toBeTruthy();
    expect(settled.querySelector('button')!.textContent).toContain('Next opens in');
    expect(open.textContent).toContain('2 of 8 picked');
    expect(open.textContent).not.toContain('Next opens in');
  });
});

/**
 * Batch 106 — the hero's corner glows.
 *
 * They used to be blurred circles hung outside the hero's edges, and `overflow-hidden`
 * alone does not hold those: a filtered child gets its own rendering context and WebKit
 * lets it paint past the parent's rounded corners. They are backgrounds now, which every
 * engine clips to `border-radius` because there is no context to escape from. jsdom paints
 * nothing, so what is asserted is that arrangement rather than the pixels.
 */
describe('the hero’s corner glows', () => {
  it('paints both glows as one clipped layer’s background, not as filtered children', async () => {
    renderPage();
    const glows = await screen.findByTestId('home-hero-glows');
    expect(glows.className).toContain('rounded-2xl');
    expect(glows.className).toContain('overflow-hidden');
    expect(glows.className).toContain('clip-path');
    // No child element to escape the corners, and no blur filter to make one.
    expect(glows.children).toHaveLength(0);
    expect(glows.className).not.toContain('blur');

    const background = glows.style.backgroundImage;
    expect(background).toContain('--primary-glow');
    expect(background).toContain('--accent-glow');
    // Anchored past the two corners the review named, so the visible part of each glow
    // is its falloff rather than its hottest point.
    expect(background).toContain('at 108% -12%');
    expect(background).toContain('at -12% 112%');

    // And the layer is the hero's own child, so it can only ever clip to the hero.
    expect(screen.getByTestId('home-hero').contains(glows)).toBe(true);
  });
});
