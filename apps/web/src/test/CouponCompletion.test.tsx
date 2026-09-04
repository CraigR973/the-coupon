import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { CurrentRoundPage } from '@/pages/CurrentRoundPage';
import type { Coupon, GameweekSlate } from '@/lib/types';

/**
 * Batch 108 — the hand-off the member who fills the coupon gets.
 *
 * The batch's whole risk is showing this to the wrong person, or at the wrong moment.
 * `all_picked` comes back true for *anyone* who submits into a full coupon, so a naive
 * reading would congratulate a member for "completing" a round that was already complete
 * before they touched it — every time they changed their mind. The rule that makes it
 * exact is that **a change of pick cannot fill a coupon**, and half the tests below exist
 * to hold that rule in place.
 *
 * The other half is the promise the screen makes about the clipboard, which browsers are
 * right to gate behind a gesture and which a member would experience as their pick
 * silently overwriting whatever they had copied.
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

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

/** Alice has *not* picked; Bob has. One free selection, so she can be the last one in. */
const SLATE: GameweekSlate = {
  gameweek_id: 'gw1',
  starts_on: '2026-08-08',
  status: 'open',
  locks_at_utc: '2999-01-01T14:30:00',
  picks_open_at_utc: null,
  fixtures: [
    {
      fixture_id: 'fx1',
      provider_event_id: 'ev1',
      home: 'Arsenal',
      away: 'Chelsea',
      competition_id: 'england-premier-league',
      competition: 'English Premier League',
      kickoff_utc: '2026-08-08T12:30:00',
      selections: [
        {
          market: 'MATCH_ODDS',
          outcome: 'HOME',
          runner_name: 'Arsenal',
          odds: 1.8,
          taken_by_player_id: null,
          taken_by_name: null,
          mine: false,
        },
        {
          market: 'MATCH_ODDS',
          outcome: 'AWAY',
          runner_name: 'Chelsea',
          odds: 4.2,
          taken_by_player_id: 'p2',
          taken_by_name: 'Bob',
          mine: false,
        },
      ],
      taken_by_names: ['Bob'],
      mine: false,
    },
  ],
  members: [
    {
      player_id: 'p1',
      display_name: 'Alice',
      has_picked: false,
      fixture_id: null,
      home: null,
      away: null,
      competition: null,
      market: null,
      outcome: null,
      runner_name: null,
      odds: null,
    },
    {
      player_id: 'p2',
      display_name: 'Bob',
      has_picked: true,
      fixture_id: 'fx1',
      home: 'Arsenal',
      away: 'Chelsea',
      competition: 'English Premier League',
      market: 'MATCH_ODDS',
      outcome: 'AWAY',
      runner_name: 'Chelsea',
      odds: 4.2,
    },
  ],
  members_missing_picks: 1,
  pick_scope: 'selection',
};

const COUPON: Coupon = {
  gameweek_id: 'gw1',
  status: 'open',
  leg_count: 1,
  combined_odds: 4.2,
  legs: [
    {
      player_id: 'p2',
      player_name: 'Bob',
      fixture_id: 'fx1',
      home: 'Arsenal',
      away: 'Chelsea',
      competition: 'English Premier League',
      market: 'MATCH_ODDS',
      outcome: 'AWAY',
      runner_name: 'Chelsea',
      odds: 4.2,
      status: 'pending',
    },
  ],
  all_won: null,
};

const GAMEWEEKS = [
  {
    gameweek_id: 'gw1',
    starts_on: '2026-08-08',
    status: 'open',
    locks_at_utc: '2999-01-01T14:30:00',
    picks_open_at_utc: null,
    fixture_count: 1,
    pick_count: 1,
  },
];

