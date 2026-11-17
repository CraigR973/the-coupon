import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "../lib/api";
import type { LeagueGames } from "../lib/twoGameTypes";
export function useHomeGames(member: string | undefined) {
  const query = useQuery({
    queryKey: ["two-games", member, "home"],
    queryFn: async () => {
      try {
        return await apiFetch<{ leagues?: LeagueGames[] }>("/api/v1/me/games");
      } catch (error) {
        if (error instanceof ApiError && error.status === 404)
          return { leagues: [] };
        throw error;
      }
    },
    enabled: !!member,
    staleTime: 15_000,
    retry: false,
    refetchInterval: (current) =>
      current.state.data?.leagues?.some((league) => league.two_games_enabled)
        ? 30_000
        : false,
  });
  const { data, refetch, dataUpdatedAt } = query;
  useEffect(() => {
    const now = Date.now();
    const boundaries = (data?.leagues ?? [])
      .filter((league) => league.two_games_enabled)
      .flatMap((league) =>
        league.games.flatMap((game) => [game.opens_at, game.locks_at]),
      )
      .map((value) => new Date(value).getTime())
      .filter((value) => Number.isFinite(value) && value > now);
    if (!boundaries.length) return;
    const timer = window.setTimeout(
      () => {
        void refetch();
      },
      Math.min(Math.min(...boundaries) - now, 86_400_000),
    );
    return () => window.clearTimeout(timer);
  }, [data, refetch, dataUpdatedAt]);
  return query;
}
