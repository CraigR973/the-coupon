import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PinInput } from '@/components/PinInput';
import { Brand } from '@/components/Brand';
import { brand } from '@/theme/tokens';

/** Mirrors the API's own bounds so the obvious mistakes are caught before a round trip. */
const MIN_NAME = 2;
const MAX_NAME = 32;
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._'-]*$/;

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

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
      await register(name, pin);
      const requested = new URLSearchParams(location.search).get('next');
      const destination = requested?.startsWith('/') && !requested.startsWith('//')
        ? requested
        : '/';
      navigate(destination, { replace: true });
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
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center p-4 pt-safe pb-safe">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Brand variant="splash" />
          <p className="mt-6 font-sans text-lg font-semibold text-text-primary">{brand.tagline}</p>
          <p className="mt-1 font-sans text-sm italic text-text-secondary">{brand.taglineSub}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-center text-text-primary">Create account</CardTitle>
          </CardHeader>
          <CardContent>
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
                  reset. Forget it and a league admin has to set you a new one.
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
