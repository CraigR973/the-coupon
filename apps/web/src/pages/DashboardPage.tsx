import { Link, useNavigate } from 'react-router-dom';
import { useGameNavigation,useHomeGameStatus } from '../hooks/useGameIntents';
import { LegacyRoundItem } from '../components/GamesHome';
import { ArrowRight, Check, ChevronRight, Clock, Lock, Ticket, Trophy } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { type CountdownParts } from '../hooks/useCountdown';
import { useCrossLeagueSummary } from '../hooks/useCrossLeagueSummary';
import { useOddsFormat } from '../hooks/useOddsFormat';
import type {
  CrossLeagueSummary,
  FormRound,
  GameweekStatus,
  MyPick,
  OddsFormat,
  PerLeagueSummary,
} from '../lib/types';
import type { GameCard, LeagueGames } from '../lib/twoGameTypes';
import {
  fixtureContext,
  formatCombinedOdds,
  formatOdds,
  outcomeLabel,
  roundName,
} from '../lib/coupon';
import {
  HOME_CARD_STATE,
  type HomeCardState,
  type TwoGameWeekResult,
  homeCardState,
  homeWeek,
  lastTwoGameWeek,
  showsCouponFigures,
  twoGameEntryFacts,
} from '../lib/home';
import { predictionsPath } from '../lib/leagues';
import { formatCalendarDate, formatInstant, parseInstant } from '../lib/time';
import { PickFormLine } from '../components/PickFormLine';
import { EmptyState } from '../components/EmptyState';
import { QueryErrorState } from '../components/QueryErrorState';
import { StatCard } from '../components/StatCard';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';
import { useExpiry } from '@/hooks/useExpiry';
import { Countdown } from '@/components/Countdown';

const FAR_PAST = new Date(0).toISOString();

/** The hero's season figures as a flat row, not tiles (Batch 243). */
const SEASON_FIGURE = 'border-0 bg-transparent px-0 py-0 shadow-none sm:px-0';

/** The two states a round can still be claimed in — settlement has finished with the rest. */
const PICKABLE: ReadonlySet<GameweekStatus> = new Set(['scheduled', 'open']);

