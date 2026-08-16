import { describe, expect, it, vi } from 'vitest';
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

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: ReactNode; open: boolean }) =>
    open ? <div role="dialog">{children}</div> : null,
}));

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

  it('puts Football in primary navigation', () => {
    render(
      <MemoryRouter initialEntries={['/predictions/football']}>
        <TabBar />
      </MemoryRouter>,
    );

    const football = screen.getByRole('link', { name: /football/i });
    const coupon = screen.getByRole('link', { name: /coupon/i });

    expect(football.getAttribute('href')).toBe('/predictions/football');
    expect(football.getAttribute('aria-current')).toBe('page');
    expect(coupon.getAttribute('aria-current')).toBeNull();
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
