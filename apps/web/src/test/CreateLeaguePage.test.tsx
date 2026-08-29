import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateLeaguePage } from '@/pages/CreateLeaguePage';

// Far-future exp so apiFetch's ensureFreshToken never tries to refresh.
const FAKE_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJwMSIsImV4cCI6OTk5OTk5OTk5OX0.fake';
const STORED_PLAYER = JSON.stringify({ id: 'p1', displayName: 'Alice', role: 'player', timezone: 'UTC' });

function stubAuth() {
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => {
      if (k === 'coupon_player') return STORED_PLAYER;
      if (k === 'coupon_access') return FAKE_JWT;
      return null;
    },
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  });
}

/** Stub fetch, capturing the parsed body of the create-league POST. */
function stubCreate(): { get: () => Record<string, unknown> | null } {
  let captured: Record<string, unknown> | null = null;
  vi.stubGlobal('fetch', (url: string, init: RequestInit) => {
    if (url.includes('/api/v1/leagues')) {
      captured = JSON.parse(init.body as string) as Record<string, unknown>;
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ slug: 'my-league' }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  return { get: () => captured };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/leagues/new']}>
      <QueryClientProvider client={qc}>
        <CreateLeaguePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  stubAuth();
});

describe('CreateLeaguePage — privacy payload maps to backend enum', () => {
  // Batch 91: the default is invite-only. Since Batch 63 opened self-registration,
  // "public" means anyone who has signed up, so the least-private option must not be
  // what a creator gets by not touching the dropdown. This also matches the API's own
  // default (`CreateLeagueRequest.privacy = LeaguePrivacy.private`).
  it('sends "private" when the creator never touches the dropdown', async () => {
    const req = stubCreate();
    renderPage();
    fireEvent.change(screen.getByLabelText(/league name/i), { target: { value: 'My League' } });
    fireEvent.click(screen.getByRole('button', { name: /create league/i }));
    await waitFor(() => expect(req.get()).not.toBeNull());
    expect(req.get()?.privacy).toBe('private');
  });

  it('preselects the invite-only option rather than leaving the field blank', () => {
    renderPage();
    expect((screen.getByLabelText(/privacy/i) as HTMLSelectElement).value).toBe('private');
  });

  it('maps the Request option to "public_request"', async () => {
    const req = stubCreate();
    renderPage();
    fireEvent.change(screen.getByLabelText(/league name/i), { target: { value: 'My League' } });
    fireEvent.change(screen.getByLabelText(/privacy/i), { target: { value: 'public_request' } });
    fireEvent.click(screen.getByRole('button', { name: /create league/i }));
    await waitFor(() => expect(req.get()).not.toBeNull());
    expect(req.get()?.privacy).toBe('public_request');
  });

  it('maps the open option to "public_open", not the legacy "open" that 422s', async () => {
    const req = stubCreate();
    renderPage();
    fireEvent.change(screen.getByLabelText(/league name/i), { target: { value: 'My League' } });
    fireEvent.change(screen.getByLabelText(/privacy/i), { target: { value: 'public_open' } });
    fireEvent.click(screen.getByRole('button', { name: /create league/i }));
    await waitFor(() => expect(req.get()).not.toBeNull());
    expect(req.get()?.privacy).toBe('public_open');
  });
});

describe('CreateLeaguePage — privacy copy states the real consequence (Batch 91)', () => {
  it('describes invite-only as hidden from Discover and join-code-only', () => {
    renderPage();
    const help = screen.getByLabelText(/privacy/i).getAttribute('aria-describedby');
    expect(help).toBe('privacy-help');
    const text = document.getElementById('privacy-help')!.textContent!;
    expect(text).toMatch(/hidden from discover/i);
    expect(text).toMatch(/join code/i);
  });

  it('warns that the open option lets strangers in without asking', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/privacy/i), { target: { value: 'public_open' } });
    const text = document.getElementById('privacy-help')!.textContent!;
    // The consequence Batch 63 created: "anyone" is now anyone with an account,
    // not only people the creator already knows.
    expect(text).toMatch(/anyone with an account/i);
    expect(text).toMatch(/without asking you/i);
    expect(text).toMatch(/never met/i);
  });

  it('distinguishes request-to-join by the approval step', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/privacy/i), { target: { value: 'public_request' } });
    const text = document.getElementById('privacy-help')!.textContent!;
    expect(text).toMatch(/approve or decline/i);
  });

  it('gives each option a label naming its consequence', () => {
    renderPage();
    const labels = Array.from(
      (screen.getByLabelText(/privacy/i) as HTMLSelectElement).options,
      (o) => o.textContent,
    );
    expect(labels).toEqual([
      'Private — invite only',
      'Public — anyone can ask to join',
      'Public — anyone can join instantly',
    ]);
  });
});

describe('CreateLeaguePage — admin config payload (Batch 15)', () => {
  it('defaults to the Saturday 3pm window and both markets', async () => {
    const req = stubCreate();
    renderPage();
    fireEvent.change(screen.getByLabelText(/league name/i), { target: { value: 'My League' } });
    fireEvent.click(screen.getByRole('button', { name: /create league/i }));
    await waitFor(() => expect(req.get()).not.toBeNull());
    const body = req.get()!;
    expect(body.offered_markets).toEqual(['MATCH_ODDS', 'BOTH_TEAMS_TO_SCORE']);
    expect(body.slate_start_weekday).toBe(5);
    expect(body.slate_start_minute).toBe(900);
    expect(body.lock_offset_minutes).toBe(30);
    // Competitions are not sent at creation — the backend defaults them to the all-UK group.
    expect('competitions' in body).toBe(false);
  });

  it('drops a market the creator unticks', async () => {
    const req = stubCreate();
    renderPage();
    fireEvent.change(screen.getByLabelText(/league name/i), { target: { value: 'My League' } });
    fireEvent.click(screen.getByLabelText(/both teams to score/i));
    fireEvent.click(screen.getByRole('button', { name: /create league/i }));
    await waitFor(() => expect(req.get()).not.toBeNull());
    expect(req.get()?.offered_markets).toEqual(['MATCH_ODDS']);
  });
});
