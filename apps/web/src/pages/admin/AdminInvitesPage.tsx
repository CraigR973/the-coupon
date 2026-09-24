import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Ban } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { AdminInvite } from '@/lib/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { AdminNav } from './AdminNav';

const INVITES_KEY = ['admin-invites'];

/**
 * Every invite in the product, live and spent.
 *
 * The league-admin screen already lists one league's *active* invites. This one is
 * cross-league and keeps the claimed ones, because the question it answers is "who let
 * this person in", which an active-only view cannot.
 */
export function InvitesPage() {
  const queryClient = useQueryClient();
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const { data: invites, isLoading } = useQuery<AdminInvite[]>({
    queryKey: INVITES_KEY,
    queryFn: () => apiFetch<AdminInvite[]>('/api/v1/admin/invites'),
  });

  async function revoke(invite: AdminInvite) {
    setRevokingId(invite.id);
    try {
      await apiFetch(`/api/v1/admin/invites/${invite.id}`, { method: 'DELETE' });
      toast.success('Invite revoked — that link stops working now');
      void queryClient.invalidateQueries({ queryKey: INVITES_KEY });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not revoke that invite');
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="Invites" />
      <AdminNav />

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : !invites?.length ? (
        <p className="font-sans text-sm text-text-secondary">No invites have been created yet.</p>
      ) : (
        <ul className="space-y-2">
          {invites.map((invite) => (
            <li key={invite.id}>
              <Card>
                <CardContent className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-sans font-semibold text-text-primary">
                      {invite.league_name}
                    </span>
                    {invite.claimed_by_name ? (
                      <Badge variant="muted">Claimed</Badge>
                    ) : invite.is_active ? (
                      <Badge>Open</Badge>
                    ) : (
                      <Badge variant="error">Revoked</Badge>
                    )}
                  </div>
                  <p className="mt-1 font-sans text-xs text-text-secondary">
                    {invite.created_by_name
                      ? `Created by ${invite.created_by_name}`
                      : 'Created by a deleted member'}
                    {invite.display_name_hint && ` · for ${invite.display_name_hint}`}
                    {invite.claimed_by_name && ` · claimed by ${invite.claimed_by_name}`}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-text-muted break-all">
                    /join/{invite.token}
                  </p>

                  {invite.is_active && !invite.claimed_by_name && (
                    <div className="mt-3">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={revokingId === invite.id}
                        onClick={() => void revoke(invite)}
                      >
                        <Ban className="mr-1.5 h-4 w-4" aria-hidden />
                        Revoke
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
