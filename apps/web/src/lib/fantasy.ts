import type { GameIntent } from "./gameIntents";
import type { GameTarget, FantasyFixture } from "./twoGameTypes";
export const fantasyResultLabel = (status: string) =>
  ({
    no_entry: "No entry",
    all_void: "All void",
    // Batch 249: plain words ("Pending results" before it).
    pending: "Waiting for results",
    scored: "Scored",
    won: "Won",
    lost: "Lost",
    void: "Void",
  })[status] ?? status;
export function movedPrice(
  intent: GameIntent | undefined,
  target: GameTarget,
  slot: number,
): string | null {
  const detail = intent?.refusal?.data;
  return intent?.phase === "refused" &&
    intent.refusal?.code === "PRICE_MOVED" &&
    detail?.league_id === target.league_id &&
    detail.week_id === target.week_id &&
    detail.game_kind === "fantasy" &&
    detail.slot === slot &&
    typeof detail.current_odds === "string" &&
    /^\d+(\.\d{1,4})?$/.test(detail.current_odds) &&
    Number(detail.current_odds) > 0
    ? detail.current_odds
    : null;
}
export function fantasyRunner(
  fixture: FantasyFixture,
  outcome: string,
): string {
  return outcome === "HOME"
    ? `${fixture.home} to win`
    : outcome === "AWAY"
      ? `${fixture.away} to win`
      : outcome === "DRAW"
        ? "Draw"
        : outcome === "YES"
          ? "Both teams score"
          : "Both teams do not score";
}
