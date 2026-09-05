import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { PickCard } from '@/components/PickCard';
import type { FixtureSlate, FormMatch, TeamContext } from '@/lib/types';

const FIXTURE: FixtureSlate = {
  fixture_id: 'fx1',
  provider_event_id: 'ev1',
  home: 'Forfar',
  away: 'Brechin',
  competition_id: 'scotland-league-two',
  competition: 'Scottish League 2',
  kickoff_utc: '2026-08-08T14:00:00',
  selections: [
    { market: 'MATCH_ODDS', outcome: 'HOME', runner_name: 'Forfar', odds: 2.0, taken_by_player_id: null, taken_by_name: null, mine: false },
    { market: 'MATCH_ODDS', outcome: 'DRAW', runner_name: 'The Draw', odds: 3.5, taken_by_player_id: 'p1', taken_by_name: 'Alice Adams', mine: true },
    { market: 'MATCH_ODDS', outcome: 'AWAY', runner_name: 'Brechin', odds: 3.2, taken_by_player_id: 'p2', taken_by_name: 'Bob Baker', taken_at: '2026-08-07T09:05:00', mine: false },
    { market: 'BOTH_TEAMS_TO_SCORE', outcome: 'YES', runner_name: 'Yes', odds: 1.8, taken_by_player_id: null, taken_by_name: null, mine: false },
  ],
  taken_by_names: ['Alice Adams', 'Bob Baker'],
  mine: true,
};

function renderCard(overrides: Partial<React.ComponentProps<typeof PickCard>> = {}) {
  const onGrab = vi.fn();
  render(
    <PickCard
      fixture={FIXTURE}
      timezone="UTC"
      locked={false}
      pendingKey={null}
      outstanding={null}
      busy={false}
      oddsFormat="decimal"
      onGrab={onGrab}
      {...overrides}
    />,
  );
  return { onGrab };
}

