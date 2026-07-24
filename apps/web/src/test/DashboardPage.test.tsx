import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { axe } from 'jest-axe';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { DashboardPage } from '@/pages/DashboardPage';
import { PointsBreakdownRow } from '@/components/PointsBreakdownRow';

const MOCK_LEAGUE = [
  {
    slug: 'steele-spreadsheet',
    name: 'The Steele Spreadsheet',
    description: null,
    privacy: 'private',
    member_count: 3,
    max_members: null,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

const HOME_EMPTY = {
  todo: {
    specials_submitted: false,
    specials_count: 0,
    opening_match_predicted: false,
    specials_lock_at: '2099-12-31T19:00:00Z', // far-future so tournamentStarted is always false
    upcoming_unpredicted: 0,
    next_match: null,
  },
  rollup: null,
};

const HOME_WITH_ROLLUP = {
  todo: {
    specials_submitted: true,
    specials_lock_at: null,
    upcoming_unpredicted: 0,
    next_match: null,
  },
  rollup: {
    matchday: '2026-06-11',
    points_gained: 10,
    match_count: 2,
    matches: [
      {
        match_id: 'match-1',
        kickoff_utc: '2026-06-11T18:00:00Z',
        home_label: '🇧🇷 Brazil',
        away_label: '🇲🇽 Mexico',
        home_flag: '🇧🇷',
        away_flag: '🇲🇽',
        actual_home: 2,
        actual_away: 1,
        predicted_home: 2,
        predicted_away: 1,
        points_breakdown: { result: 3, goals: 2, exact: 5, total: 10 },
        advancement_points: null,
      },
      {
        match_id: 'match-2',
        kickoff_utc: '2026-06-11T21:00:00Z',
        home_label: '🇦🇷 Argentina',
        away_label: '🇨🇦 Canada',
        home_flag: '🇦🇷',
        away_flag: '🇨🇦',
        actual_home: 1,
        actual_away: 0,
        predicted_home: 2,
        predicted_away: 0,
        points_breakdown: { result: 3, goals: 1, exact: 0, total: 4 },
        advancement_points: null,
      },
    ],
  },
};

const SUMMARY_ZERO = { avg_rank: null, total_points: 0, leagues_count: 0, per_league: [] };

const SUMMARY_ONE_LEAGUE = {
  avg_rank: 1.0,
  total_points: 87,
  leagues_count: 1,
  per_league: [
    {
      slug: 'steele-spreadsheet',
      name: 'The Steele Spreadsheet',
      rank: 1,
      member_count: 3,
      rank_delta: null,
      triggered_by_match_id: null,
    },
  ],
};

const SUMMARY_TWO_LEAGUES = {
  avg_rank: 1.5,
  total_points: 50,
  leagues_count: 2,
  per_league: [
    {
      slug: 'steele-spreadsheet',
      name: 'The Steele Spreadsheet',
      rank: 1,
      member_count: 3,
      rank_delta: 2,
      triggered_by_match_id: 'match-1',
    },
    {
      slug: 'office-pool',
      name: 'Office Pool',
      rank: 3,
      member_count: 5,
      rank_delta: -1,
      triggered_by_match_id: 'match-1',
    },
  ],
};

function stubAuth({ checklistDismissed = true }: { checklistDismissed?: boolean } = {}) {
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => {
      if (key === 'wc2026_player') return STORED_PLAYER;
      if (key === 'wc2026_access') return FAKE_JWT;
      if (key === 'sss_checklist_v1') {
        return checklistDismissed ? '{"rulesRead":true,"dismissed":true}' : null;
      }
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function makeWrapper(fetchImpl: (url: string) => Promise<unknown>) {
  vi.stubGlobal('fetch', fetchImpl);
  const queryClient = makeQueryClient();
  const Wrapper = () => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <LeagueProvider>
            <DashboardPage />
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return Wrapper;
}

function mockFetch(
  summary: object,
  home: object = HOME_EMPTY,
  predictions: unknown[] = [],
  matches: unknown[] = [],
  knockoutPredictions: unknown[] = [],
) {
  return (url: string) => {
    if (url.includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(MOCK_LEAGUE) });
    }
    if (url.includes('/cross-league-summary')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) });
    }
    if (url.includes('/me/home')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(home) });
    }
    if (url.includes('/api/v1/matches')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(matches) });
    }
    if (url.includes('/knockout-predictions/me')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(knockoutPredictions) });
    }
    if (url.includes('/predictions/me')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(predictions) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
  };
}

