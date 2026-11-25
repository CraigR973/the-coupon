import { Check, CloudOff, HelpCircle, Loader2 } from "lucide-react";
import { FixtureHead } from "./FixtureRow";
import { fantasyRunner, fantasyResultLabel } from "../lib/fantasy";
import type { Selection } from "../lib/fantasySlip";
import { formatOdds, outcomeLabel } from "../lib/coupon";
import { formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import type { FantasyFixture, GamePick } from "../lib/twoGameTypes";
import type { OddsFormat, PickMarket, PickOutcome } from "../lib/types";

const MARKET_ORDER = ["MATCH_ODDS", "BOTH_TEAMS_TO_SCORE"];
const OUTCOME_ORDER: Record<string, number> = { HOME: 0, DRAW: 1, AWAY: 2, YES: 0, NO: 1 };

/** Where the member's own selection on this card stands, as the slip knows it. */
export interface HeldOnCard {
  selection: Selection;
  slot: number;
  /** The saved pick, once there is one; absent while the first save is on its way. */
  pick: GamePick | null;
  /** The engine's phase for a choice on its way, if one is. */
  phase?: string;
}

export interface FantasyFixtureCardProps {
  fixture: FantasyFixture;
  /** The competition's display name, as its section heading gives it. */
  competition: string;
  oddsFormat: OddsFormat;
  /** The member's selection on this fixture, in the slot a tap here would write to. */
  held: HeldOnCard | null;
  /** Another slot holds this fixture while the list is choosing for one slot. */
  heldElsewhere: boolean;
  /** Whether a tap here may save now — the game is open and the destination slot is free to write. */
  canChoose: boolean;
  onChoose: (market: string, outcome: string, odds: string) => void;
  /** Batch 235: withdraw the member's own pick from its slot — a second tap on it. */
  onRemove?: (slot: number) => void;
}

/** The outcome a price button names, short, because the clubs sit above it (Batch 245). */
const SHORT: Record<string, string> = {
  HOME: "Home",
  DRAW: "Draw",
  AWAY: "Away",
  YES: "Both score",
  NO: "Not both",
};

/**
 * One fantasy fixture as a compact row (Batch 245): the clubs with their position and form,
 * the kick-off between them, and Home, Draw and Away as three price buttons side by side.
 * It replaces Batch 232's card, which repeated the competition and the date inside its own
 * section and laid the prices out two to a line, so about one and a half fitted a phone.
 *
 * A tap saves at once, into the slot the page names for it. The accessible names are the
 * six-slot screen's ("Choose Home 1 to win at 2.1500"), so the price a member hears is
 * the exact decimal the save sends. Both-teams-to-score prices, where a fixture has them,
 * take a second line of two.
 */
export function FantasyFixtureCard({
  fixture,
  oddsFormat,
  held,
  heldElsewhere,
  canChoose,
  onChoose,
  onRemove,
}: FantasyFixtureCardProps) {
  const prices = [...fixture.quote.prices].sort(
    (a, b) =>
      MARKET_ORDER.indexOf(a.market) - MARKET_ORDER.indexOf(b.market) ||
      (OUTCOME_ORDER[a.outcome] ?? 9) - (OUTCOME_ORDER[b.outcome] ?? 9),
  );
  const priced = ["available", "stale"].includes(fixture.quote.availability);
  const kickoff = formatInstant(fixture.kickoff_at, "Europe/London", "EEE HH:mm") ?? "";
  const button = (price: (typeof prices)[number]) => (
    <PriceButton
      key={`${price.market}/${price.outcome}`}
      fixture={fixture}
      market={price.market}
      outcome={price.outcome}
      odds={price.odds}
      oddsFormat={oddsFormat}
      held={
        held &&
        held.selection.market === price.market &&
        held.selection.outcome === price.outcome
          ? held
          : null
      }
      canChoose={canChoose && priced && !heldElsewhere}
      onChoose={onChoose}
      onRemove={held && onRemove ? () => onRemove(held.slot) : undefined}
    />
  );
  const result = prices.filter((price) => price.market === "MATCH_ODDS");
  const others = prices.filter((price) => price.market !== "MATCH_ODDS");
  return (
    <div
      className={cn(
        "rounded-lg border bg-surface px-3 py-2.5",
        held ? "border-success/60" : "border-border",
      )}
      data-testid={`fantasy-card-${fixture.fixture_id}`}
    >
      <FixtureHead fixture={fixture} kickoff={kickoff} muted={!fixture.eligible} />
      {prices.length === 0 ? (
        <p className="mt-2 font-sans text-xs text-text-muted">No prices yet.</p>
      ) : (
        <>
          {result.length > 0 && (
            <div className="mt-2 grid grid-cols-3 gap-1.5">{result.map(button)}</div>
          )}
          {others.length > 0 && (
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">{others.map(button)}</div>
          )}
        </>
      )}
      {held && (
        <p className="mt-2 eyebrow text-success">
          Your pick · slot {held.slot}
        </p>
      )}
      {heldElsewhere && (
        <p className="mt-2 font-sans text-xs text-text-muted">
          Already chosen in another slot.
        </p>
      )}
      {!fixture.eligible && (
        <p className="mt-2 font-sans text-xs text-text-muted">
          This fixture can no longer be picked.
        </p>
      )}
      {fixture.quote.degraded && prices.length > 0 && (
        <p className="mt-1.5 font-sans text-xs text-text-muted">
          These prices come from a degraded source and may be out of date.
        </p>
      )}
    </div>
  );
}

function PriceButton({
  fixture,
  market,
  outcome,
  odds,
  oddsFormat,
  held,
  canChoose,
  onChoose,
  onRemove,
}: {
  fixture: FantasyFixture;
  market: string;
  outcome: string;
  odds: string;
  oddsFormat: OddsFormat;
  held: HeldOnCard | null;
  canChoose: boolean;
  onChoose: (market: string, outcome: string, odds: string) => void;
  onRemove?: () => void;
}) {
  const label = outcomeLabel(
    market as PickMarket,
    outcome as PickOutcome,
    fixture.home,
    fixture.away,
  );
  const mine = !!held;
  const sending = held?.phase === "checking" || held?.phase === "sending";
  const waiting = held?.phase === "queued" || held?.phase === "uncertain";
  const settled =
    held?.pick && held.pick.result !== "pending" ? held.pick.result : null;
  const frozen = held?.pick?.frozen_odds;
  // A member's own selection stays focusable while it saves, so the keyboard is not
  // thrown to the top of the page by the very tap it made. Batch 235: once it is saved, a
  // second tap removes it, as a pressed toggle releases; while it saves, a tap does nothing.
  const actionable = canChoose && !mine;
  const removable =
    mine && canChoose && !!onRemove && !!held?.pick && !sending && !waiting && !settled;
  return (
    <button
      type="button"
      disabled={!canChoose && !mine}
      aria-disabled={!actionable && !removable}
      aria-pressed={mine}
      aria-label={`Choose ${fantasyRunner(fixture, outcome)} at ${odds}`}
      onClick={() => {
        if (actionable) onChoose(market, outcome, odds);
        else if (removable) onRemove?.();
      }}
      data-testid={`fantasy-price-${fixture.fixture_id}-${market}-${outcome}`}
      className={cn(
        "flex min-h-11 flex-col items-center justify-center gap-0.5 rounded-md px-1.5 py-1 text-center",
        // Batch 235: a member's own price is tappable now (to remove it), so the accessibility
        // scan reads its colours; it must not be caught mid-fade by a theme flip. Batch 242: no
        // price fades at all. The tile's own colours faded while its points line, which sets
        // its own colour, switched at once, so mid-fade the line sat on the old background.
        "transition-none",
        settled === "won"
          ? "border border-success bg-surface text-text-primary"
          : settled === "lost"
            ? "border border-error bg-surface text-text-primary"
            : settled === "void"
              ? "border border-border bg-surface-elevated text-text-primary"
              : mine
                ? "border-2 border-success bg-success/[0.08] dark:bg-success/15 text-text-primary"
                : actionable
                  ? "border border-border bg-surface-elevated text-text-primary hover:border-primary/60 press-down cursor-pointer"
                  : "cursor-not-allowed border border-border/50 bg-surface opacity-60",
        "focus-visible:outline-hidden focus-visible:shadow-glow",
      )}
    >
      <span
        className={cn(
          "flex max-w-full items-center gap-1 font-sans text-caption font-medium",
          mine ? "text-text-primary" : "text-text-secondary",
        )}
      >
        {mine && <Check className="h-3 w-3 shrink-0" aria-hidden />}
        <span className="truncate">{SHORT[outcome] ?? label}</span>
        {sending && <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden />}
        {!sending && waiting && (
          <span className="shrink-0 text-amber-300" aria-hidden>
            {held?.phase === "queued" ? (
              <CloudOff className="h-3 w-3" />
            ) : (
              <HelpCircle className="h-3 w-3" />
            )}
          </span>
        )}
      </span>
      <span className="font-mono text-sm font-semibold tabular-nums">
        {formatOdds(Number(frozen ?? odds), oddsFormat)}
      </span>
      {(waiting || settled) && (
        <span
          className={cn(
            "w-full break-words text-caption font-sans font-medium normal-case tracking-normal text-text-muted",
            settled === "won" && "text-success",
            settled === "lost" && "text-error",
          )}
        >
          {waiting
            ? held?.phase === "queued"
              ? "Waiting to send"
              : "Unconfirmed"
            : settled
              ? `${fantasyResultLabel(settled)}${settled === "won" ? ` · ${held?.pick?.points ?? 0} pts` : ""}`
              : null}
        </span>
      )}
    </button>
  );
}
