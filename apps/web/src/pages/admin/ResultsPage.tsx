import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import type { AdminPendingRound } from '@/lib/types';
import { formatCalendarDate, formatInstant } from '@/lib/time';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { AdminNav } from './AdminNav';

const PENDING_KEY = ['admin-pending-results'];

type Entry = { home: string; away: string; void: boolean };

function when(iso: string): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  return formatInstant(iso, zone, 'EEE d MMM HH:mm') ?? iso;
}

/**
 * Enter the results a round is stuck waiting for.
 *
 * A round reaches this screen because the odds provider never resolved something —
 * Batch 64's phantom Scottish Premiership round is the worked example — and that state
 * does not clear itself: the settle sweep runs three times a day and finds nothing to do.
 *
 * An admin types a **scoreline**, not a set of market verdicts. Both markets follow from
 * it, and the score goes into the same `settle_gameweek` the scheduler settles on, so a
 * hand-entered result and a provider-supplied one write identical rows.
 */
export function AdminResultsPage() {
  const queryClient = useQueryClient();
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const { data: rounds, isLoading } = useQuery<AdminPendingRound[]>({
    queryKey: PENDING_KEY,
    queryFn: () => apiFetch<AdminPendingRound[]>('/api/v1/admin/results/pending'),
  });

  function entryFor(fixtureId: string): Entry {
    return entries[fixtureId] ?? { home: '', away: '', void: false };
  }

  function update(fixtureId: string, patch: Partial<Entry>) {
    setEntries((current) => ({ ...current, [fixtureId]: { ...entryFor(fixtureId), ...patch } }));
  }

  async function settle(round: AdminPendingRound) {
    const results = round.fixtures
      .map((fixture) => {
        const entry = entryFor(fixture.fixture_id);
        if (entry.void) return { fixture_id: fixture.fixture_id, void: true };
        if (entry.home === '' || entry.away === '') return null;
        return {
          fixture_id: fixture.fixture_id,
          home_goals: Number(entry.home),
          away_goals: Number(entry.away),
        };
      })
      .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

    if (results.length === 0) {
      toast.error('Enter at least one result first');
      return;
    }

    setSaving(round.gameweek_id);
    try {
      const outcome = await apiFetch<{ picks_resolved: number; settled: boolean }>(
        `/api/v1/admin/results/${round.gameweek_id}/settle`,
        { method: 'POST', body: JSON.stringify({ results }) },
      );
      toast.success(
        `${outcome.picks_resolved} pick(s) scored` +
          (outcome.settled ? ' — the round is settled' : ' — some are still pending'),
      );
      void queryClient.invalidateQueries({ queryKey: PENDING_KEY });
      void queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not settle that round');
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="Results" />
      <AdminNav />

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : !rounds?.length ? (
        <p className="font-sans text-sm text-text-secondary">
          Nothing is waiting on a result — every locked round has settled.
        </p>
      ) : (
        <ul className="space-y-4">
          {rounds.map((round) => (
            <li key={round.gameweek_id}>
              <Card>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-sans font-semibold text-text-primary">
                      {round.league_name}
                    </span>
                    <Badge variant="muted">{formatCalendarDate(round.starts_on, 'd MMM')}</Badge>
                    <span className="font-sans text-xs text-text-muted">
                      locked {when(round.locks_at_utc)}
                    </span>
                  </div>

                  <ul className="mt-3 space-y-3">
                    {round.fixtures.map((fixture) => {
                      const entry = entryFor(fixture.fixture_id);
                      return (
                        <li key={fixture.fixture_id} className="space-y-1">
                          <p className="font-sans text-sm text-text-primary">
                            {fixture.home} v {fixture.away}
                          </p>
                          <p className="font-sans text-xs text-text-muted">
                            {fixture.competition} · {fixture.pending_picks} pending pick(s)
                          </p>
                          <div className="flex items-center gap-2">
                            <Input
                              aria-label={`${fixture.home} goals`}
                              inputMode="numeric"
                              className="w-16"
                              disabled={entry.void}
                              value={entry.home}
                              onChange={(e) =>
                                update(fixture.fixture_id, {
                                  home: e.target.value.replace(/\D/g, '').slice(0, 2),
                                })
                              }
                            />
                            <span className="font-mono text-text-muted">–</span>
                            <Input
                              aria-label={`${fixture.away} goals`}
                              inputMode="numeric"
                              className="w-16"
                              disabled={entry.void}
                              value={entry.away}
                              onChange={(e) =>
                                update(fixture.fixture_id, {
                                  away: e.target.value.replace(/\D/g, '').slice(0, 2),
                                })
                              }
                            />
                            <label className="flex items-center gap-1.5 font-sans text-xs text-text-secondary">
                              <input
                                type="checkbox"
                                checked={entry.void}
                                onChange={(e) =>
                                  update(fixture.fixture_id, { void: e.target.checked })
                                }
                              />
                              {/* Void is not a loss: a member whose game was called off
                                  keeps their record intact, exactly as a provider-voided
                                  fixture already behaves. */}
                              Not played
                            </label>
                          </div>
                        </li>
                      );
                    })}
                  </ul>

                  <div className="mt-4">
                    <Button
                      size="sm"
                      disabled={saving !== null}
                      onClick={() => void settle(round)}
                    >
                      {saving === round.gameweek_id ? 'Settling…' : 'Settle round'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
