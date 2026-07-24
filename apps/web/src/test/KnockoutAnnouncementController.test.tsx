import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KnockoutAnnouncementController } from '@/components/KnockoutAnnouncementController';
import { useAuth } from '@/contexts/AuthContext';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockedUseAuth = vi.mocked(useAuth);

const player = {
  id: 'p1',
  displayName: 'Alice',
  email: null,
  role: 'player' as const,
  timezone: 'UTC',
  avatarUrl: null,
};

const baseAuth = {
  player,
  isLoading: false,
  sessionUnlockRequired: false,
  sessionUnlockError: null,
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  updatePlayer: vi.fn(),
  unlockStoredSession: vi.fn(),
};

describe('KnockoutAnnouncementController', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    mockedUseAuth.mockReturnValue({ ...baseAuth });
    localStorage.setItem('sss_tour_seen_p1', '1');
  });

  it('shows the knockout update modal once for signed-in players', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/the bracket is ready for business/i)).toBeInTheDocument();
    expect(screen.getByText(/brother barry got the scotland gig/i)).toBeInTheDocument();
    expect(screen.getByAltText(/brother barry unveiled as the new scotland manager/i)).toBeInTheDocument();
  });

  it('stores dismissal per player and stays hidden afterwards', async () => {
    const { rerender } = render(
      <MemoryRouter initialEntries={['/']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /back to the knockouts/i }));

    await waitFor(() =>
      expect(screen.queryByText(/the bracket is ready for business/i)).not.toBeInTheDocument(),
    );
    expect(localStorage.getItem('sss_knockout_announcement_seen_v1_p1')).toBe('true');

    rerender(
      <MemoryRouter initialEntries={['/']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/the bracket is ready for business/i)).not.toBeInTheDocument();
  });

  it('stays hidden after a prior dismissal', async () => {
    localStorage.setItem('sss_knockout_announcement_seen_v1_p1', 'true');

    render(
      <MemoryRouter initialEntries={['/']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );

    expect(screen.queryByText(/the bracket is ready for business/i)).not.toBeInTheDocument();
  });

  it('stays hidden for signed-out users', () => {
    mockedUseAuth.mockReturnValue({ ...baseAuth, player: null });
    render(
      <MemoryRouter initialEntries={['/']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/the bracket is ready for business/i)).not.toBeInTheDocument();
  });

  it('stays hidden away from the dashboard route', () => {
    render(
      <MemoryRouter initialEntries={['/predictions/knockout']}>
        <KnockoutAnnouncementController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/the bracket is ready for business/i)).not.toBeInTheDocument();
  });
});
