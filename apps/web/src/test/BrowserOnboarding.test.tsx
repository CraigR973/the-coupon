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
  it('explains the private points-only game and admin-managed access', () => {
    render(<BrowserOnboarding />);

    expect(screen.getByRole('heading', { name: /one saturday pick/i })).toBeTruthy();
    expect(screen.getByText(/the app never places a bet/i)).toBeTruthy();
    expect(screen.getByText(/admin provides your display name/i)).toBeTruthy();
    expect(screen.queryByText(/create account/i)).toBeNull();
  });
});
