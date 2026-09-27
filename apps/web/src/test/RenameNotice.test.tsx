import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { axe } from 'jest-axe';
import { RenameNotice } from '@/components/RenameNotice';
import { ApiError } from '@/lib/api';
import type { RenameNoticeState } from '@/lib/types';

/**
 * Batch 148 — the rename notice's second channel. A renamed member push cannot reach is
 * shown it once in the app, and seeing it is what tells the API to stop asking.
 */

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch };
});

const NOTICE_URL = '/api/v1/me/rename-notice';
const SEEN_URL = '/api/v1/me/rename-notice/seen';
const TITLE = 'Your sign-in name changed';
const BODY =
  'Sign in as "Member B Newname" from now on. Your old sign-in name no longer works, and a ' +
  'forgotten-PIN request needs the new one. Your PIN itself has not changed.';
const PENDING: RenameNoticeState = { notice: { title: TITLE, body: BODY } };

/** Disabled because jsdom cannot evaluate CSS custom properties; see accessibility.test. */
const AXE_CONFIG = { rules: { 'color-contrast': { enabled: false } } };

function serve(state: RenameNoticeState | Error, seen: 'ok' | 'fails' = 'ok') {
  apiFetch.mockImplementation(async (path: string) => {
    if (path === NOTICE_URL) {
      if (state instanceof Error) throw state;
      return state;
    }
    if (path === SEEN_URL) {
      if (seen === 'fails') throw new ApiError(503, 'unavailable');
      return undefined;
    }
    throw new Error(`unexpected request ${path}`);
  });
}

/** A fresh query client is a fresh app load: nothing carried over from the last one. */
function load() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <RenameNotice />
    </QueryClientProvider>,
  );
}

function seenCalls() {
  return apiFetch.mock.calls.filter(([path]) => path === SEEN_URL);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RenameNotice', () => {
  it('shows a member push could not reach the notice, in the words the push uses', async () => {
    serve(PENDING);
    load();

    const dialog = await screen.findByRole('dialog', { name: TITLE });
    expect(dialog).toHaveTextContent(BODY);
    expect(seenCalls()).toHaveLength(0);
  });

  it('marks it seen when they tap "Got it", and closes', async () => {
    serve(PENDING);
    const user = userEvent.setup();
    load();

    await user.click(await screen.findByRole('button', { name: 'Got it' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(seenCalls()).toEqual([[SEEN_URL, { method: 'POST' }]]);
  });

  it.each([
    ['Escape', async (user: ReturnType<typeof userEvent.setup>) => user.keyboard('{Escape}')],
    [
      'the corner cross',
      async (user: ReturnType<typeof userEvent.setup>) =>
        user.click(screen.getByRole('button', { name: 'Close' })),
    ],
  ])('counts closing it with %s as seeing it', async (_how, close) => {
    serve(PENDING);
    const user = userEvent.setup();
    load();
    await screen.findByRole('dialog', { name: TITLE });

    await close(user);

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(seenCalls()).toHaveLength(1);
  });

  it('shows nothing to a member with nothing to be told, including one push reached', async () => {
    serve({ notice: null });
    load();

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(NOTICE_URL));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(seenCalls()).toHaveLength(0);
  });

  it('shows nothing while the deployed API does not serve the route yet', async () => {
    // Vercel ships this on merge; the API waits for /ship-prod, and until then this 404s.
    serve(new ApiError(404, 'Not Found'));
    load();

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(NOTICE_URL));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps nothing locally, so a failed acknowledgement shows it again next load', async () => {
    serve(PENDING, 'fails');
    const user = userEvent.setup();
    const first = load();
    await user.click(await screen.findByRole('button', { name: 'Got it' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    first.unmount();

    // The marker was never written, so the API still has it pending.
    load();

    expect(await screen.findByRole('dialog', { name: TITLE })).toBeTruthy();
  });

  it('has no axe violations while open', async () => {
    serve(PENDING);
    load();
    await screen.findByRole('dialog', { name: TITLE });

    expect(await axe(document.body, AXE_CONFIG)).toHaveNoViolations();
  });
});
