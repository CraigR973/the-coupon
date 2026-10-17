import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { keys } from '@/lib/queryKeys';
import { formatPence, parsePounds } from '@/lib/money';
import { formatInstant } from '@/lib/time';
import { useRouteLeague } from '@/hooks/useRouteLeague';
import { useAuth } from '@/contexts/AuthContext';
import type {
  MemberBalance,
  MonzoLinkHealth,
  PaymentsOverview,
  QueuedPayment,
} from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/PageHeader';
import { QueryErrorState } from '@/components/QueryErrorState';

const SELECT_CLASS =
  'flex h-10 w-full items-center rounded-md border border-border bg-surface px-3 py-2 ' +
  'text-base sm:text-sm text-text-primary font-sans focus:outline-hidden focus:ring-2 focus:ring-primary';

/** The three things an organiser writes down by hand, each its own ledger route. */
type EntryKind = 'cash' | 'cash-out' | 'adjustment';

const ENTRY_KINDS: { value: EntryKind; label: string; help: string }[] = [
  { value: 'cash', label: 'Cash payment', help: 'Money a member handed over outside the link.' },
  {
    value: 'cash-out',
    label: 'Cash-out',
    help: 'Credit repaid to a member outside the app. Never more than they hold.',
  },
  {
    value: 'adjustment',
    label: 'Adjustment',
    help: 'A correction or an opening balance, with the reason written down.',
  },
];

/** What the API's refusal codes mean on this screen. */
function paymentsErrorMessage(detail: string): string {
  switch (detail) {
    case 'PAYMENT_ALREADY_ASSIGNED':
      return 'That payment has already been assigned — the list was out of date.';
    case 'CASH_OUT_EXCEEDS_CREDIT':
      return 'That is more than the member holds in credit.';
    case 'Member not found':
      return 'That member is not in this league.';
    default:
      return detail || 'Could not save — try again.';
  }
}

/**
 * A league's money, for the site admin who runs it (Batch 206, ADR 0009).
 *
 * Members pay £1 a week through the league's payment link, or in cash, and nothing moves
 * through the app. This screen is where the organiser sees who owes and who is in credit,
 * matches payments nobody has matched yet, and writes down what happened outside the
 * app. Every write is a new, permanent ledger entry: there is nothing here to edit or
 * delete, because a mistake is put right with an adjustment.
 *
 * Site admins only, like the routes behind it — a league admin who could record cash
 * could record some for themselves.
 */
export function LeaguePaymentsPage() {
  const { slug, name } = useRouteLeague();
  const { player } = useAuth();
  const timezone = player?.timezone ?? 'UTC';
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery<PaymentsOverview>({
    queryKey: keys.league.payments(slug),
    queryFn: () => apiFetch<PaymentsOverview>(`/api/v1/leagues/${slug}/payments`),
  });

  // A write changes a balance, the pot on the league page and — when the organiser is a
  // member too — their own fee status on the round.
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.league.payments(slug) });
    void queryClient.invalidateQueries({ queryKey: keys.league.detail(slug) });
    void queryClient.invalidateQueries({ queryKey: keys.gameweek.all(slug) });
  };

  const members = data?.balances ?? [];

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <PageHeader
        title="Payments"
        eyebrow={name}
        back={{ to: `/leagues/${slug}`, label: 'Back' }}
      />

      {isLoading && (
        <div className="space-y-2" aria-label="Loading payments">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <QueryErrorState
          title="Couldn't load payments"
          description="Check your connection, then try again."
          onRetry={() => void refetch()}
        />
      )}

      {data && (
        <>
          <Card>
            <CardContent className="grid grid-cols-2 gap-3 pt-4 pb-4 font-sans">
              <div>
                <p className="text-caption uppercase tracking-wider text-text-muted">Fee</p>
                <p className="text-sm font-semibold text-text-primary" data-testid="payments-fee">
                  {data.entry_fee_pence === null
                    ? 'No fee set'
                    : `${formatPence(data.entry_fee_pence)} a round`}
                </p>
              </div>
              <div>
                <p className="text-caption uppercase tracking-wider text-text-muted">
                  {data.season_pot.label} pot
                </p>
                <p className="text-sm font-semibold text-text-primary" data-testid="payments-pot">
                  {formatPence(data.season_pot.pot_pence)}
                </p>
              </div>
            </CardContent>
          </Card>

          {data.monzo_link !== undefined && (
            <MonzoLink
              slug={slug}
              link={data.monzo_link}
              linkId={data.monzo_link_id ?? null}
              timezone={timezone}
            />
          )}

          <QueuedPayments
            slug={slug}
            queued={data.queued_payments}
            members={members}
            timezone={timezone}
            onWritten={refresh}
          />

          <Balances members={members} />

          <RecordEntry slug={slug} members={members} onWritten={refresh} />
        </>
      )}
    </div>
  );
}

