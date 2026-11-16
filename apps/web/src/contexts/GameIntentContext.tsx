import { useEffect, useMemo, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./AuthContext";
import { GameIntents } from "../lib/gameIntents";
import { useHomeGames } from "../hooks/useHomeGames";
import {
  GameIntentContext,
  GameNavigationContext,
  HomeGameStatusContext,
} from "../hooks/useGameIntents";
export function GameIntentProvider({ children }: { children: ReactNode }) {
  const { player } = useAuth();
  const client = useQueryClient();
  const { data, isError, isPending, error, refetch } = useHomeGames(player?.id);
  const status = useMemo(
    () => ({
      isError,
      isLoading: isPending,
      error,
      refetch: () => {
        void refetch();
      },
    }),
    [isError, isPending, error, refetch],
  );
  const leagues = useMemo(
    () => (data?.leagues ?? []).filter((league) => league.two_games_enabled),
    [data],
  );
  const engine = useMemo(
    () =>
      new GameIntents(player?.id ?? "", {
        changed: () => {
          return client.invalidateQueries(
            {
              predicate: (query) =>
                query.queryKey[0] === "two-games" ||
                query.queryKey[0] === "me" ||
                query.queryKey[0] === "leagues" ||
                query.queryKey[0] === "league" ||
                query.queryKey[0] === "standings" ||
                query.queryKey[0] === "results",
            },
            { throwOnError: true },
          );
        },
      }),
    [player?.id, client],
  );
  useEffect(() => {
    engine.activate();
    window.addEventListener("online", engine.reconnect);
    return () => {
      window.removeEventListener("online", engine.reconnect);
      engine.dispose();
    };
  }, [engine]);
  return (
    <HomeGameStatusContext.Provider value={status}>
      <GameNavigationContext.Provider value={leagues}>
        <GameIntentContext.Provider value={engine}>
          {children}
        </GameIntentContext.Provider>
      </GameNavigationContext.Provider>
    </HomeGameStatusContext.Provider>
  );
}
