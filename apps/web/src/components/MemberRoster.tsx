import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { GameweekMember, OddsFormat } from '../lib/types';
import { formatOdds, marketTag, outcomeLabel } from '../lib/coupon';
import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

export interface MemberRosterProps {
  members: GameweekMember[];
  missingCount: number;
  oddsFormat: OddsFormat;
}

/**
 * Who in the leaderboard has picked this gameweek, and what they took.
 *
 * This reveals nothing the slate does not already show — a taken selection is
 * labelled with its holder for the land-grab to be legible — but it also names
 * the members who have picked *nothing*, who by definition appear nowhere in
 * the slate. Collapsed by default so it does not push the fixtures down.
 */
export function MemberRoster({ members, missingCount, oddsFormat }: MemberRosterProps) {
  const [open, setOpen] = useState(false);
  if (members.length === 0) return null;

  const pickedCount = members.length - missingCount;

  return (
    <div className="mb-4 rounded-lg border border-border bg-surface" data-testid="member-roster">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left tap-target focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="text-sm font-sans font-medium text-text-primary">
          {pickedCount} of {members.length} picked
        </span>
        <span className="flex items-center gap-2">
          {missingCount > 0 && (
            <Badge variant="warning">
              {missingCount} to go
            </Badge>
          )}
          <ChevronDown
            className={cn('h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>

      {open && (
        <ul className="border-t border-border">
          {members.map((member) => (
            <li
              key={member.player_id}
              className="flex items-start justify-between gap-3 border-b border-border/50 px-4 py-2.5 last:border-b-0"
              data-testid={`roster-${member.player_id}`}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-sans text-text-primary">
                  {member.display_name}
                </span>
                {member.has_picked && member.market && member.outcome ? (
                  <span className="block truncate text-xs font-sans text-text-muted">
                    {outcomeLabel(
                      member.market,
                      member.outcome,
                      member.home ?? 'Home',
                      member.away ?? 'Away',
                    )}
                    <span className="mx-1.5">·</span>
                    <span className="font-mono">{marketTag(member.market)}</span>
                  </span>
                ) : (
                  <span className="block text-xs font-sans text-warning">Yet to pick</span>
                )}
              </span>
              {member.odds !== null && (
                <span className="shrink-0 font-mono text-xs tabular-nums text-text-primary">
                  {formatOdds(member.odds, oddsFormat)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
