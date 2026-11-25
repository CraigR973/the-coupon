import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useGameIntents, useGameNavigation } from "../hooks/useGameIntents";
import { useGameRoute } from "../hooks/useGameRoute";
import { useExpiry } from "../hooks/useExpiry";
import type { CountdownParts } from "../hooks/useCountdown";
import { apiFetch, ApiError, NetworkError } from "../lib/api";
import { intentKey } from "../lib/gameIntents";
import { fixtureContext } from "../lib/coupon";
import {
  competitionName,
  groupByCompetition,
  type FixtureGroup,
} from "../lib/gameFixtures";
import { groupLegs, groupPhase } from "../lib/groupCoupon";
import {
  gamePath,
  gameQueryKey,
  type GameEntry,
  type GroupGame,
  type GameCard,
  type GroupFixture,
} from "../lib/twoGameTypes";
import type { PickMarket, PickOutcome } from "../lib/types";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { cn } from "../lib/utils";
import { WeekFeePanel } from "../components/WeekFeePanel";
import { GameIntentStatus } from "../components/GameIntentStatus";
import { GameHeader, GameRules } from "../components/GameHeader";
import { Countdown } from "../components/Countdown";
import { GroupFixtureCard } from "../components/GroupFixtureCard";
import {
  GroupCouponSection,
  GroupStatusCard,
  type GroupMyPick,
} from "../components/GroupCoupon";
import { Button } from "../components/ui/button";

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return "now";
  if (p.days > 0) return `${p.days}d ${p.hours}h`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m`;
  return `${p.minutes}m ${p.seconds}s`;
}

/** A save on its way: the selection button shows it, and the card keeps its status. */
const IN_FLIGHT = new Set(["queued", "sending", "checking", "uncertain"]);

interface GroupRead {
  game: GroupGame | null;
  retained: GameCard | null;
}

/**
 * The Saturday group on the old coupon screen (Batch 233): folded competitions of the old
 * fixture cards beside the old status card and the coupon, as the legacy round screen
 * lays them out. A tap saves the member's one contribution and another switches it,
 * through the group's existing single addressed write.
 */
export function GroupGamePage() {
  const target = useGameRoute("group");
  const { player } = useAuth();
  const { engine, intents } = useGameIntents();
  const leagues = useGameNavigation();
  const client = useQueryClient();
  const key = gameQueryKey(player?.id ?? "", target);
  const query = useQuery<GroupRead>({
    queryKey: key,
    queryFn: async () => {
      try {
        return {
          game: await apiFetch<GroupGame>(gamePath(target)),
          retained: null,
        };
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
        const history = await apiFetch<{ group: GameCard | null }>(
          `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/results`,
        );
        if (!history.group) throw error;
        return { game: null, retained: history.group };
      }
    },
    retry: false,
    refetchInterval: 30_000,
  });
  const entry = useQuery({
    queryKey: [...key, "entry"],
    queryFn: () => apiFetch<GameEntry>(gamePath(target) + "/pick"),
    enabled: !!query.data?.game,
    retry: false,
  });
  const game = query.data?.game,
    retained = query.data?.retained;
  const expiry = useExpiry(
    game?.locks_at ?? retained?.locks_at ?? "1970-01-01T00:00:00Z",
  );
  const notOpened = !useExpiry(
    game?.opens_at ?? retained?.opens_at ?? "1970-01-01T00:00:00Z",
  );
  // Each competition folds on its own, and all start folded (Batch 238) unless the week
  // has a single competition, which opens so the screen never starts empty.
  const [folds, setFolds] = useState<Record<string, boolean>>({});
  const fixtures = game?.fixtures;
  const groups = useMemo(() => groupByCompetition(fixtures ?? []), [fixtures]);
  const legs = useMemo(() => groupLegs(fixtures ?? []), [fixtures]);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["two-games", player?.id] });
  };
  const intent = intents.find(
    (value) => intentKey(value.target, value.slot) === intentKey(target, 0),
  );
  const saving = intents.some(
    (value) =>
      value.target.league_id === target.league_id &&
      value.target.week_id === target.week_id &&
      value.target.game_kind === target.game_kind &&
      ["checking", "sending"].includes(value.phase),
  );
  const editable =
    !!game &&
    game.entry_state === "open" &&
    !expiry &&
    !notOpened &&
    !!entry.data &&
    !entry.isFetching &&
    !entry.isError &&
    !saving;
  if (query.isPending)
    return <p role="status">Loading the addressed Group game…</p>;
  // A refresh that fails on the connection keeps the last view, as the fantasy week does
  // (Batch 236): the 30-second poll and the refetch on returning to the app both retry it.
  // A failed first load, or a refusal from the server, still replaces the screen.
  if (query.isError && (!query.data || !(query.error instanceof NetworkError))) {
    const destination =
      query.error instanceof ApiError
        ? query.error.data?.destination
        : undefined;
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-semibold">Group game unavailable</h1>
        <p role="alert">{query.error.message}</p>
        {typeof destination === "string" &&
          destination.startsWith("/leagues/") &&
          !destination.includes("//") && (
            <Link className="underline" to={destination}>
              Open this legacy week
            </Link>
          )}
        <Button onClick={() => void query.refetch()}>Try again</Button>
        <Link className="underline" to="/">
          Home
        </Link>
      </section>
    );
  }
  const shown = game ?? retained;
  if (!shown) return null;
  const league = leagues.find((value) => value.league_id === target.league_id);
  const progress = shown.progress;
  const picked = progress.picked_count ?? 0,
    members = progress.member_count ?? 0;
  const mine = game?.my_entries[0] ?? retained?.my_entry?.pick;
  const final = shown.result.final;
  const resultStatus = shown.result.status ?? "pending";
  const entryOpen = !!game && game.entry_state === "open";
  // The pick window itself, steady through a save; `editable` also waits out each save.
  const pickable = entryOpen && !expiry && !notOpened;
  const locked = !game || expiry || game.entry_state === "locked";
  const phase = groupPhase({
    entryState: game ? game.entry_state : "locked",
    notOpened,
    expired: expiry,
    final,
    hasPick: !!mine,
    picked,
    members,
  });
  // The old card's clock: the 14:30 countdown while picks are open.
  let clock: ReactNode = null;
  if (phase === "not_open")
    clock = (
      <>
        Picks open in{" "}
        <Countdown target={shown.opens_at} format={formatCountdown} />
      </>
    );
  else if (!["settled", "suspended", "cancelled"].includes(phase))
    clock = locked ? (
      "Picks are locked"
    ) : (
      <>
        Picks lock in{" "}
        <Countdown target={shown.locks_at} format={formatCountdown} />
      </>
    );
  // Why the cards cannot be used yet, when the chip and the clock do not already say it.
  const status = retained
    ? "Retained locked history"
    : pickable
      ? entry.isError
        ? "Could not verify your saved contribution"
        : entry.isFetching || saving
          ? "Checking the current saved contribution…"
          : null
      : null;
  const myFixture = mine
    ? game?.fixtures.find((fixture) => fixture.fixture_id === mine.fixture_id)
    : undefined;
  const myPick: GroupMyPick | null = mine
    ? {
        selection: mine.runner_name,
        context: myFixture
          ? fixtureContext(
              mine.market as PickMarket,
              mine.outcome as PickOutcome,
              myFixture.home,
              myFixture.away,
            )
          : null,
        competition: myFixture ? competitionName(myFixture.competition_id) : null,
        result: mine.result,
      }
    : null;
  const pending =
    intent && IN_FLIGHT.has(intent.phase)
      ? {
          fixture_id: intent.body.fixture_id,
          market: intent.body.market,
          outcome: intent.body.outcome,
          phase: intent.phase,
        }
      : null;
  const isOpen = (competition: string) =>
    folds[competition] ?? groups.length === 1;
  // The save's status sits in the card it is about, where the member just tapped; it
  // falls back to the top of the list while that card is folded away or gone.
  const statusInCard =
    !!intent &&
    groups.some(
      (group) =>
        isOpen(group.competition_id) &&
        group.fixtures.some(
          (fixture) => fixture.fixture_id === intent.body.fixture_id,
        ),
    );
  const choose = (fixture: GroupFixture, market: string, outcome: string) =>
    engine.choose(
      target,
      0,
      { fixture_id: fixture.fixture_id, market, outcome },
      entry.data!.revision,
    );
  // Batch 235: a second tap on the member's own saved pick withdraws it.
  const remove = () => {
    const pick = entry.data?.pick;
    if (!pick || !entry.data) return;
    engine.remove(
      target,
      0,
      { fixture_id: pick.fixture_id, market: pick.market, outcome: pick.outcome },
      entry.data.revision,
    );
  };
  const weekLabel = formatCalendarDate(shown.week_label, "d MMM");
  const noPick =
    phase === "not_open"
      ? "No pick yet — this game isn't open."
      : pickable
        ? "No pick yet — tap a selection to make it yours."
        : locked
          ? "You did not pick this week."
          : "No pick saved.";
  const slate = game && (
    <section aria-labelledby="group-fixtures-heading" className="space-y-3">
      <h2
        id="group-fixtures-heading"
        className="eyebrow text-text-primary"
      >
        {pickable ? "Pick your selection" : "Saturday 15:00 fixtures"}
      </h2>
      {!statusInCard && <GameIntentStatus target={target} slot={0} compact />}
      {game.fixtures.length === 0 ? (
        <p className="font-sans text-sm text-text-secondary">
          {game.coverage_state === "confirmed_empty"
            ? "No eligible fixtures are confirmed."
            : "Fixtures are pending; an empty response does not confirm a break."}
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <CompetitionFold
              key={group.competition_id}
              group={group}
              open={isOpen(group.competition_id)}
              onToggle={() =>
                setFolds((value) => ({
                  ...value,
                  [group.competition_id]: !isOpen(group.competition_id),
                }))
              }
            >
              {group.fixtures.map((fixture) => (
                <GroupFixtureCard
                  key={fixture.fixture_id}
                  fixture={fixture}
                  competition={group.competition}
                  memberId={player?.id}
                  pending={
                    pending && pending.fixture_id === fixture.fixture_id
                      ? pending
                      : null
                  }
                  canChoose={editable}
                  onChoose={(market, outcome) => choose(fixture, market, outcome)}
                  onRemove={remove}
                >
                  {statusInCard &&
                    intent?.body.fixture_id === fixture.fixture_id && (
                      <GameIntentStatus target={target} slot={0} compact />
                    )}
                </GroupFixtureCard>
              ))}
            </CompetitionFold>
          ))}
        </div>
      )}
    </section>
  );
  return (
    <div className="space-y-5" data-testid="group-game">
      <GameHeader target={target} weekLabel={shown.week_label} />
      {/* Batch 244: the week bar names the week and the switch the game, so the heading is
          for assistive technology. The status card below keeps the countdown, so the rules
          line carries only the lock time. */}
      <header>
        <h1 className="sr-only">Saturday Group · {weekLabel}</h1>
        <GameRules
          summary={`One pick each, and a fixture belongs to one member. Locks ${formatInstant(shown.locks_at, "Europe/London", "EEE HH:mm")}.`}
        >
          <p>
            One contribution each. A fixture belongs to one member across the
            group.
          </p>
          <p>
            Locks{" "}
            {formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
            London time.
          </p>
        </GameRules>
      </header>
      <WeekFeePanel fee={shown.fee} onRefresh={refresh} />
      {query.isError && (
        <p role="alert" className="font-sans text-sm text-text-primary">
          The latest game could not be refreshed. Showing the last received
          view; a save still checks your saved contribution before sending.
        </p>
      )}
      {/* The status card and the coupon come first, so on a phone they sit above the
          fixtures (Batch 238); at desktop width the grid keeps the fixtures on the left. */}
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)]">
        <aside
          aria-label="Group status and coupon"
          className="min-w-0 space-y-4 lg:sticky lg:top-20 lg:col-start-2 lg:row-start-1 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto"
        >
          {!game && <GameIntentStatus target={target} slot={0} compact />}
          <GroupStatusCard
            phase={phase}
            clock={clock}
            status={status}
            result={{ status: resultStatus, final }}
            showResult={final || (locked && resultStatus !== "pending")}
            picked={picked}
            members={members}
            mine={myPick}
            canSwitch={pickable}
            noPick={noPick}
            stillToPick={(game?.still_to_pick ?? []).map((member) => member.display_name)}
          />
          {entry.isError && game && (
            <Button variant="outline" onClick={() => void entry.refetch()}>
              Check saved contribution
            </Button>
          )}
          {game && (
            <GroupCouponSection
              legs={legs}
              memberId={player?.id}
              picked={picked}
              members={members}
              locked={locked}
              final={final}
              resultStatus={resultStatus}
              weekLabel={weekLabel}
            />
          )}
          {league && (
            <Link
              to={`/leagues/${league.slug}/leaderboard`}
              className="inline-flex min-h-11 items-center gap-1 font-sans text-sm font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-hidden focus-visible:shadow-glow"
            >
              Season table
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Link>
          )}
        </aside>
        {slate && <div className="min-w-0 lg:col-start-1 lg:row-start-1">{slate}</div>}
      </div>
    </div>
  );
}

/**
 * One competition's fixtures behind a header that folds them away, as on the legacy
 * slate. The count reads "claimed/total" once anyone has picked a game in it.
 */
function CompetitionFold({
  group,
  open,
  onToggle,
  children,
}: {
  group: FixtureGroup<GroupFixture>;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const claimed = group.fixtures.filter((fixture) => fixture.claim).length;
  return (
    <section data-testid={`group-competition-${group.competition_id}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="mb-1 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <span className="min-w-0 truncate eyebrow text-text-primary">
          {group.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-caption tabular-nums text-text-muted">
            {claimed > 0 ? `${claimed}/${group.fixtures.length}` : group.fixtures.length}
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
