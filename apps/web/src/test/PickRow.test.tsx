import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { entriesFromLegs, entriesFromMembers, PickRow } from '@/components/PickRow';
import type { CouponLeg, GameweekMember } from '@/lib/types';

/**
 * Batch 78. The roster and the combined acca were two implementations of one list —
 * `GameweekMember` and `CouponLeg` carry the same seven facts — and each had content the
 * other could not draw. These assert that the surviving component draws **both** sets:
 * the roster's member with nothing to show, and the coupon's settled result.
 */

const PICKED: GameweekMember = {
  player_id: 'p1',
  display_name: 'Alice',
  has_picked: true,
  fixture_id: 'fx1',
  home: 'Forfar',
  away: 'Brechin',
  competition: 'Scottish League 2',
  market: 'MATCH_ODDS',
  outcome: 'HOME',
  runner_name: 'Forfar',
  odds: 2.0,
};

const YET_TO_PICK: GameweekMember = {
  player_id: 'p2',
  display_name: 'Bob',
  has_picked: false,
  fixture_id: null,
  home: null,
  away: null,
  competition: null,
  market: null,
  outcome: null,
  runner_name: null,
  odds: null,
};

const SETTLED_LEG: CouponLeg = {
  player_id: 'p1',
  player_name: 'Alice',
  fixture_id: 'fx1',
  home: 'Forfar',
  away: 'Brechin',
  competition: 'Scottish League 2',
  market: 'MATCH_ODDS',
  outcome: 'HOME',
  runner_name: 'Forfar',
  odds: 2.0,
  status: 'won',
  points_awarded: 20,
  home_goals: 2,
  away_goals: 1,
  score_is_final: true,
};

describe('PickRow', () => {
  it('draws a member with no selection — the roster content the acca never had', () => {
    const [entry] = entriesFromMembers([YET_TO_PICK]);
    render(
      <ul>
        <PickRow entry={entry} oddsFormat="decimal" lead="player" testId="row" />
      </ul>,
    );
    const row = screen.getByTestId('row');
    expect(within(row).getByText('Bob')).toBeTruthy();
    expect(within(row).getByText('Yet to pick')).toBeTruthy();
  });

  it('draws a settled result — the acca content the roster never had', () => {
    const [entry] = entriesFromLegs([SETTLED_LEG]);
    render(
      <ol>
        <PickRow
          entry={entry}
          oddsFormat="decimal"
          lead="selection"
          index={0}
          showScore
          settled
          testId="row"
        />
      </ol>,
    );
    const row = screen.getByTestId('row');
    expect(within(row).getByText('Won')).toBeTruthy();
    expect(within(row).getByText('20 pts')).toBeTruthy();
    expect(row.textContent).toContain('Forfar 2–1 Brechin');
  });

  it('reads the same seven facts out of a member and out of a leg', () => {
    const [fromMember] = entriesFromMembers([PICKED]);
    const [fromLeg] = entriesFromLegs([SETTLED_LEG]);
    // The claim the batch rests on: one pick, two endpoints, one shape. Settlement is
    // the honest difference and is not compared here.
    expect(fromMember.selection).toEqual(fromLeg.selection);
    expect(fromMember.player_name).toBe(fromLeg.player_name);
  });

  it('marks the reader on either hierarchy', () => {
    const [mine] = entriesFromMembers([PICKED], 'p1');
    const [theirs] = entriesFromMembers([PICKED], 'p9');
    render(
      <ul>
        <PickRow entry={mine} oddsFormat="decimal" lead="player" testId="mine" />
        <PickRow entry={theirs} oddsFormat="decimal" lead="player" testId="theirs" />
      </ul>,
    );
    expect(within(screen.getByTestId('mine')).getByText('You')).toBeTruthy();
    expect(within(screen.getByTestId('theirs')).queryByText('You')).toBeNull();
  });

  it('says a score is live in words, not only in colour', () => {
    const [entry] = entriesFromLegs([
      { ...SETTLED_LEG, status: 'pending', points_awarded: null, score_is_final: false },
    ]);
    render(
      <ol>
        <PickRow entry={entry} oddsFormat="decimal" lead="selection" index={0} showScore testId="row" />
      </ol>,
    );
    const row = screen.getByTestId('row');
    expect(within(row).getByText('Live')).toBeTruthy();
    expect(row.textContent).toContain('Score so far:');
  });

  it('omits the price a roster row arrived without rather than printing a zero', () => {
    const [entry] = entriesFromMembers([{ ...PICKED, odds: null }]);
    render(
      <ul>
        <PickRow entry={entry} oddsFormat="decimal" lead="player" testId="row" />
      </ul>,
    );
    expect(screen.getByTestId('row').textContent).not.toContain('0.00');
  });
});
