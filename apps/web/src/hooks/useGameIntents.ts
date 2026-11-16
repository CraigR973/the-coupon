import { createContext, useContext, useSyncExternalStore } from "react";
import type { GameIntents } from "../lib/gameIntents";
import type { LeagueGames } from "../lib/twoGameTypes";
export const GameIntentContext = createContext<GameIntents | null>(null);
export const GameNavigationContext = createContext<LeagueGames[]>([]);
export const HomeGameStatusContext = createContext({
  isError: false,
  isLoading: false,
  error: null as Error | null,
  refetch: () => {},
});
export const useGameNavigation = () => useContext(GameNavigationContext);
export const useHomeGameStatus = () => useContext(HomeGameStatusContext);
export function useGameIntents() {
  const engine = useContext(GameIntentContext);
  if (!engine) throw new Error("Game intents require the authenticated shell");
  const intents = useSyncExternalStore(
    engine.subscribe,
    engine.getSnapshot,
    engine.getSnapshot,
  );
  return { engine, intents };
}
