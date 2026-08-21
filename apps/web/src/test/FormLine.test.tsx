import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { FormLine, FormMatches, ordinal } from '@/components/FormLine';
import type { FormMatch } from '@/lib/types';

/** Arsenal's canned run, as the API sends it: most recent first. Reads "WDWW". */
const RECENT: FormMatch[] = [
  {
    match_id: 'm107',
    kickoff_utc: '2026-05-02T14:00:00Z',
    opponent: 'Chelsea FC',
    home: false,
    goals_for: 1,
    goals_against: 0,
    result: 'W',
  },
  {
    match_id: 'm105',
    kickoff_utc: '2026-04-25T14:00:00Z',
    opponent: 'Tottenham Hotspur FC',
    home: true,
    goals_for: 2,
    goals_against: 1,
    result: 'W',
  },
  {
    match_id: 'm103',
    kickoff_utc: '2026-04-18T14:00:00Z',
    opponent: 'Liverpool FC',
    home: false,
    goals_for: 2,
    goals_against: 2,
    result: 'D',
  },
  {
    match_id: 'm101',
    kickoff_utc: '2026-04-11T14:00:00Z',
    opponent: 'Everton FC',
    home: true,
    goals_for: 3,
    goals_against: 0,
    result: 'W',
  },
];

/**
 * The default run. `football_form_matches` is 5, so a complete form line is five
 * matches — the canned league data only ever reaches four, which is why the count is
 * pinned here rather than against a fixture that cannot show it.
 */
const FULL_RUN: FormMatch[] = [
  ...RECENT,
  {
    match_id: 'm099',
    kickoff_utc: '2026-04-04T14:00:00Z',
    opponent: 'Manchester City FC',
    home: false,
    goals_for: 0,
    goals_against: 2,
    result: 'L',
  },
];

describe('FormLine', () => {
  it('renders one pip per result, oldest on the left', () => {
    const { container } = render(<FormLine form="LWWDW" />);
    const pips = [...container.querySelectorAll('span[aria-hidden]')];
    expect(pips.map((pip) => pip.textContent)).toEqual(['L', 'W', 'W', 'D', 'W']);
  });

  it('keeps the letter on every pip, so colour is never the only signal', () => {
    const { container } = render(<FormLine form="WL" />);
    for (const pip of container.querySelectorAll('span[aria-hidden]')) {
      expect(pip.textContent).toMatch(/^[WDL]$/);
    }
  });

  it('spells the run out for screen readers, naming the club', () => {
    render(<FormLine form="WDL" team="Forfar Athletic" />);
    expect(
      screen.getByLabelText('Forfar Athletic form, oldest first: won, drew, lost'),
    ).toBeTruthy();
  });

  it('renders nothing for a club with no form rather than an empty box', () => {
    const { container } = render(<FormLine form="" team="Forfar Athletic" />);
    expect(container.innerHTML).toBe('');
  });

  it('ignores anything that is not a result letter', () => {
    const { container } = render(<FormLine form="W?D" />);
    expect([...container.querySelectorAll('span[aria-hidden]')].length).toBe(2);
  });
});

// ── The disclosure (Batch 53) ─────────────────────────────────────────────────

describe('FormLine as a disclosure', () => {
  it('stays a plain graphic with nothing to open', () => {
    const { container } = render(<FormLine form="WDWW" team="Arsenal FC" />);
    expect(container.querySelector('button')).toBeNull();
    expect(screen.getByRole('img')).toBeTruthy();
  });

  it('becomes a button when there is something behind the pips', () => {
    render(<FormLine form="WDWW" team="Arsenal FC" onToggle={vi.fn()} controls="panel-1" />);

    // Same sentence the graphic carried — it names the same thing — now on the control.
    const button = screen.getByLabelText('Arsenal FC form, oldest first: won, drew, won, won');
    expect(button.tagName).toBe('BUTTON');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(button.getAttribute('aria-controls')).toBe('panel-1');
    // The pips are decoration once the button carries the name, not a nested graphic.
    expect(button.querySelector('[role="img"]')).toBeNull();
  });

  it('reports its open state so a screen reader hears the panel appear', () => {
    render(<FormLine form="WDWW" team="Arsenal FC" onToggle={vi.fn()} expanded />);
    expect(screen.getByRole('button', { expanded: true })).toBeTruthy();
  });

  it('toggles on activation, from a real button rather than a clickable span', () => {
    const onToggle = vi.fn();
    render(<FormLine form="WDWW" team="Arsenal FC" onToggle={onToggle} />);
    const button = screen.getByRole('button');

    fireEvent.click(button);

    expect(onToggle).toHaveBeenCalledTimes(1);
    // A `<button type="button">` is what makes Enter and Space work and puts the run in
    // the tab order — jsdom will not synthesise either, so the element earning that
    // behaviour is the thing worth pinning.
    expect(button.getAttribute('type')).toBe('button');
  });
});

