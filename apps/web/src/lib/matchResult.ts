export interface ResultPhase {
  /** "90'", "AET", "Pens", or null for a plain single-line result. */
  label: string | null;
  home: number;
  away: number;
}

/**
 * The result-bearing fields shared by `MatchResponse` and the admin
 * `AdminMatchResult` row — the only inputs these helpers need.
 */
export interface MatchResultLike {
  actual_home_score: number | null;
  actual_away_score: number | null;
  extra_time: boolean;
  penalties: boolean;
  extra_time_home_score?: number | null;
  extra_time_away_score?: number | null;
  penalty_home_score?: number | null;
  penalty_away_score?: number | null;
}

/**
 * Break a completed match into the scorelines to display: the 90-minute score
 * plus, when applicable, the extra-time and penalty-shootout lines.
 *
 * - Returns `[]` when there is no final score to show (not completed / no score).
 * - A match decided inside 90 minutes yields a single, unlabelled phase, so it
 *   renders exactly as a plain "H – A" with no extra chrome.
 * - A match that went to extra time or penalties yields labelled phases:
 *   `90'` always, `AET` when it went to extra time, and `Pens` when there was a
 *   shootout and we know the tally.
 *
 * Prediction scoring is unaffected — it keys off the 90-minute `actual_*_score`
 * only. These phases are purely for display.
 */
export function matchResultPhases(match: MatchResultLike): ResultPhase[] {
  const h = match.actual_home_score;
  const a = match.actual_away_score;
  if (h == null || a == null) return [];

  if (!match.extra_time && !match.penalties) {
    return [{ label: null, home: h, away: a }];
  }

  const phases: ResultPhase[] = [{ label: "90'", home: h, away: a }];

  if (match.extra_time) {
    // Fall back to the 90' score if the ET scoreline wasn't captured (e.g. a
    // goalless extra time recorded only via the flag).
    phases.push({
      label: 'AET',
      home: match.extra_time_home_score ?? h,
      away: match.extra_time_away_score ?? a,
    });
  }

  if (
    match.penalties &&
    match.penalty_home_score != null &&
    match.penalty_away_score != null
  ) {
    phases.push({
      label: 'Pens',
      home: match.penalty_home_score,
      away: match.penalty_away_score,
    });
  }

  return phases;
}

/**
 * One-line summary of a result, e.g. "1 – 1" or "90' 1–1 · AET 1–1 · Pens 3–4".
 * For tight layouts (bracket cells) and aria labels. Empty string when there is
 * no result.
 */
export function formatMatchResultLine(match: MatchResultLike): string {
  const phases = matchResultPhases(match);
  if (phases.length === 0) return '';
  if (phases.length === 1) return `${phases[0].home} – ${phases[0].away}`;
  return phases.map((p) => `${p.label} ${p.home}–${p.away}`).join(' · ');
}

/**
 * The extra-time / penalty phases as a compact one-line note, excluding the 90'
 * score — e.g. "AET 1–1 · Pens 3–4". Empty string when the match was decided in
 * 90 minutes. For layouts that already show the 90' score inline (bracket cells,
 * the knockout picker) and just need the rest.
 */
export function matchResultExtraLine(match: MatchResultLike): string {
  return matchResultPhases(match)
    .filter((p) => p.label === 'AET' || p.label === 'Pens')
    .map((p) => `${p.label} ${p.home}–${p.away}`)
    .join(' · ');
}
