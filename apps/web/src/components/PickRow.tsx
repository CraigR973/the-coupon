import type {
  Coupon,
  CouponLeg,
  GameweekMember,
  OddsFormat,
  PickMarket,
  PickOutcome,
  PickStatus,
} from '../lib/types';
import { fixtureContext, formatOdds, outcomeLabel, pickStatusLabel } from '../lib/coupon';
import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

/**
 * One member's claim on a round, in the one shape the coupon section renders.
 *
 * Batch 78. `GameweekMember` (`types.ts`) and `CouponLeg` carry the same seven facts —
 * who, which fixture, which competition, which market, which outcome, at what price —
 * because they *are* the same fact, read from two endpoints. The roster and the combined
 * acca then drew them twice, and the two drawings drifted: only one carried the market
 * tag, only one marked the reader's own row, and only one truncated the competition.
 *
 * The two things that genuinely differ are kept and neither is lost here. A roster can
 * carry a member with **no** selection — that is the whole reason it exists, since a
 * member who has picked nothing appears nowhere in the slate — and a coupon leg can
 * carry a **result**: a scoreline, a status and the points it scored. Hence a nullable
 * `selection` and the optional settlement fields, rather than two types.
 */
export interface PickEntry {
  player_id: string;
  player_name: string;
  /** Marks the reader's own row. The caller supplies it; this file never reads auth. */
  is_mine: boolean;
  /** `null` when this member has not claimed a selection — a roster state only. */
  selection: PickSelection | null;
  /** Settlement, when the round has any. All optional: a live round has none of it. */
  status?: PickStatus;
  points_awarded?: number | null;
  home_goals?: number | null;
  away_goals?: number | null;
  score_is_final?: boolean;
}

export interface PickSelection {
  home: string;
  away: string;
  /** `null` on a roster row the API answered without one. */
  competition: string | null;
  market: PickMarket;
  outcome: PickOutcome;
  /** `null` on a roster row the API answered without one; never null on a leg. */
  odds: number | null;
}

/**
 * The slate's members as pick rows, in the order the API sent them.
 *
 * `home`/`away` fall back to the generic words rather than dropping the row: a member
 * who has picked is a member who has picked, and a fixture the API declined to name is
 * a smaller problem than a row that vanishes.
 */
export function entriesFromMembers(
  members: GameweekMember[],
  myPlayerId?: string,
): PickEntry[] {
  return members.map((member) => ({
    player_id: member.player_id,
    player_name: member.display_name,
    is_mine: member.player_id === myPlayerId,
    selection:
      member.has_picked && member.market && member.outcome
        ? {
            home: member.home ?? 'Home',
            away: member.away ?? 'Away',
            competition: member.competition,
            market: member.market,
            outcome: member.outcome,
            odds: member.odds,
          }
        : null,
  }));
}

/** The coupon's legs as pick rows. Every leg has a selection by construction. */
export function entriesFromLegs(legs: CouponLeg[], myPlayerId?: string): PickEntry[] {
  return legs.map((leg) => ({
    player_id: leg.player_id,
    player_name: leg.player_name,
    is_mine: leg.player_id === myPlayerId,
    selection: {
      home: leg.home,
      away: leg.away,
      competition: leg.competition,
      market: leg.market,
      outcome: leg.outcome,
      odds: leg.odds,
    },
    status: leg.status,
    points_awarded: leg.points_awarded,
    home_goals: leg.home_goals,
    away_goals: leg.away_goals,
    score_is_final: leg.score_is_final,
  }));
}

/**
 * Everybody in the round: the coupon's legs, then the members who never claimed one.
 *
 * Batch 105 merged two screens that each held half of this list. The combined coupon knew
 * what had been claimed and carried the results; the roster knew who was still missing and
 * carried nobody's score. A member reading "3-fold accumulator" next to a four-member
 * league had to hold both in their head to notice that somebody had been caught by the
 * deadline — which is precisely the thing the merged surface has to be able to say.
 *
 * The coupon is the authority on a member who appears in both, because it is the response
 * that carries settlement; a slate whose cache is a beat behind cannot demote a leg back
 * to "yet to pick".
 */
export function entriesForRound(
  coupon: Coupon | undefined,
  members: GameweekMember[],
  myPlayerId?: string,
): PickEntry[] {
  if (!coupon) return entriesFromMembers(members, myPlayerId);
  const claimed = entriesFromLegs(coupon.legs, myPlayerId);
  const held = new Set(claimed.map((entry) => entry.player_id));
  const missing = entriesFromMembers(
    members.filter((member) => !member.has_picked && !held.has(member.player_id)),
    myPlayerId,
  ).map((entry) => ({ ...entry, selection: null }));
  return [...claimed, ...missing];
}

const STATUS_VARIANT: Record<PickStatus, 'success' | 'error' | 'muted' | 'default'> = {
  won: 'success',
  lost: 'error',
  void: 'muted',
  pending: 'default',
};

/**
 * True when this leg's score is the state of play rather than the result (Batch 72).
 *
 * Defaults to *final*, so a deployed API that predates the field is read the way it has
 * always meant — Vercel ships this app on merge while the API waits for `/ship-prod`.
 */
export function isLive(entry: PickEntry): boolean {
  return entry.score_is_final === false;
}

