import type { RefObject } from "react";
import { ChevronUp, Plus, Ticket, X } from "lucide-react";
import { useGameIntents } from "../hooks/useGameIntents";
import { fantasyResultLabel, fantasyRunner } from "../lib/fantasy";
import { fantasyPoints, type SlotView } from "../lib/fantasySlip";
import { formatInstant } from "../lib/time";
import { formatOdds } from "../lib/coupon";
import { cn } from "../lib/utils";
import type { FantasyFixture, GameTarget } from "../lib/twoGameTypes";
import type { OddsFormat } from "../lib/types";
import { GameIntentStatus } from "./GameIntentStatus";
import { Sheet } from "./ui/sheet";
import { Button } from "./ui/button";

export interface SlotQueryState {
  revision: number | null;
  isError: boolean;
  refetch: () => void;
}

/**
 * One of the six slots in the slip, as a compact tile (Batch 246; Batch 232 before it).
 *
 * A held slot shows the pick and its price, the fixture, and its result once there is one;
 * tapping it removes the pick (Batch 235's Remove, the same intent-engine withdrawal), so the
 * whole tile is the "Remove slot N" button while the game is open. An empty slot is dashed and
 * reads "+ Pick", which takes the member to the fixtures. The save's progress, the moved-price
 * confirmation and the check when a slot cannot be verified stay inside the tile, word for
 * word, because the journeys read them there.
 */
export function FantasySlotCard({
  target,
  view,
  query,
  fixture,
  editable,
  onRemove,
  onPick,
  oddsFormat,
}: {
  target: GameTarget;
  view: SlotView;
  query: SlotQueryState;
  fixture: FantasyFixture | undefined;
  editable: boolean;
  onRemove: () => void;
  /** Batch 246: an empty tile's "+ Pick" goes to the fixtures. */
  onPick?: () => void;
  /** Batch 249: the pick's price in the member's notation, as the fixture rows print it. */
  oddsFormat: OddsFormat;
}) {
  const { engine } = useGameIntents();
  const { slot, pick, intent, movedPrice, ready } = view;
  const tone =
    pick?.result === "won"
      ? "text-success"
      : pick?.result === "lost"
        ? "text-error"
        : "text-text-muted";
  const summary = pick && (
    <span className="block min-w-0">
      <span className="block break-words font-sans text-sm text-text-primary">
        <span className="font-semibold">{pick.runner_name}</span>
        {/* Batch 249: "Home 1 · 2.15", not "Home 1 · Frozen odds 2.1500". */}
        <span className="text-text-secondary">
          {" "}
          · {formatOdds(Number(pick.frozen_odds), oddsFormat)}
        </span>
      </span>
      {fixture && (
        <span className="block truncate font-sans text-xs text-text-muted">
          {fixture.home} v {fixture.away} ·{" "}
          {formatInstant(fixture.kickoff_at, "Europe/London", "EEE HH:mm")}
        </span>
      )}
      <span className={cn("block font-sans text-xs", tone)}>
        {/* A pick still to play has no points to show yet. */}
        {pick.result === "pending"
          ? fantasyResultLabel(pick.result)
          : `${fantasyResultLabel(pick.result)} · ${pick.points ?? 0} points`}
      </span>
    </span>
  );
  return (
    <article
      aria-label={`Fantasy slot ${slot}`}
      className={cn(
        "min-w-0 space-y-1.5 rounded-lg border px-2.5 py-2",
        pick ? "border-success/40 bg-surface" : "border-dashed border-border-strong",
      )}
    >
      {pick ? (
        editable ? (
          <button
            type="button"
            disabled={!ready || query.revision === null}
            onClick={onRemove}
            aria-label={`Remove slot ${slot}`}
            className="flex w-full items-start justify-between gap-1.5 rounded-md text-left disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-hidden focus-visible:shadow-glow"
          >
            {summary}
            <X className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" aria-hidden />
          </button>
        ) : (
          summary
        )
      ) : ready || !editable ? (
        editable && onPick ? (
          <>
            <span className="sr-only">Empty slot</span>
            <button
              type="button"
              onClick={onPick}
              className="flex min-h-11 w-full items-center justify-center gap-1 rounded-md font-sans text-sm font-semibold text-primary focus-visible:outline-hidden focus-visible:shadow-glow"
            >
              <Plus className="h-4 w-4" aria-hidden />
              Pick
              <span className="sr-only"> for slot {slot}</span>
            </button>
          </>
        ) : (
          <p className="flex min-h-11 items-center justify-center font-sans text-sm text-text-muted">
            Empty slot
          </p>
        )
      ) : (
        <p className="flex min-h-11 items-center justify-center font-sans text-sm text-text-muted">
          {/* Batch 235: with no Fill button, an unverified slot says so instead. */}
          {`Checking slot ${slot}…`}
        </p>
      )}
      {query.isError && (
        <div className="space-y-2">
          <p role="alert" className="font-sans text-sm text-text-primary">
            Could not verify slot {slot}. Your saved choice has not been replaced.
          </p>
          <Button variant="outline" onClick={query.refetch}>
            Check slot {slot}
          </Button>
        </div>
      )}
      <GameIntentStatus target={target} slot={slot} compact />
      {movedPrice && intent && (
        <div
          className="space-y-2 rounded-md border border-warning/40 bg-warning/[0.08] p-2 dark:bg-warning/15"
          role="group"
          aria-label={`Price confirmation for slot ${slot}`}
        >
          <p className="font-sans text-sm text-text-primary">
            The price changed to {movedPrice}. Your saved choice stays until you
            confirm this new price.
          </p>
          <Button
            variant="outline"
            disabled={!ready || query.revision === null}
            onClick={() => {
              if (query.revision === null) return;
              engine.choose(
                target,
                slot,
                {
                  fixture_id: intent.body.fixture_id,
                  market: intent.body.market,
                  outcome: intent.body.outcome,
                  odds: movedPrice,
                },
                query.revision,
              );
            }}
          >
            Confirm odds {movedPrice} for slot {slot}
          </Button>
        </div>
      )}
    </article>
  );
}

