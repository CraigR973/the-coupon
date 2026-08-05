import { useOptionalAuth } from '../contexts/AuthContext';
import type { OddsFormat } from '../lib/types';

/**
 * The signed-in member's odds notation, defaulting to decimal.
 *
 * Deliberately tolerant of a missing AuthProvider: this only decides how a
 * price is spelled, so a presentational component that renders outside the
 * provider should show decimal rather than crash. The same default covers
 * sessions stored before the preference existed, whose cached player object has
 * no `oddsFormat` until the next login.
 */
export function useOddsFormat(): OddsFormat {
  return useOptionalAuth()?.player?.oddsFormat ?? 'decimal';
}
