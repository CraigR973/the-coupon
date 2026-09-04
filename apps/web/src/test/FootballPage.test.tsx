import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { FootballPage } from '@/pages/FootballPage';
import type { CompetitionTable, FormMatch, ResultEntry } from '@/lib/types';

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

const TABLES: CompetitionTable[] = [
  {
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    season: 2025,
    updated_at: '2026-08-06T06:30:00',
    rows: [
      {
        position: 1,
        team_id: 't-arsenal',
        team: 'Arsenal FC',
        played: 38,
        won: 26,
        drawn: 8,
        lost: 4,
        goals_for: 84,
        goals_against: 32,
        goal_difference: 52,
        points: 86,
        form: 'WWDWW',
      },
      {
        position: 2,
        team_id: 't-chelsea',
        team: 'Chelsea FC',
        played: 38,
        won: 23,
        drawn: 7,
        lost: 8,
        goals_for: 71,
        goals_against: 40,
        goal_difference: 31,
        points: 76,
        form: 'WLWDW',
      },
    ],
  },
  {
    competition_id: 'scotland-league-two',
    competition: 'Scotland - Scottish League Two',
    season: 2025,
    updated_at: '2026-08-06T06:30:00',
    rows: [
      {
        position: 1,
        team_id: 't-forfar',
        team: 'Forfar Athletic FC',
        played: 36,
        won: 20,
        drawn: 8,
        lost: 8,
        goals_for: 58,
        goals_against: 39,
        goal_difference: 19,
        points: 68,
        form: 'WDWWL',
      },
    ],
  },
];

const RESULTS: ResultEntry[] = [
  {
    match_id: 'm107',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00',
    home: 'Chelsea FC',
    away: 'Arsenal FC',
    home_goals: 0,
    away_goals: 1,
  },
  {
    match_id: 'm108',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-05-02T14:00:00',
    home: 'Liverpool FC',
    away: 'Everton FC',
    home_goals: 4,
    away_goals: 0,
  },
  {
    match_id: 'm105',
    competition_id: 'england-premier-league',
    competition: 'England - English Premier League',
    kickoff_utc: '2026-04-25T14:00:00',
    home: 'Arsenal FC',
    away: 'Tottenham Hotspur FC',
    home_goals: 2,
    away_goals: 1,
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

function stubFetch({
  tables = TABLES,
  results = RESULTS,
}: { tables?: CompetitionTable[]; results?: ResultEntry[] } = {}) {
  vi.stubGlobal('fetch', (url: string) => {
    if (String(url).includes('/football/tables')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(tables) });
    }
    if (String(url).includes('/football/results')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(results) });
    }
    if (String(url).includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([MOCK_LEAGUE]) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

/**
 * The browser's back and forward buttons, as two buttons a test can press.
 *
 * `MemoryRouter` keeps its own history stack, so `navigate(-1)` performs the same pop
 * the hardware button does. That is the thing Batch 109 has to keep working: the
 * selected day lives in the URL precisely so the back button walks out of the archive.
 */
function HistoryProbe() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate(-1)}>
        go back
      </button>
      <button type="button" onClick={() => navigate(1)}>
        go forward
      </button>
    </>
  );
}

function renderPage(path = '/football') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <LeagueProvider>
            <HistoryProbe />
            <Routes>
              <Route path="/football" element={<FootballPage />} />
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

/**
 * Open one competition and hand back its card.
 *
 * Batch 71 made every division start collapsed, so a test that wants to read *inside* a
 * table has to say so — which is the honest shape anyway: none of these are asserting
 * what the screen shows on arrival.
 */
async function openTable(testId = 'league-table-england-premier-league'): Promise<HTMLElement> {
  const table = await screen.findByTestId(testId);
  const header = within(table).getAllByRole('button')[0];
  if (header.getAttribute('aria-expanded') === 'false') fireEvent.click(header);
  return table;
}

