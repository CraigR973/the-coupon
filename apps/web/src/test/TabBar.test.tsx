import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { HTMLAttributes, ReactNode } from 'react';
import { TabBar } from '@/components/TabBar';

const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('framer-motion', () => ({
  motion: {
    span: ({
      children,
      layoutId: _layoutId,
      transition: _transition,
      ...props
    }: HTMLAttributes<HTMLSpanElement> & { layoutId?: string; transition?: unknown }) => (
      <span {...props}>{children}</span>
    ),
  },
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    player: { id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' },
    logout: vi.fn(),
  }),
}));

const { league } = vi.hoisted(() => ({
  league: { activeSlug: 'the-coupon', hasLeagues: true },
}));

vi.mock('@/contexts/LeagueContext', () => ({ useLeague: () => league }));

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: ReactNode; open: boolean }) =>
    open ? <div role="dialog">{children}</div> : null,
}));

beforeEach(() => {
  league.activeSlug = 'the-coupon';
  league.hasLeagues = true;
});

describe('TabBar mobile positioning', () => {
  it('stays pinned to the bottom of the mobile viewport', () => {
    const { container } = render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>,
    );

    const nav = container.querySelector('nav[aria-label="Primary"]');

    expect(nav?.className).toContain('fixed');
    expect(nav?.className).toContain('bottom-0');
    expect(nav?.className).toContain('inset-x-0');
    expect(nav?.className).toContain('z-tabbar');
  });

  it('reaches Football Stats without a slug in the path', () => {
    render(
      <MemoryRouter initialEntries={['/football']}>
        <TabBar />
      </MemoryRouter>,
    );

    const football = screen.getByRole('link', { name: /football stats/i });
    const coupon = screen.getByRole('link', { name: /^coupon$/i });

    expect(football.getAttribute('href')).toBe('/football');
    expect(football.getAttribute('aria-current')).toBe('page');
    expect(coupon.getAttribute('aria-current')).toBeNull();
  });

  // ── Batch 30: slug-addressed coupon ────────────────────────────────────────

  it('points Coupon at the bound league, and Football Stats at no league at all', () => {
    league.activeSlug = 'work-league';
    render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /^coupon$/i }).getAttribute('href')).toBe(
      '/leagues/work-league/predictions',
    );
    // Batch 51: the same address whichever league is bound, because it reads the pool.
    expect(screen.getByRole('link', { name: /football stats/i }).getAttribute('href')).toBe(
      '/football',
    );
  });

  it('falls back to the slug-less path while the member has no league to address', () => {
    league.hasLeagues = false;
    render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /^coupon$/i }).getAttribute('href')).toBe(
      '/predictions',
    );
    // Football Stats never needed one, so it is reachable from the very first frame.
    expect(screen.getByRole('link', { name: /football stats/i }).getAttribute('href')).toBe(
      '/football',
    );
  });

  it('lights Coupon for any league, not only the bound one', () => {
    render(
      <MemoryRouter initialEntries={['/leagues/work-league/predictions/coupon']}>
        <TabBar />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /coupon/i }).getAttribute('aria-current')).toBe('page');
    // ...and Leagues stays dark, though the coupon now lives under /leagues too.
    expect(screen.getByRole('link', { name: /leagues/i }).getAttribute('aria-current')).toBeNull();
  });

  it('still lights Leagues on the rest of the hub', () => {
    render(
      <MemoryRouter initialEntries={['/leagues/work-league/leaderboard']}>
        <TabBar />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /leagues/i }).getAttribute('aria-current')).toBe(
      'page',
    );
  });

  it('sends My profile to the career record, not to the active league', () => {
    render(
      <MemoryRouter>
        <TabBar />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /more/i }));
    const profile = screen.getByRole('button', { name: /my profile/i });
    fireEvent.click(profile);

    expect(navigate).toHaveBeenCalledWith('/profile');
  });

  it('marks More as current while the career profile is open', () => {
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <TabBar />
      </MemoryRouter>,
    );

    const more = screen.getByRole('button', { name: /more/i });
    expect(more.querySelector('span')?.className).toContain('bg-primary');
  });
});
