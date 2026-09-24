import { useEffect, useState } from 'react';
import { parseInstant } from '../lib/time';

/**
 * Has this instant passed? Re-renders once, when it does.
 *
 * Batch 165. `useCountdown` ticks every second, and a page that called it for the
 * *boolean* — is the round still open? — paid a full re-render of the screen every second
 * to learn something that changes exactly once. `CurrentRoundPage` did that with a
 * fixture list, a roster and a coupon under it, and there is no `React.memo` anywhere in
 * this codebase to stop the cascade.
 *
 * One `setTimeout` to the boundary instead. A component that needs to *display* the
 * remaining time still wants `useCountdown`, and should be small enough that re-rendering
 * it every second costs nothing — see `Countdown`.
 */
export function useExpiry(targetIso: string): boolean {
  const target = parseInstant(targetIso).getTime();
  const [, setPassed] = useState(0);
  const expired = !Number.isFinite(target) || target - Date.now() <= 0;

  useEffect(() => {
    if (expired) return;
    const delay = target - Date.now();
    // `setTimeout` clamps above ~24.8 days (a 32-bit millisecond overflow) and would fire
    // immediately, reporting a round two months out as already locked. Re-arm in day-long
    // hops instead; a round that far ahead re-arms once a day and nobody is watching.
    const DAY = 86_400_000;
    const id = setTimeout(() => setPassed((n) => n + 1), Math.min(delay, DAY));
    return () => clearTimeout(id);
    // `target` is a number, so this re-arms when the instant itself changes — which is
    // what happens when the slate loads and the lock time becomes known.
  }, [target, expired]);

  return expired;
}
