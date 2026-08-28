import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { createElement, type PropsWithChildren } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/api', async () => {
  // `ApiError` / `NetworkError` are the real classes: the hook branches on `instanceof`,
  // so a stubbed shape would let every failure fall through the same arm and the tests
  // below would pass without the distinction they exist to check.
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return { ...actual, apiFetch: vi.fn(), DEFAULT_LEAGUE_SLUG: 'test-league' };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ApiError, NetworkError, apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import { usePickEditor, pickErrorMessage } from '@/hooks/usePickEditor';
import type { PickResponse } from '@/lib/types';

const mockApiFetch = vi.mocked(apiFetch);
const mockToast = vi.mocked(toast);
// `vi.mocked(toast)` types the members with sonner's own signatures, not as mocks, so the
// call log has to be reached through a mock of the function itself.
const errorToasts = () => vi.mocked(toast.error).mock.calls;

const PICK: PickResponse = {
  id: 'pk1',
  league_id: 'lg1',
  gameweek_id: 'gw1',
  fixture_id: 'fx1',
  home: 'Forfar',
  away: 'Brechin',
  competition: 'Scottish League 2',
  market: 'MATCH_ODDS',
  outcome: 'HOME',
  runner_name: 'Forfar',
  odds: 2.5,
  status: 'pending',
  points_awarded: null,
};

const SUBMIT_PATH = '/api/v1/leagues/test-league/picks';
const MY_PICK_PATH = '/api/v1/leagues/test-league/gameweeks/gw1/pick';

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return createElement(QueryClientProvider, { client }, children);
}

/** Every POST the hook issued, in order — the count these tests are really about. */
function submits() {
  return mockApiFetch.mock.calls.filter(([path]) => path === SUBMIT_PATH);
}

function setOnline(online: boolean) {
  Object.defineProperty(navigator, 'onLine', { value: online, configurable: true });
}

/** Fire the browser's reconnect event, which is what flushes a queued pick. */
function reconnect() {
  setOnline(true);
  window.dispatchEvent(new Event('online'));
}

beforeEach(() => {
  vi.clearAllMocks();
  setOnline(true);
});

afterEach(() => {
  setOnline(true);
});

describe('pickErrorMessage', () => {
  it('maps backend detail codes to friendly copy', () => {
    expect(pickErrorMessage('SELECTION_TAKEN')).toMatch(/just grabbed/i);
    // The fixture rule refuses the whole game, not one selection.
    expect(pickErrorMessage('FIXTURE_TAKEN')).toMatch(/already has that game/i);
    expect(pickErrorMessage('PICKS_LOCKED')).toMatch(/locked/i);
    // Batch 27's other refusal — "come back later", not "it is over".
    expect(pickErrorMessage('PICKS_NOT_OPEN')).toMatch(/haven’t opened/i);
    expect(pickErrorMessage('SELECTION_NOT_AVAILABLE')).toMatch(/priced/i);
    // Batch 48: browsing the card degrades to stale prices, submitting never does —
    // the refusal has to say the pick was not saved, not just that something broke.
    expect(pickErrorMessage('ODDS_UNAVAILABLE')).toMatch(/wasn’t saved/i);
    expect(pickErrorMessage('')).toMatch(/could not save/i);
    expect(pickErrorMessage('Some other server message')).toBe('Some other server message');
  });

  it('names the league, not the member, when Batch 89’s shared budget refuses', () => {
    // The member did nothing wrong and their own limit is untouched. Copy that reads as
    // an accusation makes someone who has picked once today stop trying.
    const message = pickErrorMessage('PICKS_BUSY');
    expect(message).toMatch(/your league/i);
    expect(message).toMatch(/wasn’t saved/i);
    expect(message).toMatch(/few minutes/i);
  });
});

