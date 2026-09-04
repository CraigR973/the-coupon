import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLeague } from '../contexts/LeagueContext';
import { useCountdown, type CountdownParts } from '../hooks/useCountdown';
import { useGameweekHistory, useSelectedGameweekId } from '../hooks/useGameweekHistory';
import { useOddsFormat } from '../hooks/useOddsFormat';
import { useRouteLeague } from '../hooks/useRouteLeague';
import {
  couponKey,
  gameweekKey,
  usePickEditor,
  type OutstandingPick,
} from '../hooks/usePickEditor';
import type {
  Coupon,
  FixtureSlate,
  GameweekSlate,
  GameweekStatus,
  OddsFormat,
  PickMarket,
  PickOutcome,
  SelectionOption,
} from '../lib/types';
import { competitionRank } from '../lib/competitions';
import { couponLeads, fixtureContext, outcomeLabel, roundName, roundPhase } from '../lib/coupon';
import { COUPON_SECTION_HASH, COUPON_SECTION_ID } from '../lib/leagues';
import { formatCalendarDate } from '../lib/time';
import { PageHeader } from '../components/PageHeader';
import { CouponSubNav } from '../components/CouponSubNav';
import { LeagueSwitchStrip } from '../components/LeagueSwitchStrip';
import { OddsGuide } from '../components/OddsGuide';
import { PickCard } from '../components/PickCard';
import { CouponSection } from '../components/CouponSection';
import { RoundStatus, type MyClaim } from '../components/RoundStatus';
import { OutstandingPickNotice } from '../components/OutstandingPickNotice';
import { GameweekNav } from '../components/GameweekNav';
import { EmptyState } from '../components/EmptyState';
import { entriesForRound } from '../components/PickRow';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';

const FAR_PAST = new Date(0).toISOString();

/** The two states a round can still be claimed in — settlement has finished with the rest. */
const PICKABLE: ReadonlySet<GameweekStatus> = new Set(['scheduled', 'open']);

function formatCountdown(p: CountdownParts): string {
  if (p.expired) return 'Locked';
  if (p.days > 0) return `${p.days}d ${p.hours}h ${p.minutes}m`;
  if (p.hours > 0) return `${p.hours}h ${p.minutes}m ${p.seconds}s`;
  return `${p.minutes}m ${p.seconds}s`;
}

/** The current pick, derived from the slate's `mine` flags. */
function findMyPick(slate: GameweekSlate | undefined) {
  if (!slate) return null;
  for (const fixture of slate.fixtures) {
    const sel = fixture.selections.find((s: SelectionOption) => s.mine);
    if (sel) return { fixture, sel };
  }
  return null;
}

interface CompetitionGroup {
  competition_id: string;
  competition: string;
  fixtures: FixtureSlate[];
}

/**
 * The slate grouped by the provider's competition slug, each group ordered by kick-off.
 *
 * Display names can carry sponsor text and have changed before, so the group
 * identity and ordering use `fixtures.competition_id`.
 */
function groupByCompetition(fixtures: FixtureSlate[]): CompetitionGroup[] {
  const groups = new Map<string, FixtureSlate[]>();
  for (const fixture of fixtures) {
    const bucket = groups.get(fixture.competition_id) ?? [];
    bucket.push(fixture);
    groups.set(fixture.competition_id, bucket);
  }
  return [...groups.entries()]
    .map(([competition_id, groupFixtures]) => ({
      competition_id,
      competition: groupFixtures[0].competition,
      fixtures: [...groupFixtures].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc)),
    }))
    .sort((a, b) => {
      const ar = competitionRank(a.competition_id);
      const br = competitionRank(b.competition_id);
      // The shared order, with one tiebreak only this screen can apply: among
      // competitions that rank equally the fuller card comes first, which is a
      // property of this slate rather than of the competition.
      return (
        ar[0] - br[0] ||
        ar[1] - br[1] ||
        b.fixtures.length - a.fixtures.length ||
        a.competition.localeCompare(b.competition) ||
        ar[2].localeCompare(br[2])
      );
    });
}

/**
 * The whole of this week's job, on one screen.
 *
 * Batch 105. `Your pick` and `Combined coupon` were two tabs over one round, and the split
 * was the product asking the member a question it should have answered itself: before the
 * deadline what matters is the slate, after it what matters is the coupon, and on a settled
 * round what matters is the result. Nobody wants to choose. So this surface reads the
 * round's phase (`roundPhase`) and orders itself by it — the fixture list leads while a
 * pick can still be made, and the coupon leads from the moment the coupon is worth having.
 *
 * The old address still resolves: `/leagues/:slug/predictions/coupon` redirects here
 * carrying `?gw=` and landing on `#coupon`, which is where the fold, the frozen combined
 * price and the copy control now live.
 */
