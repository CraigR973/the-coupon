import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { formatCalendarDate } from '@/lib/time';
import type { AdminSeasonCalendar } from '@/lib/types';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AdminNav } from './AdminNav';

const QUERY_KEY = ['admin', 'season-calendar'] as const;

export function CalendarPage() {
  const queryClient = useQueryClient();
  const [anchor, setAnchor] = useState('');
  const [extraDate, setExtraDate] = useState('');
  const [saving, setSaving] = useState(false);
  const { data, isLoading, isError, error } = useQuery<AdminSeasonCalendar>({
    queryKey: QUERY_KEY,
    queryFn: () => apiFetch<AdminSeasonCalendar>('/api/v1/admin/calendar'),
    retry: false,
  });

  useEffect(() => {
    if (data) setAnchor(data.week_one_anchor);
  }, [data]);

  const extras = useMemo(() => data?.weeks.filter((week) => week.is_extra) ?? [], [data]);

  async function saveAnchor(event: React.FormEvent) {
    event.preventDefault();
    if (!data || !anchor) return;
    setSaving(true);
    try {
      const next = await apiFetch<AdminSeasonCalendar>('/api/v1/admin/calendar/anchor', {
        method: 'PUT',
        body: JSON.stringify({ season: data.season, week_one_anchor: anchor }),
      });
      queryClient.setQueryData(QUERY_KEY, next);
      toast.success('Season anchor updated');
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : 'Could not update the anchor');
    } finally {
      setSaving(false);
    }
  }

  async function addExtra(event: React.FormEvent) {
    event.preventDefault();
    if (!data || !extraDate) return;
    setSaving(true);
    try {
      const next = await apiFetch<AdminSeasonCalendar>('/api/v1/admin/calendar/extra-weeks', {
        method: 'POST',
        body: JSON.stringify({ season: data.season, starts_on: extraDate }),
      });
      queryClient.setQueryData(QUERY_KEY, next);
      setExtraDate('');
      toast.success('Extra week declared for every league');
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : 'Could not add the extra week');
    } finally {
      setSaving(false);
    }
  }

  async function withdraw(startsOn: string) {
    if (!data) return;
    setSaving(true);
    try {
      const next = await apiFetch<AdminSeasonCalendar>('/api/v1/admin/calendar/extra-weeks', {
        method: 'DELETE',
        body: JSON.stringify({ season: data.season, starts_on: startsOn }),
      });
      queryClient.setQueryData(QUERY_KEY, next);
      toast.success('Extra week withdrawn');
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : 'Could not withdraw the week');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader eyebrow="Site admin" title="Calendar" />
      <AdminNav />

      {isLoading && <p className="font-sans text-sm text-text-muted">Loading calendar…</p>}
      {isError && (
        <EmptyState
          title="Season calendar not ready"
          description={
            error instanceof Error
              ? error.message
              : 'Deploy the Batch 113 API and apply its reviewed calendar backfill.'
          }
        />
      )}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-primary" aria-hidden />
                {data.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="font-sans text-sm leading-relaxed text-text-muted">
                One calendar names every league’s football week. Friday through Tuesday
                sits beside the same canonical Saturday.
              </p>
              <form onSubmit={saveAnchor} className="space-y-2">
                <Label htmlFor="season-anchor">Week 1 Saturday</Label>
                <div className="flex flex-wrap gap-2">
                  <Input
                    id="season-anchor"
                    type="date"
                    value={anchor}
                    onChange={(event) => setAnchor(event.target.value)}
                    className="max-w-56"
                  />
                  <Button type="submit" variant="outline" disabled={saving || !anchor}>
                    Save anchor
                  </Button>
                </div>
                <p className="font-sans text-xs text-text-muted">
                  Once any round in the season settles, the anchor cannot move.
                </p>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Extra weeks</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="font-sans text-sm leading-relaxed text-text-muted">
                A declared date is offered to every league by the daily discovery run.
                A league whose competitions have no fixtures that day gets no empty round.
              </p>
              <form onSubmit={addExtra} className="flex flex-wrap items-end gap-2">
                <div className="space-y-2">
                  <Label htmlFor="extra-week">Date</Label>
                  <Input
                    id="extra-week"
                    type="date"
                    value={extraDate}
                    onChange={(event) => setExtraDate(event.target.value)}
                    className="max-w-56"
                  />
                </div>
                <Button type="submit" disabled={saving || !extraDate}>
                  <Plus className="h-4 w-4" aria-hidden />
                  Declare for every league
                </Button>
              </form>

              {extras.length === 0 ? (
                <p className="font-sans text-sm text-text-muted">No extra weeks declared.</p>
              ) : (
                <ul className="space-y-2">
                  {extras.map((week) => (
                    <li
                      key={week.starts_on}
                      className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
                    >
                      <span className="min-w-0">
                        <span className="block font-sans text-sm text-text-primary">
                          {formatCalendarDate(week.starts_on, 'EEEE d MMMM yyyy')}
                        </span>
                        <Badge variant="muted">Gameweek {week.label}</Badge>
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={saving}
                        onClick={() => void withdraw(week.starts_on)}
                        aria-label={`Withdraw ${week.starts_on}`}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                        Withdraw
                      </Button>
                    </li>
                  ))}
                </ul>
              )}

              <details className="rounded-lg border border-border px-3 py-2">
                <summary className="cursor-pointer font-sans text-sm text-text-secondary">
                  View all {data.weeks.length} calendar dates
                </summary>
                <ol className="mt-3 grid gap-1 sm:grid-cols-2">
                  {data.weeks.map((week) => (
                    <li key={`${week.starts_on}-${week.label}`} className="font-sans text-xs text-text-muted">
                      Gameweek {week.label} · {formatCalendarDate(week.starts_on, 'd MMM yyyy')}
                      {week.is_extra ? ' · extra' : ''}
                    </li>
                  ))}
                </ol>
              </details>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