describe('FootballPage — tables', () => {
  it('renders a table per competition in the pool', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    expect(screen.getByTestId('league-table-scotland-league-two')).toBeTruthy();
  });

  it('reads down the pyramid whatever order the API sent, like the coupon does', async () => {
    // The regression: tables rendered in the API's order, which is the ingestion
    // job's, so the same divisions the member had just scrolled past on the coupon
    // came back rearranged. Serve them upside-down and they must still read down.
    vi.restoreAllMocks();
    stubAuth();
    stubFetch({ tables: [...TABLES].reverse() });
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    const rendered = screen
      .getAllByTestId(/^league-table-/)
      .map((el) => el.getAttribute('data-testid'));
    expect(rendered).toEqual([
      'league-table-england-premier-league',
      'league-table-scotland-league-two',
    ]);
  });

  it('shows the standings figures in position order', async () => {
    renderPage();
    const table = await openTable();
    const rows = within(table).getAllByRole('row').slice(1); // drop the header
    expect(within(rows[0]).getByRole('rowheader').textContent).toBe('Arsenal FC');
    expect(rows[0].textContent).toContain('+52');
    expect(rows[0].textContent).toContain('86');
    expect(within(rows[1]).getByRole('rowheader').textContent).toBe('Chelsea FC');
  });

  it('says when the table was last ingested — nothing here is live', async () => {
    renderPage();
    const table = await openTable();
    expect(table.textContent).toMatch(/As of 6 Aug, 06:30/);
  });

  // Batch 71 — inverted. This asserted that the *first* competition opened, which was the
  // right instinct with the wrong answer: the reader has not asked for any of them yet,
  // and opening whichever sorts first makes it look chosen. The owner asked for the
  // screen collapsed on open.
  it('opens with every competition collapsed', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    const headers = screen.getAllByRole('button', { name: /premier league|league two/i });
    expect(headers.length).toBeGreaterThan(1);
    for (const header of headers) {
      expect(header.getAttribute('aria-expanded')).toBe('false');
    }
  });

  it('expands a collapsed competition on tap', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    const scotland = screen.getAllByRole('button', { name: /league two/i })[0];
    fireEvent.click(scotland);
    expect(screen.getByTestId('table-row-t-forfar')).toBeTruthy();
  });

  it('explains an empty section rather than showing a blank page', async () => {
    stubFetch({ tables: [] });
    renderPage();
    expect(await screen.findByText('No tables yet')).toBeTruthy();
  });

  it('keeps form visible at mobile width — the GD column hides instead', async () => {
    renderPage();
    const table = await openTable();
    const row = within(table).getByTestId('table-row-t-arsenal');
    const formCell = row.querySelector('td:last-child');
    expect(formCell?.className).not.toMatch(/\bhidden\b/);
    expect(screen.getAllByLabelText(/Arsenal FC form, oldest first/)[0]).toBeTruthy();
  });
});

// ── Opening a table row's form (Batch 53) ─────────────────────────────────────
//
// `recent` is optional on `TableEntry` and the shared fixture above omits it, which is
// also the deploy-gap case: Vercel ships this app from `main` while the API waits for
// `/ship-prod`, so for that window every row arrives without it and every run of pips
// stays the graphic it was.

const ARSENAL_RECENT: FormMatch[] = [
  {
    match_id: 'm107',
    kickoff_utc: '2026-05-02T14:00:00Z',
    opponent: 'Chelsea FC',
    home: false,
    goals_for: 1,
    goals_against: 0,
    result: 'W',
  },
  {
    match_id: 'm105',
    kickoff_utc: '2026-04-25T14:00:00Z',
    opponent: 'Tottenham Hotspur FC',
    home: true,
    goals_for: 2,
    goals_against: 1,
    result: 'W',
  },
];

const TABLES_WITH_FORM: CompetitionTable[] = [
  {
    ...TABLES[0],
    rows: TABLES[0].rows.map((row) =>
      row.team_id === 't-arsenal' ? { ...row, form: 'WW', recent: ARSENAL_RECENT } : row,
    ),
  },
];

describe('FootballPage — opening a table row’s form', () => {
  it('opens the matches behind the pips in a row of their own', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await openTable();

    fireEvent.click(within(table).getByLabelText(/Arsenal FC form, oldest first/));

    const panel = screen.getByRole('list', { name: /Arsenal FC recent results/ });
    expect(within(panel).getAllByRole('listitem').length).toBe(2);
    expect(panel.textContent).toContain('Tottenham Hotspur FC');

    // Across the whole table rather than inside the Form cell, which is five pips wide
    // on a phone and would push the table into sideways scrolling.
    const panelRow = within(table).getByTestId('form-matches-row-t-arsenal');
    expect(panelRow.contains(panel)).toBe(true);
    expect(panelRow.querySelector('td')?.getAttribute('colspan')).toBe('9');
    expect(within(table).getByTestId('table-row-t-arsenal').contains(panel)).toBe(false);
  });

  it('closes it again, and opens only one club at a time', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await openTable();
    const pips = within(table).getByLabelText(/Arsenal FC form, oldest first/);

    fireEvent.click(pips);
    expect(pips.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(pips);
    expect(pips.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('list', { name: /recent results/ })).toBeNull();
  });

  it('leaves a row with a form string but no stored matches inert', async () => {
    stubFetch({ tables: TABLES_WITH_FORM });
    renderPage();
    const table = await openTable();

    const chelsea = within(table).getByLabelText(/Chelsea FC form, oldest first/);
    expect(chelsea.tagName).not.toBe('BUTTON');
    expect(chelsea.getAttribute('role')).toBe('img');
  });
});

