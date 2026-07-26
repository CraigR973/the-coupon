import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { clearTokens, storeTokens } from '@/lib/tokens';

const FAKE_PLAYER = {
  id: 'p1',
  displayName: 'Alice',
  role: 'player' as const,
  timezone: 'Europe/London',
};

describe('clearTokens', () => {
  let mockCachesDelete: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    mockCachesDelete = vi.fn().mockResolvedValue(true);
    vi.stubGlobal('caches', {
      delete: mockCachesDelete,
      has: vi.fn().mockResolvedValue(false),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('removes all token keys from localStorage', async () => {
    storeTokens('access-tok', 'refresh-tok', FAKE_PLAYER);
    expect(localStorage.getItem('coupon_access')).toBe('access-tok');

    await clearTokens();

    expect(localStorage.getItem('coupon_access')).toBeNull();
    expect(localStorage.getItem('coupon_refresh')).toBeNull();
    expect(localStorage.getItem('coupon_player')).toBeNull();
  });

  it('deletes the Coupon API cache on logout', async () => {
    await clearTokens();

    expect(mockCachesDelete).toHaveBeenCalledWith('api-coupon');
    expect(mockCachesDelete).toHaveBeenCalledTimes(1);
  });

  it('caches.has("api-coupon") is false after clearTokens', async () => {
    await clearTokens();

    const stillPresent = await caches.has('api-coupon');
    expect(stillPresent).toBe(false);
  });

  it('skips cache deletion gracefully when caches API is unavailable', async () => {
    vi.stubGlobal('caches', undefined);
    // Should not throw
    await expect(clearTokens()).resolves.toBeUndefined();
  });
});
