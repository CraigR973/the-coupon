import { PageHeader } from '../components/PageHeader';
import { potentialPoints } from '../lib/coupon';

const EXAMPLES: ReadonlyArray<{ odds: number; note: string }> = [
  { odds: 1.5, note: 'Short-priced favourite' },
  { odds: 2.5, note: 'Even-ish call' },
  { odds: 6.0, note: 'Outsider' },
  { odds: 13.0, note: 'Long shot — big reward' },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <h2 className="text-base font-semibold text-text-primary font-sans tracking-tight mb-3">{title}</h2>
      {children}
    </div>
  );
}

export function AboutPage() {
  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="About & scoring rules" back={{ to: '/settings' }} />

      <Section title="How it works">
        <ul className="space-y-2 text-sm font-sans leading-snug text-text-secondary">
          <li>
            <strong className="text-text-primary">One pick a week.</strong> Choose a single selection — a
            match result (1X2) or Both Teams to Score — from this Saturday's slate.
          </li>
          <li>
            <strong className="text-text-primary">First come, first served.</strong> No two members of a
            leaderboard can hold the same selection. Once it's taken, it's gone.
          </li>
          <li>
            <strong className="text-text-primary">Odds freeze when you pick.</strong> Your price is locked in
            the moment you grab it, even if it drifts later.
          </li>
          <li>
            <strong className="text-warning">Picks lock at 14:30</strong> on Saturday. After that you can't
            change your selection.
          </li>
          <li>
            <strong className="text-text-primary">Win → odds × 10 points</strong> (rounded). Longer odds pay
            more. Lose or void → nothing. Season total is cumulative.
          </li>
        </ul>
      </Section>

      <Section title="If your pick wins">
        <table className="w-full border-collapse text-xs font-sans" aria-label="Odds to points examples">
          <thead>
            <tr className="border-b border-border">
              <th scope="col" className="py-1 text-left text-[10px] font-medium uppercase tracking-wider text-text-muted">
                Odds
              </th>
              <th scope="col" className="py-1 text-left text-[10px] font-medium uppercase tracking-wider text-text-muted">
                Example
              </th>
              <th scope="col" className="w-16 py-1 text-right text-[10px] font-medium uppercase tracking-wider text-text-muted">
                Points
              </th>
            </tr>
          </thead>
          <tbody>
            {EXAMPLES.map((ex) => (
              <tr key={ex.odds} className="border-b border-border/30">
                <td className="py-1.5 font-mono text-text-primary tabular-nums">{ex.odds.toFixed(2)}</td>
                <td className="py-1.5 text-[11px] text-text-muted">{ex.note}</td>
                <td className="py-1.5 text-right">
                  <span className="inline-block rounded-full bg-primary/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-4 text-primary">
                    {potentialPoints(ex.odds)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