function buildMatch(
  id: string,
  status: string,
  kickoffOffsetMs: number,
  options?: {
    stage?: string;
    scores?: { hs: number; as: number };
    elapsed?: number;
    extraTime?: boolean;
    penalties?: boolean;
    etScores?: { hs: number; as: number };
    penScores?: { hs: number; as: number };
    home?: { name: string; code: string; flag: string };
    away?: { name: string; code: string; flag: string };
  },
) {
  return {
    id,
    match_number: 1,
    stage: options?.stage ?? 'group',
    group_id: options?.stage == null || options.stage === 'group' ? 'g' : null,
    home_team: {
      id: `home-${id}`,
      name: options?.home?.name ?? 'Spain',
      code: options?.home?.code ?? 'ESP',
      flag_emoji: options?.home?.flag ?? '🇪🇸',
    },
    away_team: {
      id: `away-${id}`,
      name: options?.away?.name ?? 'Italy',
      code: options?.away?.code ?? 'ITA',
      flag_emoji: options?.away?.flag ?? '🇮🇹',
    },
    home_team_placeholder: null,
    away_team_placeholder: null,
    kickoff_utc: new Date(Date.now() + kickoffOffsetMs).toISOString(),
    venue: null,
    status,
    actual_home_score: options?.scores?.hs ?? null,
    actual_away_score: options?.scores?.as ?? null,
    extra_time: options?.extraTime ?? false,
    penalties: options?.penalties ?? false,
    extra_time_home_score: options?.etScores?.hs ?? null,
    extra_time_away_score: options?.etScores?.as ?? null,
    penalty_home_score: options?.penScores?.hs ?? null,
    penalty_away_score: options?.penScores?.as ?? null,
    postponed_reason: null,
    elapsed_minutes: options?.elapsed ?? null,
  };
}

function buildPrediction(matchId: string, predictedHome: number, predictedAway: number) {
  return {
    id: `pred-${matchId}`,
    player_id: 'p1',
    match_id: matchId,
    predicted_home: predictedHome,
    predicted_away: predictedAway,
    submitted_at: '2026-06-11T00:00:00Z',
    update_count: 1,
    points_awarded: null,
    points_breakdown: null,
    updated_at: '2026-06-11T00:00:00Z',
  };
}

