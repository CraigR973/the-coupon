/**
 * Batch 165 — the countdown ticks without re-rendering the screen around it.
 *
 * `useCountdown` sat in the page body, so a tick re-rendered the whole round screen —
 * fixtures, roster and coupon included — once a second, to recompute two booleans that
 * change exactly once each. There is no `React.memo` anywhere else in this codebase to
 * stop that cascade.
 *
 * The row asks for commits per idle five seconds, measured. That is what these count: a
 * render counter in a parent, fake timers advanced five seconds, and the assertion that
 * the parent stayed still while the digits moved.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { Countdown } from '@/components/Countdown';
import { useExpiry } from '@/hooks/useExpiry';
import type { CountdownParts } from '@/hooks/useCountdown';

const format = (p: CountdownParts) => (p.expired ? 'Locked' : `${p.minutes}m ${p.seconds}s`);

afterEach(() => {
  vi.useRealTimers();
});

/**
 * Computed once, *outside* the component.
 *
 * Worth saying because getting it wrong looked exactly like a bug in the hook: a target
 * derived from `Date.now()` inside a render recomputes on every render, so the deadline
 * runs away from the clock and never arrives. A real page passes an instant that came
 * from the API and does not move.
 */
function inMinutes(n: number): string {
  return new Date(Date.now() + n * 60_000).toISOString();
}

describe('a screen with a live countdown on it', () => {
  it('renders once over five idle seconds while the digits keep moving', () => {
    vi.useFakeTimers();
    let screenRenders = 0;
    const lockAt = inMinutes(10);

    function Screen() {
      screenRenders += 1;
      const locked = useExpiry(lockAt);
      return (
        <div>
          <span data-testid="state">{locked ? 'locked' : 'open'}</span>
          <span data-testid="clock">
            <Countdown target={lockAt} format={format} />
          </span>
        </div>
      );
    }

    render(<Screen />);
    expect(screenRenders).toBe(1);
    const before = screen.getByTestId('clock').textContent;

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    // The measurement the row asks for: commits per idle five seconds, which is now one
    // — the initial render and nothing after it.
    //
    // Reverting to `useCountdown` here makes this read 2, not 6: five ticks inside one
    // `act()` are five `setState` calls that React batches into a single commit. In a
    // browser each tick is its own task and each is its own commit, so the figure there
    // is one a second. What this pins is the *shape* — the screen wakes for the tick at
    // all — and that is the thing that was wrong.
    expect(screenRenders, 'the screen re-rendered on a countdown tick').toBe(1);
    expect(screen.getByTestId('clock').textContent).not.toBe(before);
    expect(screen.getByTestId('state').textContent).toBe('open');
  });

  it('still re-renders the screen at the moment the deadline passes', () => {
    // The whole point of the boolean: the screen has to change when the round locks. A
    // version that never re-rendered would pass the test above and be useless.
    vi.useFakeTimers();
    let screenRenders = 0;
    const lockAt = inMinutes(1);

    function Screen() {
      screenRenders += 1;
      const locked = useExpiry(lockAt);
      return <span data-testid="state">{locked ? 'locked' : 'open'}</span>;
    }

    render(<Screen />);
    expect(screen.getByTestId('state').textContent).toBe('open');

    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(screenRenders, 'something woke the screen before the deadline').toBe(1);

    act(() => {
      vi.advanceTimersByTime(31_000);
    });
    expect(screen.getByTestId('state').textContent).toBe('locked');
  });

  it('reports an instant far enough ahead to overflow setTimeout as still to come', () => {
    // `setTimeout` clamps above ~24.8 days and fires immediately, which would report a
    // round two months out as already locked — the screen would open shut. The hook
    // re-arms in day-long hops instead.
    vi.useFakeTimers();
    const twoMonths = new Date(Date.now() + 60 * 86_400_000).toISOString();

    function Screen() {
      return <span data-testid="state">{useExpiry(twoMonths) ? 'locked' : 'open'}</span>;
    }

    render(<Screen />);
    act(() => {
      vi.advanceTimersByTime(86_400_000 + 1_000);
    });
    expect(screen.getByTestId('state').textContent).toBe('open');
  });

  it('treats an absent instant as already past', () => {
    // Both pages pass `FAR_PAST` when a round announces no opening, and read the result
    // as "there is nothing to wait for".
    function Screen() {
      return <span data-testid="state">{useExpiry('1970-01-01T00:00:00Z') ? 'past' : 'ahead'}</span>;
    }
    render(<Screen />);
    expect(screen.getByTestId('state').textContent).toBe('past');
  });
});
