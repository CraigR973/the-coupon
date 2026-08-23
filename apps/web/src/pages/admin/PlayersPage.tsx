import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { KeyRound, LockOpen, Trash2 } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import type { AdminPlayer, AdminResetPinResult } from '@/lib/types';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { AdminNav } from './AdminNav';

const PLAYERS_KEY = ['admin-players'];

/**
 * The screen the PIN-reset notification finally has somewhere to land.
 *
 * Batch 56 pushed every site admin when a member asked for a reset and sent them to
 * `/settings`, because no admin screen existed. The push now carries `?player=<id>`, and
 * that member is filtered to the top of this list on arrival.
 */
export function PlayersPage() {
  const { player: me } = useAuth();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const [search, setSearch] = useState('');
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminPlayer | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState('');

  const { data: players, isLoading } = useQuery<AdminPlayer[]>({
    queryKey: PLAYERS_KEY,
    queryFn: () => apiFetch<AdminPlayer[]>('/api/v1/admin/players'),
  });

  const highlighted = params.get('player');
  const needle = search.trim().toLowerCase();
  const visible = (players ?? [])
    .filter((p) => !needle || p.display_name.toLowerCase().includes(needle))
    .sort((a, b) => {
      if (a.id === highlighted) return -1;
      if (b.id === highlighted) return 1;
      return 0;
    });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: PLAYERS_KEY });
  }

  async function resetPin(target: AdminPlayer) {
    setActingOn(target.id);
    try {
      const result = await apiFetch<AdminResetPinResult>(
        `/api/v1/admin/players/${target.id}/reset-pin`,
        { method: 'POST' },
      );
      // Deliberately no PIN in this message: there is no temporary PIN to read out.
      // The member chooses their own the next time they sign in.
      toast.success(
        `${target.display_name}'s PIN is cleared — they choose a new one at sign-in` +
          (result.sessions_revoked ? ` (${result.sessions_revoked} session(s) ended)` : ''),
      );
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not reset that PIN');
    } finally {
      setActingOn(null);
    }
  }

  async function unlock(target: AdminPlayer) {
    setActingOn(target.id);
    try {
      await apiFetch(`/api/v1/admin/players/${target.id}/unlock`, { method: 'POST' });
      toast.success(`${target.display_name} can try again`);
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not unlock that account');
    } finally {
      setActingOn(null);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setActingOn(deleteTarget.id);
    const name = deleteTarget.display_name;
    try {
      await apiFetch(`/api/v1/admin/players/${deleteTarget.id}`, { method: 'DELETE' });
      toast.success(`${name} removed — their past weeks are unchanged`);
      setDeleteTarget(null);
      setDeleteConfirm('');
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not remove that player');
    } finally {
      setActingOn(null);
    }
  }

  return (
    <div className="p-4 pb-24 max-w-3xl mx-auto">
      <PageHeader eyebrow="Site admin" title="Players" />
      <AdminNav />

      <Input
        aria-label="Search players"
        placeholder="Search by display name"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-4"
      />

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <p className="font-sans text-sm text-text-secondary">No players match that.</p>
      ) : (
        <ul className="space-y-2">
          {visible.map((p) => {
            const locked = !!p.locked_until && new Date(p.locked_until) > new Date();
            const busy = actingOn === p.id;
            return (
              <li key={p.id}>
                <Card className={p.id === highlighted ? 'border-primary' : undefined}>
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-sans font-semibold text-text-primary">
                        {p.display_name}
                      </span>
                      {p.role === 'admin' && <Badge variant="accent">Admin</Badge>}
                      {p.deleted_at && <Badge variant="muted">Deleted</Badge>}
                      {locked && <Badge variant="error">Locked</Badge>}
                      {!p.pin_set && <Badge variant="warning">PIN cleared</Badge>}
                    </div>
                    <p className="mt-1 font-sans text-xs text-text-secondary">
                      {p.league_count} league{p.league_count === 1 ? '' : 's'}
                      {p.failed_login_count > 0 && ` · ${p.failed_login_count} failed sign-ins`}
                      {!p.pin_set && ' · waiting for them to choose a new PIN'}
                    </p>

                    {!p.deleted_at && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => void resetPin(p)}
                        >
                          <KeyRound className="mr-1.5 h-4 w-4" aria-hidden />
                          Reset PIN
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy || (!locked && p.failed_login_count === 0)}
                          onClick={() => void unlock(p)}
                        >
                          <LockOpen className="mr-1.5 h-4 w-4" aria-hidden />
                          Unlock
                        </Button>
                        {p.id !== me?.id && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-error"
                            disabled={busy}
                            onClick={() => {
                              setDeleteTarget(p);
                              setDeleteConfirm('');
                            }}
                          >
                            <Trash2 className="mr-1.5 h-4 w-4" aria-hidden />
                            Delete
                          </Button>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.display_name}?</DialogTitle>
            <DialogDescription>
              Their picks stay exactly where they are, so past leaderboards read as they were
              played, and their display name stays reserved — nobody else can register it.
              Type the display name to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Confirm display name"
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder={deleteTarget?.display_name}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteConfirm !== deleteTarget?.display_name}
              onClick={() => void confirmDelete()}
            >
              Delete player
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
