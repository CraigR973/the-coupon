import { fixtureContext, pickStatusLabel } from "./coupon";
import { competitionName, groupByCompetition } from "./gameFixtures";
import { voidLegLabel } from "./share";
import type { GroupFixture } from "./twoGameTypes";
import type { PickMarket, PickOutcome, PickStatus } from "./types";

/**
 * The Saturday group game in the old coupon's words (Batch 233): the status card's
 * phase, every member's leg in slate order, the fold and the text for the group chat.
 *
 * The group is never priced, so nothing here carries a price: the fold is a count of
 * legs, and a voided leg drops out of it exactly as it drops out of a legacy price.
 */

export type GroupPhase =
  | "not_open"
  | "open"
  | "submitted"
  | "complete"
  | "locked_incomplete"
  | "locked"
  | "settled"
  | "suspended"
  | "cancelled";

/** The status card's chip. The word is always there, so colour is never the only carrier. */
export const GROUP_PHASE: Record<
  GroupPhase,
  { label: string; variant: "success" | "warning" | "muted" }
> = {
  not_open: { label: "Not open yet", variant: "muted" },
  open: { label: "Pick required", variant: "warning" },
  submitted: { label: "Pick submitted", variant: "success" },
  complete: { label: "Coupon complete", variant: "success" },
  locked_incomplete: { label: "Incomplete coupon", variant: "warning" },
  locked: { label: "Picks locked", variant: "muted" },
  settled: { label: "Settled", variant: "muted" },
  suspended: { label: "Entries suspended", variant: "muted" },
  cancelled: { label: "Cancelled", variant: "muted" },
};

export interface GroupPhaseInput {
  /** The API's `entry_state`; retained history reads as `locked`. */
  entryState: string;
  /** This device's clock has not reached `opens_at`. */
  notOpened: boolean;
  /** This device's clock has reached `locks_at`. */
  expired: boolean;
  final: boolean;
  hasPick: boolean;
  picked: number;
  members: number;
}

export function groupPhase(input: GroupPhaseInput): GroupPhase {
  if (input.final) return "settled";
  if (input.entryState === "cancelled") return "cancelled";
  if (input.entryState === "suspended") return "suspended";
  const missing = Math.max(0, input.members - input.picked);
  if (input.expired || input.entryState === "locked")
    return missing > 0 ? "locked_incomplete" : input.picked > 0 ? "complete" : "locked";
  if (input.notOpened || input.entryState === "not_open") return "not_open";
  if (input.members > 0 && missing === 0) return "complete";
  return input.hasPick ? "submitted" : "open";
}

/** The group's result words; Batch 249 says "Waiting for results", not "Pending results". */
export const groupResultLabel = (status: string) =>
  ({
    no_coupon: "No coupon",
    pending: "Waiting for results",
    won: "Won",
    lost: "Lost",
    void: "Void",
  })[status] ?? status;

/** "Alice" for "Alice Smith", as the old card names whoever holds a game. */
export function shortName(name: string): string {
  const trimmed = name.trim();
  if (trimmed === "Former member") return trimmed;
  return trimmed.split(/\s+/)[0] || name;
}

/** What a selection button says, and what it is called to assistive technology. */
export function groupSelection(
  fixture: Pick<GroupFixture, "home" | "away">,
  market: string,
  outcome: string,
): { label: string; name: string } {
  if (market === "MATCH_ODDS") {
    if (outcome === "HOME") return { label: fixture.home, name: `${fixture.home} to win` };
    if (outcome === "AWAY") return { label: fixture.away, name: `${fixture.away} to win` };
    return { label: "Draw", name: "Draw" };
  }
  return outcome === "YES"
    ? { label: "Both teams score", name: "Both teams score" }
    : { label: "No — not both score", name: "No — not both score" };
}

export interface GroupLeg {
  player_id: string;
  display_name: string;
  fixture_id: string;
  home: string;
  away: string;
  competition: string;
  market: string;
  outcome: string;
  /** "Draw", "Arsenal", "Both teams score" — the server's runner name. */
  selection: string;
  /** What disambiguates the selection: "v Chelsea", "Hibs v Hearts". */
  context: string;
  result: string;
}

/** Every claimed fixture as one member's leg, in the order the fixture list shows them. */
export function groupLegs(fixtures: readonly GroupFixture[]): GroupLeg[] {
  return groupByCompetition(fixtures)
    .flatMap((group) => group.fixtures)
    .flatMap((fixture) =>
      fixture.claim
        ? [
            {
              player_id: fixture.claim.player_id,
              display_name: fixture.claim.display_name,
              fixture_id: fixture.fixture_id,
              home: fixture.home,
              away: fixture.away,
              competition: competitionName(fixture.competition_id),
              market: fixture.claim.market,
              outcome: fixture.claim.outcome,
              selection: fixture.claim.runner_name,
              context: fixtureContext(
                fixture.claim.market as PickMarket,
                fixture.claim.outcome as PickOutcome,
                fixture.home,
                fixture.away,
              ),
              result: fixture.claim.result,
            },
          ]
        : [],
    );
}

export interface GroupFold {
  /** Legs that count: every leg but the voided ones. */
  fold: number;
  voided: number;
  landed: number;
  /** Members who have not picked, from the game's own count. */
  missing: number;
}

export function groupFold(
  legs: readonly GroupLeg[],
  picked: number,
  members: number,
): GroupFold {
  const voided = legs.filter((leg) => leg.result === "void").length;
  return {
    fold: legs.length - voided,
    voided,
    landed: legs.filter((leg) => leg.result === "won").length,
    missing: Math.max(0, members - picked),
  };
}

/** The line under the fold: what is missing, voided or complete about it. */
export function foldNote(
  fold: GroupFold,
  members: number,
  locked: boolean,
): string {
  const notes: string[] = [];
  if (fold.voided > 0) notes.push(`${voidLegLabel(fold.voided)} void, not in the fold`);
  if (fold.missing > 0)
    notes.push(
      locked
        ? `${fold.missing} of ${members} never picked`
        : `${fold.missing} of ${members} still to pick`,
    );
  return notes.length > 0 ? notes.join(" · ") : "Everyone has picked";
}

export interface GroupShareContext {
  /** "28 Nov". */
  weekLabel: string;
  picked: number;
  members: number;
  locked: boolean;
  final: boolean;
}

/**
 * The coupon as text for the group chat, in the legacy paste's shape without a price.
 * Once the game is final it becomes the result, each leg carrying how it ended.
 */
export function buildGroupShareText(
  legs: readonly GroupLeg[],
  context: GroupShareContext,
): string {
  const fold = groupFold(legs, context.picked, context.members);
  const round = `Saturday Group · ${context.weekLabel}`;
  const heading = context.final
    ? `The Coupon: Result — ${round} — ${fold.landed} of ${legs.length} picks landed`
    : `The Coupon — ${round}`;
  const voidNote = fold.voided > 0 ? ` — ${voidLegLabel(fold.voided)} void` : "";
  const missingNote =
    fold.missing > 0
      ? context.locked || context.final
        ? ` — incomplete, ${fold.missing} of ${context.members} never picked`
        : ` — ${fold.missing} of ${context.members} still to pick`
      : "";
  return [
    heading,
    `${fold.fold}-fold accumulator${voidNote}${missingNote}`,
    "",
    ...legs.map((leg, index) => {
      const line = `${index + 1}. ${leg.display_name} — ${leg.selection} (${leg.context})`;
      return context.final || leg.result !== "pending"
        ? `${line} — ${pickStatusLabel(leg.result as PickStatus)}`
        : line;
    }),
  ].join("\n");
}
