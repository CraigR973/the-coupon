import { Link } from "react-router-dom";
import { useGameIntents } from "../hooks/useGameIntents";
import { intentKey } from "../lib/gameIntents";
import type { GameTarget } from "../lib/twoGameTypes";
import { Button } from "./ui/button";
export function GameIntentStatus({
  target,
  slot,
}: {
  target: GameTarget;
  slot: number;
}) {
  const { engine, intents } = useGameIntents();
  const key = intentKey(target, slot);
  const intent = intents.find(
    (value) => intentKey(value.target, value.slot) === key,
  );
  if (!intent) return null;
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
