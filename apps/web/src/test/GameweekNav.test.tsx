import { describe, expect, it, afterEach, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GameweekNav } from '@/components/GameweekNav';
import type { GameweekHistory } from '@/hooks/useGameweekHistory';
import type { GameweekSummary } from '@/lib/types';

/**
 * Batch 73 — the badge is not allowed to trust `status`.
 *
 * `open_due_gameweeks` only ever moves `scheduled -> open` and the lock job only ever
 * moves `open -> locked`, both hourly, so `status` lags the instants at both ends of the
 * claim period. The two tests that matter here are the ones where the label and the
 * clock disagree: the screen said **Open** while `pick_refusal` refused every pick.
 */

const OPENS = '2026-08-29T09:00:00Z';
const LOCKS = '2026-08-29T14:30:00Z';

function round(overrides: Partial<GameweekSummary> = {}): GameweekSummary {
  return {
    gameweek_id: 'gw-1',
    starts_on: '2026-08-29',
    status: 'open',
    locks_at_utc: LOCKS,
    picks_open_at_utc: OPENS,
    number: 4,
    fixture_count: 10,
    pick_count: 3,
    ...overrides,
  };
}

/** Two rounds, because the control hides itself when there is nothing to move between. */
function history(current: GameweekSummary): GameweekHistory {
  const older = round({ gameweek_id: 'gw-0', starts_on: '2026-08-22', status: 'settled' });
  return {
    gameweeks: [current, older],
    selectedId: current.gameweek_id,
    selected: current,
    isLatest: true,
    newer: undefined,
    older,
    select: () => {},
  };
}

function at(iso: string) {
  vi.setSystemTime(new Date(iso));
}

describe('the round badge', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('reads Open while a pick would actually be taken', () => {
    at('2026-08-29T12:00:00Z');
    render(<GameweekNav history={history(round())} />);
    expect(screen.getByText('Open')).toBeTruthy();
  });

  it('reads "Not open" for a round whose status is open but whose opening is ahead', () => {
    // The owner's report. Saving `pick_open_offset_minutes` restamps every unlocked round
    // (Batch 65) and deliberately does not re-derive `status`, so the round keeps `open`
    // while the API answers PICKS_NOT_OPEN — and this badge said Open to every member.
    at('2026-08-29T08:00:00Z');
    render(<GameweekNav history={history(round())} />);
    expect(screen.getByText('Not open')).toBeTruthy();
    expect(screen.queryByText('Open')).toBeNull();
  });

  it('reads Locked for a round whose status is open but whose deadline has passed', () => {
    // The mirror at the other end, and the older of the two bugs: the lock job runs
    // hourly, so this window has existed since Batch 4.
    at('2026-08-29T14:31:00Z');
    render(<GameweekNav history={history(round())} />);
    expect(screen.getByText('Locked')).toBeTruthy();
    expect(screen.queryByText('Open')).toBeNull();
  });

  it('still calls a settled round Settled', () => {
    at('2026-08-30T12:00:00Z');
    render(<GameweekNav history={history(round({ status: 'settled' }))} />);
    expect(screen.getAllByText('Settled').length).toBeGreaterThan(0);
  });

  it('reads Open for a round that announces no opening at all', () => {
    // `picks_open_at_utc = null` is no gate, not an offset of zero — 2-1 Hibs' rounds
    // today. The badge is telling the truth in that configuration and must keep doing so.
    at('2026-08-25T12:00:00Z');
    render(<GameweekNav history={history(round({ picks_open_at_utc: null }))} />);
    expect(screen.getByText('Open')).toBeTruthy();
  });
});

describe('the round counter (Batch 78)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('counts picks and no longer prints them over the fixture count', () => {
    // `3/10` sat a few hundred pixels from the roster's "1 of 2 picked". Both read as one
    // fraction of one thing; they were picks over fixtures and picks over members.
    at('2026-08-29T12:00:00Z');
    const { container } = render(<GameweekNav history={history(round())} />);
    expect(screen.getByText('3 picks')).toBeTruthy();
    expect(container.textContent).not.toContain('3/10');
  });

  it('says pick, singular, when there is one', () => {
    at('2026-08-29T12:00:00Z');
    render(<GameweekNav history={history(round({ pick_count: 1 }))} />);
    expect(screen.getByText('1 pick')).toBeTruthy();
  });
});
