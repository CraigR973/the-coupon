import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "../lib/api";
import type { LeagueGames } from "../lib/twoGameTypes";
export function useHomeGames(member: string | undefined) {
  return useQuery({
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
  });
}
