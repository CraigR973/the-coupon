import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminDashboardPage } from '@/pages/admin/DashboardPage';
import { SyncPage } from '@/pages/admin/SyncPage';
import { AdminResultsPage } from '@/pages/admin/ResultsPage';
import type { AdminDashboard, AdminPendingRound, AdminSyncJobs } from '@/lib/types';

/**
 * Batch 69 — the operational screens.
 *
 * The load-bearing one is Sync: a manual trigger spends a shared, rate-limited budget
 * that the scheduler's own jobs are sized against, and exhaustion is silent. The button
 * has to say what it costs *before* it is pressed, and confirm.
 */

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch };
});

const { toastSuccess, toastError } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }));

function renderPage(node: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Dashboard ─────────────────────────────────────────────────────────────────

const DASHBOARD: AdminDashboard = {
  active_members: 12,
  members_awaiting_pin: 1,
  leagues: 2,
  upcoming_locks: [
    {
      league_slug: 'the-coupon',
      league_name: 'The Coupon',
      gameweek_id: 'gw-next',
      starts_on: '2027-03-13',
      locks_at_utc: '2027-03-13T14:30:00Z',
      picks_in: 9,
      members: 12,
    },
  ],
  stuck_rounds: [
    {
      league_slug: 'the-coupon',
      league_name: 'The Coupon',
      gameweek_id: 'gw-stuck',
      starts_on: '2027-03-06',
      locks_at_utc: '2027-03-06T14:30:00Z',
      pending_picks: 3,
    },
  ],
  recent_audit: [
    {
      id: 'a1',
      actor_name: 'Gaffer',
      action_type: 'player_pin_reset',
      target_table: 'profiles',
      target_id: 'p1',
      timestamp: '2027-03-06T09:00:00Z',
    },
  ],
  scheduler: { enabled: true, running: false, jobs: [{ id: 'settle_gameweeks', next_run_utc: null }] },
  odds_budget: {
    live: true,
    hour_used: 82,
    hour_limit: 100,
    hour_remaining: 18,
    day_used: 310,
    day_limit: 500,
    day_remaining: 190,
    rate_limited_for: null,
  },
};

describe('the admin dashboard', () => {
  it('leads with the rounds that are stuck, because nothing else will clear them', async () => {
    apiFetch.mockResolvedValue(DASHBOARD);

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText('3 pending')).toBeTruthy();
    expect(screen.getByRole('link', { name: /enter the result/i }).getAttribute('href')).toBe(
      '/admin/results',
    );
  });

  it('says when the scheduler is configured on but is not running', async () => {
    // The case worth knowing about: a container whose scheduler never started. Reporting
    // the *setting* would say everything is fine.
    apiFetch.mockResolvedValue(DASHBOARD);

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText('Not running')).toBeTruthy();
    expect(screen.getByText(/configured on/i)).toBeTruthy();
  });

  it('shows how much of the odds provider’s plan is left', async () => {
    // Batch 114. On 2026-09-05 the hourly allowance was gone by 08:06 and the first anyone
    // knew was a member being refused a pick on a round that locked five hours later.
    apiFetch.mockResolvedValue(DASHBOARD);

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText('This hour')).toBeTruthy();
    expect(screen.getByLabelText('This hour: 82 of 100 requests used')).toBeTruthy();
    expect(screen.getByLabelText('Today: 310 of 500 requests used')).toBeTruthy();
  });

  it('says so while a rate limit is being held off', async () => {
    apiFetch.mockResolvedValue({
      ...DASHBOARD,
      odds_budget: { ...DASHBOARD.odds_budget, rate_limited_for: 42.4 },
    });

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText(/rate limited/i)).toBeTruthy();
    expect(screen.getByText(/holding off 43s/i)).toBeTruthy();
  });

  it('renders against an API that predates the budget counters', async () => {
    // The web app deploys from `main` while the API waits for `/ship-prod`, so this
    // screen has to come up without the field at all.
    const { odds_budget: _omitted, ...older } = DASHBOARD;
    apiFetch.mockResolvedValue(older);

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText('3 pending')).toBeTruthy();
    expect(screen.queryByText('This hour')).toBeNull();
  });

  it('counts the members waiting to choose a PIN', async () => {
    apiFetch.mockResolvedValue(DASHBOARD);

    renderPage(<AdminDashboardPage />);

    expect(await screen.findByText('Awaiting PIN')).toBeTruthy();
    expect(screen.getByText('reset, not yet chosen')).toBeTruthy();
  });
});

// ── Sync ──────────────────────────────────────────────────────────────────────

const JOBS: AdminSyncJobs = {
  hourly_budget: 100,
  budget_limit: '2/hour;3/day',
  jobs: [
    {
      key: 'refresh-slate',
      label: "Refresh this week's slate",
      summary: 'Top up the card.',
      provider_requests: 30,
      spends_budget: true,
      budget_units: 1,
      next_run_utc: '2027-03-06T09:00:00Z',
    },
    {
      key: 'sync-football',
      label: 'Sync football data',
      summary: 'Free — FotMob is unmetered.',
      provider_requests: 0,
      spends_budget: false,
      budget_units: 0,
      next_run_utc: null,
    },
  ],
};

