import { Link } from "react-router-dom";
import type { LeagueGames } from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
export function GamesHome({ leagues }: { leagues: LeagueGames[] }) {
  return (
    <section aria-labelledby="your-games-heading" className="space-y-5">
      <h2 id="your-games-heading" className="text-xl font-semibold">
        Your games
      </h2>
      {leagues.map((league) => (
        <article
          key={league.league_id}
          className="rounded-xl border border-border bg-surface p-4 space-y-3"
          data-testid="two-game-home"
        >
          <h3 className="text-lg font-semibold">{league.name}</h3>
          {league.suspended && (
            <p role="status">
              Entries suspended. Results and weekly fees continue.
            </p>
          )}
          <ul className="space-y-3">
            {league.games
              .filter((card) => !card.archived)
              .map((card) => (
                <li
                  key={card.game_id}
                  className="rounded-lg border border-border p-3 space-y-1"
                >
                  <Link
                    className="inline-flex min-h-11 items-center font-semibold underline"
                    to={card.destination}
                  >
                    {card.game_kind === "group" ? "Saturday Group" : "Fantasy"}{" "}
                    · {formatCalendarDate(card.week_label, "d MMM")}
                  </Link>
                  <p>
                    {card.entry_state === "open"
                      ? "Entry open"
                      : card.entry_state === "locked"
                        ? "Locked results"
                        : card.entry_state === "not_open"
                          ? "Opening announced"
                          : card.entry_state}
                  </p>
                  <p className="text-sm">
                    {card.purpose === "upcoming" ? "Opens" : "Locks"}{" "}
                    {formatInstant(
                      card.purpose === "upcoming"
                        ? card.opens_at
                        : card.locks_at,
                      "Europe/London",
                      "EEE d MMM HH:mm",
                    )}{" "}
                    London.
                  </p>
                  {card.game_kind === "group" ? (
                    <p>
                      {card.progress.picked_count ?? 0} of{" "}
                      {card.progress.member_count ?? 0} contributed ·{" "}
                      {card.result.status === "no_coupon"
                        ? "No coupon"
                        : card.result.status}
                    </p>
                  ) : (
                    <p>
                      {card.progress.slots_filled ?? 0} of 6 slots ·{" "}
                      {card.result.weekly_points ?? 0} weekly points
                      {card.result.provisional ? " · Provisional" : ""}
                    </p>
                  )}
                  <Link
                    className="inline-flex min-h-11 items-center underline text-sm"
                    to={card.fee.destination}
                  >
                    {card.fee.paid_through
                      ? "Paid through this week"
                      : `£${(card.fee.amount_owed_pence / 100).toFixed(2)} owed through this week`}
                  </Link>
                </li>
              ))}
            {league.legacy_rounds
              .filter((card) => !card.archived)
              .map((card) => (
                <li key={card.week_id}>
                  <Link
                    className="inline-flex min-h-11 items-center underline"
                    to={card.destination}
                  >
                    Legacy round · {formatCalendarDate(card.starts_on, "d MMM")}
                  </Link>
                  <p>
                    {card.can_pick ? "Entry open" : "Locked results"} ·{" "}
                    {formatInstant(
                      card.locks_at,
                      "Europe/London",
                      "EEE d MMM HH:mm",
                    )}{" "}
                    London.
                  </p>
                </li>
              ))}
          </ul>
          {league.next_game_state === "pending" && (
            <p className="text-sm">
              Next fantasy opening is pending confirmation.
            </p>
          )}
          <Link
            className="inline-flex min-h-11 items-center underline"
            to={`/leagues/${league.league_id}/games`}
          >
            Game archive
          </Link>
        </article>
      ))}
    </section>
  );
}
