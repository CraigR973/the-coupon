import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { NotificationsPromptModal, isNotifPromptSeen } from '@/components/NotificationsPromptModal';

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  // Mock matchMedia — standalone by default
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockReturnValue({ matches: true, addListener: vi.fn(), removeListener: vi.fn() }),
  });
  // Stub Notification API
  Object.defineProperty(window, 'Notification', {
    writable: true,
    value: { permission: 'default', requestPermission: vi.fn().mockResolvedValue('granted') },
  });
  // Stub serviceWorker
  Object.defineProperty(navigator, 'serviceWorker', {
    writable: true,
    value: {
      ready: Promise.resolve({
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue({
            toJSON: () => ({ endpoint: 'https://push.example.com', keys: {} }),
          }),
        },
      }),
    },
  });
  vi.stubGlobal('fetch', () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
});

describe('NotificationsPromptModal', () => {
  it('renders Enable button and Maybe later when standalone', () => {
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    expect(screen.getByRole('button', { name: /enable notifications/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /maybe later/i })).toBeTruthy();
  });

  it('sets localStorage flag and calls onClose when Maybe later clicked', () => {
    const onClose = vi.fn();
    render(<NotificationsPromptModal playerId="p1" onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /maybe later/i }));
    expect(isNotifPromptSeen('p1')).toBe(true);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('shows install guidance when not standalone', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({ matches: false }),
    });
    Object.defineProperty(navigator, 'standalone', {
      writable: true,
      value: false,
    });
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    expect(screen.getByText(/add to home screen first/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /enable notifications/i })).toBeNull();
  });

  it('sets localStorage flag and calls onClose when enable clicked', async () => {
    const onClose = vi.fn();
    render(<NotificationsPromptModal playerId="p1" onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /enable notifications/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(isNotifPromptSeen('p1')).toBe(true);
  });

  it('treats iOS standalone mode as installed even when matchMedia is false', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({ matches: false }),
    });
    Object.defineProperty(navigator, 'standalone', {
      writable: true,
      value: true,
    });
    render(<NotificationsPromptModal playerId="p1" onClose={vi.fn()} />);
    expect(screen.getByRole('button', { name: /enable notifications/i })).toBeTruthy();
  });

  it('does not let a legacy global flag suppress a different player prompt', () => {
    localStorage.setItem('coupon_notif_prompt_seen', '1');
    expect(isNotifPromptSeen('p2')).toBe(false);
  });

  // ── Batch 108: the list has to match the product ────────────────────────────

  it('names every notification the application actually sends', () => {
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    // One line per implemented trigger. `picks_open`, the three-hour pre-lock
    // `pick_reminder`, `pick_made`/`pick_changed`, Batch 107's `all_picked`, and the
    // `fixture_postponed` alert that hands a member their claim back.
    expect(screen.getByText(/when a round opens for picks/i)).toBeTruthy();
    expect(screen.getByText(/about three hours before picks lock/i)).toBeTruthy();
    expect(screen.getByText(/when someone else in the league picks/i)).toBeTruthy();
    expect(screen.getByText(/when all picks are in/i)).toBeTruthy();
    expect(screen.getByText(/if a fixture is postponed/i)).toBeTruthy();
  });

  it('promises nothing the application does not send', () => {
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    const copy = document.body.textContent ?? '';
    // The three the screen used to promise. No result alert, no leaderboard alert, and
    // no reminder keyed to kick-off — the real one is keyed to the *lock*, which is a
    // different instant in every league and can be more than a day earlier.
    expect(copy).not.toMatch(/30 minutes/i);
    expect(copy).not.toMatch(/kick-?off/i);
    expect(copy).not.toMatch(/results? land/i);
    expect(copy).not.toMatch(/leaderboard/i);
  });

  it('says the reminder is conditional on not having picked', () => {
    // `send_pick_reminders` only targets members without a pick, so a screen that
    // promised everyone a reminder would be over-promising in the other direction.
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    expect(screen.getByText(/if you haven't picked/i)).toBeTruthy();
  });

  it('points at the mute that actually exists', () => {
    render(<NotificationsPromptModal onClose={vi.fn()} />);
    expect(screen.getByText(/mute a single league, or all of them/i)).toBeTruthy();
  });
});
