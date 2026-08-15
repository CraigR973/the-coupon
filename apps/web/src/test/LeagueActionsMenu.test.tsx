import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LeagueActionsMenu } from '@/components/LeagueActionsMenu';

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

function renderMenu(isAdmin: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LeagueActionsMenu slug="the-coupon" leagueName="The Coupon" isAdmin={isAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LeagueActionsMenu', () => {
  it('hides admin member management from regular members', () => {
    renderMenu(false);

    expect(screen.queryByRole('link', { name: /members/i })).toBeNull();
    expect(screen.getByRole('button', { name: /leave/i })).toBeTruthy();
  });

  it('shows member management to admins', () => {
    renderMenu(true);

    expect(screen.getByRole('link', { name: /members/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/members',
    );
  });
});