// ── Results: one matchday at a time (Batch 109) ───────────────────────────
//
// This screen used to be the whole archive in one column, and these tests used to
// assert that shape — two day headings, newest first. Batch 109 respecifies it: the
// job is moving *between* matchdays, so one day is on screen and the rest are in the
// strip above it. The day-grouping and competition-grouping assertions survive; the
// "every day at once" ones are gone because that is no longer the screen.

/** Land on the Results tab from a cold open. */
async function showResults(path = '/football'): Promise<HTMLElement> {
  renderPage(path);
  await screen.findByRole('tab', { name: 'Results' });
  fireEvent.click(screen.getByRole('tab', { name: 'Results' }));
  return screen.findByTestId('football-results');
}

/** Arrive by link, which opens the Results tab on its own. */
async function followLink(path: string): Promise<HTMLElement> {
  renderPage(path);
  return screen.findByTestId('football-results');
}

const dayHeading = (list: HTMLElement) =>
  within(list).getByRole('heading', { level: 2 }).textContent;

/** Every chip in the strip, excluding the step buttons that share the prefix. */
const dayChips = () => screen.getAllByTestId(/^result-day-\d/);

describe('FootballPage — results', () => {
  it('opens on the latest day with results, not on the whole archive', async () => {
    const list = await showResults();
    expect(dayHeading(list)).toBe('Saturday 2 May 2026');
    expect(within(list).getByTestId('result-m107')).toBeTruthy();
    expect(within(list).getByTestId('result-m108')).toBeTruthy();
    // The previous matchday is a tap away, not a scroll away.
    expect(within(list).queryByTestId('result-m105')).toBeNull();
  });

  it('names every result-bearing day in the strip, oldest to newest', async () => {
    await showResults();
    expect(dayChips().map((chip) => chip.getAttribute('data-date'))).toEqual([
      '2026-04-25',
      '2026-05-02',
    ]);
  });

  it('shows each score against the two clubs', async () => {
    const list = await showResults();
    const result = within(list).getByTestId('result-m107');
    expect(result.textContent).toContain('Chelsea FC');
    expect(result.textContent).toContain('Arsenal FC');
    expect(result.textContent).toContain('0–1');
  });

  it('reads the score out unambiguously for screen readers', async () => {
    const list = await showResults();
    const result = within(list).getByTestId('result-m107');
    expect(within(result).getByText('Chelsea FC 0, Arsenal FC 1')).toBeTruthy();
  });

  it('explains an empty results list', async () => {
    stubFetch({ results: [] });
    renderPage();
    fireEvent.click(await screen.findByRole('tab', { name: 'Results' }));
    expect(await screen.findByText('No results yet')).toBeTruthy();
    expect(screen.queryByTestId('result-day-carousel')).toBeNull();
  });

  it('groups two competitions on one day into two competition headings', async () => {
    const mixedResults: ResultEntry[] = [
      ...RESULTS.filter((r) => r.match_id !== 'm105'),
      {
        match_id: 'm200',
        competition_id: 'scotland-league-two',
        competition: 'Scotland - Scottish League Two',
        kickoff_utc: '2026-05-02T14:00:00',
        home: 'Forfar Athletic FC',
        away: 'Edinburgh City FC',
        home_goals: 2,
        away_goals: 2,
      },
    ];
    stubFetch({ results: mixedResults });
    const list = await showResults();

    const competitionHeadings = within(list).getAllByRole('heading', { level: 3 });
    expect(competitionHeadings.map((h) => h.textContent)).toEqual([
      'England - English Premier League',
      'Scotland - Scottish League Two',
    ]);
  });

  it('does not grow a redundant heading for a day with a single competition', async () => {
    const list = await showResults();
    expect(within(list).queryAllByRole('heading', { level: 3 })).toHaveLength(0);
  });

  it('hides the carousel when there is only one day to move between', async () => {
    stubFetch({ results: RESULTS.filter((r) => r.match_id === 'm105') });
    const list = await showResults();
    expect(screen.queryByTestId('result-day-carousel')).toBeNull();
    expect(dayHeading(list)).toBe('Saturday 25 April 2026');
  });
});