export function CurrentRoundPage() {
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const oddsFormat = useOddsFormat();
  const { slug, name: leagueName } = useRouteLeague();
  const { hasLeagues, isLoading: leaguesLoading } = useLeague();
  const gameweekId = useSelectedGameweekId();
  const { hash } = useLocation();

  const {
    data: slate,
    isLoading,
    isError,
    error,
  } = useQuery<GameweekSlate>({
    queryKey: gameweekKey(slug, gameweekId),
    queryFn: () =>
      apiFetch<GameweekSlate>(
        `/api/v1/leagues/${slug}/gameweek/current${gameweekId ? `?gameweek_id=${gameweekId}` : ''}`,
      ),
    staleTime: 30_000,
    enabled: hasLeagues,
  });

  // The combined coupon, read alongside the slate rather than on its own screen. A round
  // with no coupon yet answers 404 and simply leaves this undefined — the section below
  // then shows who is still to pick, which is the only news there is.
  const { data: couponResponse } = useQuery<Coupon>({
    queryKey: couponKey(slug, gameweekId),
    queryFn: () =>
      apiFetch<Coupon>(
        `/api/v1/leagues/${slug}/coupon${gameweekId ? `?gameweek_id=${gameweekId}` : ''}`,
      ),
    staleTime: 30_000,
    enabled: hasLeagues,
  });
  // The boundary where the API's shape becomes this screen's assumption, and therefore
  // where the shape is checked — the same guard `useGameweekHistory` puts on the season
  // list. Everything below indexes into `legs`, and a response without one is a round
  // with no coupon rather than a page that throws.
  const coupon = Array.isArray(couponResponse?.legs) ? couponResponse : undefined;

  // Anchored on the round the slate actually came back with, which on the default view
  // is the API's choice rather than the newest date (see `useGameweekHistory`).
  const history = useGameweekHistory(slug, hasLeagues, slate?.gameweek_id);

  const countdown = useCountdown(slate?.locks_at_utc ?? FAR_PAST);
  const openCountdown = useCountdown(slate?.picks_open_at_utc ?? FAR_PAST);
  const { submit, pendingKey, isSubmitting, outstanding, resolveOutstanding, discardOutstanding } =
    usePickEditor(slug, slate?.gameweek_id);

  // Mirrors the API's own rule (`pick_refusal`): the stored instants decide both ends of
  // the claim period and `status` only rules out a round settlement has finished with.
  // Deriving "shut" from `status === 'open'` alone would hold members out of a round
  // whose opening has passed until the hourly job got round to relabelling it.
  //
  // Batch 73 made `pickRefusal` in `lib/coupon.ts` the written-down form of this rule, for
  // the surfaces that only *label* a round. This stays expressed through the countdowns
  // because it needs to flip live while a member watches, and because it decides whether a
  // pick can be submitted rather than what a badge says. Keep the two in step.
  const notOpenYet =
    !!slate?.picks_open_at_utc && !openCountdown.expired && PICKABLE.has(slate.status);
  // The deadline half of the same rule, kept apart from `notOpenYet` because the phase
  // needs to tell "too early" from "too late" and the selections do not.
  const claimingShut = !slate || !PICKABLE.has(slate.status) || countdown.expired;
  const locked = claimingShut || notOpenYet;
  const myPick = findMyPick(slate);
  const groups = useMemo(() => groupByCompetition(slate?.fixtures ?? []), [slate?.fixtures]);

  const memberCount = slate?.members.length ?? 0;
  const missingCount = slate?.members_missing_picks ?? 0;
  const phase = roundPhase({
    settled: slate?.status === 'settled',
    claimingShut,
    notOpenYet,
    memberCount,
    missingCount,
    mine: !!myPick,
  });

  const roundLabel = slate
    ? roundName(slate.number, formatCalendarDate(slate.starts_on, 'EEE d MMM yyyy'))
    : 'This round';

  const entries = useMemo(
    () => entriesForRound(coupon, slate?.members ?? [], player?.id),
    [coupon, slate?.members, player?.id],
  );

  const mine: MyClaim | null = myPick
    ? {
        selection: outcomeLabel(
          myPick.sel.market,
          myPick.sel.outcome,
          myPick.fixture.home,
          myPick.fixture.away,
        ),
        context: fixtureContext(
          myPick.sel.market,
          myPick.sel.outcome,
          myPick.fixture.home,
          myPick.fixture.away,
        ),
        competition: myPick.fixture.competition,
        odds: myPick.sel.odds,
      }
    : null;

  // A notification tap or a legacy combined-coupon link arrives pointed at the copy
  // section. Focus rather than scroll alone: the section is what the reader asked for, so
  // it should also be where the keyboard is.
  useEffect(() => {
    if (hash !== COUPON_SECTION_HASH) return;
    const target = document.getElementById(COUPON_SECTION_ID);
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView?.({ block: 'start' });
  }, [hash, coupon?.gameweek_id, slate?.gameweek_id]);

  if (!leaguesLoading && !hasLeagues) {
    return (
      <div>
        <PageHeader title="This week's coupon" />
        <EmptyState
          title="You're not in a league yet"
          description={
            <>
              Join one to start picking.{' '}
              <Link to="/leagues/discover" className="text-primary underline underline-offset-2">
                Find a league
              </Link>
            </>
          }
        />
      </div>
    );
  }

  const clock = !slate
    ? ''
    : slate.status === 'settled'
      ? ''
      : notOpenYet
        ? `Picks open in ${formatCountdown(openCountdown)}`
        : claimingShut
          ? 'Picks are locked'
          : `Picks lock in ${formatCountdown(countdown)}`;

  const couponFirst = couponLeads(phase);

  const couponBlock = slate ? (
    <CouponSection
      coupon={coupon}
      entries={entries}
      phase={phase}
      memberCount={memberCount}
      roundLabel={roundLabel}
      oddsFormat={oddsFormat}
    />
  ) : null;

  const slateBlock = slate ? (
    <section aria-labelledby="slate-heading" data-testid="slate-section">
      <h2
        id="slate-heading"
        className="mb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary"
      >
        {locked ? 'Slate and prices' : 'Pick your selection'}
      </h2>
      <OddsGuide />

      {slate.fixtures.length === 0 ? (
        <EmptyState
          title="No fixtures on the slate"
          description="There are no priced fixtures for this gameweek yet."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {/* Ahead of everything else, deliberately: a member holding an unsent or
              unconfirmed claim has already picked, and telling them to pick is the wrong
              next instruction. */}
          {outstanding && (
            <OutstandingPickNotice
              outstanding={outstanding}
              onResolve={resolveOutstanding}
              onDiscard={discardOutstanding}
              disabled={locked}
            />
          )}
          {groups.map((group) => (
            <CompetitionSection
              key={group.competition_id}
              group={group}
              timezone={timezone}
              locked={locked}
              pendingKey={pendingKey}
              outstanding={outstanding}
              busy={isSubmitting}
              oddsFormat={oddsFormat}
              onGrab={submit}
            />
          ))}
        </div>
      )}
    </section>
  ) : null;

  return (
    <div>
      {/* The round's name stays in the eyebrow rather than moving to the heading: it is
          the one place that survives a league with a single round, where `GameweekNav`
          hides itself and would otherwise take the date with it. */}
      <PageHeader
        title={history.isLatest ? "This week's coupon" : 'Past coupon'}
        eyebrow={leagueName ? `${leagueName} · ${roundLabel}` : roundLabel}
      />
      <LeagueSwitchStrip currentSlug={slug} className="mb-5" />
      <CouponSubNav slug={slug} />
      <GameweekNav history={history} />

      {/*
        Batch 48: the API served this card from a *failed* price refresh — last known
        odds, or none at all. Saying so is the difference between stale numbers and
        stale numbers presented as current. Optional field, so an API that predates it
        simply never sets this.
      */}
      {slate?.odds_degraded && (
        <div
          role="status"
          aria-live="polite"
          data-testid="odds-degraded-banner"
          className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-2.5 text-center text-xs font-sans text-warning"
        >
          Prices may be out of date — the odds source isn't responding right now.
        </div>
      )}

      {slate && (
        <RoundStatus
          phase={phase}
          clock={clock}
          pickedCount={memberCount - missingCount}
          memberCount={memberCount}
          mine={mine}
          oddsFormat={oddsFormat}
          canSwitch={!locked}
        />
      )}

      {isLoading && (
        <div className="space-y-4" aria-label="Loading this week's coupon">
          <Skeleton className="h-[220px] w-full rounded-lg" />
          <Skeleton className="h-[220px] w-full rounded-lg" />
        </div>
      )}

      {isError && (
        <EmptyState
          title="No coupon this week yet"
          description={
            error instanceof Error && error.message !== 'API error 404'
              ? error.message
              : "This round's slate hasn't been published yet. Check back soon."
          }
        />
      )}

      <div className="flex flex-col gap-6">
        {couponFirst ? couponBlock : slateBlock}
        {couponFirst ? slateBlock : couponBlock}
      </div>
    </div>
  );
}

