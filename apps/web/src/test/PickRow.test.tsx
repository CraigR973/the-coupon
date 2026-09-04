import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import {
  entriesForRound,
  entriesFromLegs,
  entriesFromMembers,
  PickRow,
} from '@/components/PickRow';
import type { Coupon, CouponLeg, GameweekMember } from '@/lib/types';

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

/**
 * Batch 105 — what a row may clip, and what it may not.
 *
 * The row answers three questions: who took it, what they took, at what price. All three
 * used to share one `truncate`d line with the competition and the full fixture, and the
 * holder's name came last, so on a 390px screen a long team name ended the line before
 * the name it belonged to. jsdom cannot measure an overflow, so these assert the rule that
 * produces one: the three load-bearing facts wrap, and only the fixture context clamps.
 */
describe('a row with long names in it', () => {
  const LONG: CouponLeg = {
    ...SETTLED_LEG,
    player_name: 'Bartholomew Fitzwilliam-Harrington',
    home: 'Borussia Mönchengladbach',
    away: 'Bayer 04 Leverkusen Fußball',
    competition: 'Deutsche Fußball-Bundesliga Erste Liga',
    status: 'pending',
    points_awarded: null,
    home_goals: null,
    away_goals: null,
  };

  function renderLong() {
    const [entry] = entriesFromLegs([LONG]);
    render(
      <ol>
        <PickRow entry={entry} oddsFormat="decimal" lead="selection" index={0} testId="row" />
      </ol>,
    );
    return screen.getByTestId('row');
  }

  it('keeps the person, the selection and the price all present', () => {
    const row = renderLong();
    expect(within(row).getByText('Borussia Mönchengladbach')).toBeTruthy();
    expect(within(row).getByText('Bartholomew Fitzwilliam-Harrington')).toBeTruthy();
    expect(within(row).getByText('2.00')).toBeTruthy();
  });

  it('lets those three wrap rather than truncating them', () => {
    const row = renderLong();
    expect(within(row).getByText('Borussia Mönchengladbach').className).not.toContain('truncate');
    expect(
      within(row).getByText('Bartholomew Fitzwilliam-Harrington').className,
    ).not.toContain('truncate');
  });

  it('clamps only the fixture context, which is the line that may run on', () => {
    const row = renderLong();
    const context = within(row).getByText(/Deutsche Fußball-Bundesliga/);
    expect(context.className).toContain('line-clamp-2');
  });

  it('prints only the context the selection does not already carry', () => {
    const row = renderLong();
    // The pick *is* the home team, so the opponent is what disambiguates it. Printing
    // "Borussia Mönchengladbach v Bayer 04 Leverkusen Fußball" underneath the same words
    // is the repetition that pushed the price and the name off the row.
    expect(row.textContent).toContain('v Bayer 04 Leverkusen Fußball');
    expect(row.textContent).not.toContain('Borussia Mönchengladbach v ');
  });

  it('does not repeat the market as a tag', () => {
    // "Borussia Mönchengladbach" can only be a match-result selection; `1X2` beside it
    // said nothing, and `BTTS` beside "Both teams score" said it twice.
    expect(renderLong().textContent).not.toContain('1X2');
  });
});

describe('entriesForRound', () => {
  const coupon: Coupon = {
    gameweek_id: 'gw1',
    status: 'locked',
    leg_count: 1,
    combined_odds: 2.0,
    legs: [{ ...SETTLED_LEG, status: 'pending', points_awarded: null }],
    all_won: null,
  };

  it('puts the claims first and the members who never picked after them', () => {
    const entries = entriesForRound(coupon, [PICKED, YET_TO_PICK], 'p1');
    expect(entries.map((e) => e.player_name)).toEqual(['Alice', 'Bob']);
    expect(entries[0].selection).not.toBeNull();
    expect(entries[1].selection).toBeNull();
    expect(entries[0].is_mine).toBe(true);
  });

  it('never demotes a leg to "yet to pick" because the slate lagged', () => {
    // Two responses, one cache each: the coupon is the one that carries settlement, so a
    // member it has a leg for is claimed however stale the slate's `has_picked` is.
    const stale: GameweekMember = { ...PICKED, has_picked: false };
    const entries = entriesForRound(coupon, [stale], undefined);
    expect(entries).toHaveLength(1);
    expect(entries[0].selection).not.toBeNull();
  });

  it('falls back to the roster when the round has no coupon at all', () => {
    const entries = entriesForRound(undefined, [PICKED, YET_TO_PICK]);
    expect(entries.map((e) => e.player_name)).toEqual(['Alice', 'Bob']);
  });
});
