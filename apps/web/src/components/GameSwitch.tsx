import { Link } from "react-router-dom";
import { useGameNavigation } from "../hooks/useGameIntents";
import { currentWeeks, switchCard } from "../lib/gameSwitch";
import type { GameCard, GameKind, GameTarget } from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { cn } from "../lib/utils";

const NAME: Record<GameKind, string> = { group: "Group", fantasy: "Fantasy" };

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

/**
 * The top of the two-game coupon screen: one tap between the league's Group and Fantasy
 * (Batch 232), and between the fantasy weeks on screen at once.
 *
 * On a Saturday from noon both fantasy weeks are current — this week's results and next
 * week's entry — so the strip names each one. The links come from the home summary the
 * shell already holds; with no summary (an older API, or a league the summary does not
 * list) nothing renders and the screen carries on without it.
 */
export function GameSwitch({ target }: { target: GameTarget }) {
  const league = useGameNavigation().find(
    (value) => value.league_id === target.league_id,
  );
  if (!league) return null;
  const weeks = currentWeeks(league, "fantasy");
  return (
    <div className="mb-4 space-y-2">
      <nav
        aria-label="Game switch"
        className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface p-1"
      >
        {(["group", "fantasy"] as const).map((kind) => {
          const card = switchCard(league, kind);
          const active = kind === target.game_kind;
          const body = (
            <>
              <span className="font-sans text-sm font-semibold">{NAME[kind]}</span>
              <span
                className={cn(
                  "font-mono text-caption tabular-nums",
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
      {target.game_kind === "fantasy" && weeks.length > 1 && (
        <nav aria-label="Fantasy weeks" className="flex flex-wrap gap-2">
          {weeks.map((card) => (
            <Link
              key={card.week_id}
              to={card.destination}
              aria-current={card.week_id === target.week_id ? "page" : undefined}
              className={cn(
                "inline-flex min-h-11 items-center rounded-md border px-3 font-mono text-caption",
                "focus-visible:outline-hidden focus-visible:shadow-glow",
                card.week_id === target.week_id
                  ? "border-border-strong bg-surface-elevated text-text-primary"
                  : "border-border text-text-secondary",
              )}
            >
              {formatCalendarDate(card.week_label, "d MMM")} ·{" "}
              {card.purpose === "entry"
                ? "Open"
                : card.purpose === "results"
                  ? "Results"
                  : "Next"}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
