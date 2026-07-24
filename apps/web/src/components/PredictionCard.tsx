import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { formatInTimeZone } from 'date-fns-tz';
import { Clock, Lock } from 'lucide-react';
import type { MatchResponse, PredictionResponse, PointsBreakdown, KnockoutPredictionResponse } from '../lib/types';
import { MatchResult } from './MatchResult';
import { Badge } from './ui/badge';
import { PointsBreakdownPopover } from './PointsBreakdownPopover';
import { ScoreInput } from './ui/score-input';
import { useCountdown } from '../hooks/useCountdown';
import { canEdit, statusLabel, statusVariant } from '../lib/matchStatus';
import type { LocalPrediction } from '../hooks/usePredictionEditor';
import { shortPlaceholder } from '../lib/matchTeam';
import { cn } from '../lib/utils';

// ---------------------------------------------------------------------------
// Points badge with count-up animation
// ---------------------------------------------------------------------------

function PointsBadge({ points, breakdown }: { points: number; breakdown?: PointsBreakdown | null }) {
  const prefersReducedMotion = useReducedMotion();
  const [displayed, setDisplayed] = useState(prefersReducedMotion ? points : 0);

  useEffect(() => {
    if (prefersReducedMotion) { setDisplayed(points); return; }
    if (points === 0) { setDisplayed(0); return; }
    setDisplayed(0);
    const steps = points;
    const intervalMs = Math.max(30, Math.min(120, 600 / steps));
    let current = 0;
    const id = setInterval(() => {
      current++;
      setDisplayed(current);
      if (current >= steps) clearInterval(id);
    }, intervalMs);
    return () => clearInterval(id);
  }, [points, prefersReducedMotion]);

  return (
    <PointsBreakdownPopover breakdown={breakdown}>
      <Badge variant={points > 0 ? 'success' : 'muted'} data-testid="points-badge" aria-live="polite">
        {displayed} {displayed === 1 ? 'pt' : 'pts'}
      </Badge>
    </PointsBreakdownPopover>
  );
}

// ---------------------------------------------------------------------------
// Countdown formatter
// ---------------------------------------------------------------------------

function formatCountdown(parts: { days: number; hours: number; minutes: number; seconds: number; expired: boolean }): string {
  if (parts.expired) return 'Started';
  if (parts.days > 0) return `${parts.days}d ${parts.hours}h`;
  if (parts.hours > 0) return `${parts.hours}h ${parts.minutes}m`;
  return `${parts.minutes}m ${parts.seconds}s`;
}

// Full-granularity variant for the prediction eyebrow (U20.7): always shows all
// four parts and ticks the seconds, e.g. "7d 21h 14m 32s".
function formatCountdownFull(parts: { days: number; hours: number; minutes: number; seconds: number; expired: boolean }): string {
  if (parts.expired) return 'Started';
  return `${parts.days}d ${parts.hours}h ${parts.minutes}m ${parts.seconds}s`;
}

// ---------------------------------------------------------------------------
// Prediction card — a single match with editable score inputs.
//
// Shared by the Predictions page (group panels) and the home upcoming-matches
// carousel. Presentation only: all editing behaviour lives in the parent via
// the onHomeChange / onAwayChange callbacks (see usePredictionEditor).
// ---------------------------------------------------------------------------

export interface PredictionCardProps {
  match: MatchResponse;
  prediction: PredictionResponse | undefined;
  local: LocalPrediction | undefined;
  timezone: string;
  highlighted: boolean;
  onHomeChange: (matchId: string, value: string) => void;
  onAwayChange: (matchId: string, value: string) => void;
  /**
   * Space-constrained contexts (the home carousel) render team codes — "🇲🇽 MEX"
   * — instead of full names, which truncate to 2–3 chars in a narrow card and
   * become ambiguous (South Africa vs South Korea both show "So…"). Defaults to
   * full names so the Predictions page is unchanged.
   */
  compact?: boolean;
  knockoutPrediction?: KnockoutPredictionResponse;
  onKnockoutWinnerChange?: (matchId: string, winnerId: string) => void;
}

