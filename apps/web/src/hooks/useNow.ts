import { useEffect, useState } from 'react';

/**
 * Re-render on a fixed interval so wall-clock-derived values (e.g. an approximate
 * live-match minute) stay fresh between data fetches. Returns the current epoch ms
 * at the latest tick.
 */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
}
