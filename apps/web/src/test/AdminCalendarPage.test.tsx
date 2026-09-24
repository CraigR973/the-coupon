import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CalendarPage } from '@/pages/admin/AdminCalendarPage';
import type { AdminSeasonCalendar } from '@/lib/types';

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

const CALENDAR: AdminSeasonCalendar = {
  season: 2026,
  label: '2026/27',
  week_one_anchor: '2026-08-08',
  weeks: [
    { starts_on: '2026-08-08', label: '1', is_extra: false },
    { starts_on: '2026-09-05', label: '5', is_extra: false },
    { starts_on: '2026-09-06', label: '5b', is_extra: true },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('the deployment season calendar', () => {
  it('shows the global anchor and a suffixed extra week', async () => {
    apiFetch.mockResolvedValue(CALENDAR);
    renderPage();

    expect(await screen.findByText('Gameweek 5b')).toBeTruthy();
    await waitFor(() =>
      expect((screen.getByLabelText('Week 1 Saturday') as HTMLInputElement).value).toBe(
        '2026-08-08',
      ),
    );
    expect(screen.getByText(/offered to every league/i)).toBeTruthy();
  });

  it('declares an extra without pretending it materialised immediately', async () => {
    apiFetch.mockImplementation(async (path: string) =>
      path.endsWith('/extra-weeks') ? CALENDAR : { ...CALENDAR, weeks: CALENDAR.weeks.slice(0, 2) },
    );
    renderPage();
    await screen.findByText('No extra weeks declared.');
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-09-06' } });
    fireEvent.click(screen.getByRole('button', { name: /declare for every league/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(String(toastSuccess.mock.calls[0][0])).toContain('declared for every league');
    expect(apiFetch).toHaveBeenLastCalledWith(
      '/api/v1/admin/calendar/extra-weeks',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('surfaces a refused withdrawal when any league has a pick', async () => {
    apiFetch.mockImplementation(async (_path: string, options?: RequestInit) => {
      if (options?.method === 'DELETE') throw new Error('EXTRA_WEEK_HAS_PICKS');
      return CALENDAR;
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw 2026-09-06' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('EXTRA_WEEK_HAS_PICKS'));
  });
});
