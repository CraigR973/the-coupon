import { useEffect, useState } from 'react';
import { parseInstant } from '../lib/time';

export interface CountdownParts {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  expired: boolean;
}

const EXPIRED: CountdownParts = { days: 0, hours: 0, minutes: 0, seconds: 0, expired: true };

function compute(targetIso: string): CountdownParts {
  // `parseInstant`, not `new Date`: an offset-less target was read as local time, so
  // this reached zero an hour before the API stopped taking picks and `CurrentRoundPage`
  // shut the screen on a round still open (Batch 43).
  const diff = parseInstant(targetIso).getTime() - Date.now();
  if (!Number.isFinite(diff) || diff <= 0) return EXPIRED;
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor((diff % 86_400_000) / 3_600_000),
    minutes: Math.floor((diff % 3_600_000) / 60_000),
    seconds: Math.floor((diff % 60_000) / 1_000),
    expired: false,
  };
}

/**
 * Live countdown to `targetIso`. Recomputed fresh on every render (and on a 1 s
 * tick), so it reflects the current target immediately when it changes — e.g.
 * when the gameweek slate loads and the 14:30 lock time becomes known.
 */
export function useCountdown(targetIso: string): CountdownParts {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => clearInterval(id);
  }, []);

  return compute(targetIso);
}
