import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PinInput } from '@/components/PinInput';
import { Brand } from '@/components/Brand';
import { brand } from '@/theme/tokens';
import { PIN_NOT_SET } from '@/lib/api';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [displayName, setDisplayName] = useState(
    () => new URLSearchParams(location.search).get('name') ?? '',
  );
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Whatever brought them to /login — usually an invite at /join/:token — has to survive
  // the trip through account creation, or a new member registers and lands on an empty
  // dashboard instead of the league they were invited to.
  const next = new URLSearchParams(location.search).get('next');
  const registerHref = next ? `/register?next=${encodeURIComponent(next)}` : '/register';

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await login(displayName.trim(), pin);
      const requested = new URLSearchParams(location.search).get('next');
      const destination = requested?.startsWith('/') && !requested.startsWith('//')
        ? requested
        : '/';
      navigate(destination, { replace: true });
    } catch (err) {
      // An admin cleared this member's PIN and they have not chosen a new one yet. It
      // is not a wrong PIN — there is no PIN — and telling them it was would send them
      // round the forgot-PIN loop a second time, which is the loop that got them here.
      if (err instanceof Error && err.message === PIN_NOT_SET) {
        navigate(`/set-pin?name=${encodeURIComponent(displayName.trim())}`);
        return;
      }
      setError('Invalid display name or PIN.');
    } finally {
      setIsLoading(false);
    }
  }

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
              Sign in
            </h1>
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
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                />
              </div>

              <div className="space-y-1">
                <Label>PIN</Label>
                <PinInput value={pin} onChange={setPin} maxLength={4} />
              </div>

              {error && <p role="alert" className="text-xs text-error font-sans">{error}</p>}

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? 'Signing in…' : 'Sign in'}
              </Button>

              <div className="space-y-2 text-center">
                <Link to="/forgot-pin" className="block text-xs font-sans text-text-muted hover:text-text-primary transition-colors">
                  Forgot PIN?
                </Link>
                <p className="text-xs font-sans text-text-muted">
                  New here?{' '}
                  <Link to={registerHref} className="text-primary underline underline-offset-2">
                    Create account
                  </Link>
                </p>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
