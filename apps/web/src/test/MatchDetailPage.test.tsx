import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { MatchDetailPage } from '@/pages/MatchDetailPage';

const apiFetch = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const HOME_TEAM = { id: 't1', name: 'Brazil', code: 'BRA', flag_emoji: '🇧🇷' };
const AWAY_TEAM = { id: 't2', name: 'Germany', code: 'GER', flag_emoji: '🇩🇪' };

const KO_MATCH_LOCKED = {
  id: 'm73',
  match_number: 73,
  stage: 'r32',
  group_id: null,
  group_name: null,
  home_team: HOME_TEAM,
  away_team: AWAY_TEAM,
  home_team_placeholder: null,
  away_team_placeholder: null,
  kickoff_utc: '2026-06-01T20:00:00Z',
  venue: 'MetLife Stadium',
  status: 'locked',
  actual_home_score: null,
  actual_away_score: null,
  extra_time: false,
  penalties: false,
  postponed_reason: null,
};

const GROUP_MATCH_LOCKED = {
  ...KO_MATCH_LOCKED,
  id: 'mg1',
  match_number: 1,
  stage: 'group',
  group_id: 'ga',
  group_name: 'Group A',
};

const KO_PREDICTIONS_RESPONSE = {
  match_id: 'm73',
  predictions: [
    {
      player_id: 'p1',
      player_name: 'Alice',
      predicted_home: 2,
      predicted_away: 1,
      points_awarded: 3,
      points_breakdown: null,
      advancement_points: 2,
      predicted_winner_team_id: 't1',
    },
    {
      player_id: 'p2',
      player_name: 'Bob',
      predicted_home: 1,
      predicted_away: 1,
      points_awarded: 0,
      points_breakdown: null,
      advancement_points: 0,
      predicted_winner_team_id: 't2',
    },
  ],
};

const GROUP_PREDICTIONS_RESPONSE = {
  match_id: 'mg1',
  predictions: [
    {
      player_id: 'p1',
      player_name: 'Alice',
      predicted_home: 1,
      predicted_away: 0,
      points_awarded: 2,
      points_breakdown: null,
      advancement_points: null,
      predicted_winner_team_id: null,
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function renderPage(matchId: string, match: unknown, predictions: unknown) {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'wc2026_player') return STORED_PLAYER;
      if (k === 'wc2026_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });

  apiFetch.mockImplementation((url: string) => {
    if (url === `/api/v1/matches/${matchId}`) return Promise.resolve(match);
    if (url === '/api/v1/predictions/me') return Promise.resolve([]);
    if (url === `/api/v1/predictions/match/${matchId}`) return Promise.resolve(predictions);
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });

  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[`/matches/${matchId}`]}>
        <AuthProvider>
          <Routes>
            <Route path="/matches/:id" element={<MatchDetailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  apiFetch.mockReset();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MatchDetailPage — comparison table', () => {
  it('shows a "To Advance" column with each player\'s pick for a knockout match', async () => {
    renderPage('m73', KO_MATCH_LOCKED, KO_PREDICTIONS_RESPONSE);

    await waitFor(() => expect(screen.getByText('All Predictions')).toBeInTheDocument());

    expect(screen.getByText('To Advance')).toBeInTheDocument();
    expect(screen.getByText('Brazil')).toBeInTheDocument();
    expect(screen.getByText('Germany')).toBeInTheDocument();
  });

  it('does not show a "To Advance" column for a group-stage match', async () => {
    renderPage('mg1', GROUP_MATCH_LOCKED, GROUP_PREDICTIONS_RESPONSE);

    await waitFor(() => expect(screen.getByText('All Predictions')).toBeInTheDocument());

    expect(screen.queryByText('To Advance')).not.toBeInTheDocument();
  });
});
