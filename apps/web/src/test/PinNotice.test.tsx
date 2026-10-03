import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import { PinNotice } from '@/components/PinNotice';
import { ApiError } from '@/lib/api';
import type { PinEvents } from '@/lib/types';

/**
 * Batch 179 — a member is told in the app when their PIN was reset or set. The push may
 * not have reached them; this lists it on the next load with a session, once per device.
 */

const { apiFetch, auth } = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  auth: { current: null as null | { player: { id: string; timezone: string } | null } },
}));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch };
});
vi.mock('@/contexts/AuthContext', () => ({ useOptionalAuth: () => auth.current }));

const EVENTS_URL = '/api/v1/me/pin-events';
const TITLE = 'Your PIN changed';
const MEMBER = { id: 'member-1', timezone: 'Europe/London' };
const SEEN_KEY = `coupon.pin-notice.seen.${MEMBER.id}`;

// 3 Oct 2026 is British Summer Time, so 13:05 UTC reads as 14:05 in London.
const RESET = { kind: 'reset' as const, at: '2026-10-03T13:05:00Z' };
const SET = { kind: 'set' as const, at: '2026-10-03T13:12:00Z' };
const JOURNEY: PinEvents = { events: [SET, RESET] };

/** Disabled because jsdom cannot evaluate CSS custom properties; see accessibility.test. */
const AXE_CONFIG = { rules: { 'color-contrast': { enabled: false } } };

function serve(state: PinEvents | Error) {
  apiFetch.mockImplementation(async (path: string) => {
    if (path === EVENTS_URL) {
      if (state instanceof Error) throw state;
      return state;
    }
    throw new Error(`unexpected request ${path}`);
  });
}

/** A fresh query client is a fresh app load: nothing carried over from the last one. */
function load() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PinNotice />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  localStorage.clear();
  auth.current = { player: MEMBER };
});

describe('PinNotice', () => {
  it('lists the reset and the new PIN, newest first, in the member’s own time', async () => {
    serve(JOURNEY);
    load();

    const dialog = await screen.findByRole('dialog', { name: TITLE });
    const items = within(dialog).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'A new PIN was chosenSat 3 Oct, 14:12',
      'An admin reset your PINSat 3 Oct, 14:05',
    ]);
    expect(dialog).toHaveTextContent(/wasn’t you.*Forgot PIN\?/);
  });

  it('remembers on this device what it showed, so the next load shows nothing', async () => {
    serve(JOURNEY);
    const user = userEvent.setup();
    const first = load();

    await user.click(await screen.findByRole('button', { name: 'Got it' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(localStorage.getItem(SEEN_KEY)).toBe(SET.at);
    first.unmount();

    load();
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows only what this device has not shown yet', async () => {
    localStorage.setItem(SEEN_KEY, RESET.at);
    serve(JOURNEY);
    load();

    const dialog = await screen.findByRole('dialog', { name: TITLE });
    expect(within(dialog).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'A new PIN was chosenSat 3 Oct, 14:12',
    ]);
  });

  it('counts closing it with Escape as having seen it', async () => {
    serve(JOURNEY);
    const user = userEvent.setup();
    load();
    await screen.findByRole('dialog', { name: TITLE });

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(localStorage.getItem(SEEN_KEY)).toBe(SET.at);
  });

  it('keeps each member’s record apart on a shared device', async () => {
    localStorage.setItem(SEEN_KEY, SET.at);
    auth.current = { player: { id: 'member-2', timezone: 'UTC' } };
    serve(JOURNEY);
    load();

    expect(await screen.findByRole('dialog', { name: TITLE })).toBeTruthy();
  });

  it('still closes when the device refuses to store it, and shows it again next load', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    serve(JOURNEY);
    const user = userEvent.setup();
    const first = load();

    await user.click(await screen.findByRole('button', { name: 'Got it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    first.unmount();

    load();
    expect(await screen.findByRole('dialog', { name: TITLE })).toBeTruthy();
  });

  it('shows nothing when there has been no reset in the last thirty days', async () => {
    serve({ events: [] });
    load();

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(EVENTS_URL));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows nothing while the deployed API does not serve the route yet', async () => {
    // Vercel ships this on merge; the API waits for /ship-prod, and until then this 404s.
    serve(new ApiError(404, 'Not Found'));
    load();

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(EVENTS_URL));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks nothing without a session', async () => {
    auth.current = { player: null };
    serve(JOURNEY);
    load();

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('has no axe violations while open', async () => {
    serve(JOURNEY);
    load();
    await screen.findByRole('dialog', { name: TITLE });

    expect(await axe(document.body, AXE_CONFIG)).toHaveNoViolations();
  });
});
