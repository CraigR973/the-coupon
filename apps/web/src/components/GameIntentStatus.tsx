import { Link } from "react-router-dom";
import { useGameIntents } from "../hooks/useGameIntents";
import { intentKey } from "../lib/gameIntents";
import type { GameTarget } from "../lib/twoGameTypes";
import { Button } from "./ui/button";
export function GameIntentStatus({
  target,
  slot,
  compact = false,
}: {
  target: GameTarget;
  slot: number;
  /**
   * Batch 232: the fantasy slip shows a confirmed save as one line, so six saved picks
   * do not stack six boxes. Every other state keeps its full explanation and actions.
   */
  compact?: boolean;
}) {
  const { engine, intents } = useGameIntents();
  const key = intentKey(target, slot);
  const intent = intents.find(
    (value) => intentKey(value.target, value.slot) === key,
  );
  if (!intent) return null;
  if (compact && intent.phase === "confirmed")
    return (
      <div
        className="flex items-center justify-between gap-2 rounded-md bg-success/[0.08] px-2 py-1 dark:bg-success/15"
        data-testid={`intent-${slot}`}
      >
        <p role="status" className="font-sans text-xs text-text-primary">
          {intent.message}
        </p>
        <Button
          variant="ghost"
          size="sm"
          aria-label="Dismiss message"
          onClick={() => engine.dismiss(key)}
        >
          Dismiss
        </Button>
      </div>
    );
  return (
    <div
      className="rounded-lg border border-border p-3 space-y-2"
      data-testid={`intent-${slot}`}
    >
      <p
        role={
          ["refused", "conflict"].includes(intent.phase) ? "alert" : "status"
        }
      >
        {intent.message}
      </p>
      <p className="text-sm text-text-secondary">
        Choice:{" "}
        {(
          {
            HOME: "Home win",
            AWAY: "Away win",
            DRAW: "Draw",
            YES: "Yes",
            NO: "No",
          } as Record<string, string>
        )[intent.body.outcome] ?? "Selection"}{" "}
        ·{" "}
        {intent.body.market === "MATCH_ODDS"
          ? "Match result"
          : "Both teams to score"}
      </p>
      {["queued", "uncertain"].includes(intent.phase) && (
        <Button variant="outline" onClick={() => engine.retry(key)}>
          Check and retry this choice
        </Button>
      )}
      {!["sending", "checking"].includes(intent.phase) && (
        <Button variant="ghost" onClick={() => engine.dismiss(key)}>
          Dismiss message
        </Button>
      )}
      {intent.refusal?.status === 402 && (
        <Link
          className="underline"
          to="#payment"
          onClick={() => {
            const panel = document.getElementById("payment");
            panel?.scrollIntoView({ block: "start" });
            panel?.focus({ preventScroll: true });
          }}
        >
          Review this week’s payment
        </Link>
      )}
    </div>
  );
}