/** An entry's scoreline, or null when there is none to show. */
function scoreline(entry: PickEntry): string | null {
  if (entry.home_goals == null || entry.away_goals == null) return null;
  return `${entry.home_goals}–${entry.away_goals}`;
}

export interface PickRowProps {
  entry: PickEntry;
  oddsFormat: OddsFormat;
  /**
   * Which fact leads the row.
   *
   * `player` is the roster's question — *who has picked* — so the name is the heading
   * and the selection is the detail under it. `selection` is the coupon's — *what is
   * riding on this* — so the bet is the heading and the holder is part of the detail.
   * Same facts, same component, opposite hierarchy, and each is right for its screen.
   */
  lead: 'player' | 'selection';
  /** The leg number, on a list that is ordered. Omitted on the roster. */
  index?: number;
  /** Show the scoreline when there is one. A round in progress carries scores too. */
  showScore?: boolean;
  /** Show the status badge and points — settlement is finished with this round. */
  settled?: boolean;
  className?: string;
  testId?: string;
}

/**
 * One row of the coupon section's member list.
 *
 * Colour never carries a fact on its own here: `Live` is a word, the status is a word,
 * and a lost leg dims *in addition to* saying so. That is the rule Batch 72 set when the
 * same row started showing half-time scores, and it is why the `Live` badge exists at all
 * — 2-1 at half time and 2-1 at full time are opposite news to whoever holds that pick.
 *
 * ## What may be clipped, and what may not (Batch 105)
 *
 * A row exists to answer three questions — **who took it, what they took, at what price**
 * — and every one of those three now wraps rather than truncating. The row used to put
 * the holder's name third in a single `truncate`d line behind the competition and the
 * fixture, so on a 390px screen a long team name ended the line before the name it
 * belonged to: the coupon named nobody. Fixture context is allowed two lines and then
 * clamps, and the competition sits at the end of that line because it is the one fact
 * here that identifies nothing on its own.
 */
export function PickRow({
  entry,
  oddsFormat,
  lead,
  index,
  showScore,
  settled,
  className,
  testId,
}: PickRowProps) {
  const { selection } = entry;
  const label = selection
    ? outcomeLabel(selection.market, selection.outcome, selection.home, selection.away)
    : null;
  const score = showScore ? scoreline(entry) : null;
  const running = isLive(entry);
  const lost = settled && entry.status === 'lost';

  // The person leads a row with nothing claimed on it whichever hierarchy is asked for:
  // a coupon row's heading is normally the bet, and a member who has taken none has no
  // bet to head it with. Without this the merged list drew their row anonymously.
  const primary = lead === 'player' || !selection ? entry.player_name : label;
  const secondary = lead === 'player' ? label : entry.player_name;
  // A scoreline names both teams and the goals between them, so repeating the pairing
  // above it would be the same clutter this row was rebuilt to remove.
  const context = [
    selection && !score
      ? fixtureContext(selection.market, selection.outcome, selection.home, selection.away)
      : null,
    selection?.competition,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <li
      className={cn(
        'flex gap-3',
        lead === 'player'
          ? 'items-start border-b border-border/50 px-4 py-2.5 last:border-b-0'
          : 'items-start rounded-lg border border-border bg-surface p-3',
        lost && 'opacity-60',
        lead === 'selection' && entry.is_mine && 'border-primary',
        className,
      )}
      data-testid={testId}
    >
      {index != null && (
        <span className="w-5 shrink-0 pt-0.5 text-center font-mono text-xs tabular-nums text-text-muted">
          {index + 1}
        </span>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p
            className={cn(
              'min-w-0 break-words font-sans text-sm',
              lead === 'player' ? 'text-text-primary' : 'font-medium text-text-primary',
            )}
          >
            {primary}
          </p>
          {entry.is_mine && <Badge variant="accent">You</Badge>}
        </div>

        {selection ? (
          <p className="break-words font-sans text-xs text-text-secondary">{secondary}</p>
        ) : (
          <p className="font-sans text-xs text-warning">Yet to pick</p>
        )}

        {context && (
          <p className="line-clamp-2 font-sans text-xs text-text-muted">{context}</p>
        )}

        {/* The result, not the outcome. Absent when the leg's fixture could not be
            resolved to a played match — the join fails open rather than guessing, so
            there is simply nothing here rather than a wrong scoreline. */}
        {score && selection && (
          // A div rather than a paragraph: `Badge` renders a block, and a block inside a
          // <p> is invalid markup the browser silently rewrites.
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs tabular-nums text-text-secondary">
              <span className="sr-only">{running ? 'Score so far: ' : 'Final score: '}</span>
              {selection.home} {score} {selection.away}
            </span>
            {running && <Badge variant="live">Live</Badge>}
          </div>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-0.5">
        {selection?.odds != null && (
          <span
            className={cn(
              'font-mono tabular-nums text-text-primary',
              lead === 'player' ? 'text-xs' : 'text-sm',
            )}
          >
            {formatOdds(selection.odds, oddsFormat)}
          </span>
        )}
        {settled && entry.status && (
          <Badge variant={STATUS_VARIANT[entry.status]}>{pickStatusLabel(entry.status)}</Badge>
        )}
        {settled && entry.points_awarded != null && (
          <span className="font-mono text-[11px] tabular-nums text-text-muted">
            {entry.points_awarded} pts
          </span>
        )}
      </div>
    </li>
  );
}
