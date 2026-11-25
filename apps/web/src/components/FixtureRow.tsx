import { ClubContext } from "./FormLine";
import { cn } from "../lib/utils";
import type { FixtureContext } from "../lib/types";

/**
 * The top of a compact fixture row on both games (Batch 245): the two clubs either side of
 * a "v", and under each its table position and form, with the kick-off between them. The
 * three columns line up with the Home, Draw and Away buttons beneath.
 */
export function FixtureHead({
  fixture,
  kickoff,
  muted = false,
}: {
  fixture: {
    home: string;
    away: string;
    context?: FixtureContext | null;
  };
  kickoff: string;
  /** Another member's fixture, or one that can no longer be picked. */
  muted?: boolean;
}) {
  const club = cn(
    "min-w-0 truncate font-sans text-sm font-semibold",
    muted ? "text-text-secondary" : "text-text-primary",
  );
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 gap-y-0.5">
      <p className={club}>{fixture.home}</p>
      <span className="text-center font-sans text-xs text-text-muted" aria-hidden>
        v
      </span>
      <p className={cn(club, "text-right")}>{fixture.away}</p>
      <div className="min-w-0">
        {fixture.context && <ClubContext team={fixture.context.home} />}
      </div>
      <span className="whitespace-nowrap text-center font-sans text-caption tabular-nums text-text-muted">
        {kickoff}
      </span>
      <div className="min-w-0">
        {fixture.context && <ClubContext team={fixture.context.away} align="right" />}
      </div>
    </div>
  );
}

/**
 * A competition's header, kept in view under the top bar while its fixtures scroll
 * (Batch 245). The offsets are the offline banner's: the bar is 52px tall on a phone and 56px
 * from `sm`, plus its 1px border and the safe area.
 */
export const STICKY_HEADER =
  "sticky top-[calc(53px+var(--safe-top))] z-[5] sm:top-[calc(57px+var(--safe-top))]";

/** Room left above a competition when a jump chip scrolls to it, so the bar does not hide it. */
export const SECTION_SCROLL_MARGIN =
  "scroll-mt-[calc(61px+var(--safe-top))] sm:scroll-mt-[calc(65px+var(--safe-top))]";

/**
 * One chip per competition at the top of a game's fixtures (Batch 245), each a link to its
 * section with the count its header shows. Links rather than buttons, so a chip is never
 * mistaken for the header it jumps to.
 */
export function CompetitionChips({
  label,
  chips,
  onJump,
}: {
  label: string;
  chips: { id: string; anchor: string; name: string; count: string }[];
  /** Opens a folded section before the browser scrolls to it. */
  onJump?: (id: string) => void;
}) {
  if (chips.length < 2) return null;
  return (
    <nav aria-label={label} className="-mx-1 overflow-x-auto px-1 pb-1">
      <ul className="flex w-max gap-2">
        {chips.map((chip) => (
          <li key={chip.id}>
            <a
              href={`#${chip.anchor}`}
              onClick={() => onJump?.(chip.id)}
              className="inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-full border border-border bg-surface px-3 font-sans text-sm font-medium text-text-primary hover:border-primary/60 focus-visible:outline-hidden focus-visible:shadow-glow"
            >
              {chip.name}
              <span className="font-mono text-caption tabular-nums text-text-muted">
                {chip.count}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