describe('FormMatches', () => {
  it('lists the matches oldest first, so the nth row is the nth pip', () => {
    render(<FormMatches matches={RECENT} team="Arsenal FC" timezone="UTC" />);

    const rows = screen.getAllByRole('listitem');
    expect(rows.map((row) => within(row).getByText(/FC$/).textContent)).toEqual([
      'Everton FC',
      'Liverpool FC',
      'Tottenham Hotspur FC',
      'Chelsea FC',
    ]);
  });

  it('opens a full five-match run to one row per pip, each the right way round', () => {
    render(<FormMatches matches={FULL_RUN} team="Arsenal FC" timezone="UTC" />);

    const rows = screen.getAllByRole('listitem');
    expect(rows.length).toBe(5);
    // Oldest first, so the nth row is the nth pip, and the orientation travels with it:
    // an away trip stays an away trip wherever it lands in the run.
    expect(
      rows.map((row) => [
        within(row).getByText(/FC$/).textContent,
        within(row).getByText(/^(home|away) to$/).textContent,
      ]),
    ).toEqual([
      ['Manchester City FC', 'away to'],
      ['Everton FC', 'home to'],
      ['Liverpool FC', 'away to'],
      ['Tottenham Hotspur FC', 'home to'],
      ['Chelsea FC', 'away to'],
    ]);
  });

  it('gives a home fixture its opponent, score and date', () => {
    render(<FormMatches matches={RECENT} team="Arsenal FC" timezone="UTC" />);

    const everton = screen.getByTestId('form-match-m101');
    expect(everton.textContent).toContain('11 Apr');
    expect(everton.textContent).toContain('Everton FC');
    expect(everton.textContent).toContain('3–0');
    expect(within(everton).getByText('home to')).toBeTruthy();
  });

  it('turns an away fixture round without turning its score round', () => {
    // Chelsea 0-1 Arsenal is a 1–0 win read from Arsenal's side, and it was away.
    render(<FormMatches matches={RECENT} team="Arsenal FC" timezone="UTC" />);

    const chelsea = screen.getByTestId('form-match-m107');
    expect(chelsea.textContent).toContain('Chelsea FC');
    expect(chelsea.textContent).toContain('1–0');
    expect(within(chelsea).getByText('away to')).toBeTruthy();
    expect(within(chelsea).getByText('won')).toBeTruthy();
  });

  it('names the list for a screen reader and says which way it runs', () => {
    render(<FormMatches matches={RECENT} team="Arsenal FC" timezone="UTC" id="panel-1" />);
    const list = screen.getByRole('list', { name: 'Arsenal FC recent results, oldest first' });
    expect(list.getAttribute('id')).toBe('panel-1');
  });

  it('renders nothing rather than an empty panel for a club with no matches', () => {
    const { container } = render(<FormMatches matches={[]} team="Arsenal FC" timezone="UTC" />);
    expect(container.innerHTML).toBe('');
  });

  it('renders the reader’s own timezone, not UTC', () => {
    render(<FormMatches matches={RECENT} team="Arsenal FC" timezone="Pacific/Auckland" />);
    // 2 May 14:00 UTC is already 3 May in Auckland.
    expect(screen.getByTestId('form-match-m107').textContent).toContain('3 May');
  });
});

describe('ordinal', () => {
  it('suffixes the ordinary cases', () => {
    expect([1, 2, 3, 4, 20].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '20th']);
  });

  it('handles the teens, which are all "th" whatever they end in', () => {
    expect([11, 12, 13].map(ordinal)).toEqual(['11th', '12th', '13th']);
  });

  it('keeps suffixing past twenty — a division can run to 24 clubs', () => {
    expect([21, 22, 23, 24].map(ordinal)).toEqual(['21st', '22nd', '23rd', '24th']);
  });
});
