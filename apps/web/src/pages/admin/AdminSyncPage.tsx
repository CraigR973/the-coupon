import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Play, Zap } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { AdminSyncJob, AdminSyncJobs } from '@/lib/types';
import { formatInstant } from '@/lib/time';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { AdminNav } from './AdminNav';

const JOBS_KEY = ['admin-jobs'];

function when(iso: string | null): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  return formatInstant(iso, zone, 'EEE d MMM HH:mm') ?? 'not scheduled';
}

/**
 * Run a scheduled job now — the same coroutine the scheduler runs.
 *
 * **The cost is on the button, not in the outcome.** odds-api.io allows roughly 100
 * requests an hour across the whole deployment and the scheduler's own jobs are sized
 * against it, so an admin refreshing a slate by hand at 14:00 on a Saturday can 429 the
 * refresh that matters — and exhaustion is silent: picks stay pending and the week never
 * finishes. Anything that reaches the provider says how much of the hour it takes before
 * it is pressed, and confirms.
 */
export function SyncPage() {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState<string | null>(null);

  const { data, isLoading } = useQuery<AdminSyncJobs>({
    queryKey: JOBS_KEY,
    queryFn: () => apiFetch<AdminSyncJobs>('/api/v1/admin/jobs'),
  });

  async function run(job: AdminSyncJob) {
    if (
      job.spends_budget &&
      !window.confirm(
        `${job.label} costs about ${job.provider_requests} of the ${data?.hourly_budget ?? 100} ` +
          'odds-api.io requests this hour, shared with the scheduler. Run it now?',
      )
    ) {
      return;
    }
    setRunning(job.key);
    try {
      const result = await apiFetch<{ key: string; ok: boolean }>(
        `/api/v1/admin/jobs/${job.key}/run`,
        { method: 'POST' },
      );
      // A false answer is a job that ran and failed, not a request that broke. The detail
      // is in the logs the job itself wrote, which is where it belongs.
      if (result.ok) toast.success(`${job.label} finished`);
      else toast.error(`${job.label} ran and reported a failure — check the logs`);
      void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
      void queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not run that job');
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="Sync" />
      <AdminNav />

      {data && (
        <p className="mb-4 font-sans text-xs text-text-secondary">
          The odds provider allows <strong>{data.hourly_budget} requests an hour</strong> across
          the whole app, shared with the scheduler. Manual runs draw on one bucket capped at{' '}
          <span className="font-mono">{data.budget_limit}</span>.
        </p>
      )}

      {isLoading || !data ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <ul className="space-y-2">
          {data.jobs.map((job) => (
            <li key={job.key}>
              <Card>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-sans font-semibold text-text-primary">{job.label}</span>
                    {job.spends_budget ? (
                      <Badge variant="warning">
                        <Zap className="mr-1 h-3 w-3" aria-hidden />~{job.provider_requests}{' '}
                        requests
                      </Badge>
                    ) : (
                      <Badge variant="muted">Free</Badge>
                    )}
                  </div>
                  <p className="mt-1 font-sans text-xs text-text-secondary">{job.summary}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-text-muted">
                    Next scheduled: {when(job.next_run_utc)}
                  </p>
                  <div className="mt-3">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={running !== null}
                      onClick={() => void run(job)}
                    >
                      <Play className="mr-1.5 h-4 w-4" aria-hidden />
                      {running === job.key ? 'Running…' : 'Run now'}
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
