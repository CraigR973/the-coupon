import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PinInput } from '@/components/PinInput';
import { Brand } from '@/components/Brand';
import { API_BASE } from '@/lib/api';

/**
 * The far end of a PIN reset: the member chooses their own.
 *
 * An admin reset clears the credential rather than minting a temporary PIN, so there is
 * no secret to be read out, written down or reused — and nothing for this screen to ask
 * for except the PIN the member wants. `/login` sends them here with `PIN_NOT_SET`.
 *
 * It sets a PIN and stops. No session is issued: login stays the one place a token pair
 * is minted, so this posts and then hands the member back to the sign-in form with their
 * display name already filled.
 */
export function SetPinPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [displayName, setDisplayName] = useState(params.get('name') ?? '');
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (pin !== confirmPin) {
      setError('Those two PINs are different.');
      return;
    }
    setIsLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/auth/pin/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName.trim(), pin }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(
          typeof body?.detail === 'string' ? body.detail : 'Could not set that PIN.',
        );
      }
      navigate(`/login?name=${encodeURIComponent(displayName.trim())}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not set that PIN.');
      setPin('');
      setConfirmPin('');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center p-4 pt-safe pb-safe">
      <div className="w-full max-w-sm">
        <div className="mb-10">
          <Brand variant="splash" />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-center text-text-primary">Choose a new PIN</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
              <p className="text-sm font-sans text-text-secondary">
                An admin cleared your PIN. Pick a new one — nobody else has seen it, and
                nobody else will.
              </p>

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
                <Label>New PIN</Label>
                <PinInput
                  value={pin}
                  onChange={setPin}
                  maxLength={4}
                  autoComplete="new-password"
                  label="New PIN"
                />
              </div>

              <div className="space-y-1">
                <Label>Confirm new PIN</Label>
                <PinInput
                  value={confirmPin}
                  onChange={setConfirmPin}
                  maxLength={4}
                  autoComplete="new-password"
                  label="Confirm new PIN"
                />
              </div>

              {error && (
                <p role="alert" className="text-xs text-error font-sans">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={isLoading || pin.length !== 4 || confirmPin.length !== 4}
              >
                {isLoading ? 'Saving…' : 'Set PIN and sign in'}
              </Button>

              <div className="text-center">
                <Link
                  to="/login"
                  className="text-xs font-sans text-text-muted hover:text-text-primary transition-colors"
                >
                  Back to sign in
                </Link>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
