import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NotificationBell } from '@/components/NotificationBell';

function renderBell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.setItem(
    'coupon_access',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake',
  );
});
afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('NotificationBell', () => {
  it('shows an unread league event and marks it read when opened', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/read')) return { ok: true, status: 200, json: async () => ({ read_count: 1 }) };
      return { ok: true, status: 200, json: async () => ({
        unread_count: 1,
        items: [{
          id: 'n1', kind: 'pick_changed', title: 'Friday League', body: 'Alex moved a pick',
          url: '/leagues/friday/predictions', created_at: '2026-10-10T12:00:00Z', read_at: null,
        }],
      }) };
    });
    vi.stubGlobal('fetch', fetchMock);

    renderBell();
    fireEvent.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }));
    expect(await screen.findByText('Alex moved a pick')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Friday League/ })).toHaveAttribute(
      'href', '/leagues/friday/predictions',
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/notifications/inbox/read'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('marks an event read when its request finishes after the bell opens', async () => {
    let resolveInbox!: (value: object) => void;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('/read')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ read_count: 1 }) });
      }
      return new Promise<object>((resolve) => { resolveInbox = resolve; });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderBell();
    fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));
    expect(await screen.findByText('Loading league updates…')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    resolveInbox({
      ok: true,
      status: 200,
      json: async () => ({
        unread_count: 1,
        items: [{
          id: 'n2', kind: 'pick_made', title: 'Friday League', body: 'Alex made a pick',
          url: '/leagues/friday/predictions', created_at: '2026-10-10T12:00:00Z', read_at: null,
        }],
      }),
    });
    expect(await screen.findByText('Alex made a pick')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/notifications/inbox/read'),
      expect.objectContaining({ method: 'POST' }),
    ));
  });

  it('keeps the old home unchanged while the API route is absent', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false, status: 404, json: async () => ({ detail: 'Not found' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    renderBell();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByTestId('notification-bell')).not.toBeInTheDocument();
    });
  });
});
