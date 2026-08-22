import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Brand } from '@/components/Brand';
import { BrowserOnboarding } from '@/components/BrowserOnboarding';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { useInstallPrompt } from '@/hooks/useInstallPrompt';
import { API_BASE } from '@/lib/api';
import { dropStaleMemberships } from '@/lib/leagues';
import { getAccessToken } from '@/lib/tokens';
import { brand } from '@/theme/tokens';

const JOIN_CODE_RE = /^[A-Z0-9]{6}$/;

function AppJoinFlow() {
  const { token = '' } = useParams<{ token: string }>();
  const { player } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isJoinCode = JOIN_CODE_RE.test(token.toUpperCase());
  const returnPath = `/join/${encodeURIComponent(token)}`;

  async function claim() {
    setError('');
    setIsSubmitting(true);
    try {
      const accessToken = getAccessToken();
      if (!accessToken) throw new Error('Sign in before joining a league.');

      const endpoint = isJoinCode
        ? `${API_BASE}/api/v1/leagues/join-by-code`
        : `${API_BASE}/api/v1/leagues/claim-invite`;
      const body = isJoinCode ? { code: token.toUpperCase() } : { token };
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const detail = payload.detail ?? 'Failed to join league';
        if (detail === 'ALREADY_MEMBER') throw new Error('You are already a member.');
        if (detail === 'LEAGUE_FULL') throw new Error('This league is full.');
        throw new Error(detail);
      }
      const payload = (await response.json()) as { league_slug: string };
      dropStaleMemberships(queryClient);
      navigate(`/leagues/${payload.league_slug}`, { replace: true });
    } catch (claimError) {
      setError(claimError instanceof Error ? claimError.message : 'Failed to join league');
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center p-4 pt-safe pb-safe">
      <div className="w-full max-w-sm space-y-6">
        <div>
          <Brand variant="splash" />
          <p className="text-center text-text-primary mt-6 font-sans text-base sm:text-lg italic">
            {brand.tagline}
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-center text-text-primary">Join the league</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!token ? (
              <p role="alert" className="text-sm text-center text-error">
                This invite link is incomplete.
              </p>
            ) : player ? (
              <>
                <p className="text-sm text-center text-text-secondary">
                  Signed in as <strong className="text-text-primary">{player.displayName}</strong>.
                </p>
                {error && <p role="alert" className="text-xs text-error">{error}</p>}
                <Button className="w-full" onClick={() => void claim()} disabled={isSubmitting}>
                  {isSubmitting ? 'Joining…' : 'Join league'}
                </Button>
              </>
            ) : (
              <>
                <p className="text-sm text-center text-text-secondary">
                  Create an account or sign in, and this invite will be ready to claim.
                </p>
                {/* Create account leads, because an invite is overwhelmingly the first
                    thing a *new* member sees. Both carry `next`, so whichever they pick
                    returns here with the token intact rather than dropping them on a
                    dashboard with no leagues. */}
                <Button asChild className="w-full">
                  <Link to={`/register?next=${encodeURIComponent(returnPath)}`}>
                    Create account
                  </Link>
                </Button>
                <Button asChild variant="outline" className="w-full">
                  <Link to={`/login?next=${encodeURIComponent(returnPath)}`}>
                    I already have an account
                  </Link>
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function JoinPage() {
  const { isInstalled, isMobile } = useInstallPrompt();
  if (isMobile && !isInstalled) return <BrowserOnboarding />;
  return <AppJoinFlow />;
}