describe('the sync screen', () => {
  it('shows what a run costs against the plan, not just a number', async () => {
    apiFetch.mockResolvedValue(JOBS);

    renderPage(<SyncPage />);

    expect(await screen.findByText(/~30 requests/)).toBeTruthy();
    expect(screen.getByText(/100 requests an hour/)).toBeTruthy();
    expect(screen.getByText('Free')).toBeTruthy();
  });

  it('confirms before spending the shared budget', async () => {
    apiFetch.mockResolvedValue(JOBS);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderPage(<SyncPage />);
    const buttons = await screen.findAllByRole('button', { name: /run now/i });
    fireEvent.click(buttons[0]);

    expect(confirm).toHaveBeenCalled();
    expect(String(confirm.mock.calls[0][0])).toContain('shared with the scheduler');
    // Declining runs nothing — only the initial list fetch happened.
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });

  it('does not stop to confirm a job that spends nothing', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.endsWith('/run') ? { key: 'sync-football', ok: true } : JOBS,
    );
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderPage(<SyncPage />);
    const buttons = await screen.findAllByRole('button', { name: /run now/i });
    fireEvent.click(buttons[1]);

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(confirm).not.toHaveBeenCalled();
  });

  it('reports a job that ran and failed as a failure, not as an error', async () => {
    // `ok: false` is a job that ran and reported failure — a 200 carrying bad news. It
    // must not read as "the request broke", which is a different thing to go and fix.
    apiFetch.mockImplementation(async (path: string) =>
      path.endsWith('/run') ? { key: 'sync-football', ok: false } : JOBS,
    );

    renderPage(<SyncPage />);
    const buttons = await screen.findAllByRole('button', { name: /run now/i });
    fireEvent.click(buttons[1]);

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0])).toContain('check the logs');
  });
});

// ── Results ───────────────────────────────────────────────────────────────────

const PENDING: AdminPendingRound[] = [
  {
    league_slug: 'the-coupon',
    league_name: 'The Coupon',
    gameweek_id: 'gw-stuck',
    starts_on: '2027-03-06',
    status: 'locked',
    locks_at_utc: '2027-03-06T14:30:00Z',
    fixtures: [
      {
        fixture_id: 'fx1',
        provider_event_id: 'ev1',
        home: 'Forfar',
        away: 'Brechin',
        competition: 'Scottish League Two',
        kickoff_utc: '2027-03-06T15:00:00Z',
        pending_picks: 2,
      },
    ],
  },
];

describe('the manual results screen', () => {
  it('asks for a scoreline rather than a set of market verdicts', async () => {
    apiFetch.mockResolvedValue(PENDING);

    renderPage(<AdminResultsPage />);

    expect(await screen.findByLabelText('Forfar goals')).toBeTruthy();
    expect(screen.getByLabelText('Brechin goals')).toBeTruthy();
    expect(screen.getByLabelText(/not played/i)).toBeTruthy();
  });

  it('sends the score it was given', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.endsWith('/settle') ? { picks_resolved: 2, settled: true } : PENDING,
    );

    renderPage(<AdminResultsPage />);
    fireEvent.change(await screen.findByLabelText('Forfar goals'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Brechin goals'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /settle round/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const settleCall = apiFetch.mock.calls.find(([path]) => String(path).endsWith('/settle'));
    expect(settleCall).toBeTruthy();
    expect(JSON.parse(String(settleCall![1].body))).toEqual({
      results: [{ fixture_id: 'fx1', home_goals: 2, away_goals: 1 }],
    });
  });

  it('sends a void rather than a score for a game that was not played', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.endsWith('/settle') ? { picks_resolved: 2, settled: true } : PENDING,
    );

    renderPage(<AdminResultsPage />);
    fireEvent.click(await screen.findByLabelText(/not played/i));
    fireEvent.click(screen.getByRole('button', { name: /settle round/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const settleCall = apiFetch.mock.calls.find(([path]) => String(path).endsWith('/settle'));
    expect(JSON.parse(String(settleCall![1].body))).toEqual({
      results: [{ fixture_id: 'fx1', void: true }],
    });
  });

  it('refuses to send an empty settlement', async () => {
    apiFetch.mockResolvedValue(PENDING);

    renderPage(<AdminResultsPage />);
    fireEvent.click(await screen.findByRole('button', { name: /settle round/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(apiFetch.mock.calls.some(([path]) => String(path).endsWith('/settle'))).toBe(false);
  });

  it('says so when nothing is waiting on a result', async () => {
    apiFetch.mockResolvedValue([]);

    renderPage(<AdminResultsPage />);

    expect(await screen.findByText(/every locked round has settled/i)).toBeTruthy();
  });
});
