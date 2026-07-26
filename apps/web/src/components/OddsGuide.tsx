/**
 * OddsGuide — collapsible quick-reference for how The Coupon scores.
 *
 * Static rules and worked examples
 * live here so the pick screen can explain the odds×10 model at a glance.
 */

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { potentialPoints } from '@/lib/coupon';

const DEFAULT_STORAGE_KEY = 'coupon_odds_guide_open';

// Worked examples: odds → points a winning pick scores (round(odds × 10)).
const EXAMPLES: ReadonlyArray<{ odds: number; note: string }> = [
  { odds: 1.5, note: 'Short-priced favourite' },
  { odds: 2.5, note: 'Even-ish call' },
  { odds: 6.0, note: 'Outsider' },
  { odds: 13.0, note: 'Long shot — big reward' },
];

function getInitialOpen(storageKey: string, defaultOpen: boolean): boolean {
  try {
    const stored = localStorage.getItem(storageKey);
    return stored === null ? defaultOpen : stored !== 'false';
  } catch {
    return defaultOpen;
  }
}

function persistOpen(storageKey: string, open: boolean): void {
  try {
    localStorage.setItem(storageKey, String(open));
  } catch {
    /* ignore */
  }
}

interface OddsGuideProps {
  storageKey?: string;
  defaultOpen?: boolean;
}

export function OddsGuide({ storageKey = DEFAULT_STORAGE_KEY, defaultOpen = false }: OddsGuideProps = {}) {
  const [open, setOpen] = useState(() => getInitialOpen(storageKey, defaultOpen));

  function toggle() {
    const next = !open;
    setOpen(next);
    persistOpen(storageKey, next);
  }

  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="odds-guide-body"
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-elevated focus-visible:outline-none focus-visible:shadow-glow"
      >
        <div className="flex items-center gap-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">How scoring works</p>
          <span className="inline-block rounded bg-primary/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-4 text-primary">
            win = odds × 10
          </span>
        </div>
        <ChevronDown
          className={cn('h-4 w-4 text-text-muted transition-transform duration-200', open && 'rotate-180')}
          aria-hidden
        />
      </button>

      {open && (
        <div id="odds-guide-body">
          <ul className="mx-4 mb-3 space-y-2 border-t border-border pt-3 text-xs font-sans leading-snug text-text-secondary">
            <li>
              <strong className="text-text-primary">One pick a week.</strong> Choose a single selection — a
              match result (1X2) or Both Teams to Score — from this Saturday's slate.
            </li>
            <li>
              <strong className="text-text-primary">First come, first served.</strong> No two members of a
              leaderboard can hold the same selection. Once it's taken, it's gone.
            </li>
            <li>
              <strong className="text-text-primary">Odds freeze when you pick.</strong> Your price is locked
              in the moment you grab it, even if it drifts later.
            </li>
            <li>
              <strong className="text-warning">Picks lock at 14:30</strong> on Saturday. After that you can't
              change your selection.
            </li>
            <li>
              <strong className="text-text-primary">Win → odds × 10 points</strong> (rounded). Longer odds pay
              more. Lose or void → nothing. Season total is cumulative.
            </li>
          </ul>

          <div className="px-4 pb-4">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
              If your pick wins
            </p>
            <table className="w-full border-collapse text-xs font-sans" aria-label="Odds to points examples">
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="py-1 text-left text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    Odds
                  </th>
                  <th scope="col" className="py-1 text-left text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    Example
                  </th>
                  <th scope="col" className="w-16 py-1 text-right text-[10px] font-medium uppercase tracking-wider text-text-muted">
                    Points
                  </th>
                </tr>
              </thead>
              <tbody>
                {EXAMPLES.map((ex) => (
                  <tr key={ex.odds} className="border-b border-border/30">
                    <td className="py-1.5 font-mono text-text-primary tabular-nums">{ex.odds.toFixed(2)}</td>
                    <td className="py-1.5 text-[11px] text-text-muted">{ex.note}</td>
                    <td className="py-1.5 text-right">
                      <span className="inline-block rounded-full bg-primary/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-4 text-primary">
                        {potentialPoints(ex.odds)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
