import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useGameRoute } from "../hooks/useGameRoute";
import { apiFetch } from "../lib/api";
import { gameQueryKey, type GameCard } from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { WeekFeePanel } from "../components/WeekFeePanel";
/** Read-only addressed landing; the separate slot-editor batch adds entry controls. */
export function FantasyWeekPage() {
  const target = useGameRoute("fantasy");
  const { player } = useAuth();
  const query = useQuery({
    queryKey: gameQueryKey(player?.id ?? "", target),
    queryFn: () =>
      apiFetch<{ fantasy: GameCard | null }>(
        `/api/v1/leagues/${target.league_id}/weeks/${target.week_id}/results`,
      ),
    retry: false,
  });
  if (query.isPending) return <p role="status">Loading this Fantasy week…</p>;
  if (query.isError || !query.data.fantasy)
    return (
      <section>
        <h1>Fantasy week unavailable</h1>
        <Link to="/">Home</Link>
      </section>
    );
  const card = query.data.fantasy;
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link to="/" className="underline">
        Home
      </Link>
      <h1 className="text-2xl font-semibold">
        Fantasy · {formatCalendarDate(card.week_label, "d MMM")}
      </h1>
      <p>
        Locks {formatInstant(card.locks_at, "Europe/London", "EEE d MMM HH:mm")}{" "}
        London.
      </p>
      <p>
        {card.result.weekly_points ?? 0} weekly points ·{" "}
        {card.result.provisional ? "Provisional" : "Final"}
      </p>
      <p>Fantasy entry controls are unavailable in this version.</p>
      <WeekFeePanel fee={card.fee} onRefresh={() => void query.refetch()} />
    </div>
  );
}
