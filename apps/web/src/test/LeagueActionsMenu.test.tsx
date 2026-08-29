import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

function trigger() {
  return screen.getByRole('button', { name: /league actions/i });
}

describe('LeagueActionsMenu', () => {
  it('hides admin member management from regular members', () => {
    renderMenu(false);

    expect(screen.queryByRole('link', { name: /members/i })).toBeNull();
    expect(screen.getByRole('button', { name: /leave/i })).toBeTruthy();
  });

  it('leaves a member their single action in the open', () => {
    // One button beside a title never overflowed. Collapsing it would cost a tap and
    // save no width, so a member must not be given a menu to open.
    renderMenu(false);

    expect(screen.queryByRole('button', { name: /league actions/i })).toBeNull();
    expect(screen.getByRole('button', { name: /leave/i })).toBeTruthy();
  });

  it('collapses every admin action behind one trigger', () => {
    renderMenu(true);

    expect(trigger()).toBeTruthy();
    for (const label of [/members/i, /requests/i, /invites/i, /settings/i, /delete/i]) {
      expect(screen.queryByRole('link', { name: label })).toBeNull();
      expect(screen.queryByRole('menuitem', { name: label })).toBeNull();
    }
  });

  it('reveals the admin actions when opened', async () => {
    const user = userEvent.setup();
    renderMenu(true);

    await user.click(trigger());

    expect(screen.getByRole('menuitem', { name: /members/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/members',
    );
    expect(screen.getByRole('menuitem', { name: /requests/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/requests',
    );
    expect(screen.getByRole('menuitem', { name: /invites/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/invites',
    );
    expect(screen.getByRole('menuitem', { name: /settings/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/settings',
    );
    // Batch 94 — the league's own audit trail, reachable from the same menu as the
    // actions that write to it.
    expect(screen.getByRole('menuitem', { name: /activity/i }).getAttribute('href')).toBe(
      '/leagues/the-coupon/admin/audit-log',
    );
    expect(screen.getByRole('menuitem', { name: /leave/i })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /delete/i })).toBeTruthy();
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    renderMenu(true);

    await user.click(trigger());
    expect(screen.getByRole('menuitem', { name: /members/i })).toBeTruthy();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menuitem', { name: /members/i })).toBeNull();
    expect(trigger()).toHaveFocus();
  });

  it('opens the delete confirmation from inside the menu', async () => {
    const user = userEvent.setup();
    renderMenu(true);

    await user.click(trigger());
    await user.click(screen.getByRole('menuitem', { name: /delete/i }));

    // The menu is not itself a confirmation — the typed dialog still stands between an
    // admin and a deleted league.
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(screen.getByPlaceholderText(/type league name to confirm/i)).toBeTruthy();
  });
});
