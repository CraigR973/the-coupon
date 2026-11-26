import { useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useGameRoute } from "../hooks/useGameRoute";
import { useGameIntents, useGameNavigation } from "../hooks/useGameIntents";
import { useExpiry } from "../hooks/useExpiry";
import { useOnlineStatus } from "../hooks/useOnlineStatus";
import type { CountdownParts } from "../hooks/useCountdown";
import { apiFetch, ApiError, NetworkError } from "../lib/api";
import { intentKey } from "../lib/gameIntents";
import { fantasyResultLabel, movedPrice } from "../lib/fantasy";
import {
  SLOT_NUMBERS,
  destinationFor,
  heldSelection,
  slipSummary,
  type SlotView,
} from "../lib/fantasySlip";
import { groupByCompetition, type FixtureGroup } from "../lib/gameFixtures";
import {
  gamePath,
  gameQueryKey,
  type GameTarget,
  type GameEntry,
  type FantasyGame,
  type GameCard,
  type FantasyFixture,
} from "../lib/twoGameTypes";
import type { OddsFormat } from "../lib/types";
import { formatOdds } from "../lib/coupon";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import { WeekFeePanel } from "../components/WeekFeePanel";
import {
  CompetitionChips,
  SECTION_SCROLL_MARGIN,
  STICKY_HEADER,
} from "../components/FixtureRow";
import { GameHeader, GameRules } from "../components/GameHeader";
import { Countdown } from "../components/Countdown";
import {
  FantasyFixtureCard,
  type HeldOnCard,
  type MovedOnCard,
} from "../components/FantasyFixtureCard";
import {
  FantasySlotCard,
  SlipBar,
  SwapSheet,
  type PendingSwap,
  type SlotQueryState,
} from "../components/FantasySlip";
import { Sheet } from "../components/ui/sheet";
import { Button } from "../components/ui/button";

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return "now";
  if (p.days > 0) return `${p.days}d ${p.hours}h`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m`;
  return `${p.minutes}m ${p.seconds}s`;
}

export function FantasyWeekPage() {
  const target = useGameRoute("fantasy");
  return (
    <FantasyWeek
      key={`${target.league_id}/${target.week_id}`}
      target={target}
    />
  );
}

/**
 * The fantasy week on the old coupon layout (Batch 232).
 *
 * The fixtures lead, in folded competition sections, and every price is a button: a tap
 * saves it straight into the slip — the slot already holding that fixture, otherwise the
 * first free one, and with six in, the member says which pick to swap. The slip sits
 * beside the fixtures at desktop width and below them on narrower screens, where a bar
 * keeps its count in view and opens it as a sheet.
 *
 * Saving is exactly the six-slot screen's: one addressed slot write at a time through the
 * shared intent engine, with its revision check, readback and named price confirmation.
 * Batch 235: there is no slot to aim at any more. A tap fills the held fixture's slot or the
 * first free one, a second tap on the member's own price removes that pick, and each slot
 * offers Remove; a full slip still asks which pick to swap.
 */
function FantasyWeek({ target }: { target: GameTarget }) {
  const { player } = useAuth();
  const oddsFormat: OddsFormat = player?.oddsFormat ?? "decimal";
  const leagues = useGameNavigation();
  const client = useQueryClient();
  const { engine, intents } = useGameIntents();
  const online = useOnlineStatus();
  const [swap, setSwap] = useState<PendingSwap | null>(null);
  // Batch 245: every competition starts open; a member who folds one keeps it folded
  // through the 30-second refresh, and a jump chip opens it again.
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const [slipOpen, setSlipOpen] = useState(false);
  const barRef = useRef<HTMLButtonElement | null>(null);
  const slateRef = useRef<HTMLElement | null>(null);
  const memberKey = gameQueryKey(player?.id ?? "", target);
  const query = useQuery({
    queryKey: [...memberKey, "view"],
    queryFn: async ({ signal }) => {
      try {
        return {
          game: await apiFetch<FantasyGame>(gamePath(target), { signal }),
          retained: null,
        };
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
        const history = await apiFetch<{ fantasy: GameCard | null }>(
          `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/results`,
          { signal },
        );
        if (!history.fantasy) throw error;
        return { game: null, retained: history.fantasy };
      }
    },
    retry: false,
    refetchInterval: 30_000,
  });
  const game = query.data?.game,
    retained = query.data?.retained;
  const locked = useExpiry(
    game?.locks_at ?? retained?.locks_at ?? "1970-01-01T00:00:00Z",
  );
  const opened = useExpiry(
    game?.opens_at ?? retained?.opens_at ?? "1970-01-01T00:00:00Z",
  );
  const results = useQuery({
    queryKey: [...memberKey, "results"],
    queryFn: ({ signal }) =>
      apiFetch<{ fantasy: GameCard | null }>(
        `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/results`,
        { signal },
      ),
    enabled: !!game && locked,
    retry: false,
    refetchInterval: 30_000,
  });
  // Each slot's own readback, which decides what the slot holds and whether it may be
  // written. Read only once the game is known, as the slot cards always did.
  const entries = useQueries({
    queries: SLOT_NUMBERS.map((slot) => ({
      queryKey: [...memberKey, "entry", slot],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiFetch<GameEntry>(`${gamePath(target)}/slots/${slot}`, { signal }),
      retry: false,
      refetchInterval: 30_000,
      enabled: !!game,
    })),
  });
  const editable = !!game && game.entry_state === "open" && !locked && opened;
  const views: SlotView[] = SLOT_NUMBERS.map((slot, index) => {
    const entry = entries[index];
    const intent = intents.find(
      (value) => intentKey(value.target, value.slot) === intentKey(target, slot),
    );
    const knownOffline =
      !online &&
      !!entry.data &&
      (!entry.isError || entry.error instanceof NetworkError);
    const ready =
      editable &&
      !!entry.data &&
      (!entry.isFetching || knownOffline) &&
      (!entry.isError || knownOffline) &&
      !["checking", "sending"].includes(intent?.phase ?? "");
    const pick = entry.data
      ? entry.data.pick
      : (game?.slots.find((value) => value.slot === slot)?.pick ?? null);
    return {
      slot,
      pick,
      intent,
      movedPrice: movedPrice(intent, target, slot),
      ready,
    };
  });
  const slotQueries: SlotQueryState[] = entries.map((entry) => ({
    revision: entry.data?.revision ?? null,
    isError: entry.isError,
    refetch: () => void entry.refetch(),
  }));
  const fixtures = useMemo(
    () => new Map((game?.fixtures ?? []).map((value) => [value.fixture_id, value])),
    [game?.fixtures],
  );
  const groups = useMemo(
    () => groupByCompetition(game?.fixtures ?? []),
    [game?.fixtures],
  );
  const { upTo } = slipSummary(views);
  /** A competition's count, as its header and jump chip show it: picks of fixtures, or fixtures. */
  const countLabel = (group: FixtureGroup<FantasyFixture>) => {
    const mine = group.fixtures.filter((fixture) =>
      views.some((view) => view.pick?.fixture_id === fixture.fixture_id),
    ).length;
    return mine > 0 ? `${mine}/${group.fixtures.length}` : `${group.fixtures.length}`;
  };
  const publicCard = retained ?? results.data?.fantasy;
  const league = leagues.find((value) => value.league_id === target.league_id);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["two-games", player?.id] });
  };

  /** What this fixture's card shows as the member's, and whether a tap may save now. */
  function forCard(fixture: FantasyFixture): {
    held: HeldOnCard | null;
    heldElsewhere: boolean;
    canChoose: boolean;
  } {
    const destination = destinationFor(fixture.fixture_id, views);
    if (destination.kind === "full")
      return { held: null, heldElsewhere: false, canChoose: editable && fixture.eligible };
    const view = views[destination.slot - 1];
    const selection = heldSelection(view);
    const held =
      selection && selection.fixture_id === fixture.fixture_id
        ? {
            selection,
            slot: view.slot,
            pick:
              view.pick &&
              view.pick.fixture_id === selection.fixture_id &&
              view.pick.market === selection.market &&
              view.pick.outcome === selection.outcome
                ? view.pick
                : null,
            phase:
              view.intent?.body.fixture_id === fixture.fixture_id
                ? view.intent.phase
                : undefined,
          }
        : null;
    return {
      held,
      heldElsewhere: false,
      canChoose: editable && fixture.eligible && view.ready,
    };
  }

  /**
   * Batch 251: a save of this fixture refused because its price moved, offered on the row
   * the member tapped. Confirming sends the API's new price into the same slot, exactly
   * as the picks card's "Confirm odds" does; Cancel dismisses the refusal, so the slot
   * keeps whatever it held before.
   */
  function movedFor(fixture: FantasyFixture): MovedOnCard | null {
    const view = views.find(
      (value) =>
        value.movedPrice !== null &&
        value.intent?.body.fixture_id === fixture.fixture_id,
    );
    if (!view || !view.intent || view.movedPrice === null) return null;
    const { intent, slot } = view;
    const price = view.movedPrice;
    const revision = slotQueries[slot - 1].revision;
    return {
      slot,
      outcome: intent.body.outcome,
      price,
      ready: view.ready && revision !== null,
      onConfirm: () => {
        if (revision === null) return;
        engine.choose(
          target,
          slot,
          {
            fixture_id: intent.body.fixture_id,
            market: intent.body.market,
            outcome: intent.body.outcome,
            odds: price,
          },
          revision,
        );
      },
      onCancel: () => engine.dismiss(intentKey(target, slot)),
    };
  }

  function choose(
    fixture: FantasyFixture,
    market: string,
    outcome: string,
    odds: string,
  ) {
    const destination = destinationFor(fixture.fixture_id, views);
    if (destination.kind === "full") {
      setSwap({ fixture, market, outcome, odds });
      return;
    }
    const revision = slotQueries[destination.slot - 1].revision;
    if (revision === null) return;
    engine.choose(
      target,
      destination.slot,
      { fixture_id: fixture.fixture_id, market, outcome, odds },
      revision,
    );
  }

  /** Withdraw a slot's own saved pick (Batch 235): its card's Remove, or a second tap. */
  function removeSlot(slot: number) {
    const view = views[slot - 1];
    const revision = slotQueries[slot - 1].revision;
    if (!editable || !view?.pick || !view.ready || revision === null) return;
    engine.remove(
      target,
      slot,
      {
        fixture_id: view.pick.fixture_id,
        market: view.pick.market,
        outcome: view.pick.outcome,
      },
      revision,
    );
  }

  if (query.isPending) return <p role="status">Loading this Fantasy week…</p>;
  if (query.isError && (!query.data || !(query.error instanceof NetworkError)))
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">Fantasy week unavailable</h1>
        <p role="alert">{query.error.message}</p>
        <Button variant="outline" onClick={() => void query.refetch()}>
          Try again
        </Button>
        <Link to="/" className="underline">
          Home
        </Link>
      </section>
    );
  const shown = game ?? retained;
  if (!shown) return null;
  const points = game?.result.points ?? retained?.result.weekly_points ?? 0;
  const status =
    game?.result.status ?? retained?.result.entry_result ?? "no_entry";
  const provisional = game?.result.provisional ?? retained?.result.provisional;
  const filledCount =
    game?.progress.filled_count ?? retained?.progress.slots_filled ?? 0;
  // Batch 246: an empty tile's "+ Pick" closes the slip and puts the member on the fixtures.
  const toFixtures = () => {
    setSlipOpen(false);
    window.setTimeout(() => {
      slateRef.current?.scrollIntoView?.({ block: "start" });
      slateRef.current?.focus({ preventScroll: true });
    }, 0);
  };
  const slots = () => (
    <div className="grid grid-cols-2 gap-2">
      {views.map((view) => (
        <FantasySlotCard
          key={view.slot}
          target={target}
          view={view}
          query={slotQueries[view.slot - 1]}
          fixture={view.pick ? fixtures.get(view.pick.fixture_id) : undefined}
          editable={editable}
          onRemove={() => removeSlot(view.slot)}
          onPick={toFixtures}
          oddsFormat={oddsFormat}
        />
      ))}
    </div>
  );
  const slate = game && (
    <section
      ref={slateRef}
      tabIndex={-1}
      aria-label="Fantasy fixtures"
      data-testid="fantasy-slate"
      className="scroll-mt-20 focus-visible:outline-hidden"
    >
      <h2 className="mb-2 eyebrow text-text-primary">
        {editable ? "Tap a price to add it" : "Fixtures and prices"}
      </h2>
      {game.fixtures.length === 0 ? (
        <p className="font-sans text-sm text-text-secondary">
          Fixtures are pending; an empty response does not confirm a break.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <CompetitionChips
            label="Fantasy competitions"
            chips={groups.map((group) => ({
              id: group.competition_id,
              anchor: `fantasy-competition-${group.competition_id}`,
              name: group.competition,
              count: countLabel(group),
            }))}
            onJump={(id) => setFolded((value) => ({ ...value, [id]: false }))}
          />
          {groups.map((group) => {
            // Batch 245: a fixture with no prices to tap waits in one row at the end of its
            // competition, unless the member already holds it.
            const shownNow = (fixture: FantasyFixture) =>
              fixture.quote.prices.length > 0 ||
              views.some((view) => view.pick?.fixture_id === fixture.fixture_id);
            const card = (fixture: FantasyFixture) => (
              <FantasyFixtureCard
                key={fixture.fixture_id}
                fixture={fixture}
                competition={group.competition}
                oddsFormat={oddsFormat}
                {...forCard(fixture)}
                onChoose={(market, outcome, odds) => choose(fixture, market, outcome, odds)}
                onRemove={(slot) => removeSlot(slot)}
                moved={movedFor(fixture)}
              />
            );
            const unpriced = group.fixtures.filter((fixture) => !shownNow(fixture));
            return (
              <CompetitionSection
                key={group.competition_id}
                group={group}
                open={!folded[group.competition_id]}
                onToggle={() =>
                  setFolded((value) => ({
                    ...value,
                    [group.competition_id]: !value[group.competition_id],
                  }))
                }
                count={countLabel(group)}
              >
                {group.fixtures.filter(shownNow).map(card)}
                {unpriced.length > 0 && (
                  <UnpricedFold count={unpriced.length}>{unpriced.map(card)}</UnpricedFold>
                )}
              </CompetitionSection>
            );
          })}
        </div>
      )}
      {editable && (
        <SlipBar
          filled={views.filter((view) => view.pick).length}
          upTo={upTo}
          onOpen={() => setSlipOpen(true)}
          barRef={barRef}
        />
      )}
    </section>
  );
  const lockTime = formatInstant(shown.locks_at, "Europe/London", "EEE HH:mm");
  return (
    <div className="space-y-5" data-testid="fantasy-game">
      <GameHeader target={target} weekLabel={shown.week_label} />
      {/* Batch 244: the week bar names the week and the switch the game, so the heading is
          for assistive technology; one status line and one rules line replace the header's
          three paragraphs. */}
      <header className="space-y-1">
        <h1 className="sr-only">
          Fantasy · {formatCalendarDate(shown.week_label, "d MMM")}
        </h1>
        <p className="font-sans text-sm text-text-primary" data-testid="game-status">
          {editable ? (
            <>
              Fantasy locks in{" "}
              <span className="font-mono font-semibold tabular-nums">
                <Countdown target={shown.locks_at} format={formatCountdown} />
              </span>
              <span className="text-text-secondary"> · {lockTime}</span>
            </>
          ) : (
            <>
              <span role="status" className="font-medium">
                {retained
                  ? "Retained locked history"
                  : locked
                    ? "Fantasy locked"
                    : !opened
                      ? "Entry has not opened"
                      : "Entries suspended"}
              </span>
              <span className="text-text-secondary">
                {" "}
                ·{" "}
                {retained || locked
                  ? formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")
                  : !opened
                    ? `Opens ${formatInstant(shown.opens_at, "Europe/London", "EEE d MMM HH:mm")}`
                    : `Locks ${formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}`}
              </span>
            </>
          )}
        </p>
        <GameRules summary="Up to six picks, one per fixture. A win scores its odds × 10.">
          <p>
            Up to six picks on different fixtures. Partial entries count. Members
            can share selections, including the Group game.
          </p>
          <p>
            A winning pick scores its frozen odds × 10; losses and voids score
            nothing. Group adds no points.
          </p>
          <p>
            Locks{" "}
            {formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
            London.
          </p>
        </GameRules>
      </header>
      <WeekFeePanel fee={shown.fee} onRefresh={refresh} />
      {query.isError && (
        <p role="alert" className="font-sans text-sm text-text-primary">
          The latest game could not be refreshed. Showing the last received
          view; saves will verify the current slot before sending.
        </p>
      )}
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)]">
        <div className="min-w-0">{slate}</div>
        <aside
          aria-label="Your Fantasy picks"
          className="min-w-0 lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto"
        >
          {/* Batch 246: one "Your picks" card, the week's score over six compact tiles. */}
          <section className="rounded-xl border border-border bg-surface">
            <div aria-label="Fantasy weekly result" role="group" className="space-y-0.5 p-4 pb-3">
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="font-sans text-base font-semibold text-text-primary">
                  Your picks
                </h2>
                {game && upTo > points && (
                  <span className="font-mono text-sm tabular-nums text-text-secondary">
                    up to {upTo} pts
                  </span>
                )}
              </div>
              <p className="font-sans text-sm text-text-secondary">
                {filledCount} of 6 slots · {fantasyResultLabel(status)}
              </p>
              <p className="font-sans text-lg font-semibold text-text-primary">
                {points} weekly points · {provisional ? "Provisional" : "Final"}
              </p>
            </div>
            <div className="px-4 pb-4">
              {game ? (
                slots()
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {retained?.slots?.map((entry) => (
                    <article
                      key={entry.slot}
                      aria-label={`Fantasy slot ${entry.slot}`}
                      className={cn(
                        "min-w-0 rounded-lg border px-2.5 py-2",
                        entry.pick ? "border-border bg-surface" : "border-dashed border-border-strong",
                      )}
                    >
                      <p className="break-words font-sans text-sm text-text-primary">
                        {entry.pick
                          ? // Batch 249: the price at 2 dp, and no points on a pick still to play.
                            `${entry.pick.runner_name} · ${formatOdds(Number(entry.pick.frozen_odds), oddsFormat)} · ${fantasyResultLabel(entry.pick.result)}${entry.pick.result === "pending" ? "" : ` · ${entry.pick.points ?? 0} points`}`
                          : "Empty slot"}
                      </p>
                    </article>
                  ))}
                </div>
              )}
            </div>
            {league && (
              <Link
                to={`/leagues/${league.slug}/leaderboard`}
                className="flex min-h-11 items-center justify-between gap-2 rounded-b-xl border-t border-border px-4 font-sans text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
              >
                Season table
                <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden />
              </Link>
            )}
          </section>
        </aside>
      </div>
      {results.isError && (
        <div className="space-y-2">
          <p role="alert">Member totals could not be refreshed.</p>
          <Button variant="outline" onClick={() => void results.refetch()}>
            Retry member totals
          </Button>
        </div>
      )}
      {publicCard?.members && (
        <section
          aria-label="Member weekly totals"
          className="space-y-1 rounded-lg border border-border bg-surface p-4"
        >
          <h2 className="font-sans text-lg font-semibold">Member weekly totals</h2>
          {publicCard.members.map((member) => (
            <p key={member.player_id} className="font-sans text-sm">
              {member.display_name}: {member.weekly_points} points ·{" "}
              {fantasyResultLabel(member.entry_result)}
            </p>
          ))}
          {publicCard.result.final && (
            <p className="font-sans text-sm font-medium">
              {publicCard.winner_ids?.length
                ? `Weekly winners: ${publicCard.members
                    .filter((member) =>
                      publicCard.winner_ids?.includes(member.player_id),
                    )
                    .map((member) => member.display_name)
                    .join(", ")}`
                : "No weekly winner"}
            </p>
          )}
        </section>
      )}
      {game && (
        <Sheet
          open={slipOpen}
          onClose={() => setSlipOpen(false)}
          title={`Your picks · ${views.filter((view) => view.pick).length} of 6`}
          triggerRef={barRef}
        >
          <div className="max-h-[70vh] space-y-3 overflow-y-auto pb-2">
            {upTo > 0 && (
              <p className="font-mono text-sm tabular-nums text-text-secondary">
                up to {upTo} pts
              </p>
            )}
            {slots()}
          </div>
        </Sheet>
      )}
      {game && (
        <SwapSheet
          pending={swap}
          views={views}
          fixtures={fixtures}
          revisions={slotQueries.map((value) => value.revision)}
          oddsFormat={oddsFormat}
          onSwap={(slot, revision) => {
            if (!swap) return;
            engine.choose(
              target,
              slot,
              {
                fixture_id: swap.fixture.fixture_id,
                market: swap.market,
                outcome: swap.outcome,
                odds: swap.odds,
              },
              revision,
            );
            setSwap(null);
          }}
          onClose={() => setSwap(null)}
        />
      )}
    </div>
  );
}

/**
 * One competition's fixtures behind a header that folds them away (Batch 232). Batch 245:
 * every section starts open, its header stays in view under the top bar while its fixtures
 * scroll, and the page holds the fold state, so a jump chip can open a folded section and
 * the member's choice survives the 30-second refresh.
 */
function CompetitionSection({
  group,
  open,
  onToggle,
  count,
  children,
}: {
  group: FixtureGroup<FantasyFixture>;
  open: boolean;
  onToggle: () => void;
  count: string;
  children: ReactNode;
}) {
  return (
    <section
      id={`fantasy-competition-${group.competition_id}`}
      data-testid={`fantasy-competition-${group.competition_id}`}
      className={SECTION_SCROLL_MARGIN}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cn(
          STICKY_HEADER,
          "mb-1 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-hidden focus-visible:shadow-glow",
        )}
      >
        <span className="min-w-0 truncate eyebrow text-text-primary">
          {group.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-caption tabular-nums text-text-muted">{count}</span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-text-muted transition-transform",
              open && "rotate-180",
            )}
            aria-hidden
          />
        </span>
      </button>
      {open && <div className="flex flex-col gap-2">{children}</div>}
    </section>
  );
}

/** The fixtures in a competition with no prices to tap yet, folded into one row (Batch 245). */
function UnpricedFold({ count, children }: { count: number; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg border border-dashed border-border px-3 font-sans text-sm text-text-secondary hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        {count === 1 ? "1 fixture without prices yet" : `${count} fixtures without prices yet`}
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-text-muted transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>
      {open && <div className="mt-2 flex flex-col gap-2">{children}</div>}
    </div>
  );
}
