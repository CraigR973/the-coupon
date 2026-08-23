import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { AdminLeague } from '@/lib/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { AdminNav } from './AdminNav';

const LEAGUES_KEY = ['admin-leagues'];

const PRIVACY_LABEL: Record<AdminLeague['privacy'], string> = {
  public_open: 'Open',
  public_request: 'By request',
  private: 'Private',
};

/**
 * Every league, including the ones the admin is not a member of.
 *
 * That is the whole point of the screen: a site admin is in no league by default, so
 * without this there is no way to see one they were never invited to — and the join code
 * they would need to rotate is only served to members.
 */
export function AllLeaguesPage() {
  const queryClient = useQueryClient();
  const [rotatingId, setRotatingId] = useState<string | null>(null);

  const { data: leagues, isLoading } = useQuery<AdminLeague[]>({
    queryKey: LEAGUES_KEY,
    queryFn: () => apiFetch<AdminLeague[]>('/api/v1/admin/leagues'),
  });

  async function rotate(league: AdminLeague) {
    if (
      !window.confirm(
        `Generate a new join code for ${league.name}? The old link stops working immediately.`,
      )
    ) {
      return;
    }
    setRotatingId(league.id);
    try {
      await apiFetch<{ join_code: string }>(
        `/api/v1/admin/leagues/${league.id}/rotate-join-code`,
        { method: 'POST' },
      );
      toast.success('New join code generated');
      void queryClient.invalidateQueries({ queryKey: LEAGUES_KEY });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not rotate that join code');
    } finally {
      setRotatingId(null);
    }
  }

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="All leagues" />
      <AdminNav />

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : !leagues?.length ? (
        <p className="font-sans text-sm text-text-secondary">No leagues yet.</p>
      ) : (
        <ul className="space-y-2">
          {leagues.map((league) => (
            <li key={league.id}>
              <Card>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-sans font-semibold text-text-primary">
                      {league.name}
                    </span>
                    <Badge variant="muted">{PRIVACY_LABEL[league.privacy]}</Badge>
                    {league.deleted_at && <Badge variant="error">Deleted</Badge>}
                  </div>
                  <p className="mt-1 font-sans text-xs text-text-secondary">
                    {league.member_count} of {league.max_members} members · /{league.slug}
                  </p>
                  {league.join_code && (
                    <p className="mt-1 font-mono text-[11px] tracking-widest text-text-muted">
                      {league.join_code}
                    </p>
                  )}

                  {!league.deleted_at && (
                    <div className="mt-3">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={rotatingId === league.id}
                        onClick={() => void rotate(league)}
                      >
                        <RefreshCw className="mr-1.5 h-4 w-4" aria-hidden />
                        New join code
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