function buildKnockoutPrediction(matchId: string, predictedWinnerId: string | null) {
  return {
    id: `ko-pred-${matchId}`,
    player_id: 'p1',
    match_id: matchId,
    predicted_winner_id: predictedWinnerId,
    submitted_at: '2026-06-11T00:00:00Z',
    update_count: 1,
    points_awarded: null,
    updated_at: '2026-06-11T00:00:00Z',
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('DashboardPage — U40 home dashboard redesign', () => {
  it('renders the welcome heading and asymmetric top row from mobile up', async () => {
    stubAuth();
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], []));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('points-tile')).toBeInTheDocument());
    expect(screen.getByText('Welcome back, Alice')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-top-row').className).toContain(
      'grid-cols-[minmax(0,0.92fr)_minmax(0,1.48fr)]',
    );
  });

  it('folds +N today into the points tile and removes the old daily summary and live hub sections', async () => {
    stubAuth();
    const Wrapper = makeWrapper(mockFetch(SUMMARY_TWO_LEAGUES, HOME_WITH_ROLLUP, [], []));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByText(/\+10 pts/)).toBeInTheDocument());
    expect(screen.queryByText('Daily summary')).not.toBeInTheDocument();
    expect(screen.queryByText('Live now')).not.toBeInTheDocument();
    expect(screen.queryByText(/Across your leagues:/)).not.toBeInTheDocument();
  });

  it('shows country flags next to the previous-scores rollup', async () => {
    stubAuth();
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], []));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('points-tile')).toBeInTheDocument());
    const tile = screen.getByTestId('points-tile');
    // Flag + score only — the redundant 3-letter code is dropped so the away
    // team isn't clipped in the narrow tile.
    expect(tile.textContent).toContain('🇧🇷');
    expect(tile.textContent).toContain('🇲🇽');
    expect(tile.textContent).not.toContain('BRA');
  });

  it('uses the next fixture in the match tile when nothing is live', async () => {
    stubAuth();
    const matches = [buildMatch('next-1', 'scheduled', 1_800_000)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-next')).toBeInTheDocument());
    expect(screen.getByTestId('match-tile-next')).toHaveTextContent('Next up');
    expect(screen.getByTestId('match-tile-next')).toHaveTextContent('ESP');
  });

  it('falls back to the last result when there is no live or upcoming match', async () => {
    stubAuth();
    const matches = [buildMatch('last-1', 'completed', -3_600_000, { scores: { hs: 2, as: 1 } })];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-last')).toBeInTheDocument());
    expect(screen.getByTestId('match-tile-last')).toHaveTextContent('Latest final');
    expect(screen.getByTestId('match-tile-last')).toHaveTextContent('2–1');
  });

  it('shows the ET / penalty breakdown on the Latest final tile', async () => {
    stubAuth();
    const matches = [
      buildMatch('last-pens', 'completed', -3_600_000, {
        stage: 'r32',
        scores: { hs: 1, as: 1 },
        extraTime: true,
        penalties: true,
        etScores: { hs: 1, as: 1 },
        penScores: { hs: 3, as: 4 },
      }),
    ];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-last')).toBeInTheDocument());
    const tile = screen.getByTestId('match-tile-last');
    expect(tile).toHaveTextContent('AET');
    expect(tile).toHaveTextContent(/Pens 3.4/); // shootout tally, en-dash tolerant
  });

  it('folds knockout advancement into the Latest final tile', async () => {
    stubAuth();
    const matches = [
      buildMatch('ko-last', 'completed', -3_600_000, { stage: 'r32', scores: { hs: 0, as: 1 } }),
    ];
    const prediction = {
      ...buildPrediction('ko-last', 0, 1),
      points_awarded: 10,
      points_breakdown: { result: 3, goals: 2, exact: 5, total: 10, no_prediction: false },
    };
    // Player picked the away team (the actual winner) — +5 advancement.
    const ko = { ...buildKnockoutPrediction('ko-last', 'away-ko-last'), points_awarded: 5 };
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [prediction], matches, [ko]),
    );
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-last')).toBeInTheDocument());
    const tile = screen.getByTestId('match-tile-last');
    expect(tile).toHaveTextContent('Advancement');
    expect(tile).toHaveTextContent('15 pts'); // 10 score + 5 advancement
  });

  it('adds knockout advancement to the daily-summary per-match total', async () => {
    stubAuth();
    const home = {
      todo: {
        specials_submitted: true,
        specials_lock_at: null,
        upcoming_unpredicted: 0,
        next_match: null,
      },
      rollup: {
        matchday: '2026-06-28',
        points_gained: 15,
        match_count: 1,
        matches: [
          {
            match_id: 'ko-1',
            kickoff_utc: '2026-06-28T20:00:00Z',
            home_label: '🇿🇦 South Africa',
            away_label: '🇨🇦 Canada',
            home_flag: '🇿🇦',
            away_flag: '🇨🇦',
            actual_home: 0,
            actual_away: 1,
            predicted_home: 0,
            predicted_away: 1,
            points_breakdown: { result: 3, goals: 2, exact: 5, total: 10 },
            advancement_points: 5,
          },
        ],
      },
    };
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, home, [], []));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('points-tile')).toBeInTheDocument());
    // 10 score + 5 advancement shown as the per-match figure (not the base 10).
    expect(screen.getByTestId('points-tile')).toHaveTextContent('+15');
  });

  it('shows the live state with provisional points breakdown when a live prediction exists', async () => {
    stubAuth();
    // kickoff 10 min ago → the minute is derived from kickoff (the feed has no
    // match clock), so it reads ~10' regardless of any elapsed_minutes field.
    const matches = [buildMatch('live-1', 'live', -600_000, { scores: { hs: 1, as: 0 } })];
    const predictions = [buildPrediction('live-1', 1, 0)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent("Live · 10'");
    expect(liveCard).toHaveTextContent('Your pick: 1–0');
    expect(liveCard).toHaveTextContent('+10 if it stands');
    expect(liveCard).toHaveTextContent('Result');
    expect(liveCard).toHaveTextContent('Goals');
    expect(liveCard).toHaveTextContent('Exact');
  });

  it('hides the fabricated score and provisional points when a live match has no live score', async () => {
    stubAuth();
    // Real production state during a live match: status=live but actual scores
    // are still null (the feed has no in-play score). We must not show 0–0 or
    // "+N if it stands" computed against a fabricated 0–0.
    const matches = [buildMatch('live-noscore', 'live', -600_000)];
    const predictions = [buildPrediction('live-noscore', 2, 1)];
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches),
    );
    render(<Wrapper />);

    await waitFor(() =>
      expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument(),
    );
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('Live');
    expect(liveCard).toHaveTextContent('Your pick: 2–1');
    expect(liveCard).toHaveTextContent('Result & points at full-time');
    expect(liveCard).not.toHaveTextContent('if it stands');
    expect(liveCard).not.toHaveTextContent('0–0');
    // No live score → no provisional breakdown row at all.
    expect(liveCard).not.toHaveTextContent('Exact');
  });

  it('renders a genuine live 0–0 (U54 null-vs-zero guard treats 0 as a real score)', async () => {
    stubAuth();
    // U63: the feed now writes a real 0–0 once a match is underway. The U54 guard
    // must distinguish null ("no data", suppress) from a genuine 0 (render). The
    // pick is 1–0, so a '0–0' on the card can only be the actual live scoreline.
    const matches = [buildMatch('live-00', 'live', -600_000, { scores: { hs: 0, as: 0 }, elapsed: 12 })];
    const predictions = [buildPrediction('live-00', 1, 0)];
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches),
    );
    render(<Wrapper />);

    await waitFor(() =>
      expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument(),
    );
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('Your pick: 1–0');
    expect(liveCard).toHaveTextContent('0–0');
    expect(liveCard).not.toHaveTextContent('Result & points at full-time');
  });

  it('shows a live AET caption when a knockout match is mid-extra-time', async () => {
    // U64: _apply_live now mirrors the running ET scoreline live, so the same
    // caption helper used on the finished tile renders "AET 2–1" mid-match.
    const matches = [
      buildMatch('live-aet', 'live', -600_000, {
        stage: 'r16',
        scores: { hs: 1, as: 1 },
        extraTime: true,
        etScores: { hs: 2, as: 1 },
      }),
    ];
    const predictions = [buildPrediction('live-aet', 1, 1)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('1–1');
    expect(liveCard).toHaveTextContent('AET 2–1');
  });

  it('shows a live Pens caption with the running shootout tally', async () => {
    const matches = [
      buildMatch('live-pens', 'live', -600_000, {
        stage: 'r16',
        scores: { hs: 1, as: 1 },
        extraTime: true,
        etScores: { hs: 1, as: 1 },
        penalties: true,
        penScores: { hs: 3, as: 2 },
      }),
    ];
    const predictions = [buildPrediction('live-pens', 1, 1)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('1–1');
    expect(liveCard).toHaveTextContent('AET 1–1');
    expect(liveCard).toHaveTextContent('Pens 3–2');
  });

  it('adds projected knockout advancement points for a decisive live scoreline', async () => {
    stubAuth();
    const matches = [
      buildMatch('ko-live-1', 'live', -600_000, {
        stage: 'r16',
        scores: { hs: 2, as: 1 },
        elapsed: 88,
        home: { name: 'France', code: 'FRA', flag: '🇫🇷' },
        away: { name: 'USA', code: 'USA', flag: '🇺🇸' },
      }),
    ];
    const predictions = [buildPrediction('ko-live-1', 2, 1)];
    const knockoutPredictions = [buildKnockoutPrediction('ko-live-1', 'home-ko-live-1')];
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches, knockoutPredictions),
    );
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId('match-tile-live-card')).toHaveTextContent('+20 if it stands'),
    );
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('+20 if it stands');
    // Single combined breakdown row: Result/Goals/Exact plus the Advancement
    // chip, with the total folding in the advancement points.
    expect(liveCard).toHaveTextContent('Result');
    expect(liveCard).toHaveTextContent('Goals');
    expect(liveCard).toHaveTextContent('Exact');
    expect(liveCard).toHaveTextContent('Advancement');
    expect(liveCard).not.toHaveTextContent('Match-only breakdown');
    const breakdownRows = within(liveCard).getAllByText(/pts$/);
    expect(breakdownRows.at(-1)).toHaveTextContent('20 pts');
  });

  it('shows advancement as unearned for a level live knockout scoreline', async () => {
    stubAuth();
    const matches = [
      buildMatch('ko-live-level', 'live', -600_000, {
        stage: 'sf',
        scores: { hs: 1, as: 1 },
        elapsed: 92,
        extraTime: true,
        home: { name: 'Argentina', code: 'ARG', flag: '🇦🇷' },
        away: { name: 'England', code: 'ENG', flag: '🏴' },
      }),
    ];
    const predictions = [buildPrediction('ko-live-level', 1, 1)];
    const knockoutPredictions = [buildKnockoutPrediction('ko-live-level', 'home-ko-live-level')];
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches, knockoutPredictions),
    );
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId('match-tile-live-card')).toHaveTextContent('+10 if it stands'),
    );
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('+10 if it stands');
    // A level knockout scoreline earns no advancement yet: the chip is shown but
    // unearned (no "points pending" copy), and the total stays match-only.
    expect(liveCard).toHaveTextContent('Advancement');
    expect(liveCard).not.toHaveTextContent('Advancement points pending');
    expect(liveCard).not.toHaveTextContent('Match-only breakdown');
    const breakdownRows = within(liveCard).getAllByText(/pts$/);
    expect(breakdownRows.at(-1)).toHaveTextContent('10 pts');
  });

  it('leaves group-stage live provisional scoring unchanged', async () => {
    stubAuth();
    const matches = [buildMatch('group-live', 'live', -600_000, { scores: { hs: 2, as: 0 } })];
    const predictions = [buildPrediction('group-live', 2, 0)];
    const knockoutPredictions = [buildKnockoutPrediction('group-live', 'home-group-live')];
    const Wrapper = makeWrapper(
      mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches, knockoutPredictions),
    );
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const liveCard = screen.getByTestId('match-tile-live-card');
    expect(liveCard).toHaveTextContent('+10 if it stands');
    // Group match: the single breakdown row shows Result/Goals/Exact with no
    // Advancement chip, and the total is match-only.
    expect(liveCard).toHaveTextContent('Exact');
    expect(liveCard).not.toHaveTextContent('Advancement');
    const breakdownRows = within(liveCard).getAllByText(/pts$/);
    expect(breakdownRows.at(-1)).toHaveTextContent('10 pts');
  });

  it('defaults the multi-live carousel to the highest-stake card and exposes dots plus desktop arrows', async () => {
    stubAuth();
    const matches = [
      buildMatch('live-unpicked', 'live', -600_000, {
        scores: { hs: 0, as: 0 },
        elapsed: 83,
        home: { name: 'Netherlands', code: 'NED', flag: '🇳🇱' },
        away: { name: 'Japan', code: 'JPN', flag: '🇯🇵' },
      }),
      buildMatch('live-picked', 'live', -600_000, {
        scores: { hs: 2, as: 1 },
        elapsed: 54,
        home: { name: 'Brazil', code: 'BRA', flag: '🇧🇷' },
        away: { name: 'Mexico', code: 'MEX', flag: '🇲🇽' },
      }),
    ];
    const predictions = [buildPrediction('live-picked', 2, 1)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getAllByTestId('live-match-dot')).toHaveLength(2));
    expect(screen.getByTestId('match-tile-live-card')).toHaveTextContent('BRA');
    expect(screen.getByRole('button', { name: 'Previous live match' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next live match' })).toBeInTheDocument();
  });

  it('falls back to kickoff-derived live minute when the feed omits elapsed minutes', async () => {
    stubAuth();
    const matches = [
      buildMatch('group-earlier', 'live', -5_400_000, {
        scores: { hs: 1, as: 0 },
        home: { name: 'Spain', code: 'ESP', flag: '🇪🇸' },
        away: { name: 'Italy', code: 'ITA', flag: '🇮🇹' },
      }),
      buildMatch('group-later', 'live', -4_200_000, {
        scores: { hs: 0, as: 0 },
        home: { name: 'Brazil', code: 'BRA', flag: '🇧🇷' },
        away: { name: 'Mexico', code: 'MEX', flag: '🇲🇽' },
      }),
    ];
    const predictions = [
      buildPrediction('group-earlier', 1, 0),
      buildPrediction('group-later', 0, 0),
    ];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getAllByTestId('live-match-dot')).toHaveLength(2));
    expect(screen.getByTestId('match-tile-live-card')).toHaveTextContent('ESP');
    expect(screen.getByTestId('match-tile-live-card')).not.toHaveTextContent('BRA');
  });

  it('supports swiping between live matches', async () => {
    stubAuth();
    const matches = [
      buildMatch('live-picked', 'live', -600_000, {
        scores: { hs: 2, as: 1 },
        elapsed: 54,
        home: { name: 'Brazil', code: 'BRA', flag: '🇧🇷' },
        away: { name: 'Mexico', code: 'MEX', flag: '🇲🇽' },
      }),
      buildMatch('live-second', 'live', -600_000, {
        scores: { hs: 1, as: 1 },
        elapsed: 70,
        home: { name: 'France', code: 'FRA', flag: '🇫🇷' },
        away: { name: 'USA', code: 'USA', flag: '🇺🇸' },
      }),
    ];
    const predictions = [buildPrediction('live-picked', 2, 1)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, predictions, matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const carousel = screen.getByTestId('match-tile-live-carousel');
    fireEvent.touchStart(carousel, { changedTouches: [{ clientX: 220 }] });
    fireEvent.touchEnd(carousel, { changedTouches: [{ clientX: 80 }] });

    await waitFor(() => expect(screen.getByTestId('match-tile-live-card')).toHaveTextContent('FRA'));
  });

  it('links the points tile, league rows, and match tile to their drill targets', async () => {
    stubAuth();
    const matches = [buildMatch('next-1', 'scheduled', 1_800_000)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ONE_LEAGUE, HOME_WITH_ROLLUP, [], matches));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('points-tile')).toBeInTheDocument());
    expect(screen.getByLabelText('Open your profile')).toHaveAttribute('href', '/players/p1');
    expect(screen.getByLabelText('Open The Steele Spreadsheet leaderboard')).toHaveAttribute(
      'href',
      '/leagues/steele-spreadsheet/leaderboard',
    );
    expect(screen.getByLabelText(/Open next match ESP versus ITA/)).toHaveAttribute(
      'href',
      '/matches/next-1',
    );
  });

  it('keeps the compact league rows and preserves delta badges', async () => {
    stubAuth();
    const Wrapper = makeWrapper(mockFetch(SUMMARY_TWO_LEAGUES, HOME_WITH_ROLLUP, [], []));
    render(<Wrapper />);

    await waitFor(() => expect(screen.getAllByTestId('league-row-link')).toHaveLength(2));
    // Component renders rank + direction arrow (delta magnitude not shown inline)
    expect(screen.getByText('#1 ↑')).toBeInTheDocument();
    expect(screen.getByText('#3 ↓')).toBeInTheDocument();
  });

  it('renders the scoring guide below upcoming matches', async () => {
    stubAuth({ checklistDismissed: false });
    const Wrapper = makeWrapper(mockFetch(SUMMARY_ZERO, HOME_EMPTY, [], []));
    render(<Wrapper />);

    const scoringRef = await screen.findByTestId('dashboard-scoring-ref');
    const scoringGuideButton = within(scoringRef).getByRole('button', { name: /Knockout scoring quick-ref/i });

    expect(scoringRef).toContainElement(scoringGuideButton);
    expect(screen.getByTestId('dashboard-points-column')).not.toContainElement(scoringGuideButton);
    expect(screen.queryByText('Your tally starts when the first results land.')).not.toBeInTheDocument();
  });
});

