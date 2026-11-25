import { useState, type ReactNode } from "react";
import { ChevronDown, Clock, Copy, Lock } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { EmptyState } from "./EmptyState";
import { pickStatusLabel } from "../lib/coupon";
import {
  GROUP_PHASE,
  buildGroupShareText,
  foldNote,
  groupFold,
  groupResultLabel,
  type GroupLeg,
  type GroupPhase,
} from "../lib/groupCoupon";
import { cn } from "../lib/utils";
import type { PickStatus } from "../lib/types";

/** The member's own pick, already reduced to words by the page. */
export interface GroupMyPick {
  selection: string;
  /** The fixture context, when the fixture is still on screen to give it. */
  context: string | null;
  competition: string | null;
  result: string;
}

const SHUT: ReadonlySet<GroupPhase> = new Set([
  "locked_incomplete",
  "locked",
  "settled",
  "not_open",
]);

/**
 * The old coupon's status card for the Saturday group (Batch 233): where the game is,
 * the 14:30 clock, how many have picked and the member's own pick, in one card.
 *
 * The progress and pick sentences keep the group screen's wording, because the group's
 * browser journeys read them.
 */
export function GroupStatusCard({
  phase,
  clock,
  status,
  result,
  showResult,
  picked,
  members,
  mine,
  canSwitch,
  noPick,
  stillToPick = [],
  onChange,
}: {
  phase: GroupPhase;
  clock: ReactNode;
  /** A one-line reason the cards cannot be used yet, when there is one. */
  status: string | null;
  result: { status: string; final: boolean };
  showResult: boolean;
  picked: number;
  members: number;
  mine: GroupMyPick | null;
  canSwitch: boolean;
  /** What to say when the member has no pick. */
  noPick: string;
  /** Batch 235: the members counted as missing, by name, when the API sends them. */
  stillToPick?: readonly string[];
  /** Batch 246: takes the member to their fixture, where another tap switches the pick. */
  onChange?: () => void;
}) {
  const { label, variant } = GROUP_PHASE[phase];
  const tone =
    result.status === "won"
      ? "text-success"
      : result.status === "lost"
        ? "text-error"
        : "text-text-primary";
  return (
    <section
      className={cn(
        "rounded-lg border bg-surface p-4",
        variant === "success" && "border-success/40",
        variant === "warning" && "border-warning/40",
        variant === "muted" && "border-border",
      )}
      aria-label="Group progress and result"
      data-testid="group-status"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Changes colour with its card, not after it: the chip's background is see-through,
            so a fade on a theme change would show dark-theme text on the light card. */}
        <Badge variant={variant} className="transition-none">
          {label}
        </Badge>
        {clock && (
          <span
            className="flex items-center gap-1.5 font-mono text-sm tabular-nums text-text-secondary"
            data-testid="group-clock"
          >
            {SHUT.has(phase) && phase !== "not_open" ? (
              <Lock className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <Clock className="h-3.5 w-3.5" aria-hidden />
            )}
            {clock}
          </span>
        )}
      </div>
      {status && (
        <p role="status" className="mt-2 font-sans text-sm text-text-primary">
          {status}
        </p>
      )}
      {/* Batch 246: the member's own pick comes first, then who is in. */}
      <div className="mt-3 flex items-start justify-between gap-3" data-testid="group-my-pick">
        {mine ? (
          <>
            <div className="min-w-0">
              <p className="break-words font-sans text-base text-text-primary">
                {"Your saved contribution: "}
                <span className="font-semibold">{mine.selection}</span>
                {mine.result !== "pending" ? ` · ${groupResultLabel(mine.result)}` : ""}
              </p>
              {(mine.context || mine.competition) && (
                <p className="break-words font-sans text-xs text-text-muted">
                  {[mine.context, mine.competition].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
            {canSwitch && onChange && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onChange}
                className="shrink-0 transition-none"
              >
                Change
              </Button>
            )}
          </>
        ) : (
          <p className="font-sans text-sm text-text-secondary">{noPick}</p>
        )}
      </div>
      {showResult && (
        <p
          className={cn("mt-3 font-sans text-lg font-semibold", tone)}
          data-testid="group-result"
        >
          {groupResultLabel(result.status)}
          {result.final ? " · Final" : " · Provisional"}
        </p>
      )}
      <div className="mt-3 border-t border-border pt-3">
        {members > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1" aria-hidden data-testid="group-member-dots">
            {Array.from({ length: members }, (_, index) => (
              <span
                key={index}
                className={cn(
                  "h-2 w-2 rounded-full",
                  index < picked ? "bg-success" : "bg-border-strong",
                )}
              />
            ))}
          </div>
        )}
        <p className="font-sans text-sm font-medium text-text-primary">
          {picked} of {members} contributed · {Math.max(0, members - picked)}{" "}
          missing contributors.
        </p>
        {stillToPick.length > 0 && (
          <p className="mt-0.5 break-words font-sans text-sm text-text-secondary" data-testid="group-still-to-pick">
            Still to pick: {stillToPick.join(", ")}
          </p>
        )}
      </div>
    </section>
  );
}

const LEGS_ID = "group-coupon-legs";

/**
 * Every member's leg stacked into the group's coupon (Batch 233): the fold, Copy text for
 * the group chat, and each leg. The legacy section's shape with the price taken out,
 * because the group is never priced.
 */