/**
 * One competition's fixtures behind a collapsible header.
 *
 * Closed by default: a hundred-fixture slate should scan as league headers
 * first, with members opening only the competitions they care about.
 */
function CompetitionSection({
  group,
  timezone,
  locked,
  pendingKey,
  outstanding,
  busy,
  oddsFormat,
  onGrab,
}: {
  group: CompetitionGroup;
  timezone: string;
  locked: boolean;
  pendingKey: string | null;
  outstanding: OutstandingPick | null;
  busy: boolean;
  oddsFormat: OddsFormat;
  onGrab: (fixtureId: string, market: PickMarket, outcome: PickOutcome) => void;
}) {
  const [open, setOpen] = useState(false);
  const claimed = group.fixtures.filter((f) => f.taken_by_names.length > 0).length;

  return (
    <section data-testid={`competition-${group.competition_id}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mb-2 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="min-w-0 truncate font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary">
          {group.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-[10px] tabular-nums text-text-muted">
            {claimed > 0 ? `${claimed}/${group.fixtures.length}` : group.fixtures.length}
          </span>
          <ChevronDown
            className={cn('h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-4">
          {group.fixtures.map((fixture) => (
            <PickCard
              key={fixture.fixture_id}
              fixture={fixture}
              timezone={timezone}
              locked={locked}
              pendingKey={pendingKey}
              outstanding={outstanding}
              busy={busy}
              oddsFormat={oddsFormat}
              onGrab={onGrab}
            />
          ))}
        </div>
      )}
    </section>
  );
}
