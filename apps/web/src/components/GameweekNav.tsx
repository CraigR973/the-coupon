import { ChevronLeft, ChevronRight, History } from 'lucide-react';
import type { GameweekHistory } from '../hooks/useGameweekHistory';
import { Badge } from './ui/badge';
import { roundName, roundStateLabel } from '../lib/coupon';
import { formatCalendarDate } from '../lib/time';
import { cn } from '../lib/utils';

export interface GameweekNavProps {
  history: GameweekHistory;
}

/**
 * Move back and forward through the season's gameweeks.
 *
 * Hidden entirely until there is more than one gameweek to move between — on a
 * first Saturday there is no history to browse and the control would be noise.
 */
export function GameweekNav({ history }: GameweekNavProps) {
  const { gameweeks, selected, newer, older, isLatest, select } = history;
  if (gameweeks.length < 2) return null;

  // A `gw` parameter naming a gameweek this league has no row for leaves nothing
  // to label; fall back to the newest rather than rendering a broken control.
  const current = selected ?? gameweeks[0];
  if (!current) return null;

  // Derived from the stored instants rather than from `status`, which the hourly jobs
  // only ever move forwards: this badge said "Open" on a round whose opening had not
  // arrived, and "Open" on one whose deadline had passed, for up to an hour either way.
  const state = roundStateLabel(current);

  return (
    <div
      className="mb-4 flex items-center justify-between gap-2 rounded-lg border border-border bg-surface px-2 py-2"
      data-testid="gameweek-nav"
    >
      <NavButton
        label="Older gameweek"
        onClick={() => older && select(older.gameweek_id)}
        disabled={!older}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
      </NavButton>

      <div className="flex min-w-0 flex-col items-center gap-0.5">
        <span className="truncate font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary">
          {roundName(current.number, formatCalendarDate(current.starts_on, 'EEE d MMM yyyy'))}
        </span>
        <span className="flex items-center gap-1.5">
          <Badge variant={state.open ? 'success' : 'muted'}>{state.label}</Badge>
          {/* Batch 78: this printed `pick_count/fixture_count` — picks over *fixtures* —
              a few hundred pixels from the roster's "n of m picked", which is picks over
              *members*. Both read as one fraction of one thing and they were fractions of
              different things. The count members actually ask for is the roster's, so this
              one stops pretending to be a ratio and says what it counts. */}
          <span className="font-mono text-[10px] tabular-nums text-text-muted">
            {current.pick_count} {current.pick_count === 1 ? 'pick' : 'picks'}
          </span>
        </span>
      </div>

      <div className="flex items-center gap-1">
        {!isLatest && (
          <button
            type="button"
            onClick={() => select(undefined)}
            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted tap-target press-down hover:text-text-primary focus-visible:outline-none focus-visible:shadow-glow"
            data-testid="gameweek-latest"
          >
            <History className="h-3 w-3" aria-hidden />
            Latest
          </button>
        )}
        <NavButton
          label="Newer gameweek"
          onClick={() => newer && select(newer.gameweek_id)}
          disabled={!newer}
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </NavButton>
      </div>
    </div>
  );
}

function NavButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md border border-border p-1.5 tap-target focus-visible:outline-none focus-visible:shadow-glow',
        disabled
          ? 'cursor-not-allowed text-text-muted opacity-40'
          : 'press-down text-text-secondary hover:text-text-primary',
      )}
    >
      {children}
    </button>
  );
}