describe('PickCard', () => {
  it('renders the fixture teams, competition and odds', () => {
    renderCard();
    // Team names appear in both the header and the match-odds selection labels.
    expect(screen.getAllByText('Forfar').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Brechin').length).toBeGreaterThan(0);
    expect(screen.getByText('Scottish League 2')).toBeTruthy();
    expect(screen.getByText('2.00')).toBeTruthy();
  });

  it('grabs an available selection and reports the identity and price to onGrab', () => {
    // The price rides along since Batch 114 — and it is `2`, the number rendered on the
    // button two assertions above, because sending anything else would defeat the point:
    // the API holds the submission to the price the member was actually looking at.
    const { onGrab } = renderCard();
    fireEvent.click(screen.getByTestId('selection-fx1-MATCH_ODDS-HOME'));
    expect(onGrab).toHaveBeenCalledWith('fx1', 'MATCH_ODDS', 'HOME', 2);
  });

  it('marks the caller’s own selection as the current pick', () => {
    renderCard();
    const draw = screen.getByTestId('selection-fx1-MATCH_ODDS-DRAW');
    expect(draw.getAttribute('aria-pressed')).toBe('true');
    expect(draw.textContent).toContain('your pick');
  });

  it('still shows the points on the caller’s own claimed selection', () => {
    // Batch 50. `potentialPoints()` is a pure function of the displayed odds — it costs
    // nothing to keep alongside "your pick", and it's the figure that tells the member
    // what the game is worth to them.
    renderCard();
    const draw = screen.getByTestId('selection-fx1-MATCH_ODDS-DRAW');
    expect(draw.textContent).toContain('35 pts'); // round(3.5 * 10)
  });

  it('shows a selection held by another member as unavailable', () => {
    const { onGrab } = renderCard();
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY') as HTMLButtonElement;
    expect(away.disabled).toBe(true);
    expect(away.textContent).toContain('taken by Bob');
    fireEvent.click(away);
    expect(onGrab).not.toHaveBeenCalled();
  });

  it('still shows the points on a selection held by another member', () => {
    renderCard();
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY');
    expect(away.textContent).toContain('32 pts'); // round(3.2 * 10)
  });

  it('says when a held selection was claimed', () => {
    renderCard();
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY');
    expect(away.textContent).toContain('7 Aug, 09:05');
  });

  it('renders the kickoff in the member’s zone, not at the number the API stored', () => {
    // Batch 43. The fixture kicks off at 14:00 UTC and the API sends `2026-08-08T14:00:00`
    // with no offset; London is BST in August, so the card must say 15:00. Read as local
    // time it says 14:00 in every zone on earth — the whole defect in one assertion.
    renderCard({ timezone: 'Europe/London' });
    expect(screen.getByText(/Sat 8 Aug, 15:00/)).toBeTruthy();
  });

  it('renders the claim time in the league timezone', () => {
    // 09:05 UTC is 11:05 in Berlin (CEST, UTC+2 in August) — the label must follow the
    // league's zone, not the browser's, exactly as the kickoff line does.
    renderCard({ timezone: 'Europe/Berlin' });
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY');
    expect(away.textContent).toContain('7 Aug, 11:05');
  });

  it('omits the claim time when the API did not send one', () => {
    // The web app deploys ahead of the API, so a slate from a pre-Batch-38 API has no
    // `taken_at`. The holder's name must still render rather than the card breaking.
    const selections = FIXTURE.selections.map((sel) =>
      sel.outcome === 'AWAY' ? { ...sel, taken_at: undefined } : sel,
    );
    renderCard({ fixture: { ...FIXTURE, selections } });
    const away = screen.getByTestId('selection-fx1-MATCH_ODDS-AWAY');
    expect(away.textContent).toContain('taken by Bob');
    expect(away.textContent).not.toContain('Aug');
  });

  it('disables every selection once locked', () => {
    const { onGrab } = renderCard({ locked: true });
    const home = screen.getByTestId('selection-fx1-MATCH_ODDS-HOME') as HTMLButtonElement;
    expect(home.disabled).toBe(true);
    fireEvent.click(home);
    expect(onGrab).not.toHaveBeenCalled();
  });

  it('marks the whole fixture as the caller’s when they hold a selection on it', () => {
    renderCard();
    expect(screen.getByTestId('fixture-claimed-fx1').textContent).toContain('Your game');
  });

  it('names the other holders when the caller holds nothing on the fixture', () => {
    renderCard({ fixture: { ...FIXTURE, mine: false } });
    const marker = screen.getByTestId('fixture-claimed-fx1');
    expect(marker.textContent).toContain('Picked by Alice, Bob');
  });

  it('shows no fixture marker on an untouched game', () => {
    renderCard({ fixture: { ...FIXTURE, mine: false, taken_by_names: [] } });
    expect(screen.queryByTestId('fixture-claimed-fx1')).toBeNull();
  });

  it('renders prices in the caller’s chosen notation', () => {
    renderCard({ oddsFormat: 'fractional' });
    // 2.00 decimal is evens, 3.50 is 5/2.
    expect(screen.getByText('1/1')).toBeTruthy();
    expect(screen.getByText('5/2')).toBeTruthy();
    expect(screen.queryByText('2.00')).toBeNull();
  });
});

// ── Inline table position and form (Batch 16) ─────────────────────────────────
//
// The football data comes from a second provider and can be absent for any club,
// so the card has to read correctly with both sides, one side, or neither.

const FORFAR: TeamContext = {
  team_id: 't-forfar',
  name: 'Forfar Athletic FC',
  position: 1,
  played: 36,
  points: 68,
  goal_difference: 19,
  form: 'WDWWL',
  recent: [],
};

const BRECHIN: TeamContext = {
  team_id: 't-brechin',
  name: 'Brechin City FC',
  position: 2,
  played: 36,
  points: 63,
  goal_difference: 11,
  form: 'LWDWW',
  recent: [],
};

describe('PickCard — inline football context', () => {
  it('shows each club’s position and form beside the fixture', () => {
    renderCard({ fixture: { ...FIXTURE, context: { home: FORFAR, away: BRECHIN } } });

    const strip = screen.getByTestId('fixture-context-fx1');
    expect(within(strip).getByTestId('team-context-t-forfar').textContent).toContain('1st');
    expect(within(strip).getByTestId('team-context-t-brechin').textContent).toContain('2nd');
    expect(within(strip).getByLabelText(/Forfar Athletic FC form, oldest first/)).toBeTruthy();
  });

  it('renders no context strip at all when the fixture has none', () => {
    renderCard();
    expect(screen.queryByTestId('fixture-context-fx1')).toBeNull();
  });

  it('renders no strip when neither club resolved to a known team', () => {
    renderCard({ fixture: { ...FIXTURE, context: { home: null, away: null } } });
    expect(screen.queryByTestId('fixture-context-fx1')).toBeNull();
  });

  it('keeps one club’s data under its own name when the other is unknown', () => {
    renderCard({ fixture: { ...FIXTURE, context: { home: null, away: BRECHIN } } });

    const strip = screen.getByTestId('fixture-context-fx1');
    expect(within(strip).queryByTestId('team-context-t-forfar')).toBeNull();
    // Two grid cells regardless, so the away club cannot slide under the home name.
    expect(strip.children.length).toBe(2);
    expect(strip.children[1].textContent).toContain('2nd');
  });

  it('shows form alone for a club with no table entry — a cup has no table', () => {
    const cupSide: TeamContext = { ...FORFAR, position: null, played: null, points: null };
    renderCard({ fixture: { ...FIXTURE, context: { home: cupSide, away: null } } });

    const cell = screen.getByTestId('team-context-t-forfar');
    expect(cell.textContent).not.toContain('1st');
    expect(within(cell).getByLabelText(/Forfar Athletic FC form, oldest first/)).toBeTruthy();
  });

  it('shows nothing for a club with neither a position nor any form', () => {
    const formless: TeamContext = { ...FORFAR, position: null, form: '' };
    renderCard({ fixture: { ...FIXTURE, context: { home: formless, away: null } } });
    expect(screen.queryByTestId('fixture-context-fx1')).toBeNull();
  });

  it('puts each club’s form in its own grid column under differing name lengths', () => {
    // Batch 50. The names row and the context row must be the same two-column grid, not
    // an inline sentence over a separate grid — otherwise they align only by coincidence.
    const longHome: TeamContext = { ...FORFAR, name: 'Forfar Athletic Football Club' };
    renderCard({ fixture: { ...FIXTURE, context: { home: longHome, away: BRECHIN } } });

    const namesRow = screen.getByTestId('fixture-header-fx1');
    const strip = screen.getByTestId('fixture-context-fx1');
    // Names row and context row are both direct grid children of the same container.
    expect(namesRow).toBe(strip.parentElement);
    expect(namesRow.className).toContain('grid-cols-2');
    expect(within(strip).getByTestId('team-context-t-forfar')).toBeTruthy();
    expect(within(strip).getByTestId('team-context-t-brechin')).toBeTruthy();
  });

  it('still renders every selection when the context is present', () => {
    const { onGrab } = renderCard({
      fixture: { ...FIXTURE, context: { home: FORFAR, away: BRECHIN } },
    });
    fireEvent.click(screen.getByTestId('selection-fx1-MATCH_ODDS-HOME'));
    expect(onGrab).toHaveBeenCalledWith('fx1', 'MATCH_ODDS', 'HOME', 2);
  });
});

// ── Opening a form line (Batch 53) ────────────────────────────────────────────
//
// `TeamContext.recent` has been served on every fixture since Batch 16 and thrown away
// on render. The pips now open onto it.

const FORFAR_RECENT: FormMatch[] = [
  {
    match_id: 'm205',
    kickoff_utc: '2026-04-25T14:00:00Z',
    opponent: 'Brechin City FC',
    home: true,
    goals_for: 1,
    goals_against: 2,
    result: 'L',
  },
  {
    match_id: 'm204',
    kickoff_utc: '2026-04-18T14:00:00Z',
    opponent: 'Stranraer FC',
    home: false,
    goals_for: 2,
    goals_against: 0,
    result: 'W',
  },
];

const FORFAR_OPENABLE: TeamContext = { ...FORFAR, form: 'WL', recent: FORFAR_RECENT };
const BRECHIN_OPENABLE: TeamContext = {
  ...BRECHIN,
  form: 'W',
  // The same match from the other end: Brechin won it at home, Forfar lost it away.
  recent: [
    {
      ...FORFAR_RECENT[0],
      match_id: 'm205b',
      opponent: 'Forfar Athletic FC',
      home: false,
      goals_for: 2,
      goals_against: 1,
      result: 'W',
    },
  ],
};

describe('PickCard — opening a club’s form', () => {
  it('opens the matches behind a club’s pips, under the whole card', () => {
    renderCard({ fixture: { ...FIXTURE, context: { home: FORFAR_OPENABLE, away: null } } });

    fireEvent.click(screen.getByLabelText(/Forfar Athletic FC form, oldest first/));

    const panel = screen.getByRole('list', { name: /Forfar Athletic FC recent results/ });
    expect(within(panel).getAllByRole('listitem').length).toBe(2);
    expect(panel.textContent).toContain('Stranraer FC');
    // Full card width, not the half-column the pips sit in.
    expect(screen.getByTestId('fixture-header-fx1').contains(panel)).toBe(false);
  });

  it('closes it again on a second tap', () => {
    renderCard({ fixture: { ...FIXTURE, context: { home: FORFAR_OPENABLE, away: null } } });
    const pips = screen.getByLabelText(/Forfar Athletic FC form, oldest first/);

    fireEvent.click(pips);
    fireEvent.click(pips);

    expect(screen.queryByRole('list', { name: /recent results/ })).toBeNull();
    expect(pips.getAttribute('aria-expanded')).toBe('false');
  });

  it('shows one club at a time — opening the away side closes the home one', () => {
    renderCard({
      fixture: { ...FIXTURE, context: { home: FORFAR_OPENABLE, away: BRECHIN_OPENABLE } },
    });

    fireEvent.click(screen.getByLabelText(/Forfar Athletic FC form, oldest first/));
    fireEvent.click(screen.getByLabelText(/Brechin City FC form, oldest first/));

    expect(screen.queryByRole('list', { name: /Forfar Athletic FC recent results/ })).toBeNull();
    expect(screen.getByRole('list', { name: /Brechin City FC recent results/ })).toBeTruthy();
  });

  it('leaves a club with no stored matches inert rather than opening an empty panel', () => {
    // FORFAR carries a table position and a provider form string with nothing behind it.
    renderCard({ fixture: { ...FIXTURE, context: { home: FORFAR, away: null } } });

    const pips = screen.getByLabelText(/Forfar Athletic FC form, oldest first/);
    expect(pips.tagName).not.toBe('BUTTON');
    expect(pips.getAttribute('role')).toBe('img');
  });
});