type HomeAction =
  | { kind: 'pick'; count: number; slug: string; league: string; at: string; to: string }
  | {
      kind: 'upcoming';
      slug: string;
      league: string;
      at: string;
      to: string;
      openPicksReady: boolean;
    }
  | { kind: 'clear'; openPicksReady: boolean };

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return 'Locked';
  if (p.days > 0) return `${p.days}d ${p.hours}h`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m`;
  return `${p.minutes}m ${p.seconds}s`;
}

/**
 * The next thing that needs the member across independent league windows.
 * A league is actionable only while its own stored opening/lock instants permit
 * a pick; backend order is alphabetical, so the action is explicitly sorted by
 * the deadline instead.
 *
 * Batch 239: a two-game league answers from its own games (`games`), never from the
 * summary's `current_round`, which on such a league is the last legacy round. It counts
 * once however many of its entries are open, and the hero's link goes to the entry that
 * locks first rather than to a legacy coupon the league no longer plays.
 */
function homeActionFor(
  leagues: PerLeagueSummary[],
  games: LeagueGames[] = [],
  now = Date.now(),
): HomeAction {
  const twoGame = new Set(games.map((league) => league.slug));
  const legacy = leagues.filter((entry) => !twoGame.has(entry.slug));
  const facts = games.map((league) => ({ league, facts: twoGameEntryFacts(league, now) }));
  const needsPick = [
    ...legacy.flatMap((entry) => {
      const round = entry.current_round;
      if (!round || round.my_pick || !PICKABLE.has(round.status)) return [];
      const opensAt = round.picks_open_at_utc
        ? parseInstant(round.picks_open_at_utc).getTime()
        : null;
      const locksAt = parseInstant(round.locks_at_utc).getTime();
      if ((opensAt !== null && opensAt > now) || !Number.isFinite(locksAt) || locksAt <= now) {
        return [];
      }
      return [
        {
          slug: entry.slug,
          league: entry.name,
          at: round.locks_at_utc,
          locksAt,
          to: predictionsPath(entry.slug),
        },
      ];
    }),
    ...facts.flatMap(({ league, facts: { needs } }) =>
      needs.length > 0
        ? [
            {
              slug: league.slug,
              league: league.name,
              at: needs[0]!.locksAt,
              locksAt: parseInstant(needs[0]!.locksAt).getTime(),
              to: needs[0]!.destination,
            },
          ]
        : [],
    ),
  ].sort((a, b) => a.locksAt - b.locksAt);

  if (needsPick.length > 0) {
    const first = needsPick[0]!;
    return {
      kind: 'pick',
      count: needsPick.length,
      slug: first.slug,
      league: first.league,
      at: first.at,
      to: first.to,
    };
  }

  const openPicksReady =
    legacy.some((entry) => {
      const round = entry.current_round;
      if (!round?.my_pick || !PICKABLE.has(round.status)) return false;
      const opensAt = round.picks_open_at_utc
        ? parseInstant(round.picks_open_at_utc).getTime()
        : null;
      const locksAt = parseInstant(round.locks_at_utc).getTime();
      return (opensAt === null || opensAt <= now) && Number.isFinite(locksAt) && locksAt > now;
    }) || facts.some(({ facts: { ready } }) => ready.length > 0);

  const upcoming = [
    ...legacy.flatMap((entry) => {
      const roundOpensAt = entry.current_round?.picks_open_at_utc;
      const candidates = [roundOpensAt, entry.next_opens_at_utc]
        .filter((value): value is string => !!value)
        .map((at) => ({ at, timestamp: parseInstant(at).getTime() }))
        .filter(({ timestamp }) => Number.isFinite(timestamp) && timestamp > now)
        .sort((a, b) => a.timestamp - b.timestamp);
      return candidates.length > 0
        ? [
            {
              slug: entry.slug,
              league: entry.name,
              at: candidates[0]!.at,
              timestamp: candidates[0]!.timestamp,
              to: predictionsPath(entry.slug),
            },
          ]
        : [];
    }),
    ...facts.flatMap(({ league, facts: { next } }) =>
      next
        ? [
            {
              slug: league.slug,
              league: league.name,
              at: next.opensAt,
              timestamp: parseInstant(next.opensAt).getTime(),
              to: next.destination,
            },
          ]
        : [],
    ),
  ].sort((a, b) => a.timestamp - b.timestamp);

  if (upcoming.length > 0) {
    const first = upcoming[0]!;
    return {
      kind: 'upcoming',
      slug: first.slug,
      league: first.league,
      at: first.at,
      to: first.to,
      openPicksReady,
    };
  }

  return { kind: 'clear', openPicksReady };
}

/**
 * Home, once per league.
 *
 * It used to answer for `activeSlug` alone — one pick, one coupon peek, one
 * standings card — which is the wrong question for a member in three leagues:
 * two of their weeks were invisible until they switched. Every league the member
 * plays now gets a card carrying that league's pick and standing, and one tap
 * opens that league's coupon. The whole page is one request
 * (`GET /me/cross-league-summary`), not three per league.
 *
 * Batch 239 brought this page back for two-game leagues, which had been given a plain
 * greeting and a "Your games" list of their own. The hero and every league's card are
 * the old ones again, in one list; a two-game league's card is the old frame around that
 * league's entries (`TwoGameLeagueCard`). Which leagues play two games is known only once
 * `/me/games` answers, so the cards and the hero's next action wait for it as well as for
 * the summary, rather than drawing a two-game league as a legacy card for a moment.
 */
export function DashboardPage() {
  const { player } = useAuth();

  const { data, isLoading: summaryLoading, isError, refetch } = useCrossLeagueSummary();
  const games = useGameNavigation();
  const gameStatus = useHomeGameStatus();
  const isLoading = summaryLoading || gameStatus.isLoading;
  const gamesBySlug = new Map(games.map((league) => [league.slug, league]));
  const leagues = isLoading ? [] : (data?.per_league ?? []);
  // A two-game league the summary does not list — it failed, or has not caught up with a
  // join — still gets its card, from its games alone.
  const unlisted = isLoading
    ? []
    : games.filter((league) => !leagues.some((entry) => entry.slug === league.slug));
  const cardCount = leagues.length + unlisted.length;

  return (
    <div className="relative">
      <div className="space-y-6">
        <HomeHero
          displayName={player?.displayName ?? 'there'}
          timezone={player?.timezone}
          summary={gameStatus.isLoading ? undefined : data}
          games={games}
          isLoading={isLoading}
        />
        {gameStatus.isError && (
          <QueryErrorState
            title="Couldn't load game status"
            description="Your existing league history remains available."
            onRetry={gameStatus.refetch}
          />
        )}

        {isLoading && (
          <div className="flex flex-col gap-5" aria-label="Loading your leagues">
            <HomeLeagueLoadingCard />
            <HomeLeagueLoadingCard />
          </div>
        )}

        {isError && (
          <QueryErrorState
            title="Couldn't load your leagues"
            description="Please try again shortly."
            onRetry={() => void refetch()}
          />
        )}

        {!isLoading && !isError && cardCount === 0 && !gameStatus.isError && (
          <FirstLeaguePrompt />
        )}

        {cardCount > 0 && (
          <section aria-labelledby="home-leagues-heading">
            <div className="mb-3 flex items-end justify-between gap-3 px-1">
              <h2
                id="home-leagues-heading"
                className="font-sans text-lg font-semibold tracking-tight text-text-primary"
              >
                Your leagues
              </h2>
              <p className="eyebrow text-text-muted">
                {cardCount} in play
              </p>
            </div>
            <ul className="flex flex-col gap-5" data-testid="home-league-cards">
              {leagues.map((entry) => {
                const league = gamesBySlug.get(entry.slug);
                return (
                  <li key={entry.slug}>
                    {league ? (
                      <TwoGameLeagueCard league={league} entry={entry} />
                    ) : (
                      <LeagueHomeCard entry={entry} />
                    )}
                  </li>
                );
              })}
              {unlisted.map((league) => (
                <li key={league.slug}>
                  <TwoGameLeagueCard league={league} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function HomeLeagueLoadingCard() {
  return (
    <div
      className="rounded-xl border border-border bg-surface p-5 shadow-sm"
      data-testid="home-league-loading-card"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-2/3 max-w-56" />
        </div>
        <Skeleton className="h-7 w-16 rounded-full" />
      </div>
      <Skeleton className="mt-5 h-4 w-full max-w-md" />
      <Skeleton className="mt-3 h-11 w-full rounded-md" />
    </div>
  );
}

/**
 * A first-run member has no league card to make the home screen useful yet. The prompt
 * gives that state its own primary action and explains the path without borrowing any
 * of the populated home's stats, deadlines, or cross-league data.
 */
function FirstLeaguePrompt() {
  return (
    <section
      className="space-y-5"
      aria-labelledby="home-first-league-heading"
      data-testid="home-first-league"
    >
      <EmptyState
        icon={<Trophy />}
        title="You're not in a league yet"
        description="Find a league to follow its picks, results and standings from here."
        className="border-solid bg-surface px-5 py-8 shadow-sm"
        action={
          <div className="flex w-full max-w-sm flex-col gap-3">
            <Button asChild size="lg" className="w-full">
              <Link to="/leagues/discover">
                Find a league
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </Button>
            <Button asChild variant="outline" className="w-full">
              <Link to="/leagues/join">Join by code</Link>
            </Button>
          </div>
        }
      />

      <div className="rounded-xl border border-border bg-surface p-5 shadow-sm">
        <p className="eyebrow text-primary">
          Your first round
        </p>
        <h2
          id="home-first-league-heading"
          className="mt-2 font-sans text-lg font-semibold tracking-tight text-text-primary"
        >
          Everything starts with a league
        </h2>
        <ol className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3" aria-label="How a Coupon league works">
          <li className="rounded-lg border border-border bg-surface-elevated px-3 py-3">
            <span className="font-mono text-caption text-text-primary">01</span>
            <p className="mt-1 font-sans text-sm font-semibold text-text-primary">Find your group</p>
          </li>
          <li className="rounded-lg border border-border bg-surface-elevated px-3 py-3">
            <span className="font-mono text-caption text-text-primary">02</span>
            <p className="mt-1 font-sans text-sm font-semibold text-text-primary">Make one pick</p>
          </li>
          <li className="rounded-lg border border-border bg-surface-elevated px-3 py-3">
            <span className="font-mono text-caption text-text-primary">03</span>
            <p className="mt-1 font-sans text-sm font-semibold text-text-primary">See the result</p>
          </li>
        </ol>
      </div>
    </section>
  );
}

/**
 * The one altitude home did not have: how the member's season is going across
 * every league. The cards below still own each deadline and pick; this hero uses
 * the aggregate fields already returned in the same response, so it adds no
 * request and does not flatten ranks that only make sense inside one league.
 */
function HomeHero({
  displayName,
  timezone,
  summary,
  games,
  isLoading,
}: {
  displayName: string;
  timezone?: string;
  summary?: CrossLeagueSummary;
  games: LeagueGames[];
  isLoading: boolean;
}) {
  const leagueCount = summary?.leagues_count ?? 0;
  const action = homeActionFor(summary?.per_league ?? [], games);
  // Batch 165: only the digits tick, not this card.

  return (
    <section
      className="relative overflow-hidden rounded-2xl border border-border bg-surface px-5 py-5 shadow-md sm:px-7 sm:py-6"
      data-testid="home-hero"
      aria-labelledby="home-heading"
    >
      {/*
        Batch 106. These were two `blur-3xl` circles hung outside the hero's edges and left
        to `overflow-hidden` to contain them, which is not something every engine does: a
        `filter` gives a child its own rendering context, and WebKit lets such a child paint
        past the parent's *rounded* corners even while the straight edges clip. The result
        on Safari was a coloured bloom sitting outside the hero's top-right and bottom-left
        corners.

        The fix removes the disagreement rather than patching around it. The glows are now
        radial gradients painted as this layer's own background, and a background is clipped
        by `border-radius` in every engine because there is no separate rendering context to
        escape from — no filter, nothing hanging outside the box. `overflow-hidden` and the
        matching `clip-path` stay as a second and third line, so a future change that
        reintroduces a filtered child is still contained.
      */}
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl [clip-path:inset(0_round_var(--radius-2xl))]"
        style={{
          backgroundImage:
            'radial-gradient(220px 190px at 108% -12%, var(--primary-glow), transparent 68%), radial-gradient(240px 210px at -12% 112%, var(--accent-glow), transparent 68%)',
        }}
        aria-hidden
        data-testid="home-hero-glows"
      />

      <div className="relative">
        {/* Batch 243: the date, not the brand again (the top bar carries it). */}
        <p className="eyebrow text-primary">
          {formatInstant(new Date().toISOString(), timezone ?? 'Europe/London', 'EEEE d MMM') ??
            'Your season'}
        </p>
        <h1
          id="home-heading"
          className="mt-1 font-sans text-2xl font-semibold leading-tight tracking-tight text-text-primary sm:text-3xl"
        >
          Hi {displayName}
        </h1>
        {!summary ? (
          <p className="mt-2 max-w-md font-sans text-sm leading-relaxed text-text-secondary">
            Your picks, deadlines and results — all in one place.
          </p>
        ) : leagueCount === 0 ? (
          <p className="mt-2 max-w-md font-sans text-sm leading-relaxed text-text-secondary">
            Your picks, deadlines and results — together when your first league begins.
          </p>
        ) : (
          <div className="mt-2">
            <div data-testid="home-next-action">
              <p className="font-sans text-base font-semibold leading-snug text-text-primary">
                {action.kind === 'pick'
                  ? `${action.count} ${action.count === 1 ? 'league needs' : 'leagues need'} a pick`
                  : action.openPicksReady
                    ? 'All open picks are in'
                    : action.kind === 'upcoming'
                      ? 'Nothing needs you yet'
                      : 'You’re all caught up'}
              </p>
              {action.kind !== 'clear' && (
                <Link
                  to={action.to}
                  className="mt-1 inline-flex items-center gap-1.5 rounded-sm font-sans text-sm text-primary underline-offset-4 hover:underline focus-visible:outline-hidden focus-visible:shadow-glow"
                >
                  <span>
                    {action.league}{' '}
                    {action.kind === 'pick' ? 'locks' : 'opens'} in{' '}
                    <Countdown target={action.at} format={formatCountdown} />
                  </span>
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
              )}
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="mt-4 grid grid-cols-3 gap-3" aria-label="Loading your season summary">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-[40px] rounded-lg" />
            ))}
          </div>
        ) : summary && leagueCount > 0 ? (
          // Batch 243: one quiet row across leagues rather than three boxed tiles; each
          // league's own position and points are on its card below.
          <dl
            className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3"
            aria-label="Your season at a glance"
            data-testid="home-season-summary"
          >
            <StatCard
              compact
              definition
              className={SEASON_FIGURE}
              label="Points"
              value={summary.total_points}
            />
            <StatCard
              compact
              definition
              className={SEASON_FIGURE}
              label="Picks won"
              value={`${summary.picks_won}/${summary.picks_played}`}
            />
            <StatCard
              compact
              definition
              className={SEASON_FIGURE}
              label="Win rate"
              value={summary.win_rate_pct === null ? '—' : `${summary.win_rate_pct}%`}
            />
          </dl>
        ) : null}
      </div>
    </section>
  );
}

/**
 * One league's card: its state, its next action, and — separately and under its own
 * heading — how its last round went.
 *
 * Batch 106. The card used to be a stack of whatever fields were present, in the order
 * they happened to be written, and on the commonest Sunday shape that produced a lie: a
 * settled round's pick, fold and combined odds printed as the body, with `Next opens in
 * 2d` beside them. Two rounds, one paragraph, and only the clock said which was which.
 *
 * The state now decides. `homeCardState` names it, the primary part of the card carries
 * only what that state's next action needs, and everything about the round just gone lives
 * below under `Last result`. Every input is this league's own — its window, its round, its
 * members — because a member in three leagues is playing three different weeks.
 */
function LeagueHomeCard({ entry }: { entry: PerLeagueSummary }) {
  const oddsFormat = useOddsFormat();
  const navigate = useNavigate();
  const round = entry.current_round;
  // Batch 165. Three ticking clocks in one card, on a screen that renders one card per
  // league — so a member in three leagues re-rendered nine subtrees a second to read
  // three booleans. `useExpiry` fires once at each boundary instead.
  const lockPassed = useExpiry(round?.locks_at_utc ?? FAR_PAST);
  const openPassed = useExpiry(round?.picks_open_at_utc ?? FAR_PAST);
  // The *next* round's opening, which is a different instant to this round's: once a
  // round has settled or locked there is nothing left to count down to on it, and "when
  // does the next one open" is the question a member has on a Sunday.
  const nextOpenPassed = useExpiry(entry.next_opens_at_utc ?? FAR_PAST);
  const nextOpens = !!entry.next_opens_at_utc && !nextOpenPassed;
  // Same rule as the pick screen and the API: the stored instants decide, `status` only
  // rules out a round settlement has finished with.
  const notOpenYet =
    !!round?.picks_open_at_utc && !openPassed && PICKABLE.has(round.status);
  const claimingShut = !round || !PICKABLE.has(round.status) || lockPassed;

  const state = homeCardState({
    hasRound: !!round,
    settled: round?.status === 'settled',
    notOpenYet,
    claimingShut,
    mine: !!round?.my_pick,
  });
  const { label: stateLabel, variant: stateVariant } = HOME_CARD_STATE[state];
  const showFigures = showsCouponFigures(state) && !!round && round.leg_count > 0;
  const lastRound = lastRoundView(entry);
  // The card names its round only while it is *about* it. `between_rounds` covers two
  // shapes: a round whose picks have not opened, where the clock counts down to that
  // round's own opening and naming it is the point; and a settled round, where the clock
  // is already counting the *next* one and `Last result` below names the settled one.
  const namesRound = state !== 'between_rounds' || notOpenYet;

  // The clock belongs to whichever round the state is about — this one while it is live,
  // the next one once this one is done with. They are never both on screen.
  const clock =
    state === 'between_rounds'
      ? notOpenYet
        ? <>Opens in <Countdown target={round!.picks_open_at_utc!} format={formatCountdown} /></>
        : nextOpens
          ? <>Next opens in <Countdown target={entry.next_opens_at_utc!} format={formatCountdown} /></>
          : null
      : state === 'round_in_progress'
        ? 'Locked'
        : <>Locks in <Countdown target={round!.locks_at_utc} format={formatCountdown} /></>;

  // The coupon has its own address per league now, so opening another league's
  // week is just going there: the destination binds the context, rather than this
  // card having to bind it before navigating and hope the two agree.
  function openCoupon() {
    navigate(predictionsPath(entry.slug));
  }

  return (
    <div className="rounded-xl border border-border bg-surface shadow-sm" data-testid={`home-card-${entry.slug}`}>
      <button
        type="button"
        onClick={openCoupon}
        className="w-full rounded-t-xl p-5 text-left transition-colors press-down hover:border-primary/50 hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <Ticket className="h-5 w-5 shrink-0 text-primary" aria-hidden />
            <p className="truncate font-sans text-base font-semibold text-text-primary">{entry.name}</p>
          </div>
          <ArrowRight className="h-5 w-5 shrink-0 text-text-muted" aria-hidden />
        </div>

        {/* Batch 117. The card above `Last result` named no round at all, so home said
            "Last result · Gameweek 4" over a live card the member could not identify —
            the only thing on the screen they might still act on. Printed exactly when the
            body and the clock are about *this* round: a settled card's clock counts down
            to the next round's opening, and `Last result` below already names that one. */}
        {namesRound && round && (
          <p
            className="mb-2 truncate eyebrow text-text-muted"
            data-testid={`home-round-${entry.slug}`}
          >
            {roundName(
              round.number,
              formatCalendarDate(round.starts_on, 'EEE d MMM'),
              round.season_week,
            )}
          </p>
        )}

        <div
          className="mb-3 flex flex-wrap items-center justify-between gap-2"
          data-testid={`home-state-${entry.slug}`}
        >
          <Badge variant={stateVariant}>{stateLabel}</Badge>
          {clock && (
            <span className="flex items-center gap-1.5 font-sans text-xs tabular-nums text-text-secondary">
              {state === 'round_in_progress' ? (
                <Lock className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Clock className="h-3.5 w-3.5" aria-hidden />
              )}
              {clock}
            </span>
          )}
        </div>

        {state === 'between_rounds' ? (
          <p className="font-sans text-sm leading-relaxed text-text-muted">
            {notOpenYet
              ? 'Picks haven’t opened yet'
              : entry.next_opens_at_utc
                ? `Next round opens ${formatInstant(entry.next_opens_at_utc, 'UTC', 'EEE d MMM') ?? 'soon'}`
                : round
                  ? 'Nothing to pick right now'
                  : 'No coupon published yet'}
          </p>
        ) : round?.my_pick ? (
          <MyPickLine pick={round.my_pick} oddsFormat={oddsFormat} />
        ) : (
          <p className="font-sans text-base font-medium text-warning">
            {state === 'round_in_progress'
              ? 'No pick made this round'
              : 'You haven’t grabbed a selection yet'}
          </p>
        )}

        {round && state !== 'between_rounds' && (
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-text-muted">
            {/* This league's progress, from this league's own member count — the number a
                member actually asks for while a deadline is running. */}
            <span className="tabular-nums" data-testid={`home-progress-${entry.slug}`}>
              {round.leg_count} of {entry.member_count} picked
            </span>
            {showFigures && (
              <span className="tabular-nums">
                {/* Batch 186: the fold counts the legs the price is a product of, as the
                    coupon's does — a voided leg is on the coupon but not in the price. */}
                {round.leg_count - (round.void_leg_count ?? 0)}-fold ·{' '}
                {formatCombinedOdds(round.combined_odds, oddsFormat)}
              </span>
            )}
          </div>
        )}
      </button>

      {lastRound && <LastResultPanel round={lastRound} form={entry.recent_form} />}

      <Link
        to={`/leagues/${entry.slug}/leaderboard`}
        className="flex items-center justify-between gap-3 rounded-b-xl border-t border-border px-5 py-3.5 transition-colors hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <span className="flex items-center gap-2 eyebrow text-text-muted sm:text-xs">
          <Trophy className="h-4 w-4 text-primary" aria-hidden />
          Standings
        </span>
        <span className="font-mono text-sm tabular-nums text-text-secondary">
          <span className={cn(entry.rank === 1 && 'font-semibold text-primary')}>
            {entry.rank === null ? '—' : `#${entry.rank}`}
          </span>
          <span className="mx-1.5 text-text-muted">of {entry.member_count}</span>
          <span className="text-text-muted">·</span>
          <span className="ml-1.5">{entry.total_points} pts</span>
        </span>
      </Link>
    </div>
  );
}

