import { useState } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { useRouteLeague } from '@/hooks/useRouteLeague';
import { useAuth } from '@/contexts/AuthContext';
import type { LeagueAuditEntry, LeagueAuditLogResponse } from '@/lib/types';
import { formatInstant } from '@/lib/time';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';

/**
 * What each recorded action is called in a sentence a league admin would use.
 *
 * The stored values are the API's enum, and some of them are approximations the writers
 * chose deliberately — `member_removed` against `profiles` is a site-level deletion, and
 * `league_updated` against `gameweeks` is a hand-entered settlement. The fallback below
 * humanises anything not listed rather than showing a raw enum.
 */
const ACTION_LABELS: Record<string, string> = {
  league_created: 'League created',
  league_updated: 'Settings changed',
  league_deleted: 'League deleted',
  league_privacy_changed: 'Privacy changed',
  league_join_code_rotated: 'Join code rotated',
  league_invite_created: 'Invite created',
  league_invite_revoked: 'Invite revoked',
  league_member_pin_reset: 'Member PIN reset',
  player_pin_reset: 'PIN reset',
  member_joined: 'Member joined',
  member_left: 'Member left',
  member_removed: 'Member removed',
  member_promoted: 'Promoted to admin',
  member_demoted: 'Admin demoted',
  join_request_created: 'Join request made',
  join_request_approved: 'Join request approved',
  join_request_rejected: 'Join request rejected',
};

export function actionLabel(actionType: string): string {
  const known = ACTION_LABELS[actionType];
  if (known) return known;
  const words = actionType.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Keys that say nothing to a reader who is already looking at their own league. */
const HIDDEN_CHANGE_KEYS = new Set(['scope', 'league_slug']);

export function describeChanges(changes: Record<string, unknown> | null): string | null {
  if (!changes) return null;
  const parts = Object.entries(changes)
    .filter(([key]) => !HIDDEN_CHANGE_KEYS.has(key))
    .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value)}`);
  return parts.length > 0 ? parts.join(' · ') : null;
}

function AuditRow({ entry, timezone }: { entry: LeagueAuditEntry; timezone: string }) {
  const detail = describeChanges(entry.changes);
  const when = formatInstant(entry.timestamp, timezone, 'd MMM yyyy, HH:mm');
  return (
    <Card>
      <CardContent className="pt-3 pb-3">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm font-sans font-medium">{actionLabel(entry.action_type)}</p>
          <p className="text-xs text-text-muted font-sans shrink-0">{when}</p>
        </div>
        <p className="text-xs text-text-secondary font-sans mt-0.5">
          {entry.actor_name ?? 'A deleted member'}
        </p>
        {detail && (
          <p className="text-xs text-text-muted font-sans mt-1 break-words">{detail}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function LeagueAuditLogPage() {
  const { slug } = useRouteLeague();
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<LeagueAuditLogResponse>({
    queryKey: ['league-audit-log', slug, page],
    queryFn: () =>
      apiFetch<LeagueAuditLogResponse>(`/api/v1/leagues/${slug}/audit-log?page=${page}`),
    // The list is a history, so the previous page staying on screen while the next one
    // loads reads as paging rather than as the screen emptying and refilling.
    placeholderData: keepPreviousData,
  });

  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 25;
  const firstOnPage = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastOnPage = Math.min(page * pageSize, total);
  const hasMore = page * pageSize < total;

  return (
    <div className="space-y-6">
      <PageHeader title="Activity" back={{ to: `/leagues/${slug}`, label: 'Back' }} />

      <p className="text-xs text-text-muted font-sans">
        Every admin action recorded for this league — who changed a setting, who was
        removed, who was let in. Visible to league admins only.
      </p>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {!isLoading && entries.length === 0 && (
        <Card>
          <CardContent className="pt-8 pb-8 text-center">
            <p className="text-text-secondary font-sans text-sm">
              Nothing has been recorded for this league yet.
            </p>
          </CardContent>
        </Card>
      )}

      {entries.length > 0 && (
        <>
          <div className="space-y-2">
            {entries.map((entry) => (
              <AuditRow key={entry.id} entry={entry} timezone={timezone} />
            ))}
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-text-muted font-sans" aria-live="polite">
              Showing {firstOnPage}–{lastOnPage} of {total}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!hasMore}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
