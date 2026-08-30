import { cn } from '@/lib/utils';
import type { SeasonSummary } from '@/lib/types';

interface Props {
  seasons: SeasonSummary[];
  /** The season being shown, or `null` for whichever one the API calls current. */
  selected: number | null;
  onSelect: (season: number | null) => void;
  className?: string;
}

/**
 * The standings archive (Batch 96): which season's table is on screen, and the others.
 *
 * Renders nothing until there is a second season to switch to. A league in its first
 * year has one table and always did, and a selector offering one choice is a control
 * that changes nothing — the same reason `LeagueSwitchStrip` hides itself below two
 * leagues.
 *
 * It also renders nothing while the API has not shipped `GET /seasons`, which is not a
 * hypothetical: close-out pushes this app to members minutes after it verifies, while
 * the API waits for `/ship-prod`. The seasons query simply fails in that window, this
 * list is empty, and the page is exactly what it was before the batch.
 *
 * The current season is `null` rather than its own number so that the ordinary case
 * carries no query string: a leaderboard link a member sends someone should open on the
 * season they are both playing, not pin the reader to whichever one the sender was
 * looking at.
 */
export function SeasonStrip({ seasons, selected, onSelect, className }: Props) {
  if (seasons.length < 2) return null;

  const current = seasons.find((entry) => entry.is_current);

  return (
    <section
      className={cn(
        'space-y-3 rounded-2xl border border-border/80 bg-surface-elevated/70 px-3 py-3 shadow-sm',
        'sm:px-4',
        className,
      )}
      data-testid="season-strip"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-text-primary">
          Season
        </p>
        <span className="rounded-full border border-border/80 bg-surface px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted">
          Past seasons
        </span>
      </div>
      <nav className="-mx-1 overflow-x-auto scroll-smooth" aria-label="Choose season">
        <div className="flex min-w-max gap-2 px-1">
          {seasons.map((entry) => {
            const isSelected = entry.is_current ? selected === null : selected === entry.season;
            return (
              <button
                key={entry.season}
                type="button"
                aria-current={isSelected ? 'true' : undefined}
                /* Named rather than left to the text: the label alone does not say what
                   tapping it does, and the current entry's "now" badge runs into the year
                   when a screen reader concatenates them — "2026/27now". */
                aria-label={
                  entry.is_current
                    ? `Show ${entry.label}, the season being played`
                    : `Show the ${entry.label} season`
                }
                onClick={() => onSelect(entry.is_current ? null : entry.season)}
                className={cn(
                  'inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-medium font-sans whitespace-nowrap shadow-sm transition-colors press-down',
                  'focus-visible:outline-none focus-visible:shadow-glow',
                  isSelected
                    ? 'border-primary/40 bg-primary/15 text-primary'
                    : 'border-border bg-surface text-text-secondary hover:border-primary/40 hover:bg-surface-elevated hover:text-text-primary',
                )}
              >
                <span>{entry.label}</span>
                {entry.is_current && (
                  <span className="font-mono text-[10px] uppercase tracking-wider opacity-70">
                    now
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </nav>
      {selected !== null && (
        /* Said here rather than left to the member to infer from the year: a table that
           cannot change again reads exactly like a live one, and the difference matters
           most to whoever is at the top of it. */
        <p className="font-sans text-[11px] text-text-muted">
          A completed season. {current ? `Tap ${current.label} for the table being played.` : ''}
        </p>
      )}
    </section>
  );
}
