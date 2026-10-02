import { createHash } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MyLeaguesPage } from '@/pages/MyLeaguesPage';
import { LeagueMembersPage } from '@/pages/LeagueMembersPage';
import { LeagueAuditLogPage } from '@/pages/LeagueAuditLogPage';
import { PlayersPage } from '@/pages/admin/AdminPlayersPage';
import { AdminDashboardPage } from '@/pages/admin/AdminDashboardPage';
import type { AdminDashboard } from '@/lib/types';

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch };
});

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    player: { id: 'admin-1', displayName: 'Gaffer', role: 'admin', timezone: 'UTC' },
  }),
}));

vi.mock('@/hooks/useRouteLeague', () => ({
  useRouteLeague: () => ({ slug: 'the-coupon', name: 'The Coupon' }),
}));

const EMPTY_DASHBOARD: AdminDashboard = {
  active_members: 0,
  members_awaiting_pin: 0,
  leagues: 0,
  upcoming_locks: [],
  stuck_rounds: [],
  recent_audit: [],
  scheduler: { enabled: false, running: false, jobs: [] },
};

function renderPage(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function hashMarkup(markup: string): string {
  return createHash('sha256').update(markup).digest('hex');
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('request failures stay distinct from successful empty states', () => {
  const cases: Array<{
    name: string;
    node: React.ReactElement;
    errorTitle: string;
    emptyValue: unknown;
    emptyText: RegExp;
  }> = [
    {
      name: 'My Leagues',
      node: <MyLeaguesPage />,
      errorTitle: "Couldn't load your leagues",
      emptyValue: [],
      emptyText: /not in any leagues yet/i,
    },
    {
      name: 'league members',
      node: <LeagueMembersPage />,
      errorTitle: "Couldn't load the members",
      emptyValue: [],
      emptyText: /no members to show/i,
    },
    {
      name: 'league activity',
      node: <LeagueAuditLogPage />,
      errorTitle: "Couldn't load league activity",
      emptyValue: { entries: [], total: 0, page: 1, page_size: 25 },
      emptyText: /nothing has been recorded/i,
    },
    {
      name: 'site-admin players',
      node: <PlayersPage />,
      errorTitle: "Couldn't load the players",
      emptyValue: [],
      emptyText: /no players match/i,
    },
    {
      name: 'admin dashboard',
      node: <AdminDashboardPage />,
      errorTitle: "Couldn't load the admin dashboard",
      emptyValue: EMPTY_DASHBOARD,
      emptyText: /nothing is waiting on a result/i,
    },
  ];

  for (const testCase of cases) {
    it(`${testCase.name} shows a retryable error, then its real empty state`, async () => {
      apiFetch.mockRejectedValueOnce(new Error('Internal Server Error'));
      const { container } = renderPage(testCase.node);

      const error = await screen.findByTestId('query-error-state');
      expect(error).toHaveTextContent(testCase.errorTitle);
      expect(screen.queryByText(testCase.emptyText)).not.toBeInTheDocument();
      const errorHash = hashMarkup(container.innerHTML);

      apiFetch.mockResolvedValueOnce(testCase.emptyValue);
      fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

      expect(await screen.findByText(testCase.emptyText)).toBeInTheDocument();
      expect(screen.queryByTestId('query-error-state')).not.toBeInTheDocument();
      expect(hashMarkup(container.innerHTML)).not.toBe(errorHash);
      expect(apiFetch).toHaveBeenCalledTimes(2);
    });
  }
});