const GAME_NAME: Record<GameCard['game_kind'], string> = {
  group: 'Saturday Group',
  fantasy: 'Fantasy',
};

const money = (pence: number) =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(pence / 100);

/** "£1" rather than "£1.00" when the amount is whole pounds. */
const shortMoney = (pence: number) => (pence % 100 === 0 ? `£${pence / 100}` : money(pence));

/** How a locked week's coupon stands, in plain words. */
function couponStatus(card: GameCard): string {
  switch (card.result.status) {
    case 'won':
      return 'Coupon won';
    case 'lost':
      return 'Coupon lost';
    case 'void':
      return 'Coupon void';
    case 'no_coupon':
      return 'No coupon this week';
    default:
      return 'Coupon in play';
  }
}

/** Whether a game takes entries now, by its own state and this device's clock. */
function isOpenNow(card: GameCard, now: number): boolean {
  return card.entry_state === 'open' && parseInstant(card.locks_at).getTime() > now;
}

function isUpcoming(card: GameCard, now: number): boolean {
  return card.purpose === 'upcoming' && parseInstant(card.opens_at).getTime() > now;
}

/**
 * A two-game league's card (Batch 243): one football week at a time, then the season.
 *
 * The week comes first: the deadline that matters next as a countdown, the week's two
 * games as rows, the £1 once, and one button for the most urgent thing. Next week's
 * Fantasy, open from Saturday noon, is one line until this week's results are final
 * (`homeWeek`). The season follows: the standings line, the last result with the run of
 * five, and the archive link. The figures are the league's own season table from the
 * summary; `entry` is absent when the summary is, and the card then falls back to the
 * season figures `/me/games` carries.
 *
 * Batch 239 drew every entry of every week as an equal box with an underlined title, the
 * deadline in three places and the fee once per box. Test ids, link names and the
 * phrases the journeys read ("Group pick needed", "N of 6 slots") are kept on purpose.
 *
 * Nothing on it fades (`transition-none`): the journeys flip the theme and scan at once,
 * and a chip or link caught mid-fade reads as a contrast failure.
 */
