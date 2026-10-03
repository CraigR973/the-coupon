import { useRef } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import axeCore from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '@/App';
import { InstallPromptController } from '@/components/InstallPromptController';

const { useInstallPrompt, registerSW } = vi.hoisted(() => ({
  useInstallPrompt: vi.fn(),
  registerSW: vi.fn(),
}));
vi.mock('@/hooks/useInstallPrompt', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useInstallPrompt')>()),
  useInstallPrompt,
}));
vi.mock('virtual:pwa-register', () => ({ registerSW }));

const MOBILE_GATE = {
  isInstalled: false,
  justInstalled: false,
  isIos: false,
  isIosSafari: false,
  isAndroid: true,
  isMobile: true,
  canInstall: true,
  prompt: vi.fn(),
};

function Shell({ entry = '/login' }: { entry?: string }) {
  const backgroundRef = useRef<HTMLDivElement | null>(null);
  return (
    <MemoryRouter initialEntries={[entry]}>
      <InstallPromptController backgroundRef={backgroundRef} />
      <div ref={backgroundRef} data-testid="background-route">
        <main>
          <h1>Sign in</h1>
          <label htmlFor="hidden-name">Display name</label>
          <input id="hidden-name" />
        </main>
      </div>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useInstallPrompt.mockReset();
  useInstallPrompt.mockReturnValue(MOBILE_GATE);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('InstallPromptController', () => {
  it('makes the covered route inert and exposes one clean install landmark', async () => {
    const user = userEvent.setup();
    render(<Shell />);
    const background = screen.getByTestId('background-route');

    await waitFor(() => expect(background).toHaveAttribute('inert'));
    expect(screen.getByRole('heading', { level: 1, name: /one saturday pick/i })).toBeTruthy();

    const results = await axeCore.run(document.documentElement, {
      runOnly: { type: 'rule', values: ['landmark-one-main', 'region'] },
    });
    expect(results.violations.map((violation) => violation.id)).toEqual([]);

    await user.tab();
    expect(screen.getByRole('button', { name: /install the coupon/i })).toHaveFocus();
    expect(screen.getByLabelText('Display name')).not.toHaveFocus();
  });

  it('removes inert when the gate disappears', async () => {
    const view = render(<Shell />);
    const background = screen.getByTestId('background-route');
    await waitFor(() => expect(background).toHaveAttribute('inert'));

    useInstallPrompt.mockReturnValue({ ...MOBILE_GATE, isInstalled: true, canInstall: false });
    view.rerender(<Shell />);

    await waitFor(() => expect(background).not.toHaveAttribute('inert'));
  });

  it('keeps the post-install state under a main heading too', async () => {
    useInstallPrompt.mockReturnValue({
      ...MOBILE_GATE,
      isInstalled: true,
      justInstalled: true,
      canInstall: false,
    });
    render(<Shell />);

    expect(screen.getByRole('heading', { level: 1, name: /is installed/i })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('background-route')).toHaveAttribute('inert'));
  });

  it('leaves the app update banner usable above the gate', async () => {
    // The banner deliberately stacks above the gate (z-80 over z-70) so nobody waits on
    // an update they cannot take; only the routed page underneath may go inert.
    let needRefresh: (() => void) | undefined;
    registerSW.mockImplementation((callbacks: { onNeedRefresh?: () => void }) => {
      needRefresh = callbacks.onNeedRefresh;
      return vi.fn().mockResolvedValue(undefined);
    });
    vi.stubGlobal('fetch', () =>
      Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
    );
    window.history.pushState({}, '', '/login');
    render(<App />);

    await waitFor(() => expect(screen.getByTestId('app-content')).toHaveAttribute('inert'));
    act(() => needRefresh?.());

    const update = await screen.findByRole('button', { name: /update now/i });
    expect(update.closest('[inert]')).toBeNull();
  });
});
