import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import { TopBar } from '@/components/TopBar';

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
}));

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({
  id: 'p1',
  displayName: 'Alice',
  role: 'player',
  timezone: 'UTC',
});

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

function renderTopBar(initialEntry = '/') {
  stubAuth();
  vi.stubGlobal('fetch', () =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve([
          {
            slug: 'the-coupon',
            name: 'The Coupon',
            description: null,
            privacy: 'private',
            member_count: 2,
            max_members: null,
            pick_scope: 'selection',
            created_at: '2026-08-01T00:00:00Z',
          },
        ]),
    }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/" element={<TopBar />} />
              <Route path="/predictions/football" element={<TopBar />} />
              <Route path="/settings" element={<div>Settings route</div>} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TopBar avatar menu', () => {
  it('includes a one-tap Settings entry in the avatar dropdown', () => {
    renderTopBar();

    fireEvent.click(screen.getAllByRole('button', { name: /account menu/i })[0]);
    expect(screen.queryByRole('link', { name: /about/i })).toBeNull();
    expect(screen.getAllByRole('link', { name: /my profile/i })[0]).toBeTruthy();
    fireEvent.click(screen.getAllByRole('link', { name: /settings/i })[0]);

    expect(screen.getByText('Settings route')).toBeTruthy();
  });

  it('sends My profile to the career record, not to the active league', () => {
    renderTopBar();

    fireEvent.click(screen.getAllByRole('button', { name: /account menu/i })[0]);

    expect(screen.getAllByRole('link', { name: /my profile/i })[0].getAttribute('href')).toBe(
      '/profile',
    );
  });

  it('uses the larger compact logo size in the top bar only', () => {
    const { container } = renderTopBar();

    // The compact brand mark is now an inline themed SVG (was a navy-tile <img>).
    const brandIcons = Array.from(container.querySelectorAll('svg[width="46"]'));

    expect(brandIcons.length).toBeGreaterThan(0);
    brandIcons.forEach((icon) => {
      expect(icon).toHaveAttribute('width', '46');
      expect(icon).toHaveAttribute('height', '46');
    });
  });

  it('adds extra iPhone safe-area clearance on the mobile header', () => {
    const { container } = renderTopBar();

    const header = container.querySelector('header');
    const mobileBrandLink = container.querySelector('a[aria-label="Home"].absolute');
    const navRow = container.querySelector('header > div');

    expect(header?.className).toContain('pt-[calc(env(safe-area-inset-top,0px)+1rem)]');
    expect(navRow?.className).toContain('h-16');
    expect(mobileBrandLink?.className).toContain('inset-y-0');
  });

  it('puts Football in desktop navigation', () => {
    renderTopBar('/predictions/football');

    const football = screen.getByRole('link', { name: /^football$/i });
    const coupon = screen.getByRole('link', { name: /^coupon$/i });

    expect(football.getAttribute('href')).toBe('/predictions/football');
    expect(football.getAttribute('aria-current')).toBe('page');
    expect(football.className).toContain('bg-primary/15');
    expect(football.className).toContain('text-primary');
    expect(coupon.getAttribute('aria-current')).toBeNull();
    expect(coupon.className).not.toContain('bg-primary/15');
  });
});
