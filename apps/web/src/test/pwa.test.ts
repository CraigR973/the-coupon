import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import { useInstallPrompt } from '@/hooks/useInstallPrompt';

// ─── useOnlineStatus ─────────────────────────────────────────────────────────

describe('useOnlineStatus', () => {
  beforeEach(() => {
    vi.stubGlobal('navigator', { ...navigator, onLine: true });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns true when navigator.onLine is true', () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);
  });

  it('updates to false when offline event fires', () => {
    const { result } = renderHook(() => useOnlineStatus());
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });
    expect(result.current).toBe(false);
  });

  it('updates to true when online event fires after going offline', () => {
    vi.stubGlobal('navigator', { ...navigator, onLine: false });
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    expect(result.current).toBe(true);
  });

  it('removes event listeners on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useOnlineStatus());
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('online', expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith('offline', expect.any(Function));
  });
});

// ─── useInstallPrompt ─────────────────────────────────────────────────────────

describe('useInstallPrompt', () => {
  beforeEach(() => {
    // Not standalone, not iOS, no deferred prompt
    vi.stubGlobal('navigator', {
      ...navigator,
      userAgent:
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    });
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
    } as MediaQueryList);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('canInstall is false initially with no deferred prompt', () => {
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isInstalled).toBe(false);
  });

  it('canInstall becomes true when beforeinstallprompt fires', () => {
    const { result } = renderHook(() => useInstallPrompt());
    const fakePromptEvent = Object.assign(new Event('beforeinstallprompt'), {
      prompt: vi.fn().mockResolvedValue(undefined),
      userChoice: Promise.resolve({ outcome: 'accepted' }),
    });
    act(() => {
      window.dispatchEvent(fakePromptEvent);
    });
    expect(result.current.canInstall).toBe(true);
  });

  it('isInstalled becomes true when appinstalled fires', () => {
    const { result } = renderHook(() => useInstallPrompt());
    act(() => {
      window.dispatchEvent(new Event('appinstalled'));
    });
    expect(result.current.isInstalled).toBe(true);
    expect(result.current.canInstall).toBe(false);
  });

  it('prompt() calls deferredPrompt.prompt() and clears it', async () => {
    const { result } = renderHook(() => useInstallPrompt());
    const mockPrompt = vi.fn().mockResolvedValue(undefined);
    const fakePromptEvent = Object.assign(new Event('beforeinstallprompt'), {
      prompt: mockPrompt,
      userChoice: Promise.resolve({ outcome: 'accepted' }),
    });
    act(() => {
      window.dispatchEvent(fakePromptEvent);
    });
    await act(async () => {
      await result.current.prompt();
    });
    expect(mockPrompt).toHaveBeenCalledOnce();
    expect(result.current.canInstall).toBe(false);
  });
});