export function GroupCouponSection({
  legs,
  memberId,
  picked,
  members,
  locked,
  final,
  resultStatus,
  weekLabel,
}: {
  legs: GroupLeg[];
  memberId: string | undefined;
  picked: number;
  members: number;
  /** Picks have closed, by the stored lock or the game's state. */
  locked: boolean;
  final: boolean;
  resultStatus: string;
  /** "28 Nov". */
  weekLabel: string;
}) {
  const [open, setOpen] = useState(true);
  const fold = groupFold(legs, picked, members);
  const outcome =
    resultStatus === "won"
      ? { label: "Coupon won", colour: "text-success" }
      : resultStatus === "lost"
        ? { label: "Coupon lost", colour: "text-error" }
        : resultStatus === "void"
          ? { label: "All void", colour: "text-text-primary" }
          : { label: "Coupon settled", colour: "text-text-primary" };

  async function copy() {
    try {
      await navigator.clipboard.writeText(
        buildGroupShareText(legs, { weekLabel, picked, members, locked, final }),
      );
      toast.success(final ? "Result copied" : "Coupon copied");
    } catch {
      toast.error(final ? "Could not copy result" : "Could not copy coupon");
    }
  }

  return (
    <section
      aria-labelledby="group-coupon-heading"
      data-testid="group-coupon"
      className="rounded-xl border border-border bg-surface"
    >
      {/* Batch 246: one card — the header folds the legs away and carries the copy for the
          group chat (iMessage, so copying is how the coupon is shared). */}
      <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
        <h2 id="group-coupon-heading" className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-controls={LEGS_ID}
            className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left tap-target focus-visible:outline-hidden focus-visible:shadow-glow"
          >
            <span className="min-w-0 truncate eyebrow text-text-primary">
              {final ? "Result" : "The coupon"}
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <span className="font-mono text-caption tabular-nums text-text-muted">
                {legs.length === 0
                  ? "No picks yet"
                  : final
                    ? `${legs.length} ${legs.length === 1 ? "pick" : "picks"}`
                    : `${legs.length} of ${members}`}
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-text-muted transition-transform",
                  open && "rotate-180",
                )}
                aria-hidden
              />
            </span>
          </button>
        </h2>
        {legs.length > 0 && (
          /* transition-none: on a phone the coupon sits above the fixtures, in view when the
             theme flips (Batch 238). */
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={copy}
            className="shrink-0 transition-none"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden />
            {final ? "Copy result" : "Copy text"}
          </Button>
        )}
      </div>
      <div id={LEGS_ID} hidden={!open} className="space-y-3 p-4">
        {legs.length > 0 && (
          <div className="min-w-0">
            {final && (
              <p className="flex flex-wrap items-baseline gap-x-2 font-sans text-xl font-semibold">
                <span className={outcome.colour}>{outcome.label}</span>
                <span className="text-base font-normal text-text-secondary">
                  · {fold.landed} of {legs.length} landed
                </span>
              </p>
            )}
            <p
              className="font-sans text-2xl font-semibold tabular-nums text-text-primary"
              data-testid="group-fold"
            >
              {fold.fold > 0 ? `${fold.fold}-fold` : "All void"}
            </p>
            <p className="mt-0.5 break-words font-sans text-xs text-text-muted">
              {foldNote(fold, members, locked || final)}
            </p>
          </div>
        )}
        {legs.length === 0 ? (
          <EmptyState
            title="No picks in yet"
            description="Once members pick, their selections stack up here into one coupon."
          />
        ) : (
          <ol className="divide-y divide-border">
            {legs.map((leg, index) => (
              <li
                key={leg.fixture_id}
                className="flex items-start gap-2.5 py-2 first:pt-0 last:pb-0"
                data-testid={`group-leg-${index}`}
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-sans text-caption font-semibold",
                    // The member's own leg is ringed in green; the letters stay in the body
                    // colour, because green letters on a green tint miss contrast in light.
                    leg.player_id === memberId
                      ? "bg-success/[0.08] text-text-primary ring-1 ring-success dark:bg-success/15"
                      : "bg-surface-elevated text-text-secondary",
                  )}
                  aria-hidden
                >
                  {initials(leg.display_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="break-words font-sans text-sm text-text-primary">
                    <span className="font-medium">{leg.display_name}</span>
                    {" — "}
                    {leg.selection}
                  </p>
                  <p className="break-words font-sans text-xs text-text-muted">
                    {leg.context} · {leg.competition}
                  </p>
                </div>
                {leg.result !== "pending" && (
                  <Badge
                    className="shrink-0 transition-none"
                    variant={
                      leg.result === "won"
                        ? "success"
                        : leg.result === "lost"
                          ? "error"
                          : "muted"
                    }
                  >
                    {pickStatusLabel(leg.result as PickStatus)}
                  </Badge>
                )}
              </li>
            ))}
          </ol>
        )}
        <p className="font-sans text-xs text-text-muted">
          Incomplete participation is valid. Void legs are neutral; all void is
          void. Zero contributions means No coupon.
        </p>
      </div>
    </section>
  );
}

/** "Bob Smith" → "BS", "Alice" → "AL": a leg's avatar, beside the name it abbreviates. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return (words.length > 1 ? words[0]![0]! + words[1]![0]! : words[0]!.slice(0, 2)).toUpperCase();
}
