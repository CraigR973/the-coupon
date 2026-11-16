import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useLeague } from "../contexts/LeagueContext";
import type { GameKind, GameTarget } from "../lib/twoGameTypes";
export function useGameRoute(game_kind: GameKind): GameTarget {
  const { leagueId = "", weekId = "" } = useParams<{
    leagueId: string;
    weekId: string;
  }>();
  const { leagues, selectLeague } = useLeague();
  const slug = leagues.find((league) => league.id === leagueId)?.slug;
  useEffect(() => {
    if (slug) selectLeague(slug);
  }, [slug, selectLeague]);
  return { league_id: leagueId, week_id: weekId, game_kind };
}
