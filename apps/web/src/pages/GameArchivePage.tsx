import { Link } from "react-router-dom";
import { useGameRoute } from "../hooks/useGameRoute";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../lib/api";
import type { LeagueGames } from "../lib/twoGameTypes";
import { formatCalendarDate } from "../lib/time";
import { GamesHome } from "../components/GamesHome";
import { Button } from "../components/ui/button";
export function GameArchivePage() {
  const { league_id: leagueId } = useGameRoute("group");
  const { player } = useAuth();
  const query = useInfiniteQuery({
    queryKey: ["two-games", player?.id, leagueId, "archive"],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiFetch<LeagueGames>(
        `/api/v1/leagues/${leagueId}/games?page_size=10${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  });
  if (query.isPending) return <p role="status">Loading game history…</p>;
  if (query.isError)
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">Game history unavailable</h1>
        <p role="alert">{query.error.message}</p>
        <Button onClick={() => void query.refetch()}>Try again</Button>
        <Link to="/">Home</Link>
      </section>
    );
  const first = query.data.pages[0];
  const seen = new Set<string>();
  const archive = query.data.pages
    .flatMap((page) => [
      ...page.games
        .filter((card) => card.archived)
        .map((card) => ({
          id: card.game_id,
          destination: card.destination,
          label: `${card.game_kind === "group" ? "Saturday Group" : "Fantasy"} · ${formatCalendarDate(card.week_label, "d MMM")}`,
        })),
      ...page.legacy_rounds
        .filter((card) => card.archived)
        .map((card) => ({
          id: card.week_id,
          destination: card.destination,
          label: `Legacy round · ${formatCalendarDate(card.starts_on, "d MMM")}`,
        })),
    ])
    .filter((card) => {
      if (seen.has(card.id)) return false;
      seen.add(card.id);
      return true;
    });
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link to="/" className="underline">
        Home
      </Link>
      <h1 className="text-2xl font-semibold">{first.name} · Game archive</h1>
      {first.two_games_enabled && <GamesHome leagues={[first]} />}
      <section aria-labelledby="archived-games-heading" className="space-y-3">
        <h2 id="archived-games-heading" className="text-xl font-semibold">
          Previous games
        </h2>
        {archive.length === 0 ? (
          <p>No archived games yet.</p>
        ) : (
          <ul className="space-y-2">
            {archive.map((card) => (
              <li key={card.id}>
                <Link
                  className="inline-flex min-h-11 items-center underline"
                  to={card.destination}
                >
                  {card.label}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {query.hasNextPage && (
          <Button
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load older weeks"}
          </Button>
        )}
      </section>
    </div>
  );
}