describe('FootballPage — the day in the address', () => {
  it('opens the day a ?date= link names, on the tab that holds one', async () => {
    const list = await followLink('/football?date=2026-04-25');
    expect(dayHeading(list)).toBe('Saturday 25 April 2026');
    expect(within(list).getByTestId('result-m105')).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Results' }).getAttribute('aria-selected')).toBe('true');
  });

  it('leaves the tables tab in front when no day is named', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');
    expect(screen.getByRole('tab', { name: 'Tables' }).getAttribute('aria-selected')).toBe('true');
  });

  // A date the archive does not hold is a stale link, a postponed card or a typed
  // guess. All three want the newest day rather than an empty screen.
  it('falls back to the latest day for a date it holds no results for', async () => {
    const list = await followLink('/football?date=2026-04-26');
    expect(dayHeading(list)).toBe('Saturday 2 May 2026');
  });

  it('falls back to the latest day for a date that is not a date', async () => {
    const list = await followLink('/football?date=banana');
    expect(dayHeading(list)).toBe('Saturday 2 May 2026');
  });

  it('walks back and forward through the days with the browser buttons', async () => {
    const list = await showResults();
    fireEvent.click(within(list).getByTestId('result-day-2026-04-25'));
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe(
      'Saturday 25 April 2026',
    );

    fireEvent.click(screen.getByRole('button', { name: 'go back' }));
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe('Saturday 2 May 2026');

    fireEvent.click(screen.getByRole('button', { name: 'go forward' }));
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe(
      'Saturday 25 April 2026',
    );
  });
});

