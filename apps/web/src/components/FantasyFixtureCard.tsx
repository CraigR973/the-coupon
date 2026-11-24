import { Check, CloudOff, HelpCircle, Loader2 } from "lucide-react";
import { Badge } from "./ui/badge";
import { ClubContext } from "./FormLine";
import { fantasyRunner, fantasyResultLabel } from "../lib/fantasy";
import { fantasyPoints, type Selection } from "../lib/fantasySlip";
import { formatOdds, marketLabel, outcomeLabel } from "../lib/coupon";
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

/**
 * One fantasy fixture as the old coupon drew it (Batch 232): competition and kick-off,
 * the two clubs, and each price as a button carrying the selection, the price in the
 * member's notation and what it would score.
 *
 * A tap saves at once, into the slot the page names for it. The accessible names are the
 * six-slot screen's ("Choose Home 1 to win at 2.1500"), so the price a member hears is
 * the exact decimal the save sends.
 */
export function FantasyFixtureCard({
  fixture,
  competition,
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
  const markets = MARKET_ORDER.filter((market) =>
    prices.some((price) => price.market === market),
  );
  const priced = ["available", "stale"].includes(fixture.quote.availability);
  const kickoff =
    formatInstant(fixture.kickoff_at, "Europe/London", "EEE d MMM, HH:mm") ?? "";
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border bg-surface px-4 py-3",
        held ? "border-success/60" : "border-border",
      )}
      data-testid={`fantasy-card-${fixture.fixture_id}`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <Badge variant="muted">{competition}</Badge>
        <span className="shrink-0 font-mono text-caption uppercase tracking-[0.2em] text-text-muted">
          {kickoff}
        </span>
      </div>
      <div className="relative mb-2 grid grid-cols-2 items-baseline gap-2">
        <p className="min-w-0 truncate pr-3 text-sm font-sans font-medium text-text-primary">
          {fixture.home}
        </p>
        <span className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 text-sm text-text-muted">
          v
        </span>
        <p className="min-w-0 truncate pl-3 text-right text-sm font-sans font-medium text-text-primary">
          {fixture.away}
        </p>
      </div>
      {fixture.context && (
        <div className="-mt-1 mb-2 grid grid-cols-2 gap-2">
          <ClubContext team={fixture.context.home} />
          <ClubContext team={fixture.context.away} align="right" />
        </div>
      )}
      {held && (
        <p className="mb-3 font-mono text-caption uppercase tracking-[0.2em] text-success-ink">
          Your pick · slot {held.slot}
        </p>
      )}
      {heldElsewhere && (
        <p className="mb-3 font-sans text-xs text-text-muted">
          Already chosen in another slot.
        </p>
      )}
      {!fixture.eligible && (
        <p className="mb-3 font-sans text-xs text-text-muted">
          This fixture can no longer be picked.
        </p>
      )}
      {prices.length === 0 ? (
        <p className="text-xs font-sans text-text-muted">
          Prices unavailable. Refresh prices to check again.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {markets.map((market) => (
            <div key={market}>
              <p className="mb-1 font-mono text-caption uppercase tracking-[0.2em] text-text-muted">
                {marketLabel(market as PickMarket)}
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {prices
                  .filter((price) => price.market === market)
                  .map((price) => (
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
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {fixture.quote.degraded && prices.length > 0 && (
        <p className="mt-2 font-sans text-xs text-text-muted">
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
  const points = fantasyPoints(frozen ?? odds);
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
        "flex min-h-[56px] flex-col items-start justify-center gap-0.5 rounded-md px-2.5 py-2 text-left",
        // Batch 235: a member's own price is tappable now (to remove it), so the accessibility
        // scan reads its colours; it must not be caught mid-fade by a theme flip.
        mine ? "transition-none" : "transition-colors",
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
      <span className="flex w-full items-start justify-between gap-1">
        <span className="min-w-0 break-words text-label font-sans font-medium sm:truncate">
          {mine && <Check className="mr-0.5 inline h-3 w-3" aria-hidden />}
          {label}
        </span>
        {sending && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />}
        {!sending && waiting && (
          <span className="shrink-0 text-amber-300" aria-hidden>
            {held?.phase === "queued" ? (
              <CloudOff className="h-3.5 w-3.5" />
            ) : (
              <HelpCircle className="h-3.5 w-3.5" />
            )}
          </span>
        )}
      </span>
      <span className="font-mono text-price tabular-nums">
        {formatOdds(Number(frozen ?? odds), oddsFormat)}
      </span>
      <span
        className={cn(
          "w-full truncate text-caption font-mono uppercase tracking-wide text-text-muted",
          mine && !settled && "text-text-secondary",
          settled && "font-sans normal-case tracking-normal",
          settled === "won" && "text-success-ink",
          settled === "lost" && "text-error-ink",
        )}
      >
        {waiting
          ? held?.phase === "queued"
            ? "waiting to send"
            : "unconfirmed"
          : settled
            ? `${fantasyResultLabel(settled)}${settled === "won" ? ` · ${held?.pick?.points ?? 0} pts` : ""}`
            : mine
              ? `your pick${points !== null ? ` · ${points} pts` : ""}`
              : points !== null
                ? `win ${points} pts`
                : ""}
      </span>
    </button>
  );
}
