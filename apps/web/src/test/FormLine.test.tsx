import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FormLine, ordinal } from '@/components/FormLine';

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
