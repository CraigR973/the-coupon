import { useCallback, useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ResultDay } from '@/lib/footballResults';
import { cn } from '@/lib/utils';

interface Props {
  /** Every result-bearing day, newest first. */
  days: ResultDay[];
  /** The day on screen. */
  selected: string;
  onSelect: (date: string) => void;
}

/**
 * Move through the result archive one matchday at a time (Batch 109).
 *
 * Football Results was a single column of every day we hold, so reaching the Saturday
 * before last meant scrolling past eighty matches to get to it. The task is almost
 * always "show me a different matchday", and this is the control for that task: a
 * strip of the days that exist, plus a step either side of the one being read.
 *
 * **The list is newest-first and the strip is not.** Newest-first is what the page
 * defaults to and what `older`/`newer` index against — the same convention
 * `useGameweekHistory` uses. But a row of dates reads left-to-right as a calendar
 * does, so the strip renders reversed and the chevrons point the way time runs:
 * left is earlier, right is later.
 */
export function ResultDayCarousel({ days, selected, onSelect }: Props) {
  const stripRef = useRef<HTMLDivElement>(null);
  const chips = useRef(new Map<string, HTMLButtonElement>());
  // Set only by the arrow keys. A tap must not pull focus back to the chip — the
  // finger is already there — but an arrow press has to carry focus with the
  // selection or the next press would move from wherever focus was left behind.
  const focusAfterSelect = useRef(false);

  const index = days.findIndex((day) => day.date === selected);
  const older = index >= 0 ? days[index + 1] : undefined;
  const newer = index > 0 ? days[index - 1] : undefined;

  useEffect(() => {
    const chip = chips.current.get(selected);
    if (!chip) return;
    // jsdom implements neither `scrollIntoView` nor layout, so the strip does not
    // scroll under test; selection is asserted instead, which is the behaviour.
    if (typeof chip.scrollIntoView === 'function') {
      /**
       * `instant`, and the container carries no `scroll-smooth`, because a smooth
       * scroll and `scroll-snap-type: mandatory` together simply refuse a long one.
       * Measured in Chrome on a full season: arriving on the newest day, with the
       * chip 8,443px along an 8,486px strip, left `scrollLeft` at 404 and never
       * moved — the heading said May and the strip showed the previous August.
       * Short hops worked, which is exactly how this hides until the archive fills.
       */
      chip.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'instant' });
    }
    if (focusAfterSelect.current) {
      focusAfterSelect.current = false;
      chip.focus();
    }
  }, [selected]);

  const step = useCallback(
    (day: ResultDay | undefined, withFocus: boolean) => {
      if (!day) return;
      focusAfterSelect.current = withFocus;
      onSelect(day.date);
    },
    [onSelect],
  );

  /**
   * Arrow keys move along the strip, Home and End jump to its ends.
   *
   * Only the selected chip is tabbable, so a season of Saturdays costs one tab stop
   * rather than sixty. That is the standard trade and it is only honest if the arrows
   * work, which is why this is on the toolbar rather than left to the buttons.
   */
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const target =
      event.key === 'ArrowLeft'
        ? older
        : event.key === 'ArrowRight'
          ? newer
          : event.key === 'Home'
            ? days[days.length - 1]
            : event.key === 'End'
              ? days[0]
              : undefined;
    if (!target || target.date === selected) return;
    event.preventDefault();
    step(target, true);
  };

  return (
    <nav aria-label="Result days" className="mb-4 space-y-2" data-testid="result-day-carousel">
      <div className="flex items-center gap-2">
        <StepButton
          label="Previous day with results"
          onClick={() => step(older, false)}
          disabled={!older}
          testId="result-day-previous"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </StepButton>

        <div
          ref={stripRef}
          role="toolbar"
          aria-label="Choose a result day"
          aria-orientation="horizontal"
          onKeyDown={onKeyDown}
          className="-mx-1 flex-1 snap-x snap-mandatory overflow-x-auto px-1"
          data-testid="result-day-strip"
        >
          <div className="flex min-w-max items-center gap-2">
            {[...days].reverse().map((day) => {
              const isSelected = day.date === selected;
              return (
                <button
                  key={day.date}
                  ref={(node) => {
                    if (node) chips.current.set(day.date, node);
                    else chips.current.delete(day.date);
                  }}
                  type="button"
                  data-date={day.date}
                  data-testid={`result-day-${day.date}`}
                  /* `date` rather than `true`: the strip is a run of days and this is
                     the one being read, which is exactly what the token means. */
                  aria-current={isSelected ? 'date' : undefined}
                  tabIndex={isSelected ? 0 : -1}
                  /* The chip says "Sat 2 May" because sixty of them share a row. That
                     is not enough on its own — no year, and the count is a bare number
                     beside it — so the accessible name says the whole thing. */
                  aria-label={`Show ${day.matchCount} ${
                    day.matchCount === 1 ? 'result' : 'results'
                  } from ${day.label}`}
                  onClick={() => step(day, false)}
                  className={cn(
                    'inline-flex snap-center items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-1.5 font-sans text-xs font-medium shadow-sm transition-colors tap-target press-down',
                    'focus-visible:outline-none focus-visible:shadow-glow',
                    isSelected
                      ? 'border-primary/40 bg-primary/15 text-primary'
                      : 'border-border bg-surface text-text-secondary hover:border-primary/40 hover:bg-surface-elevated hover:text-text-primary',
                  )}
                >
                  <span aria-hidden>{day.short}</span>
                  <span
                    aria-hidden
                    className={cn(
                      'font-mono text-[10px] tabular-nums',
                      isSelected ? 'opacity-70' : 'text-text-muted',
                    )}
                  >
                    {day.matchCount}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <StepButton
          label="Next day with results"
          onClick={() => step(newer, false)}
          disabled={!newer}
          testId="result-day-next"
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </StepButton>
      </div>
    </nav>
  );
}

function StepButton({
  label,
  onClick,
  disabled,
  testId,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
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
