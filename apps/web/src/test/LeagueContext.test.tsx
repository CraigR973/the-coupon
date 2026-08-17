import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LeagueProvider, useLeague } from '@/contexts/LeagueContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { LAST_VIEWED_LEAGUE_KEY } from '@/lib/leagueRecency';

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({ id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' });

const MOCK_LEAGUE = {
  slug: 'the-coupon',
  name: 'The Coupon',
  description: null,
  privacy: 'private',
  member_count: 2,
  max_members: null,
  created_at: '2026-01-01T00:00:00Z',
};

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function stubAuth(lastViewedSlug: string | null = null) {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      if (k === LAST_VIEWED_LEAGUE_KEY && lastViewedSlug) {
        return JSON.stringify({ slug: lastViewedSlug, name: lastViewedSlug });
      }
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function LeagueDisplay() {
  const { leagues, isLoading, activeSlug, activeLeagueName, hasLeagues, selectLeague } = useLeague();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      <div data-testid="count">{leagues.length}</div>
      <div data-testid="active-slug">{activeSlug}</div>
      <div data-testid="active-league-name">{activeLeagueName ?? ''}</div>
      <div data-testid="has-leagues">{String(hasLeagues)}</div>
      {leagues.map((l) => (
        <div key={l.slug} data-testid={`league-${l.slug}`}>{l.name}</div>
      ))}
      <button type="button" onClick={() => selectLeague('friends-league')}>
        select friends
      </button>
      <button type="button" onClick={() => selectLeague('not-mine')}>
        select stranger
      </button>
    </div>
  );
}

function renderWithLeague(leagues: unknown[]) {
  vi.stubGlobal('fetch', (url: string) => {
    if (url.includes('/leagues/mine')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(leagues) });
    }
    return Promise.reject(new Error('unexpected'));
  });

  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <AuthProvider>
          <LeagueProvider>
            <LeagueDisplay />
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('LeagueContext', () => {
  it('loads leagues and exposes them', async () => {
    renderWithLeague([MOCK_LEAGUE]);
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
    expect(screen.getByTestId('league-the-coupon').textContent).toBe('The Coupon');
  });

  it('shows empty list when no leagues', async () => {
    renderWithLeague([]);
    await waitFor(() => {
      expect(screen.queryByTestId('count')).toBeTruthy();
    });
  });

  it('exposes the active league name and gates hasLeagues on a resolved membership', async () => {
    renderWithLeague([MOCK_LEAGUE]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon'));
    expect(screen.getByTestId('active-league-name').textContent).toBe('The Coupon');
    expect(screen.getByTestId('has-leagues').textContent).toBe('true');
  });

  it('reports hasLeagues as false for a member of no league', async () => {
    renderWithLeague([]);
    await waitFor(() => expect(screen.getByTestId('has-leagues').textContent).toBe('false'));
    expect(screen.getByTestId('active-league-name').textContent).toBe('');
  });

  it('exposes multiple leagues', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    renderWithLeague([MOCK_LEAGUE, second]);
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
  });

  it('defaults activeSlug to the first league when nothing was last viewed', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    renderWithLeague([MOCK_LEAGUE, second]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon'));
  });

  it('prefers the last-viewed league when the member still belongs to it', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    stubAuth('friends-league');
    renderWithLeague([MOCK_LEAGUE, second]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('friends-league'));
  });

  it('falls back to the first league when the last-viewed one is no longer a membership', async () => {
    stubAuth('some-old-league');
    renderWithLeague([MOCK_LEAGUE]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon'));
  });

  it('rebinds activeSlug when a league is selected, and persists the choice', async () => {
    const second = { ...MOCK_LEAGUE, slug: 'friends-league', name: 'Friends League' };
    renderWithLeague([MOCK_LEAGUE, second]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon'));

    fireEvent.click(screen.getByRole('button', { name: 'select friends' }));

    // Home's cards open a league other than the bound one, so the choice has to
    // re-render — writing the recency store alone would not.
    expect(screen.getByTestId('active-slug').textContent).toBe('friends-league');
    expect(localStorage.setItem).toHaveBeenCalledWith(
      LAST_VIEWED_LEAGUE_KEY,
      JSON.stringify({ slug: 'friends-league', name: 'Friends League' }),
    );
  });

  it('ignores a selection the member is not a member of', async () => {
    renderWithLeague([MOCK_LEAGUE]);
    await waitFor(() => expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon'));

    fireEvent.click(screen.getByRole('button', { name: 'select stranger' }));

    expect(screen.getByTestId('active-slug').textContent).toBe('the-coupon');
  });

  it('useLeague throws when used outside LeagueProvider', () => {
    const ThrowingComponent = () => {
      useLeague();
      return null;
    };
    expect(() =>
      render(
        <MemoryRouter>
          <ThrowingComponent />
        </MemoryRouter>,
      ),
    ).toThrow('useLeague must be used within LeagueProvider');
  });
});
