import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useGameIntents } from "../hooks/useGameIntents";
import { useGameRoute } from "../hooks/useGameRoute";
import { useExpiry } from "../hooks/useExpiry";
import { apiFetch, ApiError } from "../lib/api";
import {
  gamePath,
  gameQueryKey,
  type GameEntry,
  type GroupGame,
  type GameCard,
} from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { WeekFeePanel } from "../components/WeekFeePanel";
import { GameIntentStatus } from "../components/GameIntentStatus";
import { Button } from "../components/ui/button";

const label = (status: string) =>
  ({
    no_coupon: "No coupon",
    pending: "Pending results",
    won: "Won",
    lost: "Lost",
    void: "Void",
  })[status] ?? status;
interface GroupRead {
  game: GroupGame | null;
  retained: GameCard | null;
}
export function GroupGamePage() {
  const target = useGameRoute("group");
  const { player } = useAuth();
  const { engine, intents } = useGameIntents();
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
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["two-games", player?.id] });
  };
  const saving = intents.some(
    (intent) =>
      intent.target.league_id === target.league_id &&
      intent.target.week_id === target.week_id &&
      intent.target.game_kind === target.game_kind &&
      ["checking", "sending"].includes(intent.phase),
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
  if (query.isError) {
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
  const progress = shown.progress;
  const picked = progress.picked_count ?? 0,
    members = progress.member_count ?? 0;
  const mine = game?.my_entries[0] ?? retained?.my_entry?.pick;
  return (
    <div className="mx-auto max-w-3xl space-y-5" data-testid="group-game">
      <nav aria-label="Game navigation" className="flex flex-wrap gap-4">
        <Link to="/" className="underline">
          Home
        </Link>
        <Link to={`/leagues/${target.league_id}/games`} className="underline">
          Game archive
        </Link>
      </nav>
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">
          Saturday Group · {formatCalendarDate(shown.week_label, "d MMM")}
        </h1>
        <p>
          One contribution each. A fixture belongs to one member across the
          group.
        </p>
        <p>
          Locks{" "}
          {formatInstant(shown.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
          London time.
        </p>
        {!editable && (
          <p role="status">
            {retained
              ? "Retained locked history"
              : expiry
                ? "Group locked"
                : notOpened
                  ? "Entry has not opened"
                  : game?.entry_state === "suspended"
                    ? "Entries suspended"
                    : entry.isError
                      ? "Could not verify your saved contribution"
                      : entry.isFetching || saving
                        ? "Checking the current saved contribution…"
                        : game?.entry_state}
          </p>
        )}
      </header>
      <section
        className="rounded-xl border border-border bg-surface p-4 space-y-2"
        aria-label="Group progress and result"
      >
        <p>
          {picked} of {members} contributed · {Math.max(0, members - picked)}{" "}
          missing contributors.
        </p>
        <p className="font-semibold">
          {label(shown.result.status ?? "pending")}
          {shown.result.final ? " · Final" : " · Provisional"}
        </p>
        <p className="text-sm text-text-secondary">
          Incomplete participation is valid. Void legs are neutral; all void is
          void. Zero contributions means No coupon.
        </p>
        <p>
          Your saved contribution:{" "}
          {mine ? `${mine.runner_name} · ${label(mine.result)}` : "None yet"}
        </p>
      </section>
      <GameIntentStatus target={target} slot={0} />
      {entry.isError && game && (
        <Button variant="outline" onClick={() => void entry.refetch()}>
          Check saved contribution
        </Button>
      )}
      {game && (
        <section aria-labelledby="group-fixtures-heading" className="space-y-3">
          <h2 id="group-fixtures-heading" className="text-xl font-semibold">
            Saturday 15:00 fixtures
          </h2>
          {game.fixtures.length === 0 && (
            <p>
              {game.coverage_state === "confirmed_empty"
                ? "No eligible fixtures are confirmed."
                : "Fixtures are pending; an empty response does not confirm a break."}
            </p>
          )}
          {game.fixtures.map((fixture) => (
            <article
              key={fixture.fixture_id}
              className="rounded-xl border border-border bg-surface p-4 space-y-3"
            >
              <h3 className="font-semibold">
                {fixture.home} v {fixture.away}
              </h3>
              <p className="text-sm">
                {formatInstant(
                  fixture.kickoff_at,
                  "Europe/London",
                  "EEE d MMM HH:mm",
                )}{" "}
                London · {fixture.competition_id}
              </p>
              {fixture.claim && (
                <p>
                  Claimed by {fixture.claim.display_name}:{" "}
                  {fixture.claim.runner_name} · {label(fixture.claim.result)}
                </p>
              )}
              {!fixture.eligible && (
                <p>This fixture is unavailable for a new contribution.</p>
              )}
              {fixture.allowed_markets.map((market) => (
                <fieldset key={market.market} className="space-y-2">
                  <legend className="text-sm">
                    {market.market === "MATCH_ODDS"
                      ? "Match result"
                      : "Both teams to score"}
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {market.outcomes.map((outcome) => {
                      const name =
                        outcome === "HOME"
                          ? `${fixture.home} to win`
                          : outcome === "AWAY"
                            ? `${fixture.away} to win`
                            : outcome === "DRAW"
                              ? "Draw"
                              : outcome === "YES"
                                ? "Both teams score"
                                : "Both teams do not score";
                      return (
                        <Button
                          key={outcome}
                          variant={
                            mine?.fixture_id === fixture.fixture_id &&
                            mine.market === market.market &&
                            mine.outcome === outcome
                              ? "default"
                              : "outline"
                          }
                          disabled={
                            !editable ||
                            !fixture.eligible ||
                            (!!fixture.claim &&
                              fixture.claim.player_id !== player?.id)
                          }
                          aria-label={`Choose ${name}`}
                          onClick={() =>
                            engine.choose(
                              target,
                              0,
                              {
                                fixture_id: fixture.fixture_id,
                                market: market.market,
                                outcome,
                              },
                              entry.data!.revision,
                            )
                          }
                        >
                          {name}
                        </Button>
                      );
                    })}
                  </div>
                </fieldset>
              ))}
            </article>
          ))}
        </section>
      )}
      <WeekFeePanel fee={shown.fee} onRefresh={refresh} />
    </div>
  );
}
