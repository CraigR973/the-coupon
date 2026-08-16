import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { createElement, type PropsWithChildren } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn(), DEFAULT_LEAGUE_SLUG: 'test-league' }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import { usePickEditor, pickErrorMessage } from '@/hooks/usePickEditor';
import type { PickResponse } from '@/lib/types';

const mockApiFetch = vi.mocked(apiFetch);
const mockToast = vi.mocked(toast);

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

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
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
    expect(pickErrorMessage('')).toMatch(/could not save/i);
    expect(pickErrorMessage('Some other server message')).toBe('Some other server message');
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
      '/api/v1/leagues/test-league/picks',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ fixture_id: 'fx1', market: 'MATCH_ODDS', outcome: 'HOME' }),
      }),
    );
    expect(mockToast.success).toHaveBeenCalledWith(expect.stringContaining('Forfar'));
  });

  it('maps a 409 SELECTION_TAKEN into a friendly error toast', async () => {
    mockApiFetch.mockRejectedValue(new Error('SELECTION_TAKEN'));
    const { result } = renderHook(() => usePickEditor('test-league', 'gw1'), { wrapper });

    act(() => {
      result.current.submit('fx1', 'MATCH_ODDS', 'AWAY');
    });

    await waitFor(() => expect(mockToast.error).toHaveBeenCalled());
    expect(mockToast.error).toHaveBeenCalledWith(expect.stringMatching(/just grabbed/i));
  });
});
