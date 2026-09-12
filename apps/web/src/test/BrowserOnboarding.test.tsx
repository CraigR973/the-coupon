import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BrowserOnboarding } from '@/components/BrowserOnboarding';
import type { InstallPromptState } from '@/hooks/useInstallPrompt';

/**
 * Batch 118. The five cold-visit cases, asserted as a table because the holes this closed
 * were both *absences* — a whole class of visitor reaching the explainer and finding no
 * way to act on it — and an absence is only caught by enumerating the cases.
 */
const state = vi.hoisted(() => ({
  current: {} as Partial<InstallPromptState>,
}));

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    isInstalled: false,
    justInstalled: false,
    isIos: false,
    isIosSafari: false,
    isAndroid: false,
    isMobile: false,
    canInstall: false,
    prompt: vi.fn(),
    ...state.current,
  }),
  detectStandalone: () => false,
}));

function renderAs(platform: Partial<InstallPromptState>) {
  state.current = platform;
  return render(
    <MemoryRouter>
      <BrowserOnboarding />
    </MemoryRouter>,
  );
}

const IOS_SAFARI = { isIos: true, isIosSafari: true, isMobile: true };
const IOS_ELSEWHERE = { isIos: true, isIosSafari: false, isMobile: true };
const ANDROID_WITH_EVENT = { isAndroid: true, isMobile: true, canInstall: true };
const ANDROID_WITHOUT_EVENT = { isAndroid: true, isMobile: true, canInstall: false };
const DESKTOP = {};

const EVERY_CASE: [string, Partial<InstallPromptState>][] = [
  ['iOS Safari', IOS_SAFARI],
  ['iOS elsewhere', IOS_ELSEWHERE],
  ['Android with the install event', ANDROID_WITH_EVENT],
  ['Android without the install event', ANDROID_WITHOUT_EVENT],
  ['desktop', DESKTOP],
];

afterEach(() => {
  state.current = {};
});

describe('BrowserOnboarding — the product is described on every platform', () => {
  it.each(EVERY_CASE)('%s says what the app is', (_name, platform) => {
    renderAs(platform);

    expect(screen.getByRole('heading', { name: /one saturday pick/i })).toBeTruthy();
    expect(screen.getByText(/no two members can hold the same selection/i)).toBeTruthy();
    expect(screen.getByText(/the app never places a bet/i)).toBeTruthy();
  });

  // Was asserting "your admin provides your display name" plus the *absence* of account
  // creation. Both described the operator-provisioned model that public signup replaced
  // on 2026-08-22 — this is the first screen a shared link reaches, so it pointing at an
  // admin was the dead end in miniature.
  it.each(EVERY_CASE)('%s never sends anyone to an admin for credentials', (_name, platform) => {
    renderAs(platform);

    expect(screen.queryByText(/from your admin/i)).toBeNull();
    expect(screen.queryByText(/admin provides your display name/i)).toBeNull();
  });
});

describe('BrowserOnboarding — every mobile case gets an install instruction', () => {
  const MOBILE = EVERY_CASE.filter(([name]) => name !== 'desktop');

  it.each(MOBILE)('%s can act on what it is told', (_name, platform) => {
    renderAs(platform);

    expect(screen.getByText(/add to home screen/i)).toBeTruthy();
  });

  it('iOS Safari is told to use the Share button it already has', () => {
    renderAs(IOS_SAFARI);

    expect(screen.getByText(/tap share in safari/i)).toBeTruthy();
    expect(screen.queryByText(/open this page in safari/i)).toBeNull();
  });

  it('iOS elsewhere is told to open the page in Safari first', () => {
    renderAs(IOS_ELSEWHERE);

    expect(screen.getByText(/open this page in safari/i)).toBeTruthy();
  });

  it('Android with the install event offers the native prompt as well as the steps', () => {
    renderAs(ANDROID_WITH_EVENT);

    expect(screen.getByRole('button', { name: /install the coupon/i })).toBeTruthy();
    expect(screen.getByText(/install on android/i)).toBeTruthy();
    expect(screen.getByText(/add to home screen/i)).toBeTruthy();
  });

  /**
   * The hole. `beforeinstallprompt` is Chromium-only and fires late even there, so Firefox
   * Android, Samsung Internet and Chrome-before-the-event all landed on an explainer with
   * no install button and no manual steps — the iOS steps were gated on `isIos`.
   */
  it('Android without the install event still gets manual steps', () => {
    renderAs(ANDROID_WITHOUT_EVENT);

    expect(screen.queryByRole('button', { name: /install the coupon/i })).toBeNull();
    expect(screen.getByText(/open your browser/i)).toBeTruthy();
    expect(screen.getByText(/add to home screen/i)).toBeTruthy();
    expect(screen.getByText(/install app/i)).toBeTruthy();
  });
});

describe('BrowserOnboarding — desktop', () => {
  /**
   * The other hole, and the owner's reading of it: the app runs in a desktop browser, so
   * desktop is a supported way to play rather than a prompt to install. `InstallPromptController`
   * gates nothing off a phone, which already agreed with that; the invite copy was the
   * odd one out and Batch 118 rewrote it to match.
   */
  it('offers the app rather than an install it cannot do', () => {
    renderAs(DESKTOP);

    expect(screen.getByText(/runs right here in your browser/i)).toBeTruthy();
    expect(screen.getByRole('link', { name: /create an account/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /i already have an account/i })).toBeTruthy();
  });

  it('does not show phone install steps to somebody at a computer', () => {
    renderAs(DESKTOP);

    expect(screen.queryByText(/add to home screen/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /install the coupon/i })).toBeNull();
  });
});
