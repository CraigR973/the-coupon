import { useRef, useState, type ReactNode } from "react";
import { Check, CloudOff, HelpCircle, Loader2 } from "lucide-react";
import { FixtureHead } from "./FixtureRow";
import { Sheet } from "./ui/sheet";
import {
  groupResultLabel,
  groupSelection,
  shortName,
} from "../lib/groupCoupon";
import { formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import type { GroupFixture } from "../lib/twoGameTypes";

const OUTCOME_ORDER: Record<string, number> = { HOME: 0, DRAW: 1, AWAY: 2, YES: 0, NO: 1 };

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

/** The outcome a result button names, short, because the clubs sit above it (Batch 245). */
const SHORT: Record<string, string> = { HOME: "Home", DRAW: "Draw", AWAY: "Away" };

/**
 * One Saturday fixture as a compact row (Batch 245), shaped like a Fantasy row (owner, 25 Nov
 * 2026): the clubs with their position and form, the kick-off between them, and Home, Draw and
 * Away as three buttons, so one tap picks. Both teams to score sits behind a fourth button
 * that opens a sheet. Group picks are never priced, so the buttons carry the selection alone.
 *
 * A fixture belongs to one member across the group. Another member's reads "Picked by
 * <name>" and greys out entirely; the member's own reads "Your game", and another of its
 * selections switches the pick in place.
 */
export function GroupFixtureCard({
  fixture,
  memberId,
  pending,
  canChoose,
  onChoose,
  onRemove,
  children,
}: GroupFixtureCardProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLButtonElement | null>(null);
  const claim = fixture.claim;
  const mine = !!claim && claim.player_id === memberId;
  const takenBy = claim && !mine ? claim : null;
  const closed = !!takenBy || !fixture.eligible;
  const settled = claim && claim.result !== "pending" ? claim.result : null;
  const kickoff = formatInstant(fixture.kickoff_at, "Europe/London", "EEE HH:mm") ?? "";
  const outcomesOf = (market: string) =>
    [...(fixture.allowed_markets.find((value) => value.market === market)?.outcomes ?? [])].sort(
      (a, b) => (OUTCOME_ORDER[a] ?? 9) - (OUTCOME_ORDER[b] ?? 9),
    );
  const result = outcomesOf("MATCH_ODDS");
  const btts = outcomesOf("BOTH_TEAMS_TO_SCORE");
  const button = (market: string, outcome: string, wide = false) => {
    const held = !!claim && claim.market === market && claim.outcome === outcome;
    return (
      <SelectionButton
        key={`${market}/${outcome}`}
        fixture={fixture}
        market={market}
        outcome={outcome}
        short={wide ? null : (SHORT[outcome] ?? null)}
        pressed={mine && held}
        holder={takenBy && held ? shortName(takenBy.display_name) : null}
        settled={held ? settled : null}
        phase={
          pending && pending.market === market && pending.outcome === outcome
            ? pending.phase
            : null
        }
        actionable={canChoose && !closed && !(mine && held)}
        removable={canChoose && mine && held && !settled && !pending}
        onChoose={(chosenMarket, chosenOutcome) => {
          setMoreOpen(false);
          onChoose(chosenMarket, chosenOutcome);
        }}
        onRemove={
          onRemove &&
          (() => {
            setMoreOpen(false);
            onRemove();
          })
        }
      />
    );
  };
  const bttsHeld = !!claim && claim.market === "BOTH_TEAMS_TO_SCORE";
  const bttsMine = mine && bttsHeld;
  const bttsPending = pending?.market === "BOTH_TEAMS_TO_SCORE";
  return (
    <div
      className={cn(
        "rounded-lg border bg-surface px-3 py-2.5",
        mine ? "border-success/60" : closed ? "border-border/50" : "border-border",
      )}
      data-testid={`group-card-${fixture.fixture_id}`}
    >
      <FixtureHead fixture={fixture} kickoff={kickoff} muted={closed} />
      <div
        className={cn("mt-2 grid gap-1.5", btts.length > 0 ? "grid-cols-4" : "grid-cols-3")}
      >
        {result.map((outcome) => button("MATCH_ODDS", outcome))}
        {btts.length > 0 && (
          <button
            ref={moreRef}
            type="button"
            disabled={closed && !bttsMine}
            aria-pressed={bttsMine}
            aria-label={
              bttsHeld && claim
                ? `Both teams to score: ${groupSelection(fixture, claim.market, claim.outcome).name}`
                : "Both teams to score"
            }
            onClick={() => setMoreOpen(true)}
            data-testid={`group-more-${fixture.fixture_id}`}
            className={cn(
              "flex min-h-11 flex-col items-center justify-center gap-0.5 rounded-md px-1.5 py-1 text-center font-sans text-caption font-medium transition-none",
              bttsMine
                ? "border-2 border-success bg-success/[0.08] text-text-primary dark:bg-success/15"
                : closed
                  ? "cursor-not-allowed border border-border/50 bg-surface text-text-secondary opacity-55"
                  : "cursor-pointer border border-border bg-surface-elevated text-text-secondary hover:border-primary/60 press-down",
              "focus-visible:outline-hidden focus-visible:shadow-glow",
            )}
          >
            <span className="flex items-center gap-1">
              {bttsMine && <Check className="h-3 w-3 shrink-0" aria-hidden />}
              Both score?
              {bttsPending && <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden />}
            </span>
            {bttsHeld && claim && (
              <span className="max-w-full truncate text-text-muted">
                {claim.outcome === "YES" ? "Yes" : "No"}
              </span>
            )}
          </button>
        )}
      </div>
      {claim && (
        <p
          className={cn("mt-2 eyebrow", mine ? "text-success" : "text-text-secondary")}
          data-testid={`group-claim-${fixture.fixture_id}`}
        >
          {mine ? "Your game" : `Picked by ${shortName(claim.display_name)}`}
          {settled ? ` · ${groupResultLabel(settled)}` : ""}
        </p>
      )}
      {!fixture.eligible && !claim && (
        <p className="mt-2 font-sans text-xs text-text-muted">
          This fixture is unavailable for a new contribution.
        </p>
      )}
      {children && <div className="mt-2">{children}</div>}
      {btts.length > 0 && (
        <Sheet
          open={moreOpen}
          onClose={() => setMoreOpen(false)}
          title={`Both teams to score · ${fixture.home} v ${fixture.away}`}
          triggerRef={moreRef}
        >
          <div className="grid gap-2 pb-2">
            {btts.map((outcome) => button("BOTH_TEAMS_TO_SCORE", outcome, true))}
          </div>
        </Sheet>
      )}
    </div>
  );
}

function SelectionButton({
  fixture,
  market,
  outcome,
  short,
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
  /** Batch 245: a short label ("Home") on the row, where the clubs are named above it. */
  short: string | null;
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
        "flex min-h-11 flex-col justify-center gap-0.5 rounded-md py-1",
        short ? "items-center px-1.5 text-center" : "items-start px-3 text-left",
        // Batch 235: the member's own pick is tappable now (to withdraw it), so the
        // accessibility scan reads its colours; it must not be caught mid-fade. Batch 242: no
        // choice fades at all; its points line sets its own colour and would lag the tile.
        "transition-none",
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
      <span
        className={cn(
          "flex max-w-full items-center gap-1",
          short ? "justify-center" : "w-full justify-between",
        )}
      >
        <span
          className={cn(
            "min-w-0 font-sans font-medium",
            short ? "truncate text-caption" : "break-words text-label",
          )}
        >
          {pressed && <Check className="mr-0.5 inline h-3 w-3" aria-hidden />}
          {short ?? label}
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
            "w-full break-words text-caption font-sans font-medium text-text-muted first-letter:uppercase",
            pressed && !settled && "text-text-secondary",
            settled && "font-sans normal-case tracking-normal",
            settled === "won" && "text-success",
            settled === "lost" && "text-error",
          )}
        >
          {caption}
        </span>
      )}
    </button>
  );
}