const MONZO_STATUS: Record<string, string> = {
  connected: 'Connected',
  awaiting_approval: 'Waiting for approval in the Monzo app',
  needs_reconnect: 'Needs connecting again',
  not_connected: 'Not connected',
};

const MONZO_BADGE: Record<string, 'success' | 'warning' | 'error' | 'muted'> = {
  connected: 'success',
  awaiting_approval: 'warning',
  needs_reconnect: 'error',
  not_connected: 'muted',
};

/** What the payments service's error codes mean to the organiser. */
function monzoProblem(code: string): string {
  switch (code) {
    case 'monzo_unavailable':
      return 'Monzo could not be reached. The next read tries again within five minutes.';
    case 'refresh_refused':
      return 'Monzo refused the saved login, so the owner needs to connect again.';
    case 'webhook_unregistered':
      return 'Monzo did not take the webhook. Payments are still read every five minutes.';
    case 'token_unreadable':
      return 'The saved login could not be opened, so the owner needs to connect again.';
    case 'forbidden':
      return 'Monzo refused access to the account.';
    default:
      return `Reading from Monzo failed (${code}).`;
  }
}

/**
 * The Monzo link's health (Batch 210, from Batch 208's API): whether the payments service
 * is connected, when it last read, and whether anything has gone wrong since.
 *
 * Only drawn when the API says anything about Monzo — an API from before Batch 208 sends
 * neither field, and this screen then says nothing rather than "not connected".
 */