/**
 * The slip's bar below desktop width: how many picks are in and what they can still
 * score, in view while the member scrolls the fixtures, and the way into the slip.
 *
 * Sticky at the foot of the fixture list rather than fixed to the screen, so once the
 * list ends it settles above the slip itself instead of covering it.
 *
 * Batch 242: it scrolls away with the list's end, so it must pass under the sticky top
 * bar (`z-header`, 50) rather than over it, and still sit above the tab bar (40).
 * Batch 246: slim — n of 6, up to N pts and Review.
 */
export function SlipBar({
  filled,
  upTo,
  onOpen,
  barRef,
}: {
  filled: number;
  upTo: number;
  onOpen: () => void;
  barRef: RefObject<HTMLButtonElement>;
}) {
  return (
    <div className="sticky bottom-[calc(var(--tabbar-height)+var(--safe-bottom)+0.5rem)] z-[45] mt-4 sm:bottom-4 lg:hidden">
        <button
          ref={barRef}
          type="button"
          onClick={onOpen}
          aria-haspopup="dialog"
          className="flex min-h-11 w-full items-center justify-between gap-2 rounded-full bg-primary px-4 py-2 text-on-primary shadow-sheet focus-visible:outline-hidden focus-visible:shadow-glow"
        >
          <span className="flex items-center gap-2 font-sans text-sm font-semibold">
            <Ticket className="h-4 w-4" aria-hidden />
            <span className="sr-only">Your picks </span>
            {filled} of 6
            <span className="font-mono font-normal tabular-nums">· up to {upTo} pts</span>
          </span>
          <span className="flex items-center gap-1 font-sans text-sm font-semibold">
            Review
            <ChevronUp className="h-4 w-4" aria-hidden />
          </span>
        </button>
    </div>
  );
}

export interface PendingSwap {
  fixture: FantasyFixture;
  market: string;
  outcome: string;
  odds: string;
}

/**
 * Six picks in and a seventh price tapped: which one goes? Nothing is replaced until the
 * member names the slot, and the write is the ordinary save to that slot.
 */
export function SwapSheet({
  pending,
  views,
  fixtures,
  revisions,
  oddsFormat,
  onSwap,
  onClose,
}: {
  pending: PendingSwap | null;
  views: readonly SlotView[];
  fixtures: ReadonlyMap<string, FantasyFixture>;
  revisions: readonly (number | null)[];
  oddsFormat: OddsFormat;
  onSwap: (slot: number, revision: number) => void;
  onClose: () => void;
}) {
  const runner = pending ? fantasyRunner(pending.fixture, pending.outcome) : "";
  const points = pending ? fantasyPoints(pending.odds) : null;
  return (
    <Sheet open={!!pending} onClose={onClose} title="Swap a pick">
      {pending && (
        <div className="max-h-[70vh] space-y-2 overflow-y-auto px-5 pb-5">
          <p className="font-sans text-sm text-text-secondary">
            Your six picks are in. Choose the one {runner} at{" "}
            {formatOdds(Number(pending.odds), oddsFormat)}
            {points !== null ? ` (${points} pts)` : ""} replaces.
          </p>
          {views.map((view) => {
            const fixture = view.pick ? fixtures.get(view.pick.fixture_id) : undefined;
            const revision = revisions[view.slot - 1];
            return (
              <button
                key={view.slot}
                type="button"
                disabled={!view.ready || revision === null || revision === undefined}
                onClick={() => {
                  if (revision !== null && revision !== undefined)
                    onSwap(view.slot, revision);
                }}
                aria-label={`Swap slot ${view.slot} for ${runner}`}
                className="flex min-h-12 w-full items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2 text-left hover:border-primary/60 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-hidden focus-visible:shadow-glow"
              >
                <span className="min-w-0">
                  <span className="block eyebrow text-text-muted">
                    Slot {view.slot}
                  </span>
                  <span className="block break-words font-sans text-sm text-text-primary">
                    {view.pick
                      ? `${view.pick.runner_name} · ${view.pick.frozen_odds ?? ""}`
                      : "Saving…"}
                  </span>
                  {fixture && (
                    <span className="block font-sans text-xs text-text-muted">
                      {fixture.home} v {fixture.away}
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-sans text-sm font-semibold text-text-primary">
                  Swap
                </span>
              </button>
            );
          })}
        </div>
      )}
    </Sheet>
  );
}
