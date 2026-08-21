import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { CompetitionTable } from '../lib/types';
import { FormLine } from './FormLine';
import { formatInstant } from '../lib/time';
import { cn } from '../lib/utils';

export interface LeagueTableCardProps {
  table: CompetitionTable;
  timezone: string;
  /** Collapsed by default below the first, so a thirty-division card is scannable. */
  defaultOpen?: boolean;
}

/**
 * One competition's table, behind a collapsible header.
 *
 * Played / won / drawn / lost and goal difference are hidden on narrow screens, so a
 * phone shows position, club, form and points — and shows them without sideways
 * scrolling. Points is the column a table exists for; pushing it off the edge behind
 * a scrollbar to keep "P" visible would be the wrong trade. Form is a glanceable
 * five-glyph run and one of the two things a member opens the screen to read, so it
 * stays too. The full set returns from `sm` up, where it fits.
 *
 * The "as of" line is not decoration. Nothing here is live: a scheduled job writes
 * these rows and every screen reads them, so a table can legitimately be a day old
 * and saying so is better than implying otherwise.
 */
export function LeagueTableCard({ table, timezone, defaultOpen = true }: LeagueTableCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section data-testid={`league-table-${table.competition_id}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mb-2 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-elevated px-3 py-2 text-left tap-target focus-visible:outline-none focus-visible:shadow-glow"
      >
        <span className="min-w-0 truncate font-mono text-[11px] uppercase tracking-[0.2em] text-text-primary">
          {table.competition}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-[10px] tabular-nums text-text-muted">
            {table.rows.length}
          </span>
          <ChevronDown
            className={cn('h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </span>
      </button>

      {open && (
        <div className="rounded-lg border border-border bg-surface">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[288px] border-collapse text-sm font-sans">
              <caption className="sr-only">
                {table.competition} table, {table.season}/{(table.season + 1) % 100}
              </caption>
              <thead>
                <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted">
                  <th scope="col" className="w-8 py-2 pl-3 text-right font-normal">
                    #
                  </th>
                  <th scope="col" className="py-2 pl-2 text-left font-normal">
                    Team
                  </th>
                  <ColumnHeader label="P" title="Played" narrowHidden />
                  <ColumnHeader label="W" title="Won" narrowHidden />
                  <ColumnHeader label="D" title="Drawn" narrowHidden />
                  <ColumnHeader label="L" title="Lost" narrowHidden />
                  <ColumnHeader label="GD" title="Goal difference" narrowHidden />
                  <ColumnHeader label="Pts" title="Points" />
                  <th scope="col" className="py-2 pl-3 pr-3 text-left font-normal">
                    Form
                  </th>
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => (
                  <tr
                    key={row.team_id}
                    className="border-b border-border/50 last:border-0"
                    data-testid={`table-row-${row.team_id}`}
                  >
                    <td className="py-2 pl-3 text-right font-mono text-xs tabular-nums text-text-muted">
                      {row.position}
                    </td>
                    <th
                      scope="row"
                      className="max-w-[10rem] truncate py-2 pl-2 text-left font-medium text-text-primary"
                    >
                      {row.team}
                    </th>
                    <NumberCell value={row.played} narrowHidden />
                    <NumberCell value={row.won} narrowHidden />
                    <NumberCell value={row.drawn} narrowHidden />
                    <NumberCell value={row.lost} narrowHidden />
                    <NumberCell value={signed(row.goal_difference)} narrowHidden />
                    <td className="px-2 py-2 text-right font-mono text-xs font-semibold tabular-nums text-text-primary">
                      {row.points}
                    </td>
                    <td className="py-2 pl-3 pr-3">
                      <FormLine form={row.form} team={row.team} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {table.updated_at && (
            <p className="border-t border-border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
              As of {formatInstant(table.updated_at, timezone, 'd MMM, HH:mm')}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/** `+7` reads as a goal difference; `7` reads as a count of something. */
function signed(value: number): string {
  return value > 0 ? `+${value}` : `${value}`;
}

function ColumnHeader({
  label,
  title,
  narrowHidden = false,
}: {
  label: string;
  title: string;
  narrowHidden?: boolean;
}) {
  return (
    <th
      scope="col"
      className={cn('px-2 py-2 text-right font-normal', narrowHidden && 'hidden sm:table-cell')}
    >
      <abbr title={title} className="no-underline">
        {label}
      </abbr>
    </th>
  );
}

function NumberCell({
  value,
  narrowHidden = false,
}: {
  value: number | string;
  narrowHidden?: boolean;
}) {
  return (
    <td
      className={cn(
        'px-2 py-2 text-right font-mono text-xs tabular-nums text-text-secondary',
        narrowHidden && 'hidden sm:table-cell',
      )}
    >
      {value}
    </td>
  );
}
