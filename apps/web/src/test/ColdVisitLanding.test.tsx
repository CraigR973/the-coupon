import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from '@/components/ProtectedRoute';

/**
 * Batch 118. Where a person who is not signed in ends up, which is the whole reason the
 * desktop hole existed: the mobile install gate returns `null` off a phone, so a desktop
 * visitor following an invite landed on the sign-in form with no statement anywhere of
 * what the app is.
 */
const { auth, standalone } = vi.hoisted(() => ({
  auth: { player: null as { id: string } | null, sessionUnlockRequired: false },
  standalone: { value: false },
}));

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('../hooks/useInstallPrompt', () => ({ detectStandalone: () => standalone.value }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/welcome" element={<p>welcome surface</p>} />
        <Route path="/login" element={<p>sign-in form</p>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<p>dashboard</p>} />
          <Route path="/leagues/:slug/predictions" element={<p>the coupon</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  auth.player = null;
  auth.sessionUnlockRequired = false;
  standalone.value = false;
});

describe('a cold visit', () => {
  it('lands on the product rather than on a login form', () => {
    renderAt('/');

    expect(screen.getByText('welcome surface')).toBeTruthy();
  });

  /**
   * An installed app whose session has expired belongs at the sign-in form. Sending its
   * owner to a page explaining how to install what they are already standing inside would
   * be the same class of mistake in the other direction.
   */
  it('from an installed app goes to sign in, not to install instructions', () => {
    standalone.value = true;
    renderAt('/');

    expect(screen.getByText('sign-in form')).toBeTruthy();
  });

  /**
   * A deep link is a returning member, not a stranger — and `next` on the login form is
   * what brings them back to the page they asked for.
   */
  it('to a deep link still goes to sign in', () => {
    renderAt('/leagues/the-coupon/predictions');

    expect(screen.getByText('sign-in form')).toBeTruthy();
  });

  it('does not divert a signed-in member', () => {
    auth.player = { id: 'p1' };
    renderAt('/');

    expect(screen.getByText('dashboard')).toBeTruthy();
  });
});
