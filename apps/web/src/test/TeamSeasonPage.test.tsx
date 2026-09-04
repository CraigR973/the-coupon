import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import { AuthProvider } from '@/contexts/AuthContext';
import { TeamSeasonPage } from '@/pages/TeamSeasonPage';
import type { MatchState, TeamSeason, TeamSeasonMatch } from '@/lib/types';

/**
 * A club's whole season, over Batch 110's contract (Batch 111).
 *
 * The screen that replaced the table's hidden form disclosure. What is worth testing at
 * this level rather than in `teamSeason.test.ts` is what a *reader* can tell apart: a
 * fixture from an abandoned match, a win from a defeat, and which match is next — none
 * of which a bare row of numbers answers.
 */

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function match(
  id: string,
  day: string,
  state: MatchState,
  extra: Partial<TeamSeasonMatch> = {},
): TeamSeasonMatch {
  const played = state === 'finished';
  return {
    match_id: id,
    kickoff_utc: `${day}T14:00:00Z`,
    opponent: 'Chelsea FC',
    opponent_team_id: 't-chelsea',
    home: true,
    state,
    status: played ? 'FT' : '',
    goals_for: played ? 2 : null,
    goals_against: played ? 1 : null,
    result: played ? 'W' : null,
    ...extra,
  };
}

const SEASON: TeamSeason = {
  team_id: 't-arsenal',
  team: 'Arsenal FC',
  competition_id: 'england-premier-league',
  competition: 'England - English Premier League',
  season: 2026,
  matches: [
    match('r1', '2026-08-08', 'finished', { opponent: 'Everton FC', result: 'W' }),
    match('r2', '2026-08-15', 'finished', {
      opponent: 'Liverpool FC',
      home: false,
      goals_for: 0,
      goals_against: 3,
      result: 'L',
    }),
    match('pp', '2026-08-22', 'postponed', { opponent: 'Tottenham Hotspur FC', status: 'PP' }),
    match('f1', '2026-08-29', 'scheduled', { opponent: 'Brighton & Hove Albion FC' }),
    match('f2', '2026-09-05', 'scheduled', { opponent: 'Wolverhampton Wanderers FC' }),
  ],
};

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

