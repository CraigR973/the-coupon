import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SurveyEnhancementsController } from '@/components/SurveyEnhancementsController';
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

describe('SurveyEnhancementsController', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    mockedUseAuth.mockReturnValue({ ...baseAuth });
    localStorage.setItem('sss_tour_seen_p1', '1');
  });

  it('shows the feedback updates modal once for signed-in players', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SurveyEnhancementsController />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/we shipped a few league upgrades/i)).toBeInTheDocument();
    expect(screen.getByText(/long-hold any player row/i)).toBeInTheDocument();
  });

  it('stores dismissal and stays hidden afterwards', async () => {
    const { rerender } = render(
      <MemoryRouter initialEntries={['/']}>
        <SurveyEnhancementsController />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /got it/i }));

    await waitFor(() =>
      expect(screen.queryByText(/we shipped a few league upgrades/i)).not.toBeInTheDocument(),
    );
    expect(localStorage.getItem('sss_survey_enhancements_seen_v1')).toBe('true');

    rerender(
      <MemoryRouter initialEntries={['/']}>
        <SurveyEnhancementsController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/we shipped a few league upgrades/i)).not.toBeInTheDocument();
  });

  it('stays hidden for signed-out users', () => {
    mockedUseAuth.mockReturnValue({ ...baseAuth, player: null });
    render(
      <MemoryRouter initialEntries={['/']}>
        <SurveyEnhancementsController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/we shipped a few league upgrades/i)).not.toBeInTheDocument();
  });

  it('stays hidden away from the dashboard route', () => {
    render(
      <MemoryRouter initialEntries={['/predictions/group']}>
        <SurveyEnhancementsController />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/we shipped a few league upgrades/i)).not.toBeInTheDocument();
  });
});
