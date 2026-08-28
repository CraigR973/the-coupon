import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OutstandingPickNotice } from '@/components/OutstandingPickNotice';
import type { OutstandingPick } from '@/hooks/usePickEditor';

const QUEUED: OutstandingPick = {
  key: 'fx1:MATCH_ODDS:HOME',
  state: 'queued',
  body: { fixture_id: 'fx1', market: 'MATCH_ODDS', outcome: 'HOME' },
};
const UNCONFIRMED: OutstandingPick = { ...QUEUED, state: 'unconfirmed' };

function renderNotice(outstanding: OutstandingPick, overrides = {}) {
  const onResolve = vi.fn();
  const onDiscard = vi.fn();
  render(
    <OutstandingPickNotice
      outstanding={outstanding}
      onResolve={onResolve}
      onDiscard={onDiscard}
      {...overrides}
    />,
  );
  return { onResolve, onDiscard };
}

describe('OutstandingPickNotice', () => {
  it('says a queued pick has not been sent and offers to send it', () => {
    renderNotice(QUEUED);
    expect(screen.getByTestId('outstanding-pick-notice')).toHaveAttribute('data-state', 'queued');
    expect(screen.getByTestId('outstanding-pick-notice')).toHaveTextContent(/hasn’t been sent/i);
    expect(screen.getByTestId('outstanding-pick-resolve')).toHaveTextContent(/send now/i);
  });

  it('says an unconfirmed claim is unconfirmed and offers to check, not to re-send', () => {
    // The wording is the deliverable. "Send again" on a claim that may already be the
    // member's is an offer to overwrite a selection they might have moved on from — the
    // exact silent double-submit this batch exists to prevent.
    renderNotice(UNCONFIRMED);
    const notice = screen.getByTestId('outstanding-pick-notice');
    expect(notice).toHaveAttribute('data-state', 'unconfirmed');
    expect(notice).toHaveTextContent(/unconfirmed/i);
    expect(notice).toHaveTextContent(/may or may not have landed/i);
    expect(screen.getByTestId('outstanding-pick-resolve')).toHaveTextContent(/check my pick/i);
    expect(screen.getByTestId('outstanding-pick-resolve')).not.toHaveTextContent(/send/i);
  });

  it('reads the two states differently, and neither reads as losing the race', () => {
    // The three outcomes the old single toast collapsed. "Someone got there first" is an
    // answer from the server and clears the held intent, so it never renders here — this
    // notice must not claim it, and must not read like it either.
    const { unmount } = render(
      <OutstandingPickNotice outstanding={QUEUED} onResolve={vi.fn()} onDiscard={vi.fn()} />,
    );
    const queuedText = screen.getByTestId('outstanding-pick-notice').textContent ?? '';
    unmount();

    renderNotice(UNCONFIRMED);
    const unconfirmedText = screen.getByTestId('outstanding-pick-notice').textContent ?? '';

    expect(queuedText).not.toEqual(unconfirmedText);
    for (const text of [queuedText, unconfirmedText]) {
      expect(text).not.toMatch(/grabbed|taken|someone else/i);
    }
  });

  it('is announced to a screen reader as it appears', () => {
    // It replaces a toast that a member on a phone in a pub will not have been looking at.
    renderNotice(UNCONFIRMED);
    const notice = screen.getByTestId('outstanding-pick-notice');
    expect(notice).toHaveAttribute('role', 'status');
    expect(notice).toHaveAttribute('aria-live', 'polite');
  });

  it('wires the two actions and keeps dismiss usable after the round shuts', () => {
    // A locked round can no longer take the pick, so sending is off — but the member must
    // still be able to clear a notice that can never resolve.
    const { onResolve, onDiscard } = renderNotice(QUEUED, { disabled: true });
    expect(screen.getByTestId('outstanding-pick-resolve')).toBeDisabled();

    fireEvent.click(screen.getByTestId('outstanding-pick-discard'));
    expect(onDiscard).toHaveBeenCalledTimes(1);
    expect(onResolve).not.toHaveBeenCalled();
  });
});