describe('usePickEditor', () => {
  it('POSTs the selection identity and toasts the grabbed runner + odds', async () => {
    mockApiFetch.mockResolvedValue(PICK);
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(mockToast.success).toHaveBeenCalled());
    expect(mockApiFetch).toHaveBeenCalledWith(
      SUBMIT_PATH,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ fixture_id: 'fx1', market: 'MATCH_ODDS', outcome: 'HOME' }),
      }),
    );
    expect(mockToast.success).toHaveBeenCalledWith(expect.stringContaining('Forfar'));
    expect(result.current.outstanding).toBeNull();
  });

  it('gives the submission a deadline rather than waiting forever', async () => {
    // A hung write is the failure this batch is about: without a deadline the member
    // watches a spinner through the last minute before lock and learns nothing.
    mockApiFetch.mockResolvedValue(PICK);
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(mockToast.success).toHaveBeenCalled());
    const [, options] = submits()[0];
    expect((options as { timeoutMs?: number }).timeoutMs).toBeGreaterThan(0);
  });

  it('maps a 409 SELECTION_TAKEN into a friendly error toast', async () => {
    mockApiFetch.mockRejectedValue(new ApiError(409, 'SELECTION_TAKEN'));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'AWAY');
    });

    await waitFor(() => expect(mockToast.error).toHaveBeenCalled());
    expect(mockToast.error).toHaveBeenCalledWith(expect.stringMatching(/just grabbed/i));
  });

  // ── Batch 90: the two failures that are not answers ───────────────────────

  it('holds an offline pick as queued and sends it exactly once on reconnect', async () => {
    // The double-submit test. A pick that never left the device is safe to re-send, but
    // it must be sent *once* — a flush that fires per listener, per event or per render
    // spends the league's provider budget and can race the member's own next tap.
    setOnline(false);
    mockApiFetch.mockRejectedValue(new NetworkError('You are offline', false));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(result.current.outstanding).not.toBeNull());
    expect(result.current.outstanding).toMatchObject({ key: 'fx1:MATCH_ODDS:HOME', state: 'queued' });
    expect(mockToast.error).toHaveBeenCalledWith(expect.stringMatching(/offline/i));

    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue(PICK);
    act(() => reconnect());

    await waitFor(() => expect(result.current.outstanding).toBeNull());
    expect(submits()).toHaveLength(1);
    expect(mockToast.success).toHaveBeenCalledWith(expect.stringContaining('Forfar'));
  });

  it('never re-sends a submission that may already have landed — it checks instead', async () => {
    // The heart of the batch. The request left the device and nothing came back, so the
    // server may hold this claim already. Re-sending is the harmful move: if the member
    // has since picked something else, a late retry of this one silently takes their
    // claim backwards. One GET settles it without changing anything.
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === SUBMIT_PATH) throw new NetworkError('The network request failed', true);
      return PICK; // the round's pick — it did land after all
    });
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(mockToast.success).toHaveBeenCalled());
    // Exactly one POST — the failed one. The recovery was a read.
    expect(submits()).toHaveLength(1);
    expect(mockApiFetch).toHaveBeenCalledWith(MY_PICK_PATH);
    expect(result.current.outstanding).toBeNull();
    expect(mockToast.success).toHaveBeenCalledWith(expect.stringMatching(/did land/i));
  });

  it('reports an unconfirmed claim as unconfirmed while it cannot be checked', async () => {
    // Offline *and* unanswered: nothing can settle it yet, so the honest answer is that
    // it is unknown. Guessing either way here is the failure this batch exists to end.
    mockApiFetch.mockRejectedValue(new NetworkError('The network request failed', true));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(result.current.outstanding).not.toBeNull());
    expect(result.current.outstanding).toMatchObject({ state: 'unconfirmed' });
    expect(mockToast.error).toHaveBeenCalledWith(expect.stringMatching(/didn’t hear back/i));
    // The check failed too, so nothing was re-sent and nothing was claimed either way.
    expect(submits()).toHaveLength(1);
  });

  it('drops an unconfirmed claim back to queued once the server proves it did not land', async () => {
    // Reconciling turns the unknown into a fact. The server holds someone else's shape of
    // the round — or nothing — so this intent demonstrably is not applied, and re-sending
    // it can no longer overwrite anything. It still is not sent automatically.
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === SUBMIT_PATH) throw new NetworkError('The network request failed', true);
      return null; // the member holds no pick for this round
    });
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });

    await waitFor(() => expect(result.current.outstanding).toMatchObject({ state: 'queued' }));
    expect(submits()).toHaveLength(1);
    expect(mockToast.error).toHaveBeenCalledWith(expect.stringMatching(/didn’t land/i));

    // And only now, on the member's say-so, does it go out again.
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue(PICK);
    act(() => result.current.resolveOutstanding());
    await waitFor(() => expect(result.current.outstanding).toBeNull());
    expect(submits()).toHaveLength(1);
  });

  it('tells losing the race apart from not knowing', async () => {
    // The two states a member has to act on differently, and the ones the old generic
    // toast collapsed together. A lost race is an answer: it holds nothing and names what
    // happened. An unanswered request holds the claim and says it is unconfirmed.
    mockApiFetch.mockRejectedValue(new ApiError(409, 'SELECTION_TAKEN'));
    const lost = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });
    act(() => {
      lost.result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });
    await waitFor(() => expect(mockToast.error).toHaveBeenCalled());
    expect(lost.result.current.outstanding).toBeNull();
    const lostMessage = errorToasts().at(-1)?.[0];

    vi.clearAllMocks();
    mockApiFetch.mockRejectedValue(new NetworkError('The network request failed', true));
    const unknown = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });
    act(() => {
      unknown.result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });
    await waitFor(() => expect(unknown.result.current.outstanding).not.toBeNull());
    const unknownMessage = errorToasts().at(-1)?.[0];

    expect(lostMessage).not.toEqual(unknownMessage);
    expect(lostMessage).toMatch(/grabbed that selection/i);
    expect(unknownMessage).toMatch(/may not have been saved/i);
    expect(unknown.result.current.outstanding).toMatchObject({ state: 'unconfirmed' });
  });

  it('lets a newer pick supersede an older unsent one instead of queueing behind it', async () => {
    // One pick per member per round, so only the newest intent can be right. If the first
    // one survived to fire on reconnect it would silently take the member's claim back to
    // a selection they had already changed their mind about.
    setOnline(false);
    mockApiFetch.mockRejectedValue(new NetworkError('You are offline', false));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });
    await waitFor(() => expect(result.current.outstanding).toMatchObject({ key: 'fx1:MATCH_ODDS:HOME' }));

    act(() => {
      result.current.submit('fx2', 'MATCH_ODDS', 'AWAY');
    });
    await waitFor(() => expect(result.current.outstanding).toMatchObject({ key: 'fx2:MATCH_ODDS:AWAY' }));

    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue({ ...PICK, fixture_id: 'fx2', outcome: 'AWAY' });
    act(() => reconnect());

    await waitFor(() => expect(result.current.outstanding).toBeNull());
    const sent = submits();
    expect(sent).toHaveLength(1);
    expect((sent[0][1] as { body: string }).body).toBe(
      JSON.stringify({ fixture_id: 'fx2', market: 'MATCH_ODDS', outcome: 'AWAY' }),
    );
  });

  it('lets the member drop a held claim without sending it', async () => {
    setOnline(false);
    mockApiFetch.mockRejectedValue(new NetworkError('You are offline', false));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'HOME');
    });
    await waitFor(() => expect(result.current.outstanding).not.toBeNull());

    act(() => result.current.discardOutstanding());
    expect(result.current.outstanding).toBeNull();

    mockApiFetch.mockReset();
    act(() => reconnect());
    expect(submits()).toHaveLength(0);
  });
});