function TwoGameLeagueCard({ league, entry }: { league: LeagueGames; entry?: PerLeagueSummary }) {
  const facts = twoGameEntryFacts(league);
  const deadline = facts.needs[0] ?? facts.ready[0];
  // Re-draw at the boundary the state hangs on: the soonest lock, else the next opening.
  useExpiry(deadline?.locksAt ?? facts.next?.opensAt ?? FAR_PAST);
  const state: HomeCardState =
    facts.needs.length > 0
      ? 'pick_required'
      : facts.ready.length > 0
        ? 'pick_submitted'
        : facts.inProgress
          ? 'round_in_progress'
          : 'between_rounds';
  const { label: stateLabel, variant: stateVariant } = HOME_CARD_STATE[state];
  const { week, nextFantasy, legacyInPlay } = homeWeek(league);
  const now = Date.now();
  const games = week ? [week.fantasy, week.group].filter((card): card is GameCard => !!card) : [];
  const fee = games[0]?.fee;
  const open = games
    .filter((card) => isOpenNow(card, now))
    .sort((a, b) => parseInstant(a.locks_at).getTime() - parseInstant(b.locks_at).getTime());
  const upcoming = games
    .filter((card) => isUpcoming(card, now))
    .sort((a, b) => parseInstant(a.opens_at).getTime() - parseInstant(b.opens_at).getTime());
  const action = weekAction(games, now);
  const last = lastResultFor(league, entry);
  const rank = entry ? entry.rank : (league.season_stats?.rank ?? null);
  const points = entry ? entry.total_points : (league.season_stats?.total_points ?? 0);

  return (
    <article
      className="rounded-2xl border border-border bg-surface shadow-sm"
      aria-labelledby={`home-league-${league.slug}`}
      data-testid="two-game-home"
    >
      <div className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="eyebrow text-text-muted">
              {week
                ? `This week · ${formatCalendarDate(week.weekLabel, 'EEE d MMM')}`
                : legacyInPlay
                  ? 'This week'
                  : 'Between weeks'}
            </p>
            <h3
              id={`home-league-${league.slug}`}
              className="mt-0.5 truncate font-sans text-lg font-semibold text-text-primary"
            >
              {league.name}
            </h3>
          </div>
          {fee && <FeeChip fee={fee} />}
        </div>
        {league.suspended && (
          <p role="status" className="font-sans text-sm text-text-secondary">
            Entries suspended. Results and weekly fees continue.
          </p>
        )}
        <div className="flex flex-col items-start gap-2" data-testid={`home-state-${league.slug}`}>
          <Badge variant={stateVariant} className="transition-none">
            {stateLabel}
          </Badge>
          <WeekClock open={open} upcoming={upcoming} games={games} next={facts.next} />
        </div>
        {legacyInPlay ? (
          <ul className="space-y-3">
            {league.legacy_rounds
              .filter((card) => !card.archived)
              .map((card) => (
                <LegacyRoundItem key={card.week_id} card={card} serverNow={league.server_now} />
              ))}
          </ul>
        ) : (
          games.length > 0 && (
            <ul className="overflow-hidden rounded-xl border border-border divide-y divide-border">
              {games.map((card) => (
                <WeekGameRow key={card.game_id} card={card} now={now} />
              ))}
            </ul>
          )
        )}
        {action && (
          <Button asChild className="w-full transition-none">
            <Link to={action.to}>{action.label}</Link>
          </Button>
        )}
        {nextFantasy && (
          <p className="font-sans text-sm text-text-secondary">
            Next week’s Fantasy is open:{' '}
            <Link
              to={nextFantasy.destination}
              className="inline-flex min-h-11 items-center font-semibold text-primary transition-none hover:underline focus-visible:outline-hidden focus-visible:shadow-glow"
            >
              {GAME_NAME.fantasy} · {formatCalendarDate(nextFantasy.week_label, 'd MMM')}
            </Link>
            {!nextFantasy.fee.paid_through && (
              <> · {money(nextFantasy.fee.amount_owed_pence)} owed through this week</>
            )}
          </p>
        )}
        {league.next_game_state === 'pending' && (
          <p className="font-sans text-sm text-text-secondary">
            Next fantasy opening is pending confirmation.
          </p>
        )}
      </div>

      {last?.kind === 'legacy' && <LastResultPanel round={last.round} form={entry?.recent_form} />}
      {last?.kind === 'two_game' && (
        <TwoGameLastResult week={last.week} form={entry?.recent_form} />
      )}

      <Link
        to={`/leagues/${league.slug}/leaderboard`}
        className="flex items-center justify-between gap-3 border-t border-border px-5 py-3.5 transition-none hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        <span className="flex items-center gap-2 eyebrow text-text-muted sm:text-xs">
          <Trophy className="h-4 w-4 text-primary" aria-hidden />
          Standings
        </span>
        <span className="font-mono text-sm tabular-nums text-text-secondary">
          <span className={cn(rank === 1 && 'font-semibold text-primary')}>
            {rank === null ? '—' : `#${rank}`}
          </span>
          {entry && <span className="mx-1.5 text-text-muted">of {entry.member_count}</span>}
          <span className="text-text-muted">·</span>
          <span className="ml-1.5">{points} pts</span>
        </span>
      </Link>
      <Link
        to={`/leagues/${league.league_id}/games`}
        className="flex min-h-11 items-center justify-between rounded-b-2xl border-t border-border px-5 font-sans text-sm text-text-secondary transition-none hover:bg-surface-elevated focus-visible:outline-hidden focus-visible:shadow-glow"
      >
        Game archive
        <ChevronRight className="h-4 w-4 text-text-muted" aria-hidden />
      </Link>
    </article>
  );
}

