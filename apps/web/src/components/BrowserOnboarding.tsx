import { Plus, Share } from 'lucide-react';
import { Brand } from '@/components/Brand';
import { Button } from '@/components/ui/button';
import { useInstallPrompt } from '@/hooks/useInstallPrompt';
import { brand } from '@/theme/tokens';

/**
 * Full-page install guidance for mobile browsers — what a shared link reaches first on a
 * phone, since `JoinPage` shows this instead of the claim flow until the PWA is
 * installed. It explains the game and the install, then hands off to account creation:
 * signup became public on 2026-08-22, so the old "your admin will provide your details"
 * line was describing a flow that no longer exists.
 */
export function BrowserOnboarding() {
  const { isIos, isIosSafari, canInstall, prompt } = useInstallPrompt();

  return (
    <div className="min-h-screen bg-bg flex flex-col items-center justify-center p-6 pt-safe pb-safe">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-3">
          <Brand variant="splash" />
          <p className="text-text-primary font-sans text-lg italic mt-6">{brand.tagline}</p>
        </div>

        <div className="rounded-xl border border-border bg-surface px-5 py-5 space-y-3">
          <h1 className="text-base font-sans font-semibold text-text-primary">
            One Saturday pick. One shared coupon.
          </h1>
          <p className="text-sm font-sans text-text-secondary leading-relaxed">
            Claim a priced football selection before the weekly lock. No two
            members can hold the same selection, and a winner scores its frozen
            odds multiplied by ten.
          </p>
          <p className="text-xs font-sans text-text-muted">
            Points and bragging rights only — the app never places a bet.
          </p>
        </div>

        {canInstall && (
          <Button className="w-full" onClick={() => void prompt()}>
            <Plus className="h-4 w-4 mr-2" aria-hidden />
            Install The Coupon
          </Button>
        )}

        {isIos && (
          <div className="rounded-xl border border-border bg-surface px-5 py-5 space-y-3">
            <p className="text-sm font-sans font-semibold text-text-primary">
              Install on iPhone or iPad
            </p>
            <ol className="space-y-3">
              <li className="flex gap-3 text-sm font-sans text-text-secondary">
                <Share className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                <span>
                  {isIosSafari
                    ? 'Tap Share in Safari.'
                    : 'Open this page in Safari, then tap Share.'}
                </span>
              </li>
              <li className="flex gap-3 text-sm font-sans text-text-secondary">
                <Plus className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                <span>Choose Add to Home Screen, then open the new icon.</span>
              </li>
            </ol>
          </div>
        )}

        <p className="text-center text-xs font-sans text-text-muted">
          Once the app is installed, create your account and join with your code or
          invite link.
        </p>
      </div>
    </div>
  );
}