export function PredictionCard({
  match,
  prediction,
  local,
  timezone,
  highlighted,
  onHomeChange,
  onAwayChange,
  compact = false,
  knockoutPrediction,
  onKnockoutWinnerChange,
}: PredictionCardProps) {
  const kickoffLocal = formatInTimeZone(
    new Date(match.kickoff_utc),
    timezone,
    'EEE d MMM, HH:mm',
  );

  const countdown = useCountdown(match.kickoff_utc);
  const prefersReducedMotion = useReducedMotion();

  const editable = canEdit(match);
  const isVoided = match.status === 'cancelled' || match.status === 'postponed';
  const isCompleted = match.status === 'completed';
  const isLocked = match.status === 'locked';
  const isLive = match.status === 'live';
  const hasLiveScore =
    match.actual_home_score !== null && match.actual_away_score !== null;

  // Deadline warning: scheduled + < 1hr remaining
  const isDeadlineWarning =
    match.status === 'scheduled' &&
    !countdown.expired &&
    countdown.days === 0 &&
    countdown.hours === 0;

  const flag = (emoji: string) => (emoji ? `${emoji} ` : '');
  const homeLabel = match.home_team
    ? `${flag(match.home_team.flag_emoji)}${compact ? match.home_team.code : match.home_team.name}`
    : shortPlaceholder(match.home_team_placeholder);
  const awayLabel = match.away_team
    ? `${flag(match.away_team.flag_emoji)}${compact ? match.away_team.code : match.away_team.name}`
    : shortPlaceholder(match.away_team_placeholder);
  const homeTitle = !match.home_team ? (match.home_team_placeholder ?? undefined) : undefined;
  const awayTitle = !match.away_team ? (match.away_team_placeholder ?? undefined) : undefined;

  const homeVal = local?.home ?? (prediction?.predicted_home !== null && prediction?.predicted_home !== undefined ? String(prediction.predicted_home) : '');
  const awayVal = local?.away ?? (prediction?.predicted_away !== null && prediction?.predicted_away !== undefined ? String(prediction.predicted_away) : '');

  const points = prediction?.points_awarded ?? null;
  const noSubmission = isCompleted && !prediction;

  // Knockout progression logic
  const isKnockout = match.stage !== 'group';
  const hScore = homeVal === '' ? null : Number(homeVal);
  const aScore = awayVal === '' ? null : Number(awayVal);
  const hasScore = hScore !== null && aScore !== null;
  const isDraw = hasScore && hScore === aScore;
  const autoWinnerId = isKnockout && hasScore && hScore !== aScore
    ? (hScore! > aScore! ? match.home_team?.id : match.away_team?.id) ?? null
    : null;

  // A complete prediction has both scores entered.
  // For knockout draws, also requires a who-progresses pick.
  const hasPrediction = homeVal !== '' && awayVal !== ''
    && !(isKnockout && isDraw && !knockoutPrediction?.predicted_winner_id);

  // The who-progresses buttons are interactive only when the player can still
  // change the pick. A clear 90-min win fixes the progressor from the score, so
  // both buttons become read-only — tapping the losing team must not overwrite
  // the auto-saved winner and silently cost the player their progression points
  // (the scoring trigger grades knockout picks purely on predicted_winner_id).
  const winnerPickable = editable && autoWinnerId === null;

  // Auto-save the knockout winner when score settles on a clear win (debounced).
  const prevSentWinnerId = useRef<string | null>(null);
  useEffect(() => {
    if (!isKnockout || !onKnockoutWinnerChange || !autoWinnerId) {
      prevSentWinnerId.current = null;
      return;
    }
    if (autoWinnerId === knockoutPrediction?.predicted_winner_id) return;
    if (autoWinnerId === prevSentWinnerId.current) return;
    const timer = setTimeout(() => {
      prevSentWinnerId.current = autoWinnerId;
      onKnockoutWinnerChange(match.id, autoWinnerId);
    }, 800);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoWinnerId, knockoutPrediction?.predicted_winner_id]);

  return (
    <motion.div
      className={cn(
        'flex h-full flex-col rounded-lg border bg-surface p-4 transition-all',
        isVoided && 'opacity-50',
        isDeadlineWarning
          ? 'border-warning/60'
          : highlighted
            ? 'border-primary shadow-glow'
            : 'border-border',
      )}
      data-testid={`prediction-card-${match.id}`}
      animate={highlighted && !prefersReducedMotion ? { scale: [1, 1.02, 1] } : {}}
      transition={{ duration: 0.4 }}
    >
      {/* Eyebrow row: kickoff time with countdown beneath it + status pills */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <span className="block font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
            {kickoffLocal}
          </span>
          {editable && !countdown.expired && (
            <span
              className={cn(
                'mt-1 flex items-center gap-1 whitespace-nowrap font-mono text-sm tabular-nums',
                isDeadlineWarning ? 'text-warning font-semibold' : 'text-success',
              )}
              data-testid={isDeadlineWarning ? 'deadline-warning' : undefined}
            >
              <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {formatCountdownFull(countdown)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isCompleted && points !== null && !noSubmission && (
            <PointsBadge points={points} breakdown={prediction?.points_breakdown} />
          )}
          {isCompleted && noSubmission && <Badge variant="muted">No entry</Badge>}
          {/* Live carries its own green pulse in the footer (U20.6) — skip the
              red status pill so the two don't clash. */}
          {!isLive && (
            <Badge variant={statusVariant(match.status)}>{statusLabel(match.status)}</Badge>
          )}
        </div>
      </div>

      {/* Teams + score inputs */}
      {isKnockout && (
        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-text-muted mb-1.5 text-center">
          90-min score
        </p>
      )}
      <div className="flex items-center gap-3">
        <div
          title={homeTitle}
          className={cn(
            'flex-1 text-sm font-sans text-text-primary truncate text-right',
            homeTitle && 'italic text-text-muted font-mono text-xs',
          )}
        >
          {homeLabel}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <ScoreInput
            value={homeVal}
            onChange={(v) => onHomeChange(match.id, v)}
            disabled={!editable}
            aria-label={`Home score for match ${match.match_number}`}
          />
          <span className="text-text-muted font-mono text-base self-center pt-1">–</span>
          <ScoreInput
            value={awayVal}
            onChange={(v) => onAwayChange(match.id, v)}
            disabled={!editable}
            aria-label={`Away score for match ${match.match_number}`}
          />
        </div>
        <div
          title={awayTitle}
          className={cn(
            'flex-1 text-sm font-sans text-text-primary truncate',
            awayTitle && 'italic text-text-muted font-mono text-xs',
          )}
        >
          {awayLabel}
        </div>
      </div>

      {/* Who progresses — knockout matches with known teams */}
      {isKnockout && match.home_team && match.away_team && (
        <div className="mt-3 pt-3 border-t border-border/50">
          <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-text-muted mb-2 text-center">
            Who progresses{hasScore && hScore === aScore ? ' — draw: tap to pick' : ''}
          </p>
          <div className="flex gap-2">
            {([
              { team: match.home_team, isHome: true },
              { team: match.away_team, isHome: false },
            ] as const).map(({ team }) => {
              const isAuto = autoWinnerId === team.id;
              const isManual = !autoWinnerId && knockoutPrediction?.predicted_winner_id === team.id;
              const isSelected = isAuto || isManual;
              const baseLabel = compact
                ? `${team.flag_emoji} ${team.code}`
                : `${team.flag_emoji} ${team.name}`;
              const label = isSelected ? `✓ ${baseLabel}` : baseLabel;
              return (
                <button
                  key={team.id}
                  type="button"
                  disabled={!winnerPickable}
                  onClick={() => onKnockoutWinnerChange?.(match.id, team.id)}
                  className={cn(
                    'flex-1 rounded-md px-2 py-2 text-xs font-sans transition-colors text-center truncate',
                    isSelected
                      ? 'bg-success/30 border-2 border-success text-success font-bold shadow-sm cursor-default'
                      : winnerPickable
                        ? 'bg-surface-elevated border border-border text-text-muted hover:border-primary/50 hover:text-text-primary cursor-pointer'
                        : 'bg-surface border border-border/40 text-text-muted/60',
                  )}
                  aria-pressed={isSelected}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {hasScore && hScore === aScore && !knockoutPrediction?.predicted_winner_id && editable && (
            <p className="mt-1.5 text-[10px] font-sans text-warning text-center">
              Tap above to pick who goes through
            </p>
          )}
        </div>
      )}

      {/* Footer states — mt-auto pushes this to the bottom so all cards share
          the same height regardless of status. */}
      <div className="mt-auto">
      {isLocked && (
        <div
          className="mt-3 flex items-center justify-center gap-1.5 text-xs font-sans text-warning"
          data-testid="lock-indicator"
        >
          <Lock size={12} aria-hidden="true" />
          <span>Kicks off in {formatCountdown(countdown)}</span>
        </div>
      )}

      {/* Live: green pulse badge + current score (prediction stays visible in the
          disabled inputs above). U20.6 */}
      {isLive && (
        <div
          className="mt-3 flex items-center justify-center gap-2 font-mono text-xs"
          data-testid="live-indicator"
        >
          <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-[0.2em] text-success">
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            Live
          </span>
          {hasLiveScore && (
            <span className="tabular-nums text-text-secondary">
              Now {match.actual_home_score}–{match.actual_away_score}
            </span>
          )}
        </div>
      )}

      {/* Uniform scheduled footer: prediction status, centered. A single
          always-present row keeps every open card the same height. */}
      {editable && (
        <div className="mt-3 text-center">
          {hasPrediction ? (
            <span
              className="font-mono text-xs uppercase tracking-[0.2em] text-success"
              data-testid="predicted-indicator"
            >
              Predicted
            </span>
          ) : (
            <span
              className="font-mono text-xs uppercase tracking-[0.2em] text-warning"
              data-testid="not-predicted-warning"
            >
              Not predicted yet
            </span>
          )}
        </div>
      )}

      {isCompleted && match.actual_home_score !== null && match.actual_away_score !== null && (
        <div className="mt-3 flex items-center justify-center gap-1.5 text-xs font-mono text-text-muted tabular-nums">
          <span>Result:</span>
          <MatchResult match={match} />
        </div>
      )}

      {match.status === 'postponed' && match.postponed_reason && (
        <p className="mt-3 text-xs font-sans text-text-muted text-center">
          {match.postponed_reason}
        </p>
      )}
      </div>{/* end footer */}
    </motion.div>
  );
}
