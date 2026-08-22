import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BrowserOnboarding } from '@/components/BrowserOnboarding';

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({
    isIos: false,
    isIosSafari: false,
    canInstall: false,
    prompt: vi.fn(),
  }),
}));

describe('BrowserOnboarding', () => {
  it('explains the private points-only game', () => {
    render(<BrowserOnboarding />);

    expect(screen.getByRole('heading', { name: /one saturday pick/i })).toBeTruthy();
    expect(screen.getByText(/the app never places a bet/i)).toBeTruthy();
  });

  // Was asserting "your admin provides your display name" plus the *absence* of account
  // creation. Both described the operator-provisioned model that public signup replaced
  // on 2026-08-22 — this is the first screen a shared link reaches on a phone, so it
  // pointing at an admin was the dead end in miniature.
  it('sends a new visitor to create their own account', () => {
    render(<BrowserOnboarding />);

    expect(screen.getByText(/create your account/i)).toBeTruthy();
    expect(screen.queryByText(/admin provides your display name/i)).toBeNull();
  });
});
