import { describe, it, expect } from 'vitest';
import { compareCompetitions, competitionRank } from '@/lib/competitions';

/** The shape both the pick screen's groups and Football Stats' tables satisfy. */
const c = (competition_id: string, competition = competition_id) => ({
  competition_id,
  competition,
});

describe('competitionRank', () => {
  it('puts the named ladder first, in its declared order', () => {
    const ladder = [
      'england-premier-league',
      'england-championship',
      'england-league-one',
      'england-league-two',
      'scotland-premiership',
      'scotland-championship',
      'scotland-league-one',
      'scotland-league-two',
    ];
    const ranks = ladder.map((id) => competitionRank(id));
    expect(ranks.every(([bucket]) => bucket === 0)).toBe(true);
    expect(ranks.map(([, tier]) => tier)).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
  });

  it('sinks an unrecognised division to the bottom of its own country', () => {
    // 99, not 0 — otherwise a division nobody has a rule for sorts alongside the
    // Premier League rather than under the pyramid it actually belongs to.
    expect(competitionRank('england-some-new-division')).toEqual([
      1,
      99,
      'england-some-new-division',
    ]);
    expect(competitionRank('scotland-some-new-division')).toEqual([
      2,
      99,
      'scotland-some-new-division',
    ]);
  });

  it('files a competition the slug does not place at all last', () => {
    expect(competitionRank('fa-cup')[0]).toBe(3);
  });
});

describe('compareCompetitions', () => {
  it('sorts a shuffled set into pyramid order', () => {
    const shuffled = [
      c('scotland-premiership'),
      c('england-national-league'),
      c('england-premier-league'),
      c('fa-cup'),
      c('england-league-two'),
      c('england-championship'),
      c('scotland-highland-league'),
    ];
    expect([...shuffled].sort(compareCompetitions).map((x) => x.competition_id)).toEqual([
      'england-premier-league',
      'england-championship',
      'england-league-two',
      'scotland-premiership',
      'england-national-league',
      'scotland-highland-league',
      'fa-cup',
    ]);
  });

  it('orders the English pyramid below the named ladder by tier', () => {
    const tiers = [
      c('england-isthmian-league'),
      c('england-national-league-north'),
      c('england-national-league'),
    ];
    expect([...tiers].sort(compareCompetitions).map((x) => x.competition_id)).toEqual([
      'england-national-league',
      'england-national-league-north',
      'england-isthmian-league',
    ]);
  });

  it('breaks a tie on display name, then on slug, so the order is total', () => {
    const tied = [c('fa-vase', 'Vase'), c('fa-trophy', 'Trophy'), c('fa-cup', 'Cup')];
    expect([...tied].sort(compareCompetitions).map((x) => x.competition)).toEqual([
      'Cup',
      'Trophy',
      'Vase',
    ]);
  });

  it('is stable across the two screens that use it', () => {
    // The regression this module exists for: Football Stats rendered tables in the
    // API's order while the coupon ranked them, so the same divisions read in two
    // different orders one tap apart.
    const set = [c('england-championship'), c('england-premier-league'), c('scotland-league-one')];
    const asTables = [...set].sort(compareCompetitions).map((x) => x.competition_id);
    const asGroups = [...set].reverse().sort(compareCompetitions).map((x) => x.competition_id);
    expect(asTables).toEqual(asGroups);
  });
});