/** The week's £1, once per card: a tick when paid, the amount when owed (Batch 243). */
function FeeChip({ fee }: { fee: GameCard['fee'] }) {
  return (
    <Link
      to={fee.destination}
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 font-sans text-xs font-semibold transition-none focus-visible:outline-hidden focus-visible:shadow-glow',
        fee.paid_through ? 'bg-success/[0.08] text-success dark:bg-success/15' : 'bg-warning/[0.08] text-warning dark:bg-warning/15',
      )}
    >
      {fee.paid_through ? (
        <>
          <Check className="h-3.5 w-3.5" aria-hidden />
          {shortMoney(fee.obligation_pence)} paid
        </>
      ) : (
        <>{shortMoney(fee.amount_owed_pence)} owed</>
      )}
    </Link>
  );
}

/**
 * The deadline that matters next, large: the soonest open game's lock with the other open
 * game's lock beside it; else the soonest opening; else, once the week is locked, its
 * results so far; else the next week's opening (Batch 243).
 */
function WeekClock({
  open,
  upcoming,
  games,
  next,
}: {
  open: GameCard[];
  upcoming: GameCard[];
  games: GameCard[];
  next: { opensAt: string } | null;
}) {
  const lead = open[0];
  if (lead) {
    const other = open[1] ?? upcoming[0];
    return (
      <div className="min-w-0">
        <p className="font-sans text-sm text-text-secondary">{GAME_NAME[lead.game_kind]} locks in</p>
        <p className="font-mono text-3xl font-semibold leading-tight tabular-nums text-text-primary">
          <Countdown target={lead.locks_at} format={formatCountdown} />
        </p>
        <p className="font-sans text-xs text-text-muted">
          {formatInstant(lead.locks_at, 'Europe/London', 'EEE HH:mm')}
          {other &&
            (open[1]
              ? ` · ${GAME_NAME[other.game_kind]} locks at ${formatInstant(other.locks_at, 'Europe/London', 'HH:mm')}`
              : ` · ${GAME_NAME[other.game_kind]} opens ${formatInstant(other.opens_at, 'Europe/London', 'EEE HH:mm')}`)}
        </p>
      </div>
    );
  }
  const soonest = upcoming[0];
  if (soonest) {
    return (
      <div className="min-w-0">
        <p className="font-sans text-sm text-text-secondary">{GAME_NAME[soonest.game_kind]} opens in</p>
        <p className="font-mono text-3xl font-semibold leading-tight tabular-nums text-text-primary">
          <Countdown target={soonest.opens_at} format={formatCountdown} />
        </p>
        <p className="font-sans text-xs text-text-muted">
          {formatInstant(soonest.opens_at, 'Europe/London', 'EEE d MMM HH:mm')}
        </p>
      </div>
    );
  }
  const fantasy = games.find((card) => card.game_kind === 'fantasy');
  if (games.length > 0) {
    return (
      <div className="min-w-0">
        <p className="font-sans text-sm text-text-secondary">Results so far</p>
        <p className="font-mono text-3xl font-semibold leading-tight tabular-nums text-text-primary">
          {fantasy ? `${fantasy.result.weekly_points ?? 0} pts` : '—'}
        </p>
        <p className="font-sans text-xs text-text-muted">Final once every game has finished</p>
      </div>
    );
  }
  if (next) {
    return (
      <p className="font-sans text-sm text-text-secondary">
        Next week opens in <Countdown target={next.opensAt} format={formatCountdown} />
      </p>
    );
  }
  return null;
}

