import type { GameIntent } from "./gameIntents";
import type { GamePick } from "./twoGameTypes";

/**
 * The fantasy pick slip's rules, apart from any screen (Batch 232).
 *
 * The fantasy week used to make a member open a slot, choose a fixture inside it and come
 * back for the next one. The coupon layout instead lets them tap prices down one fixture
 * list, the way a betting app builds a slip, and this decides which of the six slots each
 * tap lands in. Every save is still the existing single-slot write: nothing here sends
 * anything, it only names the slot.
 */
export const SLOT_NUMBERS = [1, 2, 3, 4, 5, 6] as const;

/** A choice the engine is still carrying to the server, or waiting to carry. */
const IN_FLIGHT: ReadonlySet<string> = new Set([
  "queued",
  "uncertain",
  "checking",
  "sending",
]);

export interface SlotView {
  slot: number;
  /** The slot's pick as the latest authoritative readback has it. */
  pick: GamePick | null;
  /** This slot's choice in the engine, if it has one. */
  intent?: GameIntent;
  /** The new price a `PRICE_MOVED` refusal is offering for this slot, if any. */
  movedPrice: string | null;
  /** Whether a write to this slot can be dispatched now. */
  ready: boolean;
}

export interface Selection {
  fixture_id: string;
  market: string;
  outcome: string;
}

/**
 * Whether the slot's engine choice still speaks for it: on its way, or refused only for a
 * price the member has yet to accept or turn down.
 */
function choiceStands(view: SlotView): view is SlotView & { intent: GameIntent } {
  return !!view.intent && (IN_FLIGHT.has(view.intent.phase) || !!view.movedPrice);
}

/** The selection a slot holds: a standing engine choice first, then the saved pick. */
export function heldSelection(view: SlotView): Selection | null {
  if (choiceStands(view)) {
    const { fixture_id, market, outcome } = view.intent.body;
    return { fixture_id, market, outcome };
  }
  return view.pick
    ? {
        fixture_id: view.pick.fixture_id,
        market: view.pick.market,
        outcome: view.pick.outcome,
      }
    : null;
}

export const heldFixture = (view: SlotView) =>
  heldSelection(view)?.fixture_id ?? null;

export type Destination = { kind: "slot"; slot: number } | { kind: "full" };

/**
 * Where a tap on a fixture's price lands.
 *
 * A member holds one pick per fixture, so a fixture already in the slip goes back to the
 * slot holding it — tapping another price on it swaps that pick. Anything else takes the
 * first free slot. With none free the member is asked which pick to swap; nothing is
 * replaced without that answer.
 */
export function destinationFor(
  fixtureId: string,
  views: readonly SlotView[],
): Destination {
  const holding = views.find((view) => heldFixture(view) === fixtureId);
  if (holding) return { kind: "slot", slot: holding.slot };
  const free = views.find((view) => heldFixture(view) === null);
  return free ? { kind: "slot", slot: free.slot } : { kind: "full" };
}

/**
 * The fixtures the other slots hold, which a deliberate choice for `slot` cannot use.
 *
 * Only saved picks and choices on their way count, as the six-slot chooser always
 * counted them, so two offline fills can never offer the same fixture twice.
 */
export function fixturesHeldElsewhere(
  slot: number,
  views: readonly SlotView[],
): Set<string> {
  const held = new Set<string>();
  for (const view of views) {
    if (view.slot === slot) continue;
    if (view.pick) held.add(view.pick.fixture_id);
    if (view.intent && IN_FLIGHT.has(view.intent.phase))
      held.add(view.intent.body.fixture_id);
  }
  return held;
}

/**
 * Points a winning pick at this exact decimal price would score.
 *
 * Worked on the decimal string, not a float: the API rounds `odds × 10` half-up in
 * `Decimal` (`services/scoring.points_for`), and a float can land a hair under the half.
 * Returns `null` for anything that is not a plain positive decimal.
 */
export function fantasyPoints(odds: string): number | null {
  const match = /^(\d+)(?:\.(\d{1,4}))?$/.exec(odds.trim());
  if (!match) return null;
  const tenThousandths =
    Number(match[1]) * 10_000 + Number((match[2] ?? "").padEnd(4, "0"));
  if (!Number.isSafeInteger(tenThousandths) || tenThousandths <= 0) return null;
  return Math.floor((tenThousandths + 500) / 1_000);
}

export interface SlipSummary {
  /** Slots holding a saved pick. */
  filled: number;
  /** The most the saved picks can still total: won points plus every pending win. */
  upTo: number;
}

export function slipSummary(views: readonly SlotView[]): SlipSummary {
  let filled = 0;
  let upTo = 0;
  for (const { pick } of views) {
    if (!pick) continue;
    filled++;
    if (pick.result === "won") upTo += pick.points ?? 0;
    else if (pick.result === "pending" && pick.frozen_odds)
      upTo += fantasyPoints(pick.frozen_odds) ?? 0;
  }
  return { filled, upTo };
}
