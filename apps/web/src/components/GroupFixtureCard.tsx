import type { ReactNode } from "react";
import { Check, CloudOff, HelpCircle, Loader2 } from "lucide-react";
import { Badge } from "./ui/badge";
import { ClubContext } from "./FormLine";
import {
  groupResultLabel,
  groupSelection,
  shortName,
} from "../lib/groupCoupon";
import { formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import type { GroupFixture } from "../lib/twoGameTypes";

const MARKET_ORDER = ["MATCH_ODDS", "BOTH_TEAMS_TO_SCORE"];
const OUTCOME_ORDER: Record<string, number> = { HOME: 0, DRAW: 1, AWAY: 2, YES: 0, NO: 1 };
/** "Match result", not the legacy "Match Odds": nothing on the group screen is priced. */
const MARKET_LABEL: Record<string, string> = {
  MATCH_ODDS: "Match result",
  BOTH_TEAMS_TO_SCORE: "Both teams to score",
};

/** The member's choice on its way to this fixture, as the save engine reports it. */
export interface PendingGroupChoice {
  market: string;
  outcome: string;
  phase: string;
}

export interface GroupFixtureCardProps {
  fixture: GroupFixture;
  /** The competition's display name, as its section heading gives it. */
  competition: string;
  memberId: string | undefined;
  pending: PendingGroupChoice | null;
  /** The game is open and the member's saved contribution is verified. */
  canChoose: boolean;
  onChoose: (market: string, outcome: string) => void;
  /** Batch 235: withdraw the member's own saved pick — a second tap on it. */
  onRemove?: () => void;
  /** The save's status, when it is about this fixture. */
  children?: ReactNode;
}

/**
 * One Saturday fixture as the old coupon drew it (Batch 233): competition and kick-off,
 * the two clubs, and each selection as a button. Group picks are never priced, so the
 * buttons carry the selection alone.
 *
 * A fixture belongs to one member across the group. Another member's reads "Picked by
 * <name>" and greys out entirely; the member's own reads "Your game", and another of its
 * selections switches the pick in place.
 */
export function GroupFixtureCard({
  fixture,
  competition,
  memberId,
  pending,
  canChoose,
  onChoose,
  onRemove,
  children,
}: GroupFixtureCardProps) {
  const claim = fixture.claim;
  const mine = !!claim && claim.player_id === memberId;
  const takenBy = claim && !mine ? claim : null;
  const closed = !!takenBy || !fixture.eligible;
  const settled = claim && claim.result !== "pending" ? claim.result : null;
  const kickoff =
    formatInstant(fixture.kickoff_at, "Europe/London", "EEE d MMM, HH:mm") ?? "";
  const markets = MARKET_ORDER.filter((market) =>
    fixture.allowed_markets.some((value) => value.market === market),
  );
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border bg-surface px-4 py-3",
        mine ? "border-success/60" : closed ? "border-border/50" : "border-border",
      )}
      data-testid={`group-card-${fixture.fixture_id}`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <Badge variant="muted">{competition}</Badge>
        <span className="shrink-0 font-mono text-caption uppercase tracking-[0.2em] text-text-muted">
          {kickoff}
        </span>
      </div>
      <div className="relative mb-2 grid grid-cols-2 items-baseline gap-2">
        <p
          className={cn(
            "min-w-0 truncate pr-3 text-sm font-sans font-medium",
            closed ? "text-text-secondary" : "text-text-primary",
          )}
        >
          {fixture.home}
        </p>
        <span className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 text-sm text-text-muted">
          v
        </span>
        <p
          className={cn(
            "min-w-0 truncate pl-3 text-right text-sm font-sans font-medium",
            closed ? "text-text-secondary" : "text-text-primary",
          )}
        >
          {fixture.away}
        </p>
      </div>
      {fixture.context && (
        <div className="-mt-1 mb-2 grid grid-cols-2 gap-2">
          <ClubContext team={fixture.context.home} />
          <ClubContext team={fixture.context.away} align="right" />
        </div>
      )}
      {claim && (
        <p
          className={cn(
            "mb-3 font-mono text-caption uppercase tracking-[0.2em]",
            mine ? "text-success-ink" : "text-text-secondary",
          )}
          data-testid={`group-claim-${fixture.fixture_id}`}
        >
          {mine ? "Your game" : `Picked by ${shortName(claim.display_name)}`}
          {settled ? ` · ${groupResultLabel(settled)}` : ""}
        </p>
      )}
      {!fixture.eligible && !claim && (
        <p className="mb-3 font-sans text-xs text-text-muted">
          This fixture is unavailable for a new contribution.
        </p>
      )}
      <div className="flex flex-col gap-3">
        {markets.map((market) => {
          const outcomes = [
            ...(fixture.allowed_markets.find((value) => value.market === market)
              ?.outcomes ?? []),
          ].sort((a, b) => (OUTCOME_ORDER[a] ?? 9) - (OUTCOME_ORDER[b] ?? 9));
          return (
            <div key={market}>
              <p className="mb-1 font-mono text-caption uppercase tracking-[0.2em] text-text-muted">
                {MARKET_LABEL[market] ?? market}
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {outcomes.map((outcome) => {
                  const held =
                    !!claim && claim.market === market && claim.outcome === outcome;
                  return (
                    <SelectionButton
                      key={`${market}/${outcome}`}
                      fixture={fixture}
                      market={market}
                      outcome={outcome}
                      pressed={mine && held}
                      holder={takenBy && held ? shortName(takenBy.display_name) : null}
                      settled={held ? settled : null}
                      phase={
                        pending &&
                        pending.market === market &&
                        pending.outcome === outcome
                          ? pending.phase
                          : null
                      }
                      actionable={canChoose && !closed && !(mine && held)}
                      removable={canChoose && mine && held && !settled && !pending}
                      onChoose={onChoose}
                      onRemove={onRemove}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}

function SelectionButton({
  fixture,
  market,
  outcome,
  pressed,
  holder,
  settled,
  phase,
  actionable,
  removable,
  onChoose,
  onRemove,
}: {
  fixture: GroupFixture;
  market: string;
  outcome: string;
  /** The member's saved pick. */
  pressed: boolean;
  /** Another member holds this exact selection. */
  holder: string | null;
  settled: string | null;
  /** The engine's phase while the member's choice of this selection is on its way. */
  phase: string | null;
  actionable: boolean;
  /** Batch 235: the member's own saved pick, which a second tap withdraws. */
  removable: boolean;
  onChoose: (market: string, outcome: string) => void;
  onRemove?: () => void;
}) {
  const { label, name } = groupSelection(fixture, market, outcome);
  const sending = phase === "sending" || phase === "checking";
  const waiting = phase === "queued" || phase === "uncertain";
  // The selection a tap just chose stays focusable while it saves, so the keyboard is
  // not thrown to the top of the page by the tap that made it; a second tap does nothing.
  const keepsFocus = pressed || sending || waiting;
  const caption = waiting
    ? phase === "queued"
      ? "waiting to send"
      : "unconfirmed"
    : settled
      ? `${groupResultLabel(settled)} · ${pressed ? "your pick" : (holder ?? "")}`
      : pressed
        ? "your pick"
        : holder
          ? `${holder}’s pick`
          : null;
  return (
    <button
      type="button"
      disabled={!actionable && !keepsFocus}
      aria-disabled={!actionable && !removable}
      aria-pressed={pressed}
      aria-label={`Choose ${name}`}
      onClick={() => {
        if (actionable) onChoose(market, outcome);
        else if (removable) onRemove?.();
      }}
      data-testid={`group-selection-${fixture.fixture_id}-${market}-${outcome}`}
      className={cn(
        "flex min-h-[56px] flex-col items-start justify-center gap-0.5 rounded-md px-2.5 py-2 text-left",
        // Batch 235: the member's own pick is tappable now (to withdraw it), so the
        // accessibility scan reads its colours; it must not be caught mid-fade.
        pressed ? "transition-none" : "transition-colors",
        settled === "won"
          ? "cursor-not-allowed border border-success bg-surface text-text-primary"
          : settled === "lost"
            ? "cursor-not-allowed border border-error bg-surface text-text-primary"
            : settled === "void"
              ? "cursor-not-allowed border border-border bg-surface-elevated text-text-primary"
              : pressed
                ? "border-2 border-success bg-success/[0.08] dark:bg-success/15 text-text-primary"
                : actionable
                  ? "border border-border bg-surface-elevated text-text-primary hover:border-primary/60 press-down cursor-pointer"
                  : "cursor-not-allowed border border-border/50 bg-surface opacity-55",
        "focus-visible:outline-hidden focus-visible:shadow-glow",
      )}
    >
      <span className="flex w-full items-start justify-between gap-1">
        <span className="min-w-0 break-words text-label font-sans font-medium sm:truncate">
          {pressed && <Check className="mr-0.5 inline h-3 w-3" aria-hidden />}
          {label}
        </span>
        {sending && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />}
        {waiting && (
          <span className="shrink-0 text-amber-300" aria-hidden>
            {phase === "queued" ? (
              <CloudOff className="h-3.5 w-3.5" />
            ) : (
              <HelpCircle className="h-3.5 w-3.5" />
            )}
          </span>
        )}
      </span>
      {caption && (
        <span
          className={cn(
            "w-full truncate text-caption font-mono uppercase tracking-wide text-text-muted",
            pressed && !settled && "text-text-secondary",
            settled && "font-sans normal-case tracking-normal",
            settled === "won" && "text-success-ink",
            settled === "lost" && "text-error-ink",
          )}
        >
          {caption}
        </span>
      )}
    </button>
  );
}