/** The one button a week card offers: whatever needs the member soonest (Batch 243). */
function weekAction(games: GameCard[], now: number): { label: string; to: string } | null {
  const open = games
    .filter((card) => isOpenNow(card, now))
    .sort((a, b) => parseInstant(a.locks_at).getTime() - parseInstant(b.locks_at).getTime());
  if (open.length === 0) return null;
  const fee = open[0]!.fee;
  if (!fee.paid_through) {
    return {
      label: fee.amount_owed_pence === 100 ? 'Pay £1 to play' : `Pay ${money(fee.amount_owed_pence)} to play`,
      to: fee.destination,
    };
  }
  for (const card of open) {
    if (card.game_kind === 'fantasy') {
      const filled = card.progress.slots_filled ?? 0;
      if (filled < 6) {
        return {
          label: filled === 0 ? 'Make your Fantasy picks' : `Pick ${6 - filled} more for Fantasy`,
          to: card.destination,
        };
      }
    } else if (!card.my_entry?.pick) {
      return { label: 'Make your Saturday Group pick', to: card.destination };
    }
  }
  return null;
}

/** One game of the week as a row: its name, what it needs and a chip (Batch 243). */
function WeekGameRow({ card, now }: { card: GameCard; now: number }) {
  const open = isOpenNow(card, now);
  const upcoming = isUpcoming(card, now);
  const filled = card.progress.slots_filled ?? 0;
  const picked = card.progress.picked_count ?? 0;
  const members = card.progress.member_count ?? 0;
  const opens = formatInstant(card.opens_at, 'Europe/London', 'EEE HH:mm');
  const chip: { label: string; variant: 'success' | 'warning' | 'muted' } = upcoming
    ? { label: `Opens ${opens}`, variant: 'muted' }
    : !open
      ? { label: card.entry_state === 'suspended' ? 'Suspended' : 'Locked', variant: 'muted' }
      : card.game_kind === 'fantasy'
        ? filled >= 6
          ? { label: 'Full', variant: 'success' }
          : { label: `${6 - filled} to pick`, variant: 'warning' }
        : card.my_entry?.pick
          ? { label: 'Picked', variant: 'success' }
          : { label: 'Pick needed', variant: 'warning' };

  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1 space-y-1">
        <Link
          to={card.destination}
          className="inline-flex items-center font-sans text-base font-semibold text-text-primary transition-none hover:text-primary focus-visible:outline-hidden focus-visible:shadow-glow"
        >
          {GAME_NAME[card.game_kind]}
          <span className="sr-only"> · {formatCalendarDate(card.week_label, 'd MMM')}</span>
        </Link>
        {card.game_kind === 'fantasy' ? (
          <>
            {!upcoming && (
              <div className="grid max-w-[9.5rem] grid-cols-6 gap-1" aria-hidden>
                {Array.from({ length: 6 }, (_, index) => (
                  <span
                    key={index}
                    className={cn(
                      'h-1.5 rounded-full',
                      index < filled ? 'bg-primary' : 'bg-border-strong',
                    )}
                  />
                ))}
              </div>
            )}
            {!upcoming && (
              <p className="font-sans text-sm text-text-secondary">
                <span>{filled} of 6 slots</span>
                {!open && <span> · {card.result.weekly_points ?? 0} pts so far</span>}
              </p>
            )}
          </>
        ) : (
          <p className="flex flex-wrap gap-x-2 font-sans text-sm text-text-secondary">
            {upcoming ? (
              <span>Not open yet</span>
            ) : (
              <>
                {!open && <span>{couponStatus(card)} ·</span>}
                {card.my_entry?.pick ? (
                  <span className="text-text-primary">Your pick: {card.my_entry.pick.runner_name}</span>
                ) : open ? (
                  <span className="font-medium text-warning">Group pick needed</span>
                ) : (
                  <span>You didn’t pick</span>
                )}
                {open && members > 0 && (
                  <span className="tabular-nums text-text-muted">
                    {picked} of {members} in
                  </span>
                )}
              </>
            )}
          </p>
        )}
      </div>
      <Badge variant={chip.variant} className="shrink-0 transition-none">
        {chip.label}
      </Badge>
      <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" aria-hidden />
    </li>
  );
}