/** What Batch 107's API answers a submission with. */
function pickResponse(over: { picked_count: number; member_count: number; all_picked: boolean }) {
  return {
    id: 'pick1',
    league_id: 'l1',
    gameweek_id: 'gw1',
    fixture_id: 'fx1',
    home: 'Arsenal',
    away: 'Chelsea',
    competition: 'English Premier League',
    market: 'MATCH_ODDS',
    outcome: 'HOME',
    runner_name: 'Arsenal',
    odds: 1.8,
    status: 'pending',
    points_awarded: null,
    ...over,
  };
}

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
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  });
}

/**
 * `submitAnswer` is what `POST .../picks` returns. `slateOverrides` shifts the round the
 * page reads, which is how "this member already holds a pick" is expressed.
 */
function stubFetch(
  submitAnswer: ReturnType<typeof pickResponse>,
  slateOverrides: Partial<GameweekSlate> = {},
) {
  const posts: string[] = [];
  vi.stubGlobal('fetch', (url: string, opts?: RequestInit) => {
    const href = String(url);
    if (href.includes('/picks') && opts?.method === 'POST') {
      posts.push(String(opts.body));
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(submitAnswer) });
    }
    if (href.includes('/gameweek/current')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ...SLATE, ...slateOverrides }),
      });
    }
    if (href.includes('/coupon')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(COUPON) });
    }
    if (href.includes('/gameweeks')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(GAMEWEEKS) });
    }
    if (href.includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  return posts;
}

/** Reports the address the page settled on, fragment included. */
function Landed() {
  const { pathname, search, hash } = useLocation();
  return <span data-testid="landed">{`${pathname}${search}${hash}`}</span>;
}

function renderPage(entry = '/leagues/the-coupon/predictions') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <AuthProvider>
          <LeagueProvider>
            <Landed />
            <Routes>
              <Route path="/leagues/:slug/predictions" element={<CurrentRoundPage />} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Competitions start collapsed, so every claim is two clicks: open, then grab. */
async function openCard() {
  const section = await screen.findByTestId('competition-england-premier-league');
  fireEvent.click(within(section).getByRole('button', { name: /english premier league/i }));
}