describe('FootballPage — the matchday carousel', () => {
  it('steps to the previous day and back to the next', async () => {
    await showResults();

    fireEvent.click(screen.getByTestId('result-day-previous'));
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe(
      'Saturday 25 April 2026',
    );

    fireEvent.click(screen.getByTestId('result-day-next'));
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe('Saturday 2 May 2026');
  });

  it('disables the step that would run off the end of the archive', async () => {
    await showResults();
    // Opening on the newest day, there is no later one.
    expect(screen.getByTestId('result-day-next')).toBeDisabled();
    expect(screen.getByTestId('result-day-previous')).not.toBeDisabled();

    fireEvent.click(screen.getByTestId('result-day-previous'));
    await screen.findByTestId('result-m105');
    expect(screen.getByTestId('result-day-previous')).toBeDisabled();
    expect(screen.getByTestId('result-day-next')).not.toBeDisabled();
  });

  it('marks one day current and makes only that one tabbable', async () => {
    await showResults();
    const chips = dayChips();
    expect(chips.map((chip) => chip.getAttribute('aria-current'))).toEqual([null, 'date']);
    // Roving tabindex: a season of Saturdays costs one tab stop, not sixty.
    expect(chips.map((chip) => chip.getAttribute('tabindex'))).toEqual(['-1', '0']);
  });

  it('says what a chip does, including the year the abbreviation drops', async () => {
    await showResults();
    expect(screen.getByTestId('result-day-2026-05-02').getAttribute('aria-label')).toBe(
      'Show 2 results from Saturday 2 May 2026',
    );
    expect(screen.getByTestId('result-day-2026-04-25').getAttribute('aria-label')).toBe(
      'Show 1 result from Saturday 25 April 2026',
    );
  });

  it('moves along the strip with the arrow keys, carrying focus with the selection', async () => {
    await showResults();
    const strip = screen.getByTestId('result-day-strip');

    fireEvent.keyDown(strip, { key: 'ArrowLeft' });
    await screen.findByTestId('result-m105');
    expect(document.activeElement).toBe(screen.getByTestId('result-day-2026-04-25'));

    fireEvent.keyDown(strip, { key: 'ArrowRight' });
    await screen.findByTestId('result-m107');
    expect(document.activeElement).toBe(screen.getByTestId('result-day-2026-05-02'));
  });

  it('jumps to either end of the archive with Home and End', async () => {
    await showResults();
    const strip = screen.getByTestId('result-day-strip');

    fireEvent.keyDown(strip, { key: 'Home' });
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe(
      'Saturday 25 April 2026',
    );

    fireEvent.keyDown(strip, { key: 'End' });
    expect(dayHeading(await screen.findByTestId('football-results'))).toBe('Saturday 2 May 2026');
  });

  it('holds every day control above the 44px touch floor', async () => {
    await showResults();
    const controls = [
      screen.getByTestId('result-day-previous'),
      screen.getByTestId('result-day-next'),
      ...dayChips(),
    ];
    for (const control of controls) {
      expect(control.className).toMatch(/\btap-target\b/);
    }
  });

  // A full season is roughly sixty result days. They scroll inside the strip, snapped,
  // rather than widening the page — the phone the screen is read on is 390px across.
  it('scrolls a season of days inside the strip rather than widening the page', async () => {
    const season: ResultEntry[] = Array.from({ length: 60 }, (_, index) => ({
      match_id: `s${index}`,
      competition_id: 'england-premier-league',
      competition: 'England - English Premier League',
      kickoff_utc: `2026-01-${String((index % 28) + 1).padStart(2, '0')}T${String(
        index % 24,
      ).padStart(2, '0')}:00:00`,
      home: 'Arsenal FC',
      away: 'Chelsea FC',
      home_goals: 1,
      away_goals: 0,
    }));
    stubFetch({ results: season });
    await showResults();

    const strip = screen.getByTestId('result-day-strip');
    expect(strip.className).toMatch(/overflow-x-auto/);
    expect(strip.className).toMatch(/snap-x/);
    expect(strip.className).toMatch(/snap-mandatory/);
    expect(strip.firstElementChild?.className).toMatch(/min-w-max/);
    // Paired with the `behavior: 'instant'` below — see that test for what a smooth
    // scroll does to a mandatory-snap strip this long.
    expect(strip.className).not.toMatch(/scroll-smooth/);

    const chips = dayChips();
    expect(chips).toHaveLength(28);
    for (const chip of chips) expect(chip.className).toMatch(/\bsnap-center\b/);
  });

  /**
   * Measured in Chrome against a full season, and the reason `scroll-smooth` is not on
   * the strip: a smooth programmatic scroll inside `scroll-snap-type: x mandatory`
   * refuses a long one outright. Arriving on the newest day — the chip 8,443px along an
   * 8,486px strip — left `scrollLeft` at 404 and never moved, so the heading read May
   * while the strip showed the previous August. Short hops worked, which is exactly how
   * it stays hidden until the archive is a season deep.
   */
  it('brings the selected day into view without a smooth scroll', async () => {
    const scrollIntoView = vi.fn();
    // jsdom implements no `scrollIntoView` at all, so there is nothing to spy on.
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      value: scrollIntoView,
      configurable: true,
      writable: true,
    });
    try {
      await showResults();
      expect(scrollIntoView).toHaveBeenCalledWith({
        block: 'nearest',
        inline: 'center',
        behavior: 'instant',
      });
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it('has no axe violations with the carousel on screen', async () => {
    const list = await showResults();
    // `color-contrast` needs computed custom properties, which jsdom does not do.
    // `region` wants every node inside a landmark, and in the app this page renders
    // inside `Layout`'s <main> — which a page-only render has no way to include.
    const results = await axe(list.parentElement ?? list, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});

// ── Batch 51: no league anywhere on the screen ────────────────────────────

describe('FootballPage — untied from a league', () => {
  it('asks the slug-less endpoints, not a league-scoped pair', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/football/tables')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(TABLES) });
      }
      if (String(url).includes('/football/results')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(RESULTS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([MOCK_LEAGUE]),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    await screen.findByTestId('league-table-england-premier-league');

    const football = fetchMock.mock.calls
      .map(([url]) => String(url))
      .filter((url) => url.includes('/football/'));
    expect(football.some((url) => url.endsWith('/api/v1/football/tables'))).toBe(true);
    expect(football.some((url) => url.endsWith('/api/v1/football/results'))).toBe(true);
    expect(football.some((url) => url.includes('/leagues/'))).toBe(false);
  });

  it('names no league in the header, and carries neither switcher nor sub-nav', async () => {
    renderPage();
    await screen.findByTestId('league-table-england-premier-league');

    expect(screen.getByRole('heading', { name: 'Football Stats' })).toBeTruthy();
    expect(screen.queryByText(/the coupon/i)).toBeNull();
    expect(screen.queryByTestId('league-switch-strip')).toBeNull();
    expect(screen.queryByLabelText('Coupon sections')).toBeNull();
  });

  it('still reads for a member of no league at all', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes('/football/tables')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(TABLES) });
      }
      if (String(url).includes('/football/results')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(RESULTS) });
      }
      if (String(url).includes('/leagues/mine')) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    expect(await screen.findByTestId('league-table-england-premier-league')).toBeTruthy();
    expect(screen.queryByText("You're not in a league yet")).toBeNull();
  });

  it('says what "every competition" actually covers when there is nothing yet', async () => {
    stubFetch({ tables: [] });
    renderPage();

    const empty = await screen.findByText('No tables yet');
    expect(empty.parentElement?.textContent).toContain('not every competition in Britain');
  });
});