/** Which week a two-game league's `Last result` reports, and from which source. */
type CardLastResult =
  | { kind: 'legacy'; round: LastRoundView }
  | { kind: 'two_game'; week: TwoGameWeekResult };

/**
 * The later of the league's last settled legacy round (the summary's `last_result`) and
 * its last final two-game week (Batch 239). Until the first two-game week is final, a
 * league that has just switched keeps reporting the legacy round it last played.
 */
function lastResultFor(league: LeagueGames, entry?: PerLeagueSummary): CardLastResult | null {
  const week = lastTwoGameWeek(league);
  const round = entry ? lastRoundView(entry) : null;
  const roundOn =
    entry?.last_result?.starts_on ??
    (entry?.current_round?.status === 'settled' ? entry.current_round.starts_on : null);
  if (week && (!round || !roundOn || week.weekLabel > roundOn)) {
    return { kind: 'two_game', week };
  }
  return round ? { kind: 'legacy', round } : null;
}

/** The member's fantasy week in one line: what it scored and how many picks came in. */
function fantasyResultLine(card: GameCard): string {
  const { result } = card;
  if (result.entry_result === 'no_entry') return 'Fantasy: no entry';
  if (result.entry_result === 'all_void') return 'Fantasy: every pick void';
  const filled = result.slots_filled ?? card.progress.slots_filled ?? 0;
  return `Fantasy: ${result.weekly_points ?? 0} pts · ${result.won ?? 0} of ${filled} won`;
}

/** How the week's group coupon went, and the member's own part in it. Never a price. */
function groupResultLine(card: GameCard): string {
  const status = card.result.status;
  const outcome =
    status === 'won'
      ? 'Group coupon won'
      : status === 'lost'
        ? 'Group coupon lost'
        : status === 'void'
          ? 'Group coupon void'
          : status === 'no_coupon'
            ? 'No group coupon'
            : 'Group coupon settling';
  const mine = card.my_entry?.pick;
  return mine ? `${outcome} · Your pick: ${mine.runner_name}` : `${outcome} · You didn’t pick`;
}

/**
 * A two-game week in the `Last result` frame (Batch 239): the member's fantasy score and
 * the group coupon's outcome, beside the season's run. The run is the summary's, which
 * already draws fantasy weeks as their weekly points.
 */
function TwoGameLastResult({ week, form }: { week: TwoGameWeekResult; form?: FormRound[] }) {
  return (
    <div className="border-t border-border px-5 py-4" data-testid="last-result">
      <p className="truncate eyebrow text-text-muted">
        Last result · {formatCalendarDate(week.weekLabel, 'EEE d MMM')}
      </p>
      {week.fantasy && (
        <p className="mt-1.5 font-sans text-base font-medium text-text-primary">
          {fantasyResultLine(week.fantasy)}
        </p>
      )}
      <div className="mt-1 flex items-end justify-between gap-3">
        <p className="font-sans text-sm text-text-muted">
          {week.group ? groupResultLine(week.group) : 'No group game that week'}
        </p>
        <PickFormLine form={form} className="shrink-0" />
      </div>
    </div>
  );
}

/** The member's own claim, as the card's primary line. */
function MyPickLine({ pick, oddsFormat }: { pick: MyPick; oddsFormat: OddsFormat }) {
  return (
    <>
      <p className="font-sans text-base font-medium text-text-primary">
        {outcomeLabel(pick.market, pick.outcome, pick.home, pick.away)}
        <span className="mx-1.5 text-text-muted">·</span>
        <span className="font-mono tabular-nums">{formatOdds(pick.odds, oddsFormat)}</span>
      </p>
      <p className="mt-1 truncate font-sans text-sm text-text-muted">
        {fixtureContext(pick.market, pick.outcome, pick.home, pick.away)}
      </p>
    </>
  );
}

