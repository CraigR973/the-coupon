import { useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
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
import { formatCalendarDate, formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import { WeekFeePanel } from "../components/WeekFeePanel";
import { GameSwitch } from "../components/GameSwitch";
import { Countdown } from "../components/Countdown";
import {
  FantasyFixtureCard,
  type HeldOnCard,
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
  const slots = () =>
    views.map((view) => (
      <FantasySlotCard
        key={view.slot}
        target={target}
        view={view}
        query={slotQueries[view.slot - 1]}
        fixture={view.pick ? fixtures.get(view.pick.fixture_id) : undefined}
        editable={editable}
        onRemove={() => removeSlot(view.slot)}
      />
    ));
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
          {groups.map((group) => (
            <CompetitionSection
              key={group.competition_id}
              group={group}
              defaultOpen={groups.length === 1}
              mine={
                group.fixtures.filter((fixture) =>
                  views.some((view) => view.pick?.fixture_id === fixture.fixture_id),
                ).length
              }
            >
              {group.fixtures.map((fixture) => (
                <FantasyFixtureCard
                  key={fixture.fixture_id}
                  fixture={fixture}
                  competition={group.competition}
                  oddsFormat={oddsFormat}
                  {...forCard(fixture)}
                  onChoose={(market, outcome, odds) =>
                    choose(fixture, market, outcome, odds)
                  }
                  onRemove={(slot) => removeSlot(slot)}
                />
              ))}
            </CompetitionSection>
          ))}
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
  return (
    <div className="space-y-5" data-testid="fantasy-game">
      <GameSwitch target={target} />
      <nav
        aria-label="Game navigation"
        className="flex flex-wrap gap-x-4 font-sans text-sm"
      >
        <Link className="inline-flex min-h-11 items-center underline" to="/">
          Home
        </Link>
        <Link
          className="inline-flex min-h-11 items-center underline"
          to={`/leagues/${target.league_id}/games`}
        >
          Game archive
        </Link>
        {league && (
          <Link
            className="inline-flex min-h-11 items-center underline"
            to={`/leagues/${league.slug}/leaderboard`}
          >
            Season table
          </Link>
        )}
      </nav>
      <header className="space-y-1">
        <h1 className="font-sans text-2xl font-semibold text-text-primary">
          Fantasy · {formatCalendarDate(shown.week_label, "d MMM")}
        </h1>
        <p className="font-sans text-sm text-text-secondary">
          Up to six picks on different fixtures. Partial entries count. Members
          can share selections, including the Group game.
        </p>
        <p className="font-sans text-sm text-text-secondary">
          Locks{" "}
          {formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
          London
          {editable && (
            <>
              {" "}
              · in <Countdown target={shown.locks_at} format={formatCountdown} />
            </>
          )}
          .
        </p>
        {!editable && (
          <p role="status" className="font-sans text-sm text-text-primary">
            {retained
              ? "Retained locked history"
              : locked
                ? "Fantasy locked"
                : !opened
                  ? "Entry has not opened"
                  : "Entries suspended"}
          </p>
        )}
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
          className="min-w-0 space-y-3 lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto"
        >
          <section
            aria-label="Fantasy weekly result"
            className="space-y-1 rounded-lg border border-border bg-surface p-4"
          >
            <p className="font-sans text-sm text-text-primary">
              {filledCount} of 6 slots · {fantasyResultLabel(status)}
            </p>
            <p className="font-sans text-lg font-semibold text-text-primary">
              {points} weekly points · {provisional ? "Provisional" : "Final"}
            </p>
            {game && upTo > points && (
              <p className="font-sans text-xs text-text-secondary">
                Up to {upTo} points if every pending pick wins.
              </p>
            )}
            <p className="font-sans text-xs text-text-muted">
              A winning pick scores its frozen odds × 10; losses and voids score
              nothing. Group adds no points.
            </p>
          </section>
          {game
            ? slots()
            : retained?.slots?.map((entry) => (
                <article
                  key={entry.slot}
                  className="rounded-lg border border-border bg-surface px-3 py-2.5"
                >
                  <h2 className="eyebrow text-text-muted">
                    Slot {entry.slot}
                  </h2>
                  <p className="font-sans text-sm text-text-primary">
                    {entry.pick
                      ? `${entry.pick.runner_name} · Frozen odds ${entry.pick.frozen_odds} · ${fantasyResultLabel(entry.pick.result)} · ${entry.pick.points ?? 0} points`
                      : "Empty slot"}
                  </p>
                </article>
              ))}
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
          <div className="max-h-[70vh] space-y-2 overflow-y-auto px-4 pb-5">
            {upTo > 0 && (
              <p className="font-sans text-sm text-text-secondary">
                Up to {upTo} points if every pending pick wins.
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
 * One competition's fixtures behind a header, as the old coupon folds its slate. All
 * start closed (Batch 238) so a card of a hundred-odd fixtures scans as competitions; a
 * week with a single competition opens it. `defaultOpen` seeds the state only, so a
 * member who opens or closes a section keeps it that way through the 30-second refresh.
 */
function CompetitionSection({
  group,
  defaultOpen,
  mine,
  children,
}: {
  group: FixtureGroup<FantasyFixture>;
  defaultOpen: boolean;
  mine: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section data-testid={`fantasy-competition-${group.competition_id}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mb-1 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <span className="min-w-0 truncate eyebrow text-text-primary">
          {group.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-caption tabular-nums text-text-muted">
            {mine > 0 ? `${mine}/${group.fixtures.length}` : group.fixtures.length}
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
      {open && <div className="flex flex-col gap-4">{children}</div>}
    </section>
  );
}
