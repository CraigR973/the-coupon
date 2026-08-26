import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { GameweekMember, OddsFormat } from '../lib/types';
import { entriesFromMembers, PickRow } from './PickRow';
import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

export interface MemberRosterProps {
  members: GameweekMember[];
  missingCount: number;
  oddsFormat: OddsFormat;
  /** Marks the reader's own row, the same way the combined coupon marks their leg. */
  myPlayerId?: string;
}

/**
 * Who in the leaderboard has picked this gameweek, and what they took.
 *
 * This reveals nothing the slate does not already show — a taken selection is
 * labelled with its holder for the land-grab to be legible — but it also names
 * the members who have picked *nothing*, who by definition appear nowhere in
 * the slate. Collapsed by default so it does not push the fixtures down.
 *
 * Batch 78 made the rows themselves `PickRow`, which is also what the combined coupon
 * draws. The two lists had been separate implementations of one list, and had drifted:
 * this one did not mark the reader's own row and did not truncate the same way. What is
 * left here is the part that is genuinely a roster and not a coupon — the count, the
 * disclosure, and the members with nothing to show.
 */
export function MemberRoster({
  members,
  missingCount,
  oddsFormat,
  myPlayerId,
}: MemberRosterProps) {
  const [open, setOpen] = useState(false);
  if (members.length === 0) return null;

  const pickedCount = members.length - missingCount;
  const entries = entriesFromMembers(members, myPlayerId);

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
          {missingCount > 0 && <Badge variant="warning">{missingCount} to go</Badge>}
          <ChevronDown
            className={cn('h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>

      {open && (
        <ul className="border-t border-border">
          {entries.map((entry) => (
            <PickRow
              key={entry.player_id}
              entry={entry}
              oddsFormat={oddsFormat}
              lead="player"
              testId={`roster-${entry.player_id}`}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