function stubFetch(season: TeamSeason | null = SEASON, status = 200) {
  const mock = vi.fn((url: string) => {
    if (String(url).includes('/football/teams/')) {
      if (season === null) {
        return Promise.resolve({
          ok: false,
          status,
          json: () => Promise.resolve({ detail: 'Team not found' }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(season) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

function renderPage(path = '/football/teams/t-arsenal?competition=england-premier-league&season=2026') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path="/football/teams/:teamId" element={<TeamSeasonPage />} />
          </Routes>
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

describe('TeamSeasonPage — the season a link names', () => {
  it('asks for the club, competition and season in the address', async () => {
    const fetchMock = stubFetch();
    renderPage();
    await screen.findByTestId('team-season');

    const call = fetchMock.mock.calls.map(([url]) => String(url)).find((u) => u.includes('/teams/'));
    expect(call).toContain('/api/v1/football/teams/t-arsenal/season');
    expect(call).toContain('competition=england-premier-league');
    expect(call).toContain('season=2026');
  });

  it('names the club, the competition and the season on the page', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    expect(screen.getByRole('heading', { name: 'Arsenal FC' })).toBeTruthy();
    // The competition is named once, in the header, rather than repeated down a list
    // that is by definition all one competition.
    expect(screen.getByText(/England - English Premier League · 2026\/27/)).toBeTruthy();
  });

  it('shows the complete season — every result and every remaining fixture', async () => {
    renderPage();
    const season = await screen.findByTestId('team-season');

    for (const id of ['r1', 'r2', 'pp', 'f1', 'f2']) {
      expect(within(season).getByTestId(`team-match-${id}`)).toBeTruthy();
    }
  });

  it('reads results newest first and fixtures chronologically', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const results = within(screen.getByTestId('team-season-results'))
      .getAllByRole('listitem')
      .map((li) => li.getAttribute('data-testid'));
    const fixtures = within(screen.getByTestId('team-season-fixtures'))
      .getAllByRole('listitem')
      .map((li) => li.getAttribute('data-testid'));

    expect(results).toEqual(['team-match-r2', 'team-match-r1']);
    expect(fixtures).toEqual(['team-match-pp', 'team-match-f1', 'team-match-f2']);
  });

  it('offers the way back to the division it was opened from', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const back = screen.getByTestId('back-to-table');
    expect(back.getAttribute('href')).toBe(
      '/football?competition=england-premier-league&season=2026',
    );
  });
});

describe('TeamSeasonPage — telling one row from another', () => {
  it('gives a result its score, its orientation and its outcome', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const win = screen.getByTestId('team-match-r1');
    expect(win.textContent).toContain('Everton FC');
    expect(win.textContent).toContain('2–1');
    expect(within(win).getByText(/won 2–1/)).toBeTruthy();
    expect(within(win).getByText('home to')).toBeTruthy();

    const loss = screen.getByTestId('team-match-r2');
    expect(within(loss).getByText(/lost 0–3/)).toBeTruthy();
    expect(within(loss).getByText('away to')).toBeTruthy();
  });

  it('gives a fixture no score rather than a nil-nil', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const fixture = screen.getByTestId('team-match-f1');
    expect(fixture.textContent).not.toMatch(/\d+–\d+/);
    expect(fixture.textContent).toContain('Brighton & Hove Albion FC');
  });

  it('says a postponed match is postponed rather than leaving it looking scheduled', async () => {
    renderPage();
    await screen.findByTestId('team-season');
    expect(screen.getByTestId('team-match-pp').textContent).toContain('Postponed');
  });

  it('keeps a cancelled match visible and says so', async () => {
    stubFetch({
      ...SEASON,
      matches: [...SEASON.matches, match('can', '2026-09-12', 'cancelled')],
    });
    renderPage();
    await screen.findByTestId('team-season');

    const cancelled = screen.getByTestId('team-match-can');
    expect(cancelled.textContent).toContain('Cancelled');
  });

  it('marks a match being played right now as live', async () => {
    stubFetch({
      ...SEASON,
      matches: [match('live', '2026-08-29', 'live', { goals_for: 1, goals_against: 0, status: '63' })],
    });
    renderPage();
    await screen.findByTestId('team-season');
    expect(screen.getByTestId('team-match-live').textContent).toContain('Live');
  });
});

describe('TeamSeasonPage — the next fixture', () => {
  it('marks exactly one match next, and it is the earliest playable one', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const marked = screen.getAllByTestId(/^team-match-/).filter((li) => li.dataset.next === 'true');
    expect(marked).toHaveLength(1);
    // Not the postponed one sitting above it — that night is no longer happening.
    expect(marked[0].getAttribute('data-testid')).toBe('team-match-f1');
    expect(within(marked[0]).getByTestId('next-fixture-badge').textContent).toBe('Next');
  });

  it('marks nothing next once the season is played out', async () => {
    stubFetch({ ...SEASON, matches: SEASON.matches.filter((m) => m.state === 'finished') });
    renderPage();
    await screen.findByTestId('team-season');

    expect(screen.queryByTestId('next-fixture-badge')).toBeNull();
    expect(screen.queryByTestId('team-season-fixtures')).toBeNull();
  });
});

describe('TeamSeasonPage — the states either half can be in', () => {
  it('shows a season that is all fixtures and no results yet', async () => {
    stubFetch({ ...SEASON, matches: SEASON.matches.filter((m) => m.state !== 'finished') });
    renderPage();
    await screen.findByTestId('team-season');

    expect(screen.getByTestId('team-season-fixtures')).toBeTruthy();
    expect(screen.queryByTestId('team-season-results')).toBeNull();
  });

  it('explains a season with nothing stored rather than showing an empty frame', async () => {
    stubFetch({ ...SEASON, matches: [] });
    renderPage();
    expect(await screen.findByText('Nothing stored for this season yet')).toBeTruthy();
  });

  it('says so when the club is not one we hold', async () => {
    stubFetch(null, 404);
    renderPage();
    expect(await screen.findByText("Couldn't load this season")).toBeTruthy();
  });

  /** The link is always built with one, so arriving without one means a hand-typed URL. */
  it('asks for a competition rather than guessing one', async () => {
    const fetchMock = stubFetch();
    renderPage('/football/teams/t-arsenal');

    expect(await screen.findByText('No competition named')).toBeTruthy();
    expect(fetchMock.mock.calls.map(([u]) => String(u)).some((u) => u.includes('/teams/'))).toBe(
      false,
    );
  });
});

describe('TeamSeasonPage — reachable without a mouse', () => {
  it('puts the back link in the tab order and gives it a visible focus ring', async () => {
    renderPage();
    await screen.findByTestId('team-season');

    const back = screen.getByTestId('back-to-table');
    back.focus();
    expect(document.activeElement).toBe(back);
    expect(back.className).toMatch(/focus-visible:shadow-glow/);
    expect(back.className).toMatch(/\btap-target\b/);
  });

  it('has no axe violations with results, fixtures and a next match on screen', async () => {
    const { container } = renderPage();
    await screen.findByTestId('team-season');

    // `color-contrast` needs computed custom properties, which jsdom does not do;
    // `region` wants a landmark this page gets from `Layout` in the app.
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });

  it('does not reach a provider — it reads one database-backed route and nothing else', async () => {
    const fetchMock = stubFetch();
    renderPage();
    await screen.findByTestId('team-season');

    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls.every((u) => u.startsWith('http') || u.startsWith('/'))).toBe(true);
    expect(urls.some((u) => /fotmob|api-sports|api-football/i.test(u))).toBe(false);
  });
});

// A fixture list is read on a phone, and British club names are long.
describe('TeamSeasonPage — long names at mobile width', () => {
  it('truncates the opponent rather than letting a row grow sideways', async () => {
    stubFetch({
      ...SEASON,
      team: 'Inverness Caledonian Thistle Football Club',
      matches: [
        match('long', '2026-08-29', 'scheduled', {
          opponent: 'Wolverhampton Wanderers Football Club',
        }),
      ],
    });
    renderPage();
    await screen.findByTestId('team-season');

    const row = screen.getByTestId('team-match-long');
    const opponent = within(row).getByText('Wolverhampton Wanderers Football Club');
    expect(opponent.className).toMatch(/\btruncate\b/);
    expect(opponent.parentElement?.className).toMatch(/\bmin-w-0\b/);
  });
});
