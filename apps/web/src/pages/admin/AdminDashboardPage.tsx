import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { AdminDashboard } from '@/lib/types';
import { formatInstant } from '@/lib/time';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { cn } from '@/lib/utils';
import { AdminNav } from './AdminNav';

/** Every instant on this screen is operational, so it reads in the admin's own zone. */
function when(iso: string | null): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  return formatInstant(iso, zone, 'EEE d MMM HH:mm') ?? '—';
}

/**
 * Everything an admin checks on a Saturday morning, in one read.
 *
 * Read-only by design — nothing here triggers a job, spends a provider request or writes
 * a row — so it is safe to leave open on a second screen while the round plays.
 */
export function AdminDashboardPage() {
  const { data, isLoading } = useQuery<AdminDashboard>({
    queryKey: ['admin-dashboard'],
    queryFn: () => apiFetch<AdminDashboard>('/api/v1/admin/dashboard'),
    refetchInterval: 60_000,
  });

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="Dashboard" />
      <AdminNav />

      {isLoading || !data ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Members" value={data.active_members} />
            <Stat label="Leagues" value={data.leagues} />
            <Stat
              label="Awaiting PIN"
              value={data.members_awaiting_pin}
              hint={data.members_awaiting_pin > 0 ? 'reset, not yet chosen' : undefined}
            />
          </div>

          {/* The state Batch 64's phantom Premiership round sat in: locked, unsettled, and
              nothing about to settle it. It does not clear itself, so it is first. */}
          <Section title="Rounds stuck unsettled">
            {data.stuck_rounds.length === 0 ? (
              <p className="font-sans text-sm text-text-secondary">
                Nothing is waiting on a result.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.stuck_rounds.map((round) => (
                  <li key={round.gameweek_id}>
                    <Card>
                      <CardContent className="p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
                          <span className="font-sans font-semibold text-text-primary">
                            {round.league_name}
                          </span>
                          <Badge variant="warning">{round.pending_picks} pending</Badge>
                        </div>
                        <p className="mt-1 font-sans text-xs text-text-secondary">
                          Locked {when(round.locks_at_utc)} ·{' '}
                          <Link
                            to="/admin/results"
                            className="text-primary underline underline-offset-2"
                          >
                            enter the result
                          </Link>
                        </p>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Next deadline per league">
            {data.upcoming_locks.length === 0 ? (
              <p className="font-sans text-sm text-text-secondary">No round is open yet.</p>
            ) : (
              <ul className="space-y-2">
                {data.upcoming_locks.map((lock) => (
                  <li key={lock.gameweek_id}>
                    <Card>
                      <CardContent className="p-3">
                        <p className="font-sans font-semibold text-text-primary">
                          {lock.league_name}
                        </p>
                        <p className="mt-1 font-sans text-xs text-text-secondary">
                          Locks {when(lock.locks_at_utc)} · {lock.picks_in} of{' '}
                          {lock.members} picked
                        </p>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {/* Batch 114. The plan running down used to be invisible: on 2026-09-05 the
              hourly allowance was gone by 08:06 and the first anyone knew was a member
              being refused a pick. An estimate — this counts what the API process sent —
              but the difference between watching a quota fall and being told about it. */}
          {data.odds_budget && (
            <Section title="Odds provider budget">
              <Card>
                <CardContent className="p-3">
                  {data.odds_budget.rate_limited_for !== null && (
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
                      <Badge variant="warning">
                        Rate limited · holding off {Math.ceil(data.odds_budget.rate_limited_for)}s
                      </Badge>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <Meter
                      label="This hour"
                      used={data.odds_budget.hour_used}
                      limit={data.odds_budget.hour_limit}
                    />
                    <Meter
                      label="Today"
                      used={data.odds_budget.day_used}
                      limit={data.odds_budget.day_limit}
                    />
                  </div>
                  {!data.odds_budget.live && (
                    <p className="mt-2 font-sans text-[11px] text-text-muted">
                      No provider session yet — nothing has been spent since this API
                      process started.
                    </p>
                  )}
                </CardContent>
              </Card>
            </Section>
          )}

          <Section title="Scheduler">
            <Card>
              <CardContent className="p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={data.scheduler.running ? 'success' : 'error'}>
                    {data.scheduler.running ? 'Running' : 'Not running'}
                  </Badge>
                  {data.scheduler.enabled !== data.scheduler.running && (
                    /* The case worth knowing about: configured on, never started. The
                       runbook's answer is the external cron, and Sync is the third way. */
                    <Badge variant="warning">
                      Configured {data.scheduler.enabled ? 'on' : 'off'}
                    </Badge>
                  )}
                </div>
                {data.scheduler.jobs.length > 0 && (
                  <ul className="mt-2 space-y-0.5">
                    {data.scheduler.jobs.map((job) => (
                      <li key={job.id} className="font-mono text-[11px] text-text-muted">
                        {job.id} · {job.next_run_utc ? when(job.next_run_utc) : 'idle'}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </Section>

          <Section title="Recent activity">
            {data.recent_audit.length === 0 ? (
              <p className="font-sans text-sm text-text-secondary">Nothing recorded yet.</p>
            ) : (
              <ul className="space-y-1">
                {data.recent_audit.map((entry) => (
                  <li key={entry.id} className="font-sans text-xs text-text-secondary">
                    <span className="font-mono text-text-muted">
                      {when(entry.timestamp)}
                    </span>{' '}
                    {entry.actor_name ?? 'system'} · {entry.action_type.replaceAll('_', ' ')}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-text-primary">{value}</p>
        {hint && <p className="font-sans text-[11px] text-text-muted">{hint}</p>}
      </CardContent>
    </Card>
  );
}

/**
 * One allowance, as used-of-limit with a bar behind it.
 *
 * A bar rather than a bare number because the question an admin has on a match morning is
 * "have we got enough left", which is a proportion, not a count. The count is there for
 * the runbook.
 */
function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const fraction = limit > 0 ? Math.min(1, used / limit) : 0;
  // The same three bands the cache widens its browse ceiling on, so the screen and the
  // behaviour agree: past half spent it slackens, past three-quarters it slackens again.
  const tone =
    fraction >= 0.75 ? 'bg-error' : fraction >= 0.5 ? 'bg-warning' : 'bg-success';
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">{label}</p>
      <p className="mt-1 font-sans text-sm tabular-nums text-text-primary">
        {used} <span className="text-text-muted">/ {limit || '—'}</span>
      </p>
      <div
        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border"
        role="img"
        aria-label={`${label}: ${used} of ${limit} requests used`}
      >
        <div className={cn('h-full rounded-full', tone)} style={{ width: `${fraction * 100}%` }} />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.25em] text-text-muted">
        {title}
      </h2>
      {children}
    </section>
  );
}
