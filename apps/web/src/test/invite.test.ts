import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildInviteMessage, shareInvite } from '@/lib/invite';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const PARAMS = {
  leagueName: 'Test League',
  joinCode: 'ABC123',
  origin: 'https://example.com',
};

const WITH_LINK = { ...PARAMS, inviteUrl: 'https://example.com/join/tok-123' };

/**
 * Batch 118. Every one of these asserts a *claim the message makes*, not a string it
 * happens to contain — the previous suite pinned "display name and PIN" and "your admin"
 * and was green for three weeks while the message described a sign-in flow that had been
 * deleted, which is the failure mode the tests themselves have to stop repeating.
 */
describe('buildInviteMessage', () => {
  it('names the league and the join code', () => {
    const msg = buildInviteMessage(PARAMS);
    expect(msg).toContain('Test League');
    expect(msg).toContain('ABC123');
  });

  it('mentions The Coupon and leads with the unique Saturday-pick hook', () => {
    const msg = buildInviteMessage(PARAMS);
    expect(msg).toContain('The Coupon');
    expect(msg.toLowerCase()).toContain('unique saturday selection');
    expect(msg.toLowerCase()).toContain('frozen odds');
  });

  /**
   * The defect. Public signup landed on 2026-08-22 and `BrowserOnboarding` was corrected
   * then; this was not, and this is the half that gets sent to strangers. Nobody who
   * followed it could have got in.
   */
  it('never sends the recipient to an admin for a display name or PIN', () => {
    for (const msg of [buildInviteMessage(PARAMS), buildInviteMessage(WITH_LINK)]) {
      const lower = msg.toLowerCase();
      expect(lower).not.toContain('from your admin');
      expect(lower).not.toContain('display name and pin');
      expect(lower).toContain('your own account');
    }
  });

  it('offers the invite link as the path to take when there is one', () => {
    const msg = buildInviteMessage(WITH_LINK);
    expect(msg).toContain('https://example.com/join/tok-123');
    // Before the fallback, because it is the one action the recipient should take.
    expect(msg.indexOf('https://example.com/join/tok-123')).toBeLessThan(msg.indexOf('ABC123'));
  });

  it('keeps the join code as the alternative, for a message forwarded without its link', () => {
    const msg = buildInviteMessage(WITH_LINK);
    expect(msg).toContain('ABC123');
    expect(msg).toContain('Join by code');
  });

  it('falls back to the join-code flow when the league has no live invite', () => {
    const msg = buildInviteMessage(PARAMS);
    expect(msg).not.toContain('/join/');
    expect(msg).toContain('https://example.com');
    expect(msg).toContain('Join by code');
    expect(msg).toContain('Join code: ABC123');
  });

  /**
   * It opened with "Install the app first:" over the bare origin. On a computer there is
   * nothing to install — the app runs in the browser — so the first instruction a desktop
   * recipient read was one they could not carry out.
   */
  it('reads correctly for a recipient on a computer', () => {
    for (const msg of [buildInviteMessage(PARAMS), buildInviteMessage(WITH_LINK)]) {
      expect(msg).not.toContain('Install the app first');
      expect(msg.toLowerCase()).toContain('on a computer it runs in the browser');
      expect(msg.toLowerCase()).toContain('on a phone');
    }
  });

  it('puts the link or the origin above the league details so a url is not read as a code', () => {
    const msg = buildInviteMessage(PARAMS);
    expect(msg.indexOf('https://example.com')).toBeLessThan(msg.indexOf('Join code: ABC123'));
    const linked = buildInviteMessage(WITH_LINK);
    expect(linked.indexOf('https://example.com/join/tok-123')).toBeLessThan(
      linked.indexOf('Join by code'),
    );
  });

  it('stays slim and focused on onboarding', () => {
    expect(buildInviteMessage(PARAMS).length).toBeLessThan(400);
    expect(buildInviteMessage(WITH_LINK).length).toBeLessThan(400);
  });
});

describe('shareInvite — navigator.share absent', () => {
  beforeEach(() => {
    vi.stubGlobal('navigator', {
      share: undefined,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('falls back to clipboard and returns "copied"', async () => {
    const result = await shareInvite({ message: 'hello' });
    expect(result).toBe('copied');
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
  });
});

describe('shareInvite — navigator.share present', () => {
  beforeEach(() => {
    vi.stubGlobal('navigator', {
      share: vi.fn().mockResolvedValue(undefined),
      clipboard: { writeText: vi.fn() },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('calls navigator.share with text only (no url param) and returns "shared"', async () => {
    const result = await shareInvite({ message: 'hello' });
    expect(result).toBe('shared');
    expect(navigator.share).toHaveBeenCalledWith({ text: 'hello' });
  });

  it('returns "cancelled" (not error) when user dismisses the share sheet', async () => {
    const abortErr = Object.assign(new Error('share cancelled'), { name: 'AbortError' });
    vi.mocked(navigator.share).mockRejectedValueOnce(abortErr);
    const result = await shareInvite({ message: 'hello' });
    expect(result).toBe('cancelled');
  });

  it('re-throws non-abort errors', async () => {
    const networkErr = new Error('network failure');
    vi.mocked(navigator.share).mockRejectedValueOnce(networkErr);
    await expect(shareInvite({ message: 'hello' })).rejects.toThrow('network failure');
  });
});
