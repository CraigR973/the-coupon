import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, History, Home } from "lucide-react";
import { useGameNavigation } from "../hooks/useGameIntents";
import { switchTarget, weekStep, type WeekRelation } from "../lib/gameSwitch";
import type { GameCard, GameKind, GameTarget } from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import { Sheet } from "./ui/sheet";

const NAME: Record<GameKind, string> = { group: "Group", fantasy: "Fantasy" };

const RELATION: Record<WeekRelation, string> = {
  this: "This week",
  next: "Next week",
  past: "Results",
};

/** A square, icon-only link in the week bar. Colours change at once: no fade to cross. */
const ICON_LINK =
  "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-text-secondary hover:bg-surface-elevated hover:text-text-primary focus-visible:outline-hidden focus-visible:shadow-glow";

/** What a game's segment says about the member's part in it, in a few words. */
function standing(card: GameCard | undefined): string {
  if (!card) return "Not open yet";
  if (card.purpose === "upcoming")
    return `Opens ${formatInstant(card.opens_at, "Europe/London", "EEE HH:mm") ?? ""}`.trim();
  if (card.purpose === "results") return card.result.final ? "Final" : "Results";
  if (card.entry_state === "suspended") return "Suspended";
  if (card.entry_state === "cancelled") return "Cancelled";
  if (card.game_kind === "group") return card.my_entry?.pick ? "Picked" : "Pick needed";
  return `${card.progress.slots_filled ?? 0} of 6 picked`;
}

const day = (label: string) => formatCalendarDate(label, "EEE d MMM") ?? label;

/**
 * The top of both game screens (Batch 244): the week on screen, with arrows to the weeks
 * either side, then one tap between the league's Group and Fantasy for that week.
 *
 * It replaces Batch 232's strip of fantasy week chips. The arrows step back through earlier
 * weeks' results, into a legacy round where one comes first, and forward to next week once
 * it is announced; a dot on the forward arrow says next week's Fantasy is already open,
 * which on a Saturday afternoon is while this week's results are still coming in. Home and
 * the archive, the full list behind the week, sit at either end of the same bar.
 *
 * The weeks come from the home summary the shell already holds. With no summary (an older
 * API, or a league the summary does not list) the bar still names the week and keeps its
 * Home and archive links, without arrows or the switch.
 */
export function GameHeader({
  target,
  weekLabel,
}: {
  target: GameTarget;
  /** The shown week's Saturday, `yyyy-mm-dd`, from the screen's own read. */
  weekLabel: string;
}) {
  const league = useGameNavigation().find(
    (value) => value.league_id === target.league_id,
  );
  const step = league
    ? weekStep(league, { weekId: target.week_id, label: weekLabel }, target.game_kind)
    : null;
  return (
    <div className="space-y-3">
      <nav aria-label="Game navigation" className="flex items-center gap-1">
        <Link to="/" aria-label="Home" title="Home" className={ICON_LINK}>
          <Home className="h-5 w-5" aria-hidden />
        </Link>
        <div className="flex min-w-0 flex-1 items-center justify-center gap-1">
          {step?.previous ? (
            <Link
              to={step.previous.destination}
              aria-label={`Earlier week, ${day(step.previous.label)}`}
              className={ICON_LINK}
            >
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </Link>
          ) : (
            <span className="h-11 w-11 shrink-0" aria-hidden />
          )}
          <p className="min-w-0 px-1 text-center" data-testid="game-week">
            {step && (
              <span className="block eyebrow text-text-muted">{RELATION[step.relation]}</span>
            )}
            <span className="block truncate font-sans text-base font-semibold text-text-primary">
              {day(weekLabel)}
            </span>
          </p>
          {step?.next ? (
            <Link
              to={step.next.destination}
              aria-label={`Next week, ${day(step.next.label)}${step.next.fantasyOpen ? ", Fantasy open" : ""}`}
              className={cn(ICON_LINK, "relative")}
            >
              <ChevronRight className="h-5 w-5" aria-hidden />
              {step.next.fantasyOpen && (
                <span
                  className="absolute right-2 top-2 h-2 w-2 rounded-full bg-primary"
                  data-testid="next-week-dot"
                  aria-hidden
                />
              )}
            </Link>
          ) : (
            <span className="h-11 w-11 shrink-0" aria-hidden />
          )}
        </div>
        <Link
          to={`/leagues/${target.league_id}/games`}
          aria-label="Game archive"
          title="Game archive"
          className={ICON_LINK}
        >
          <History className="h-5 w-5" aria-hidden />
        </Link>
      </nav>
      {league && (
        <nav
          aria-label="Game switch"
          className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface p-1"
        >
          {(["group", "fantasy"] as const).map((kind) => {
            const card = switchTarget(league, kind, target.week_id);
            const active = kind === target.game_kind;
            const body = (
              <>
                <span className="font-sans text-sm font-semibold">{NAME[kind]}</span>
                <span
                  className={cn(
                    "font-sans text-caption tabular-nums",
                    active ? "text-text-secondary" : "text-text-muted",
                  )}
                >
                  {standing(card)}
                </span>
              </>
            );
            const shape = cn(
              "flex min-h-11 flex-col items-center justify-center rounded-md px-2 py-1 text-center",
              "focus-visible:outline-hidden focus-visible:shadow-glow",
              active
                ? "bg-surface-elevated text-text-primary border border-border-strong"
                : "text-text-secondary",
            );
            return card ? (
              <Link
                key={kind}
                to={card.destination}
                className={shape}
                aria-current={
                  active && card.week_id === target.week_id ? "page" : undefined
                }
              >
                {body}
              </Link>
            ) : (
              <span key={kind} className={shape}>
                {body}
              </span>
            );
          })}
        </nav>
      )}
    </div>
  );
}

/**
 * A game's rules as one line, with the full text one tap away (Batch 244). The sheet holds
 * the screen's existing rule sentences, so nothing is lost by moving them out of the way.
 */
export function GameRules({
  summary,
  children,
}: {
  summary: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement | null>(null);
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 font-sans text-sm text-text-secondary">{summary}</p>
        <button
          ref={button}
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex min-h-11 shrink-0 items-center font-sans text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-hidden focus-visible:shadow-glow"
        >
          How it works
        </button>
      </div>
      <Sheet open={open} onClose={() => setOpen(false)} title="How it works" triggerRef={button}>
        <div className="space-y-3 pb-2 font-sans text-sm text-text-secondary">
          {children}
        </div>
      </Sheet>
    </>
  );
}