function MonzoLink({
  slug,
  link,
  linkId,
  timezone,
}: {
  slug: string;
  link: MonzoLinkHealth | null;
  linkId: string | null;
  timezone: string;
}) {
  const when = (iso: string | null) => formatInstant(iso, timezone, 'EEE d MMM, HH:mm');
  const errorAt = link?.last_error_at ? Date.parse(link.last_error_at) : null;
  const successAt = link?.last_success_at ? Date.parse(link.last_success_at) : null;
  // An error is news only when nothing has worked since.
  const problem =
    link?.last_error && errorAt !== null && (successAt === null || errorAt > successAt)
      ? link.last_error
      : null;
  const reading = link?.status === 'connected' || link?.status === 'awaiting_approval';

  return (
    <Card data-testid="monzo-link">
      <CardHeader>
        <CardTitle className="text-base">Monzo</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 font-sans">
        <div className="flex items-center gap-2">
          <Badge variant={MONZO_BADGE[link?.status ?? 'not_connected'] ?? 'muted'}>
            <span data-testid="monzo-status">
              {link ? (MONZO_STATUS[link.status] ?? link.status) : 'Not connected'}
            </span>
          </Badge>
        </div>
        {!link && (
          <p className="text-xs text-text-muted">
            The owner connects Monzo once, from the payments service. Until then, record
            payments by hand.
          </p>
        )}
        {link?.status === 'connected' && link.last_success_at && (
          <p className="text-xs text-text-muted" data-testid="monzo-last-read">
            Last read {when(link.last_success_at)}
            {link.token_expires_at ? ` · login renews before ${when(link.token_expires_at)}` : ''}
          </p>
        )}
        {link?.status === 'needs_reconnect' && (
          <p className="text-xs text-text-muted">
            Nothing is read until the owner connects Monzo again. Record payments by hand
            meanwhile.
          </p>
        )}
        {problem && (
          <p className="text-xs text-error" role="status" data-testid="monzo-problem">
            {when(link?.last_error_at ?? null)}: {monzoProblem(problem)}
          </p>
        )}
        {link?.counting_since && (
          <p className="text-xs text-text-muted" data-testid="monzo-counting-since">
            Payments count from {when(link.counting_since)}. Record anything earlier as an
            opening balance.
          </p>
        )}
        {reading && linkId === null && (
          <p className="text-xs text-text-muted" data-testid="monzo-no-link-id">
            This league has no Monzo link id, so none of its payments are read yet. Add it
            in{' '}
            <Link className="underline" to={`/leagues/${slug}/admin/settings`}>
              league settings
            </Link>
            .
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function QueuedPayments({
  slug,
  queued,
  members,
  timezone,
  onWritten,
}: {
  slug: string;
  queued: QueuedPayment[];
  members: MemberBalance[];
  timezone: string;
  onWritten: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Waiting to be matched</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {queued.length === 0 ? (
          <p className="text-xs font-sans text-text-muted" data-testid="queued-empty">
            Nothing waiting. Payments from someone the app has not seen before land here.
          </p>
        ) : (
          <>
            <p className="text-xs font-sans text-text-muted">
              Say whose each one is. The payer is remembered, so their next payment matches
              itself.
            </p>
            <ul className="flex flex-col gap-2" data-testid="queued-payments">
              {queued.map((payment) => (
                <QueuedRow
                  key={payment.id}
                  slug={slug}
                  payment={payment}
                  members={members}
                  timezone={timezone}
                  onWritten={onWritten}
                />
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function QueuedRow({
  slug,
  payment,
  members,
  timezone,
  onWritten,
}: {
  slug: string;
  payment: QueuedPayment;
  members: MemberBalance[];
  timezone: string;
  onWritten: () => void;
}) {
  const [playerId, setPlayerId] = useState('');
  const assign = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/leagues/${slug}/payments/${payment.id}/assign`, {
        method: 'POST',
        body: JSON.stringify({ player_id: playerId }),
      }),
    onSuccess: () => {
      const member = members.find((m) => m.player_id === playerId);
      toast.success(`${formatPence(payment.amount_pence)} assigned to ${member?.display_name ?? 'the member'}`);
      onWritten();
    },
    onError: (err) => {
      toast.error('Could not assign the payment', {
        description: paymentsErrorMessage(err instanceof Error ? err.message : ''),
      });
      onWritten();
    },
  });
  const selectId = `assign-${payment.id}`;
  const when = formatInstant(payment.occurred_at, timezone, 'EEE d MMM, HH:mm');

  return (
    <li
      data-testid={`queued-${payment.id}`}
      className="space-y-2 rounded-md border border-border bg-surface px-3 py-2 font-sans"
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">
            {payment.payer_name ?? 'Unnamed payer'}
          </p>
          <p className="text-xs text-text-muted">{when}</p>
        </div>
        <p className="shrink-0 font-mono text-sm tabular-nums text-text-primary">
          {formatPence(payment.amount_pence)}
        </p>
      </div>
      <div className="flex gap-2">
        <label htmlFor={selectId} className="sr-only">
          Whose payment is this?
        </label>
        <select
          id={selectId}
          value={playerId}
          onChange={(e) => setPlayerId(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="">Whose is it?</option>
          {members.map((m) => (
            <option key={m.player_id} value={m.player_id}>
              {m.display_name}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          className="h-10 shrink-0"
          disabled={!playerId || assign.isPending}
          onClick={() => assign.mutate()}
        >
          {assign.isPending ? 'Assigning…' : 'Assign'}
        </Button>
      </div>
    </li>
  );
}

function Balances({ members }: { members: MemberBalance[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Balances</CardTitle>
      </CardHeader>
      <CardContent>
        {members.length === 0 ? (
          <p className="text-xs font-sans text-text-muted">No members yet.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border" data-testid="balances">
            {members.map((m) => (
              <li
                key={m.player_id}
                data-testid={`balance-${m.player_id}`}
                className="flex items-center justify-between gap-3 py-2 font-sans"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm text-text-primary">{m.display_name}</span>
                  {!m.active && <Badge variant="muted">Left</Badge>}
                </span>
                <span
                  className={
                    m.owed_pence > 0
                      ? 'shrink-0 font-mono text-sm tabular-nums text-error'
                      : 'shrink-0 font-mono text-sm tabular-nums text-text-secondary'
                  }
                >
                  {m.owed_pence > 0
                    ? `Owes ${formatPence(m.owed_pence)}`
                    : m.credit_pence > 0
                      ? `${formatPence(m.credit_pence)} credit`
                      : 'Paid up'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function RecordEntry({
  slug,
  members,
  onWritten,
}: {
  slug: string;
  members: MemberBalance[];
  onWritten: () => void;
}) {
  const [kind, setKind] = useState<EntryKind>('cash');
  const [playerId, setPlayerId] = useState('');
  const [amount, setAmount] = useState('');
  const [direction, setDirection] = useState<'credit' | 'charge'>('credit');
  const [note, setNote] = useState('');

  const record = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch(
        `/api/v1/leagues/${slug}/payments/${kind === 'cash' ? 'cash' : kind === 'cash-out' ? 'cash-outs' : 'adjustments'}`,
        { method: 'POST', body: JSON.stringify(body) },
      ),
    onSuccess: () => {
      toast.success(`${ENTRY_KINDS.find((k) => k.value === kind)?.label ?? 'Entry'} recorded`);
      setAmount('');
      setNote('');
      onWritten();
    },
    onError: (err) => {
      toast.error('Could not record it', {
        description: paymentsErrorMessage(err instanceof Error ? err.message : ''),
      });
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!playerId) {
      toast.error('Choose the member.');
      return;
    }
    const pence = parsePounds(amount);
    if (pence === null || pence < 1) {
      toast.error('Enter an amount in pounds, such as 1 or 2.50.');
      return;
    }
    const trimmed = note.trim();
    if (kind === 'adjustment' && trimmed.length < 3) {
      toast.error('Say why — an adjustment always carries its reason.');
      return;
    }
    const signed = kind === 'adjustment' && direction === 'charge' ? -pence : pence;
    record.mutate({ player_id: playerId, amount_pence: signed, note: trimmed || null });
  }

  const help = ENTRY_KINDS.find((k) => k.value === kind)?.help;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Record an entry</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4" data-testid="record-entry">
          <div className="space-y-1">
            <Label htmlFor="entryKind">What happened</Label>
            <select
              id="entryKind"
              value={kind}
              onChange={(e) => setKind(e.target.value as EntryKind)}
              className={SELECT_CLASS}
              aria-describedby="entry-kind-help"
            >
              {ENTRY_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <p id="entry-kind-help" className="text-xs font-sans text-text-muted">
              {help}
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="entryMember">Member</Label>
            <select
              id="entryMember"
              value={playerId}
              onChange={(e) => setPlayerId(e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">Choose a member</option>
              {members.map((m) => (
                <option key={m.player_id} value={m.player_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>

          {kind === 'adjustment' && (
            <div className="space-y-1">
              <Label htmlFor="entryDirection">Direction</Label>
              <select
                id="entryDirection"
                value={direction}
                onChange={(e) => setDirection(e.target.value as 'credit' | 'charge')}
                className={SELECT_CLASS}
              >
                <option value="credit">Credit the member</option>
                <option value="charge">Charge the member</option>
              </select>
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="entryAmount">Amount (£)</Label>
            <Input
              id="entryAmount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="1.00"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="entryNote">
              {kind === 'adjustment' ? 'Reason' : 'Note (optional)'}
            </Label>
            <Input
              id="entryNote"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          <p className="text-xs font-sans text-text-muted">
            Entries are permanent. A mistake is put right with an adjustment.
          </p>

          <Button type="submit" className="w-full" disabled={record.isPending}>
            {record.isPending ? 'Recording…' : 'Record'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
