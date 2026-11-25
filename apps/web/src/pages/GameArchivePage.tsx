import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
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
  // Batch 244: the list behind the game screens' week bar. Current games keep their rows;
  // every earlier game is one tappable row, newest first, with nothing underlined.
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-1">
        <Link
          to="/"
          className="-ml-1 inline-flex min-h-11 items-center gap-1 rounded-md px-1 font-sans text-sm font-semibold text-text-secondary hover:text-text-primary focus-visible:outline-hidden focus-visible:shadow-glow"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
          Home
        </Link>
        <h1 className="font-sans text-2xl font-semibold text-text-primary">
          {first.name} · Game archive
        </h1>
      </header>
      {first.two_games_enabled && (
        <section aria-labelledby="current-games-heading" className="space-y-3">
          <h2 id="current-games-heading" className="eyebrow text-text-muted">
            Current games
          </h2>
          <GamesHome leagues={[first]} />
        </section>
      )}
      <section aria-labelledby="archived-games-heading" className="space-y-3">
        <h2
          id="archived-games-heading"
          className="font-sans text-lg font-semibold text-text-primary"
        >
          Previous games
        </h2>
        {archive.length === 0 ? (
          <p className="font-sans text-sm text-text-secondary">No archived games yet.</p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
            {archive.map((card) => (
              <li key={card.id}>
                <Link
                  className="flex min-h-11 items-center justify-between gap-3 px-4 py-3 font-sans text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
                  to={card.destination}
                >
                  {card.label}
                  <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {query.hasNextPage && (
          <Button
            variant="outline"
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
