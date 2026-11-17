import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useGameRoute } from "../hooks/useGameRoute";
import { useGameIntents, useGameNavigation } from "../hooks/useGameIntents";
import { useExpiry } from "../hooks/useExpiry";
import { useOnlineStatus } from "../hooks/useOnlineStatus";
import { apiFetch, ApiError, NetworkError } from "../lib/api";
import { intentKey } from "../lib/gameIntents";
import { fantasyResultLabel, fantasyRunner, movedPrice } from "../lib/fantasy";
import {
  gamePath,
  gameQueryKey,
  type GameTarget,
  type GameEntry,
  type FantasyGame,
  type GameCard,
  type FantasyFixture,
} from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { WeekFeePanel } from "../components/WeekFeePanel";
import { GameIntentStatus } from "../components/GameIntentStatus";
import { Button } from "../components/ui/button";

function FantasySlot({
  target,
  slot,
  game,
  selected,
  onSelect,
  editable,
}: {
  target: GameTarget;
  slot: number;
  game: FantasyGame;
  selected: boolean;
  onSelect: () => void;
  editable: boolean;
}) {
  const { player } = useAuth();
  const { engine, intents } = useGameIntents();
  const entry = useQuery({
    queryKey: [...gameQueryKey(player?.id ?? "", target), "entry", slot],
    queryFn: ({ signal }) =>
      apiFetch<GameEntry>(`${gamePath(target)}/slots/${slot}`, { signal }),
    retry: false,
    refetchInterval: 30_000,
  });
  const intent = intents.find(
    (value) => intentKey(value.target, value.slot) === intentKey(target, slot),
  );
  const online = useOnlineStatus();
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
    : game.slots.find((value) => value.slot === slot)?.pick;
  const price = movedPrice(intent, target, slot);
  return (
    <article
      aria-label={`Fantasy slot ${slot}`}
      className="rounded-xl border border-border bg-surface p-4 space-y-3"
    >
      <h2 className="text-lg font-semibold">Slot {slot}</h2>
      {pick ? (
        <div>
          <p>
            {pick.runner_name} · Frozen odds {pick.frozen_odds}
          </p>
          <p>
            {fantasyResultLabel(pick.result)} · {pick.points ?? 0} points
          </p>
        </div>
      ) : (
        <p>Empty slot</p>
      )}
      {editable && (
        <Button
          variant="outline"
          className={selected ? "bg-surface-elevated" : undefined}
          disabled={!ready}
          onClick={onSelect}
          aria-pressed={selected}
        >
          {pick ? "Replace" : "Fill"} slot {slot}
        </Button>
      )}
      {entry.isError && (
        <div>
          <p role="alert">
            Could not verify slot {slot}. Your saved choice has not been
            replaced.
          </p>
          <Button variant="outline" onClick={() => void entry.refetch()}>
            Check slot {slot}
          </Button>
        </div>
      )}
      <GameIntentStatus target={target} slot={slot} />
      {price && intent && (
        <div
          className="space-y-2"
          role="group"
          aria-label={`Price confirmation for slot ${slot}`}
        >
          <p>
            The price changed to {price}. Your saved choice stays until you
            confirm this new price.
          </p>
          <Button
            variant="outline"
            disabled={!ready}
            onClick={() =>
              engine.choose(
                target,
                slot,
                {
                  fixture_id: intent.body.fixture_id,
                  market: intent.body.market,
                  outcome: intent.body.outcome,
                  odds: price,
                },
                entry.data!.revision,
              )
            }
          >
            Confirm odds {price} for slot {slot}
          </Button>
        </div>
      )}
      {selected && (
        <FantasyChooser
          target={target}
          slot={slot}
          game={game}
          ready={ready}
          revision={entry.data?.revision ?? 0}
        />
      )}
    </article>
  );
}
function FantasyChooser({
  target,
  slot,
  game,
  ready,
  revision,
}: {
  target: GameTarget;
  slot: number;
  game: FantasyGame;
  ready: boolean;
  revision: number;
}) {
  const { engine, intents } = useGameIntents();
  const used = new Set(
    game.slots
      .filter((entry) => entry.slot !== slot && entry.pick)
      .map((entry) => entry.pick!.fixture_id),
  );
  // Include local choices in other slots so two offline fills do not offer the same fixture.
  for (const intent of intents)
    if (
      intent.target.league_id === target.league_id &&
      intent.target.week_id === target.week_id &&
      intent.target.game_kind === "fantasy" &&
      intent.slot !== slot &&
      ["queued", "uncertain", "checking", "sending"].includes(intent.phase)
    )
      used.add(intent.body.fixture_id);
  return (
    <section
      aria-label={`Choose fixture for slot ${slot}`}
      className="space-y-3"
    >
      <h3 className="font-semibold">Choose a fixture for slot {slot}</h3>
      {game.fixtures.length === 0 && (
        <p>Fixtures are pending; an empty response does not confirm a break.</p>
      )}
      {game.fixtures.map((fixture) => (
        <FantasyFixtureRow
          key={fixture.fixture_id}
          fixture={fixture}
          disabled={!ready || used.has(fixture.fixture_id) || !fixture.eligible}
          used={used.has(fixture.fixture_id)}
          choose={(market, outcome, odds) =>
            engine.choose(
              target,
              slot,
              { fixture_id: fixture.fixture_id, market, outcome, odds },
              revision,
            )
          }
        />
      ))}
    </section>
  );
}
function FantasyFixtureRow({
  fixture,
  disabled,
  used,
  choose,
}: {
  fixture: FantasyFixture;
  disabled: boolean;
  used: boolean;
  choose: (market: string, outcome: string, odds: string) => void;
}) {
  const quote = fixture.quote;
  const expired = useExpiry(
    quote.observed_at
      ? new Date(new Date(quote.observed_at).getTime() + 60_000).toISOString()
      : "1970-01-01T00:00:00Z",
  );
  return (
    <div className="border-t border-border pt-3 space-y-2">
      <h4 className="font-semibold">
        {fixture.home} v {fixture.away}
      </h4>
      <p className="text-sm">
        {formatInstant(fixture.kickoff_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
        London
      </p>
      {used && <p>Already chosen in another slot.</p>}
      <p className="text-sm">
        {quote.provider} · {quote.bookmaker} ·{" "}
        {quote.observed_at
          ? `Observed ${formatInstant(quote.observed_at, "Europe/London", "HH:mm:ss")} London`
          : "No observed price"}{" "}
        · {quote.availability}
        {expired && quote.prices.length > 0
          ? " · Price expired; saving will check a fresh price."
          : ""}
        {quote.degraded ? " · Degraded coverage" : ""}
      </p>
      {quote.prices.length === 0 && (
        <p>Prices unavailable. Refresh prices to check again.</p>
      )}
      <div className="flex flex-wrap gap-2">
        {quote.prices.map((price) => (
          <Button
            key={`${price.market}/${price.outcome}`}
            variant="outline"
            disabled={
              disabled || !["available", "stale"].includes(quote.availability)
            }
            onClick={() => choose(price.market, price.outcome, price.odds)}
            aria-label={`Choose ${fantasyRunner(fixture, price.outcome)} at ${price.odds}`}
          >
            {fantasyRunner(fixture, price.outcome)} · {price.odds}
          </Button>
        ))}
      </div>
    </div>
  );
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
function FantasyWeek({ target }: { target: GameTarget }) {
  const { player } = useAuth();
  const leagues = useGameNavigation();
  const client = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const query = useQuery({
    queryKey: [...gameQueryKey(player?.id ?? "", target), "view"],
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
    queryKey: [...gameQueryKey(player?.id ?? "", target), "results"],
    queryFn: ({ signal }) =>
      apiFetch<{ fantasy: GameCard | null }>(
        `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/results`,
        { signal },
      ),
    enabled: !!game && locked,
    retry: false,
    refetchInterval: 30_000,
  });
  const publicCard = retained ?? results.data?.fantasy;
  const league = leagues.find((value) => value.league_id === target.league_id);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["two-games", player?.id] });
  };
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
  const editable = !!game && game.entry_state === "open" && !locked && opened;
  const points = game?.result.points ?? retained?.result.weekly_points ?? 0;
  const status =
    game?.result.status ?? retained?.result.entry_result ?? "no_entry";
  return (
    <div className="mx-auto max-w-3xl space-y-5" data-testid="fantasy-game">
      <nav aria-label="Game navigation" className="flex flex-wrap gap-4">
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
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">
          Fantasy · {formatCalendarDate(shown.week_label, "d MMM")}
        </h1>
        <p>
          Up to six picks on different fixtures. Partial entries count. Members
          can share selections, including the Group game.
        </p>
        <p>
          Locks{" "}
          {formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
          London.
        </p>
        {!editable && (
          <p role="status">
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
      <section
        aria-label="Fantasy weekly result"
        className="rounded-xl border border-border bg-surface p-4 space-y-2"
      >
        <p>
          {game?.progress.filled_count ?? retained?.progress.slots_filled ?? 0}{" "}
          of 6 slots · {fantasyResultLabel(status)}
        </p>
        <p className="font-semibold">
          {points} weekly points ·{" "}
          {(game?.result.provisional ?? retained?.result.provisional)
            ? "Provisional"
            : "Final"}
        </p>
        <p>
          Winning legs score rounded frozen odds × 10; losses and voids score
          zero. Group contributes no points. Season totals retain legacy points
          and add Fantasy legs once.
        </p>
      </section>
      {query.isError && (
        <p role="alert">
          The latest game could not be refreshed. Showing the last received
          view; saves will verify the current slot before sending.
        </p>
      )}
      {game && (
        <Button variant="outline" onClick={refresh}>
          Refresh prices and results
        </Button>
      )}
      {game
        ? Array.from({ length: 6 }, (_, index) => (
            <FantasySlot
              key={index + 1}
              target={target}
              slot={index + 1}
              game={game}
              selected={selected === index + 1}
              onSelect={() => setSelected(index + 1)}
              editable={editable}
            />
          ))
        : retained?.slots?.map((entry) => (
            <article
              key={entry.slot}
              className="rounded-xl border border-border p-4"
            >
              <h2>Slot {entry.slot}</h2>
              <p>
                {entry.pick
                  ? `${entry.pick.runner_name} · Frozen odds ${entry.pick.frozen_odds} · ${fantasyResultLabel(entry.pick.result)} · ${entry.pick.points ?? 0} points`
                  : "Empty slot"}
              </p>
            </article>
          ))}
      {results.isError && (
        <div>
          <p role="alert">Member totals could not be refreshed.</p>
          <Button variant="outline" onClick={() => void results.refetch()}>
            Retry member totals
          </Button>
        </div>
      )}
      {publicCard?.members && (
        <section aria-label="Member weekly totals">
          <h2 className="text-lg font-semibold">Member weekly totals</h2>
          {publicCard.members.map((member) => (
            <p key={member.player_id}>
              {member.display_name}: {member.weekly_points} points ·{" "}
              {fantasyResultLabel(member.entry_result)}
            </p>
          ))}
          {publicCard.result.final && (
            <p>
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
      {league?.weekly_form.length ? (
        <section aria-label="Your recent weeks">
          <h2 className="text-lg font-semibold">Your recent weeks</h2>
          {league.weekly_form.map((week) => (
            <p key={week.week_id}>
              <Link
                className="inline-flex min-h-11 items-center underline"
                to={week.destination}
              >
                {formatCalendarDate(week.week_label, "d MMM")} ·{" "}
                {week.format === "legacy" ? "Legacy" : "Fantasy"} ·{" "}
                {week.weekly_points} points
              </Link>
            </p>
          ))}
        </section>
      ) : null}
      <WeekFeePanel fee={shown.fee} onRefresh={refresh} />
    </div>
  );
}
