import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { LeagueProvider } from '@/contexts/LeagueContext';
import {
  LeagueAuditLogPage,
  actionLabel,
  describeChanges,
} from '@/pages/LeagueAuditLogPage';

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

function entry(overrides: Record<string, unknown> = {}) {
  return {
    id: `e-${Math.random().toString(16).slice(2)}`,
    actor_name: 'Alice',
    action_type: 'member_removed',
    target_table: 'league_memberships',
    target_id: 'l1',
    changes: { player_id: 'p9' },
    timestamp: '2026-08-28T14:30:00',
    ...overrides,
  };
}

/** Stub the audit-log fetch, capturing every URL the page asks for. */
function stubApi(pages: Record<number, unknown>): { urls: string[] } {
  const urls: string[] = [];
  vi.stubGlobal('fetch', (url: string) => {
    urls.push(url);
    if (url.includes('/audit-log')) {
      const page = Number(new URL(url, 'http://test').searchParams.get('page') ?? '1');
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(pages[page]),
      });
    }
    // LeagueProvider wraps the page in the app and reads the member's leagues; without
    // this it dereferences an empty list and the render throws before the page mounts.
    if (url.includes('/api/v1/leagues/mine')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve([{ slug: 'the-coupon', name: 'The Coupon' }]),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
  });
  return { urls };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/leagues/the-coupon/admin/audit-log']}>
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <LeagueProvider>
            <Routes>
              <Route path="/leagues/:slug/admin/audit-log" element={<LeagueAuditLogPage />} />
            </Routes>
          </LeagueProvider>
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('LeagueAuditLogPage — the league its own trail (Batch 94)', () => {
  it('asks only for this league, and renders what came back', async () => {
    const api = stubApi({
      1: { entries: [entry()], total: 1, page: 1, page_size: 25 },
    });
    renderPage();

    expect(await screen.findByText('Member removed')).toBeTruthy();
    expect(screen.getByText('Alice')).toBeTruthy();
    // The route is league-scoped: nothing here may ask for a global feed.
    expect(api.urls.some((u) => u.includes('/api/v1/leagues/the-coupon/audit-log'))).toBe(true);
    expect(api.urls.some((u) => u.includes('/admin/dashboard'))).toBe(false);
  });

  it('shows the changes payload, which is the "who did what to whom"', async () => {
    stubApi({
      1: {
        entries: [entry({ changes: { player_id: 'p9' } })],
        total: 1,
        page: 1,
        page_size: 25,
      },
    });
    renderPage();

    expect(await screen.findByText(/player id: p9/i)).toBeTruthy();
  });

  it('pages rather than stopping at the first 25', async () => {
    const api = stubApi({
      1: {
        entries: [entry({ action_type: 'league_created' })],
        total: 30,
        page: 1,
        page_size: 25,
      },
      2: {
        entries: [entry({ action_type: 'member_promoted' })],
        total: 30,
        page: 2,
        page_size: 25,
      },
    });
    renderPage();

    expect(await screen.findByText('League created')).toBeTruthy();
    expect(screen.getByText(/showing 1–25 of 30/i)).toBeTruthy();
    expect((screen.getByRole('button', { name: /previous/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.click(screen.getByRole('button', { name: /next/i }));

    expect(await screen.findByText('Promoted to admin')).toBeTruthy();
    await waitFor(() => expect(api.urls.some((u) => u.includes('page=2'))).toBe(true));
    expect(screen.getByText(/showing 26–30 of 30/i)).toBeTruthy();
    expect((screen.getByRole('button', { name: /next/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it('says so when a league has no history yet', async () => {
    stubApi({ 1: { entries: [], total: 0, page: 1, page_size: 25 } });
    renderPage();

    expect(await screen.findByText(/nothing has been recorded/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /next/i })).toBeNull();
  });
});

describe('LeagueAuditLogPage — rendering helpers', () => {
  it('names every action a league admin can cause', () => {
    expect(actionLabel('member_promoted')).toBe('Promoted to admin');
    expect(actionLabel('league_privacy_changed')).toBe('Privacy changed');
    expect(actionLabel('join_request_rejected')).toBe('Join request rejected');
  });

  it('humanises an action it has never seen rather than showing the raw enum', () => {
    expect(actionLabel('something_new_entirely')).toBe('Something new entirely');
  });

  it('drops the keys that say nothing to someone reading their own league', () => {
    // `league_slug` is how the reader found the row; `scope` is a site-console detail.
    expect(describeChanges({ league_slug: 'the-coupon', scope: 'site' })).toBeNull();
    expect(describeChanges({ league_slug: 'the-coupon', player_id: 'p9' })).toBe('player id: p9');
    expect(describeChanges(null)).toBeNull();
  });
});
