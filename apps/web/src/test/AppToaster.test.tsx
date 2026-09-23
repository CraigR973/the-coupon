import { describe, expect, it, afterEach } from 'vitest';
import { render, screen, waitFor, act, cleanup } from '@testing-library/react';
import { toast } from 'sonner';
import { AppToaster } from '@/components/AppToaster';

/**
 * UX-17. Sonner publishes every toast through one `<section aria-live="polite">`,
 * so a failed pick was announced no more urgently than a successful one — a screen
 * reader finished whatever it was saying first. Since Batch 139 that also covers a
 * lost claim race, which is a warning the member has to act on now.
 *
 * Sonner has no per-toast `aria-live`, so `AppToaster` takes the region over: its
 * own is switched off and two of ours carry the text instead.
 */
afterEach(() => {
  act(() => toast.dismiss());
  cleanup();
});

const alerts = () => screen.getByTestId('toast-alerts');
const statuses = () => screen.getByTestId('toast-status');

describe('AppToaster', () => {
  it('announces a failure assertively and a success politely', async () => {
    render(<AppToaster />);

    act(() => {
      toast.error('Your pick didn’t land.');
      toast.success('Grabbed Arsenal @ 2.50');
    });

    await waitFor(() => expect(alerts().textContent).toContain('Your pick didn’t land.'));
    expect(alerts().getAttribute('role')).toBe('alert');
    // The failure must not also sit in the polite region, or it is announced twice.
    expect(statuses().textContent).not.toContain('Your pick didn’t land.');
    expect(statuses().textContent).toContain('Grabbed Arsenal @ 2.50');
    expect(alerts().textContent).not.toContain('Grabbed Arsenal');
  });

  it('treats a warning as urgent, because it is a refusal to act on', async () => {
    // Batch 139 made a lost claim race a warning rather than an error. It is still
    // something the member has to answer, so it still has to interrupt.
    render(<AppToaster />);

    act(() => {
      toast.warning('Someone in your league just grabbed that selection — pick another.');
    });

    await waitFor(() => expect(alerts().textContent).toContain('just grabbed that selection'));
    expect(statuses().textContent).not.toContain('just grabbed that selection');
  });

  it('keeps an informational toast out of the assertive region', async () => {
    render(<AppToaster />);

    act(() => {
      toast.info('You’re offline — we’ll send this pick the moment you’re back.');
    });

    await waitFor(() => expect(statuses().textContent).toContain('You’re offline'));
    expect(alerts().textContent).not.toContain('You’re offline');
  });

  it('silences sonner’s own region, so nothing is announced twice', async () => {
    const { container } = render(<AppToaster />);

    act(() => {
      toast.error('Prices are unavailable right now.');
    });

    await waitFor(() => expect(alerts().textContent).toContain('Prices are unavailable'));
    const region = container.querySelector('section[aria-label*="Notifications"]');
    expect(region, 'sonner’s live region').not.toBeNull();
    expect(region?.getAttribute('aria-live')).toBe('off');
  });
});
