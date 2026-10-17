import { Trophy } from 'lucide-react';
import { formatPence, sortMembers } from '@/lib/money';
import { formatCalendarDate } from '@/lib/time';
import type { LeagueMoney, MemberMoneyStatus, MoneyTarget } from '@/lib/types';
import { cn } from '@/lib/utils';

/**
 * The league's money, as every member sees it (Batch 212, ADR 0009).
 *
 * Owner decisions of 2026-10-17: in a friends' league every member sees every member's
 * status — the nudge is the point — and the target shows both **to date** (exact) and
 * **full season** (an estimate while the season's last round is not known).
 *
 * Shown on the standings page in place of the one-line season pot, for the season being
 * played. A league without a fee never asks for it, and an API from before this batch
 * answers 404, so the page keeps the pot line it had.
 */
export function MoneyCard({
  money,
  currentPlayerId,
}: {
  money: LeagueMoney;
  currentPlayerId?: string;
}) {
  const full = money.target_full_season;
  const members = sortMembers(money.members);

  return (
    <section
      aria-labelledby="money-card-heading"
      data-testid="money-card"
      className="mt-3 rounded-lg border border-border bg-surface px-4 py-3 font-sans text-text-primary"
    >
      <div className="flex items-start gap-2">
        <Trophy className="mt-0.5 h-4 w-4 shrink-0 text-gold-ink" aria-hidden />
        <div className="min-w-0">
          <h2 id="money-card-heading" className="text-sm font-semibold">
            Prize fund so far{' '}
            <span data-testid="money-pot" className="font-mono tabular-nums">
              {formatPence(money.pot_pence)}
            </span>
          </h2>
          <p className="text-caption text-text-muted">
            The weekly fees paid so far, {formatPence(money.entry_fee_pence)} a week. It all
            goes to the season’s winner, and a tie splits it.
          </p>
        </div>
      </div>

      <dl className="mt-3 flex flex-col gap-2 text-xs sm:max-w-lg" data-testid="money-targets">
        <TargetRow
          testId="money-target-to-date"
          label="Target to date"
          target={money.target_to_date}
        />
        <TargetRow
          testId="money-target-full-season"
          label={full.is_estimate ? 'Full season (estimate)' : 'Full season'}
          target={full}
        />
      </dl>
      {full.is_estimate && full.estimated_through && (
        <p className="mt-1 text-caption text-text-muted" data-testid="money-estimate-note">
          An estimate: one round a week to{' '}
          {formatCalendarDate(full.estimated_through, 'd MMMM')}.
        </p>
      )}
      <p className="mt-2 text-xs" data-testid="money-shortfall">
        {money.short_of_target_pence > 0 ? (
          <>
            The fund is{' '}
            <strong className="font-semibold text-warning">
              {formatPence(money.short_of_target_pence)} short
            </strong>{' '}
            of the target to date.
          </>
        ) : (
          <span className="text-success">Everything due so far is paid.</span>
        )}
      </p>

      {members.length > 0 && (
        <>
          <h3 className="mt-3 text-xs font-semibold text-text-secondary">Who’s paid</h3>
          <ul
            className="mt-1 flex flex-col divide-y divide-border sm:max-w-lg"
            data-testid="money-members"
          >
            {members.map((member) => (
              <li
                key={member.player_id}
                data-testid="money-member"
                data-status={member.status}
                className="flex items-baseline justify-between gap-3 py-1.5 text-sm"
              >
                <span
                  className={cn(
                    'min-w-0 truncate',
                    member.player_id === currentPlayerId && 'font-semibold',
                  )}
                >
                  {member.display_name}
                  {member.player_id === currentPlayerId && (
                    <span className="font-normal text-text-muted"> (you)</span>
                  )}
                </span>
                <StatusLabel member={member} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function TargetRow({
  label,
  target,
  testId,
}: {
  label: string;
  target: MoneyTarget;
  testId: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3" data-testid={testId}>
      <dt className="min-w-0">
        {label}
        <span className="text-text-muted">
          {' '}
          · {target.rounds} {target.rounds === 1 ? 'round' : 'rounds'}
        </span>
      </dt>
      <dd className="shrink-0 text-right font-mono tabular-nums">
        {formatPence(target.per_person_pence)} each
        <span className="text-text-muted"> · </span>
        {formatPence(target.total_pence)} total
      </dd>
    </div>
  );
}

function StatusLabel({ member }: { member: MemberMoneyStatus }) {
  if (member.status === 'owes') {
    return (
      <span className="shrink-0 font-mono text-xs tabular-nums text-warning">
        Owes {formatPence(member.amount_pence)}
      </span>
    );
  }
  if (member.status === 'credit') {
    return (
      <span className="shrink-0 font-mono text-xs tabular-nums text-primary">
        In credit {formatPence(member.amount_pence)}
      </span>
    );
  }
  return <span className="shrink-0 text-xs text-text-muted">Paid up</span>;
}
