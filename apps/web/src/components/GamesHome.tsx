import { Link } from "react-router-dom";
import type { LeagueGames } from "../lib/twoGameTypes";
import { formatCalendarDate, formatInstant } from "../lib/time";
import { useOddsFormat } from "../hooks/useOddsFormat";
import { formatOdds, marketTag, pickStatusLabel } from "../lib/coupon";
/**
 * A two-game league's entries, as rows inside its home card: each game's link, state,
 * deadline, progress and weekly fee, then any legacy round still in play.
 *
 * Batch 239 moved these rows into the league's own card on home, the old card's frame
 * around them (`DashboardPage`'s `TwoGameLeagueCard`), so this renders the rows alone.
 * The group row also says whether the member's own pick is in, which is the action the
 * card exists to prompt; the fantasy row's "N of 6 slots" already does.
 */
export function GamesHome({ leagues }: { leagues: LeagueGames[] }) {
  return (
    <>
      {leagues.map((league) => (
        <div key={league.league_id} className="space-y-3">
          <ul className="space-y-3">
            {league.games
              .filter((card) => !card.archived)
              .map((card) => (
                <li
                  key={card.game_id}
                  className="rounded-lg border border-border bg-surface p-3 space-y-1 font-sans text-sm text-text-secondary"
                >
                  <Link
                    className="inline-flex min-h-11 items-center text-base font-semibold text-text-primary hover:text-primary focus-visible:outline-hidden focus-visible:shadow-glow"
                    to={card.destination}
                  >
                    {card.game_kind === "group" ? "Saturday Group" : "Fantasy"}{" "}
                    · {formatCalendarDate(card.week_label, "d MMM")}
                  </Link>
                  <p className="font-medium text-text-primary">
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
                    <>
                      {card.entry_state === "open" &&
                        (card.my_entry?.pick ? (
                          <p className="font-sans text-sm text-text-primary">
                            Your pick: {card.my_entry.pick.runner_name}
                          </p>
                        ) : (
                          <p className="font-sans text-base font-medium text-warning">
                            Group pick needed
                          </p>
                        ))}
                      <p>
                        {card.progress.picked_count ?? 0} of{" "}
                        {card.progress.member_count ?? 0} contributed ·{" "}
                        {card.result.status === "no_coupon"
                          ? "No coupon"
                          : card.result.status}
                      </p>
                    </>
                  ) : (
                    <p>
                      {card.progress.slots_filled ?? 0} of 6 slots ·{" "}
                      {card.result.weekly_points ?? 0} weekly points
                      {card.result.provisional ? " · Provisional" : ""}
                    </p>
                  )}
                  <Link
                    className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-hidden focus-visible:shadow-glow"
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
                <LegacyRoundItem key={card.week_id} card={card} serverNow={league.server_now} />
              ))}
          </ul>
          {league.next_game_state === "pending" && (
            <p className="text-sm">
              Next fantasy opening is pending confirmation.
            </p>
          )}
        </div>
      ))}
    </>
  );
}

/**
 * One legacy round as a row (Batch 239), shared by the archive and, while a league that has
 * switched still has a legacy round in play, by Home's week card (Batch 243).
 */
export function LegacyRoundItem({
  card,
  serverNow,
}: {
  card: LeagueGames["legacy_rounds"][number];
  serverNow: string;
}) {
  const oddsFormat = useOddsFormat();
  return (
    <li className="rounded-lg border border-border bg-surface p-3 space-y-1 font-sans text-sm text-text-secondary">
      <Link
        className="inline-flex min-h-11 items-center text-base font-semibold text-text-primary hover:text-primary focus-visible:outline-hidden focus-visible:shadow-glow"
        to={card.destination}
      >
        Legacy round · {formatCalendarDate(card.starts_on, "d MMM")}
      </Link>
      <p className="font-medium text-text-primary">
        {card.status === "cancelled"
          ? "Cancelled"
          : card.status === "settled"
            ? "Settled results"
            : card.picks_open_at && new Date(serverNow) < new Date(card.picks_open_at)
              ? "Entry has not opened"
              : card.can_pick ? "Entry open" : "Locked results"}
      </p>
      {card.picks_open_at && (
        <p className="text-sm">
          Opens {formatInstant(card.picks_open_at, "Europe/London", "EEE d MMM HH:mm")} London.
        </p>
      )}
      <p className="text-sm">
        Locks{" "}
        {formatInstant(
          card.locks_at,
          "Europe/London",
          "EEE d MMM HH:mm",
        )}{" "}
        London.
      </p>
      {card.my_pick ? (
        <p>
          Your pick: {card.my_pick.runner_name} · {marketTag(card.my_pick.market)} · Frozen odds {formatOdds(Number(card.my_pick.odds), oddsFormat)}
          {card.my_pick.result !== "pending" && ` · ${pickStatusLabel(card.my_pick.result)} · ${card.my_pick.points ?? 0} points`}
        </p>
      ) : <p>No selection saved.</p>}
      <p>
        {card.fee
          ? `£${(card.fee.entry_fee_pence / 100).toFixed(2)} per legacy round · ${card.fee.owed_pence === 0 ? "Paid through this round" : `£${(card.fee.owed_pence / 100).toFixed(2)} owed through this round`}`
          : "No legacy entry fee required."}
      </p>
    </li>
  );
}