describe('DashboardPage — accessibility', () => {
  it('has no axe violations with the redesigned top row and live carousel', async () => {
    stubAuth();
    const matches = [
      buildMatch('live-picked', 'live', -600_000, { scores: { hs: 2, as: 1 }, elapsed: 54 }),
      buildMatch('live-second', 'live', -300_000, { scores: { hs: 0, as: 0 }, elapsed: 77 }),
    ];
    const predictions = [buildPrediction('live-picked', 2, 1)];
    const Wrapper = makeWrapper(mockFetch(SUMMARY_TWO_LEAGUES, HOME_WITH_ROLLUP, predictions, matches));
    const { container } = render(<Wrapper />);

    await waitFor(() => expect(screen.getByTestId('match-tile-live-carousel')).toBeInTheDocument());
    const results = await axe(container, { rules: { 'color-contrast': { enabled: false } } });
    expect(results).toHaveNoViolations();
  });
});

describe('PointsBreakdownRow', () => {
  it('shows checkmarks and values for positive breakdown fields', () => {
    render(<PointsBreakdownRow breakdown={{ result: 3, goals: 2, exact: 0, total: 5 }} />);
    expect(screen.getByText('Result')).toBeTruthy();
    expect(screen.getByText('+3')).toBeTruthy();
    expect(screen.getByText('+2')).toBeTruthy();
    expect(screen.getByText('Exact')).toBeTruthy();
    expect(screen.getByText('5 pts')).toBeTruthy();
  });

  it('shows — for zero breakdown fields', () => {
    render(<PointsBreakdownRow breakdown={{ result: 0, goals: 0, exact: 0, total: 0 }} />);
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBe(3);
  });

  it('shows an Advancement chip when advancement points are provided', () => {
    render(
      <PointsBreakdownRow
        breakdown={{ result: 3, goals: 2, exact: 0, total: 10, advancement: 5 }}
      />,
    );
    expect(screen.getByText('Advancement')).toBeTruthy();
    expect(screen.getByText('+5')).toBeTruthy(); // unique to the advancement chip
    expect(screen.getByText('10 pts')).toBeTruthy();
  });

  it('hides the Advancement chip for group matches (no advancement field)', () => {
    render(<PointsBreakdownRow breakdown={{ result: 3, goals: 2, exact: 0, total: 5 }} />);
    expect(screen.queryByText('Advancement')).toBeNull();
  });
});
