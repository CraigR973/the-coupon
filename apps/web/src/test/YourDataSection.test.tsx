import { describe, it, expect, vi, beforeEach, afterEach, onTestFinished } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { YourDataSection } from '@/components/YourDataSection';

// Batch 136 — a member takes a copy of their data, or deletes their account.

const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({ id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' });

type Answer = { status: number; body?: unknown };

function makeStorage() {
  const values = new Map<string, string>([
    ['coupon_player', STORED_PLAYER],
    ['coupon_access', FAKE_JWT],
    ['coupon_refresh', 'refresh-token'],
  ]);
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => void values.set(key, value)),
    removeItem: vi.fn((key: string) => void values.delete(key)),
    clear: vi.fn(() => values.clear()),
  };
}

function renderSection(answers: Record<string, Answer>) {
  const storage = makeStorage();
  vi.stubGlobal('localStorage', storage);
  const fetchMock = vi.fn((url: string) => {
    const route = Object.keys(answers).find((path) => url.includes(path));
    const answer: Answer = route ? answers[route] : { status: 200, body: {} };
    return Promise.resolve({
      ok: answer.status >= 200 && answer.status < 300,
      status: answer.status,
      json: () => Promise.resolve(answer.body ?? {}),
    });
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/settings']}>
        <AuthProvider>
          <Routes>
            <Route path="/settings" element={<YourDataSection />} />
            <Route path="/login" element={<p>Sign-in screen</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, storage };
}

function openAndEnterPin(pin = '8351') {
  fireEvent.click(screen.getByRole('button', { name: /delete my account$/i }));
  fireEvent.change(screen.getByLabelText('Confirm PIN digit 1'), { target: { value: pin } });
}

function deleteCall(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.find(([url]) => String(url).includes('/api/v1/me/delete'));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('YourDataSection', () => {
  it('downloads the export as a dated JSON file', async () => {
    const createObjectURL = vi.fn(() => 'blob:export');
    const revokeObjectURL = vi.fn();
    const original = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    onTestFinished(() => {
      URL.createObjectURL = original.create;
      URL.revokeObjectURL = original.revoke;
    });
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });
    const { fetchMock } = renderSection({
      '/api/v1/me/export': { status: 200, body: { profile: { display_name: 'Alice' }, picks: [] } },
    });

    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/me/export'))).toBe(true);
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked[0].download).toMatch(/^the-coupon-my-data-\d{4}-\d{2}-\d{2}\.json$/);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export');
  });

  it('deletes the account with the PIN, signs out and leaves for the sign-in screen', async () => {
    const { fetchMock, storage } = renderSection({ '/api/v1/me/delete': { status: 204 } });

    openAndEnterPin();
    fireEvent.click(screen.getByRole('button', { name: /delete my account permanently/i }));

    expect(await screen.findByText('Sign-in screen')).toBeTruthy();
    const [, init] = deleteCall(fetchMock) ?? [];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ pin: '8351' });
    expect(storage.removeItem).toHaveBeenCalledWith('coupon_access');
  });

  it('shows why a league admin cannot leave yet, where they are looking, and stays put', async () => {
    const detail = "You're the only admin of Friday League. Make another member an admin first, so the league still has someone to run it.";
    const { storage } = renderSection({ '/api/v1/me/delete': { status: 409, body: { detail } } });

    openAndEnterPin();
    fireEvent.click(screen.getByRole('button', { name: /delete my account permanently/i }));

    expect((await screen.findByRole('alert')).textContent).toBe(detail);
    expect(screen.queryByText('Sign-in screen')).toBeNull();
    expect(storage.removeItem).not.toHaveBeenCalledWith('coupon_access');
    expect((screen.getByLabelText('Confirm PIN digit 1') as HTMLInputElement).value).toBe('');
  });

  it('a wrong PIN says so without signing the member out', async () => {
    const { storage } = renderSection({
      '/api/v1/me/delete': { status: 403, body: { detail: "That PIN isn't right." } },
    });

    openAndEnterPin('0000');
    fireEvent.click(screen.getByRole('button', { name: /delete my account permanently/i }));

    expect((await screen.findByRole('alert')).textContent).toBe("That PIN isn't right.");
    expect(storage.removeItem).not.toHaveBeenCalledWith('coupon_access');
  });

  it('cannot be confirmed without a full PIN, and Cancel closes it', () => {
    const { fetchMock } = renderSection({});

    fireEvent.click(screen.getByRole('button', { name: /delete my account$/i }));
    const confirm = screen.getByRole('button', { name: /delete my account permanently/i });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('button', { name: /delete my account permanently/i })).toBeNull();
    expect(deleteCall(fetchMock)).toBeUndefined();
  });
});