/** The round just gone, in the shape the panel below draws. */
interface LastRoundView {
  label: string;
  movement: number | null;
  mine: MyPick | null;
  legCount: number;
  /** `null` when the source could not say how many landed. */
  picksWon: number | null;
  combinedOdds: number;
  /** How many of `legCount` the price leaves out as void (Batch 186); 0 when not sent. */
  voidLegCount: number;
}

/**
 * Which round the `Last result` panel is reporting, and where its figures come from.
 *
 * `last_result` is the answer whenever the API sends one. The fallback matters because
 * Batch 106 takes the settled round's pick, fold and odds *out* of the primary card: on an
 * API that predates Batch 79 there would otherwise be nowhere left for them, and a settled
 * round would show a member nothing at all. `current_round` cannot say how many legs
 * landed, so that line is simply absent rather than guessed.
 */
function lastRoundView(entry: PerLeagueSummary): LastRoundView | null {
  const result = entry.last_result;
  if (result) {
    return {
      label: roundName(
        result.number,
        formatCalendarDate(result.starts_on, 'EEE d MMM'),
        result.season_week,
      ),
      movement: result.rank_movement ?? null,
      mine: result.my_pick,
      legCount: result.leg_count,
      picksWon: result.picks_won,
      combinedOdds: result.combined_odds,
      voidLegCount: result.void_leg_count ?? 0,
    };
  }
  const round = entry.current_round;
  if (!round || round.status !== 'settled') return null;
  return {
    label: roundName(
      round.number,
      formatCalendarDate(round.starts_on, 'EEE d MMM'),
      round.season_week,
    ),
    movement: null,
    mine: round.my_pick,
    legCount: round.leg_count,
    picksWon: null,
    combinedOdds: round.combined_odds,
    voidLegCount: round.void_leg_count ?? 0,
  };
}

/**
 * How the round just gone actually went (Batch 79).
 *
 * Four facts the card printed the word `Settled` in place of: whether the member's pick
 * came in, what it scored, how many of the league's picks landed, and whether they moved
 * in the table. It is a sibling of the coupon button rather than part of it because the
 * two answer different rounds — on most leagues the round above this panel is next
 * week's, not the one being reported.
 *
 * Batch 106 made that separation load-bearing rather than tidy. The primary card no longer
 * carries a settled round's pick or price at all, so this panel is the *only* place they
 * appear, and it is labelled `Last result` so nothing here can be mistaken for the round
 * the clock above is counting down to.
 *
 * Movement never rides on colour alone: the arrow is decorative and the direction is a
 * word underneath it, the same rule the live scoreline follows.
 *
 * Batch 81 hangs the season's run of five here rather than on the standings link below.
 * Two reasons, and the second is the binding one: a run belongs with "how it is going"
 * rather than beside a tap target, and `PickFormLine` carries a `role="img"` label that
 * spells the run out in words — nested in a link, that whole sentence is appended to the
 * link's accessible name.
 */
function LastResultPanel({ round, form }: { round: LastRoundView; form?: FormRound[] }) {
  const oddsFormat = useOddsFormat();
  const { movement, mine } = round;
  // Batch 186. The fold is the number of legs the price is a product of, as on the
  // coupon: "2 of 4 picks landed · 2-fold" when two legs were void, never "4-fold".
  const foldCount = round.legCount - round.voidLegCount;

  return (
    <div className="border-t border-border px-5 py-4" data-testid="last-result">
      <div className="flex items-center justify-between gap-3">
        <p className="truncate eyebrow text-text-muted">
          Last result · {round.label}
        </p>
        {movement != null && movement !== 0 && (
          <span
            className={cn(
              'shrink-0 font-mono text-xs tabular-nums',
              movement > 0 ? 'text-success' : 'text-error',
            )}
            data-testid="rank-movement"
          >
            <span aria-hidden>{movement > 0 ? '▲' : '▼'}</span>
            {Math.abs(movement)}
            <span className="sr-only">
              {' '}
              {movement > 0 ? 'places gained' : 'places lost'}
            </span>
          </span>
        )}
      </div>

      <p className="mt-1.5 font-sans text-base font-medium text-text-primary">
        {!mine ? (
          <span className="text-text-muted">You didn’t pick this round</span>
        ) : mine.status === 'won' ? (
          <>
            <span className="text-success">Your pick won</span>
            {mine.points_awarded != null && (
              <>
                <span className="mx-1.5 text-text-muted">·</span>
                <span className="font-mono tabular-nums">{mine.points_awarded} pts</span>
              </>
            )}
          </>
        ) : mine.status === 'void' ? (
          // A void pick is not a loss: the fixture never ran, so there was nothing to
          // win. Saying "lost" here would be the same conflation the leaderboard's two
          // denominators exist to avoid.
          <span className="text-text-muted">Your pick was void</span>
        ) : mine.status === 'lost' ? (
          <span className="text-text-muted">Your pick didn’t come in</span>
        ) : (
          <span className="text-text-muted">Your pick hasn’t settled</span>
        )}
      </p>

      {mine && (
        <p className="mt-0.5 truncate font-sans text-sm text-text-muted">
          {outcomeLabel(mine.market, mine.outcome, mine.home, mine.away)}
          <span className="mx-1.5">·</span>
          <span className="font-mono tabular-nums">{formatOdds(mine.odds, oddsFormat)}</span>
          <span className="mx-1.5">·</span>
          {fixtureContext(mine.market, mine.outcome, mine.home, mine.away)}
        </p>
      )}

      <div className="mt-1 flex items-end justify-between gap-3">
        <p className="font-sans text-sm text-text-muted">
          {round.picksWon === null
            ? `${foldCount}-fold · ${formatCombinedOdds(round.combinedOdds, oddsFormat)}`
            : round.legCount === 0
              ? 'Nobody picked this round'
              : `${round.picksWon} of ${round.legCount} ${round.legCount === 1 ? 'pick' : 'picks'} landed · ${foldCount}-fold · ${formatCombinedOdds(round.combinedOdds, oddsFormat)}`}
        </p>
        <PickFormLine form={form} className="shrink-0" />
      </div>
    </div>
  );
}
