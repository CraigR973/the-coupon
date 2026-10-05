import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import type { AdminFixtureCorrection, AdminPendingRound, AdminSettledFixture } from '@/lib/types';
import { formatCalendarDate, formatInstant } from '@/lib/time';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { AdminNav } from './AdminNav';

const PENDING_KEY = ['admin-pending-results'];
const SETTLED_KEY = ['admin-settled-fixtures'];

type Entry = { home: string; away: string; void: boolean };
type Correction = Entry & { reason: string };

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

      <CorrectSettledResult />
    </div>
  );
}

/** What the admin is told a correction did — the only feedback before the coupon reloads. */
function correctionSummary(outcome: AdminFixtureCorrection): string {
  if (outcome.changed.length === 0) {
    return 'Nothing changed — every settled pick already had that result';
  }
  const leagues = outcome.leagues_audited.length;
  return (
    `${outcome.changed.length} pick(s) re-scored across ${leagues} league(s)` +
    ` · ${outcome.members_told} member(s) told`
  );
}

/**
 * Correct a fixture the provider settled wrongly — once, for every league (Batch 187).
 *
 * Owner decision, 2026-09-30: per fixture, across every league. The old tool corrected
 * one pick by an id nothing on screen showed, so a wrong result meant a database read,
 * and fixing one member's pick left everyone else on the same match with the old answer.
 * The admin picks the match, enters the true score (or that it was not played) and a
 * reason; the API re-scores every settled pick on it, audits each league and tells each
 * member whose result moved.
 */
function CorrectSettledResult() {
  const queryClient = useQueryClient();
  // Closed until asked for: a correction is rare, and the list of every settled match in
  // the last sixty days is not what this screen is for on an ordinary Saturday.
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Record<string, Correction>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const { data: fixtures, isLoading } = useQuery<AdminSettledFixture[]>({
    queryKey: SETTLED_KEY,
    queryFn: () => apiFetch<AdminSettledFixture[]>('/api/v1/admin/results/settled-fixtures'),
    enabled: open,
  });

  function entryFor(fixtureId: string): Correction {
    return entries[fixtureId] ?? { home: '', away: '', void: false, reason: '' };
  }

  function update(fixtureId: string, patch: Partial<Correction>) {
    setEntries((current) => ({ ...current, [fixtureId]: { ...entryFor(fixtureId), ...patch } }));
  }

  async function correct(fixture: AdminSettledFixture) {
    const entry = entryFor(fixture.fixture_id);
    if (!entry.void && (entry.home === '' || entry.away === '')) {
      toast.error('Enter the final score, or mark it not played');
      return;
    }
    if (entry.reason.trim().length < 3) {
      toast.error('Say why the result is being corrected');
      return;
    }
    const result = entry.void
      ? { void: true }
      : { home_goals: Number(entry.home), away_goals: Number(entry.away) };

    setSaving(fixture.fixture_id);
    try {
      const outcome = await apiFetch<AdminFixtureCorrection>(
        `/api/v1/admin/fixtures/${fixture.fixture_id}/correct`,
        { method: 'POST', body: JSON.stringify({ ...result, reason: entry.reason.trim() }) },
      );
      toast.success(correctionSummary(outcome));
      void queryClient.invalidateQueries({ queryKey: SETTLED_KEY });
      void queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not correct that result');
    } finally {
      setSaving(null);
    }
  }

  return (
    <section className="mt-8" aria-labelledby="correct-heading">
      <h2 id="correct-heading" className="font-sans text-base font-semibold text-text-primary">
        Correct a settled result
      </h2>
      <p className="mt-1 font-sans text-sm text-text-secondary">
        Every settled pick on the match is re-scored, in every league, and each member whose
        result changes is told.
      </p>

      {!open ? (
        <Button
          size="sm"
          variant="outline"
          className="mt-3"
          aria-expanded={false}
          onClick={() => setOpen(true)}
        >
          Find a match to correct
        </Button>
      ) : isLoading ? (
        <Skeleton className="mt-3 h-32 w-full" />
      ) : !fixtures?.length ? (
        <p className="mt-3 font-sans text-sm text-text-secondary">
          No settled matches in the last 60 days.
        </p>
      ) : (
        <ul className="mt-3 space-y-3" data-testid="settled-fixtures">
          {fixtures.map((fixture) => {
            const entry = entryFor(fixture.fixture_id);
            return (
              <li key={fixture.fixture_id}>
                <Card>
                  <CardContent className="space-y-2 p-4">
                    <p className="font-sans text-sm font-medium text-text-primary">
                      {fixture.home} v {fixture.away}
                    </p>
                    <p className="font-sans text-xs text-text-muted">
                      {fixture.competition} · {when(fixture.kickoff_utc)} ·{' '}
                      {fixture.settled_picks} settled pick(s) · {fixture.leagues.join(', ')}
                    </p>
                    <div className="flex items-center gap-2">
                      <Input
                        aria-label={`${fixture.home} final goals`}
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
                        aria-label={`${fixture.away} final goals`}
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
                          onChange={(e) => update(fixture.fixture_id, { void: e.target.checked })}
                        />
                        Not played
                      </label>
                    </div>
                    <Input
                      aria-label={`Why ${fixture.home} v ${fixture.away} is being corrected`}
                      placeholder="Why it is being corrected"
                      maxLength={500}
                      value={entry.reason}
                      onChange={(e) => update(fixture.fixture_id, { reason: e.target.value })}
                    />
                    <Button
                      size="sm"
                      disabled={saving !== null}
                      onClick={() => void correct(fixture)}
                    >
                      {saving === fixture.fixture_id ? 'Correcting…' : 'Correct result'}
                    </Button>
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