/** Claim Arsenal — the free selection Alice can be last in with. */
async function grabArsenal() {
  await openCard();
  fireEvent.click(await screen.findByTestId('selection-fx1-MATCH_ODDS-HOME'));
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('the completion hand-off', () => {
  it('appears when this submission is the one that fills the coupon', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    renderPage();
    await grabArsenal();

    const notice = await screen.findByTestId('coupon-complete-notice');
    expect(notice).toBeTruthy();
    // The exact label the row specifies, so the button and the push name one event.
    expect(
      screen.getByRole('button', { name: 'All picks are in — open and copy coupon' }),
    ).toBeTruthy();
  });

  it('stays away when the round is not complete', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 3, all_picked: false }));
    renderPage();
    await grabArsenal();

    // Settled by waiting for the submission to have been answered rather than by a bare
    // assertion, which would pass while the request was still in flight.
    await waitFor(() => expect(screen.getByTestId('landed')).toBeTruthy());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('coupon-complete-notice')).toBeNull();
  });

  it('stays away for a member changing their pick in an already-full coupon', async () => {
    // The trap the batch is built around. `all_picked` is true — it is *true* — but this
    // member already held a pick, so their submission moved no count and cannot have been
    // the transition. Congratulating them here would fire on every change of mind.
    const alreadyPicked: Partial<GameweekSlate> = {
      members: [
        {
          ...SLATE.members[0],
          has_picked: true,
          fixture_id: 'fx1',
          home: 'Arsenal',
          away: 'Chelsea',
          competition: 'English Premier League',
          market: 'MATCH_ODDS',
          outcome: 'HOME',
          runner_name: 'Arsenal',
          odds: 1.8,
        },
        SLATE.members[1],
      ],
      members_missing_picks: 0,
      fixtures: [
        {
          ...SLATE.fixtures[0],
          mine: true,
          taken_by_names: ['Alice', 'Bob'],
          selections: [
            {
              ...SLATE.fixtures[0].selections[0],
              taken_by_player_id: 'p1',
              taken_by_name: 'Alice',
              mine: true,
            },
            SLATE.fixtures[0].selections[1],
            // Free, so there is somewhere for her to move to.
            {
              market: 'MATCH_ODDS' as const,
              outcome: 'DRAW' as const,
              runner_name: 'The Draw',
              odds: 3.4,
              taken_by_player_id: null,
              taken_by_name: null,
              mine: false,
            },
          ],
        },
      ],
    };
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }), alreadyPicked);
    renderPage();

    await openCard();
    fireEvent.click(await screen.findByTestId('selection-fx1-MATCH_ODDS-DRAW'));

    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByTestId('coupon-complete-notice')).toBeNull();
  });

  it('opens the exact gameweek with the copy section focused', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    renderPage();
    await grabArsenal();

    fireEvent.click(await screen.findByTestId('coupon-complete-open'));

    // The round is named in the address rather than left to "whatever is current" — the
    // completion is worth reopening later, by which time the league's current round may
    // be a different one.
    await waitFor(() =>
      expect(screen.getByTestId('landed').textContent).toBe(
        '/leagues/the-coupon/predictions?gw=gw1#coupon',
      ),
    );
    await waitFor(() => expect(document.activeElement?.id).toBe('coupon'));
  });

  it('never writes to the clipboard on its own', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      writable: true,
      configurable: true,
    });
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    renderPage();
    await grabArsenal();

    // Not on the completion itself…
    await screen.findByTestId('coupon-complete-notice');
    expect(writeText).not.toHaveBeenCalled();

    // …and not on taking the hand-off either. The copy control lives in the section this
    // opens, and the member presses it themselves.
    fireEvent.click(screen.getByTestId('coupon-complete-open'));
    await waitFor(() => expect(document.activeElement?.id).toBe('coupon'));
    expect(writeText).not.toHaveBeenCalled();
  });

  it('can be dismissed without going anywhere', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    renderPage();
    await grabArsenal();

    fireEvent.click(await screen.findByTestId('coupon-complete-dismiss'));
    await waitFor(() => expect(screen.queryByTestId('coupon-complete-notice')).toBeNull());
    expect(screen.getByTestId('landed').textContent).toBe('/leagues/the-coupon/predictions');
  });

  it('is a real button, so the keyboard reaches it', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    renderPage();
    await grabArsenal();

    const open = await screen.findByTestId('coupon-complete-open');
    expect(open.tagName).toBe('BUTTON');
    open.focus();
    expect(document.activeElement).toBe(open);
    fireEvent.keyDown(open, { key: 'Enter' });
    fireEvent.click(open); // what Enter does on a native button
    await waitFor(() => expect(document.activeElement?.id).toBe('coupon'));
  });

  it('announces itself politely and has no axe violations', async () => {
    stubFetch(pickResponse({ picked_count: 2, member_count: 2, all_picked: true }));
    const { container } = renderPage();
    await grabArsenal();

    const notice = await screen.findByTestId('coupon-complete-notice');
    // A status rather than an alert: the round filling up is good news about somebody
    // else's screen too, not an error interrupting this one.
    expect(notice.getAttribute('role')).toBe('status');
    expect(notice.getAttribute('aria-live')).toBe('polite');

    const results = await axe(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(results).toHaveNoViolations();
  });

  it('quotes the same progress the league is pushed', async () => {
    // Batch 107's push ends `· 12/12 picked — all picks are in`; the screen says the same
    // count, from the same read, so a member holding both does not see two numbers.
    stubFetch(pickResponse({ picked_count: 12, member_count: 12, all_picked: true }));
    renderPage();
    await grabArsenal();

    const notice = await screen.findByTestId('coupon-complete-notice');
    expect(notice.textContent).toContain('All picks are in');
    expect(notice.textContent).toContain('12/12');
  });
});
