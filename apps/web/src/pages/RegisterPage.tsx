import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PinInput } from '@/components/PinInput';
import { Brand } from '@/components/Brand';
import { brand } from '@/theme/tokens';
import { resolveNextDestination } from '@/lib/redirect';
import { API_BASE } from '@/lib/api';
import { keys } from '@/lib/queryKeys';

/** Mirrors the API's own bounds so the obvious mistakes are caught before a round trip. */
const MIN_NAME = 2;
const MAX_NAME = 32;
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._'-]*$/;

function opaqueInviteFromDestination(destination: string): string | undefined {
  const match = /^\/join\/([^/?#]+)$/.exec(destination);
  if (!match) return undefined;
  try {
    const token = decodeURIComponent(match[1]);
    // Six-character links are reusable join codes, not account-creation invites.
    return token.length > 6 && /^[A-Za-z0-9_-]+$/.test(token) ? token : undefined;
  } catch {
    return undefined;
  }
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = resolveNextDestination(location.search, window.location.origin);
  const inviteToken = opaqueInviteFromDestination(destination);
  const { data: signupStatus } = useQuery<{ open: boolean }>({
    queryKey: keys.signupStatus(),
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/v1/auth/signup-status`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Sign-up status unavailable');
      return response.json();
    },
    // Keep today's form on an older API or a failed read. The API remains the authority.
    initialData: { open: true },
    staleTime: 0,
    retry: false,
  });
  const signupClosed = signupStatus?.open === false;

  const [displayName, setDisplayName] = useState('');
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    // Collapsed the same way the API collapses it, so what is validated here is what
    // gets stored — and so "Sam  Smith" is not accepted locally then renamed server-side.
    const name = displayName.trim().replace(/\s+/g, ' ');

    if (name.length < MIN_NAME || name.length > MAX_NAME) {
      setError(`Display name must be ${MIN_NAME}-${MAX_NAME} characters.`);
      return;
    }
    if (!NAME_RE.test(name)) {
      setError("Use letters, numbers, spaces, and . _ ' - starting with a letter or number.");
      return;
    }
    if (pin.length !== 4) {
      setError('Choose a 4-digit PIN.');
      return;
    }
    // Checked before the request rather than after. There is no email on an account and
    // no way to prove who owns one, so a mistyped PIN is not a retry — it is an account
    // only a site admin can reopen.
    if (pin !== confirmPin) {
      setError('Those PINs do not match.');
      return;
    }

    setIsLoading(true);
    try {
      const joinedLeague = await register(name, pin, inviteToken);
      navigate(joinedLeague ? `/leagues/${encodeURIComponent(joinedLeague)}` : destination, {
        replace: true,
      });
    } catch (err) {
      // The API's message is shown as written: "that name is taken", "that PIN is too
      // common" and "sign-ups are closed" are each the only thing that tells a member
      // what to do differently, and a generic string would strand them.
      setError(err instanceof Error ? err.message : 'Could not create your account.');
    } finally {
      setIsLoading(false);
    }
  }

  const next = new URLSearchParams(location.search).get('next');
  const signInHref = next ? `/login?next=${encodeURIComponent(next)}` : '/login';

  return (
    <main className="min-h-screen bg-bg flex flex-col items-center justify-center p-4 pt-safe pb-safe">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Brand variant="splash" />
          <p className="mt-6 font-sans text-lg font-semibold text-text-primary">{brand.tagline}</p>
          <p className="mt-1 font-sans text-sm italic text-text-secondary">{brand.taglineSub}</p>
        </div>

        <Card>
          <CardHeader>
            {/*
              Deliberately not `CardTitle`, which is hard-coded to `<h2>`. These two pages
              render outside `Layout`/`ProtectedRoute`, so nothing on them supplies the
              `<h1>` that `PageHeader` gives every authenticated screen — axe reported
              `page-has-heading-one` on both. The classes are `CardTitle`'s own plus this
              card's, so it is the same heading to look at; only the level changes.
            */}
            <h1 className="text-lg font-semibold leading-tight tracking-tight text-center text-text-primary">
              {signupClosed && !inviteToken ? 'Sign-ups are closed' : 'Create account'}
            </h1>
          </CardHeader>
          <CardContent>
            {signupClosed && !inviteToken ? (
              <div className="space-y-4 text-center">
                <p className="text-sm font-sans text-text-secondary">
                  New accounts need a league invitation while sign-ups are closed.
                </p>
                <Link
                  to={signInHref}
                  className="text-sm font-sans text-text-primary underline underline-offset-4"
                >
                  Already have an account? Sign in
                </Link>
              </div>
            ) : (
            <>
            {signupClosed && inviteToken && (
              <p className="mb-4 text-sm text-center text-text-secondary">
                Your league invitation lets you create an account while public sign-ups are closed.
              </p>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="display-name">Display name</Label>
                <Input
                  id="display-name"
                  type="text"
                  autoComplete="username"
                  required
                  maxLength={MAX_NAME}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                />
                <p className="text-xs font-sans text-text-muted">
                  This is how you sign in and how you appear on every leaderboard.
                </p>
              </div>

              <div className="space-y-1">
                <Label>Choose a PIN</Label>
                <PinInput
                  value={pin}
                  onChange={setPin}
                  maxLength={4}
                  autoComplete="new-password"
                  label="Choose a PIN"
                />
              </div>

              <div className="space-y-1">
                <Label>Confirm PIN</Label>
                <PinInput
                  value={confirmPin}
                  onChange={setConfirmPin}
                  maxLength={4}
                  autoComplete="new-password"
                  label="Confirm PIN"
                />
                <p className="text-xs font-sans text-text-muted">
                  Your PIN is the only way back into your account — there is no email
                  reset. Forget it and tap “Forgot PIN?” on the sign-in screen to ask an
                  admin for a reset.
                </p>
              </div>

              {error && <p role="alert" className="text-xs text-error font-sans">{error}</p>}

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? 'Creating account…' : 'Create account'}
              </Button>

              <div className="text-center">
                <Link
                  to={signInHref}
                  className="text-xs font-sans text-text-muted hover:text-text-primary transition-colors"
                >
                  Already have an account? Sign in
                </Link>
              </div>
            </form>
            </>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
