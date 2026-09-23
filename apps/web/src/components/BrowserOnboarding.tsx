import { Link } from 'react-router-dom';
import { Menu, Plus, Share } from 'lucide-react';
import { Brand } from '@/components/Brand';
import { Button } from '@/components/ui/button';
import { useInstallPrompt } from '@/hooks/useInstallPrompt';
import { brand } from '@/theme/tokens';

/**
 * The product's one statement of what it is, for anybody who is not signed in.
 *
 * Batch 118 made it the *only* one. There were two onboarding surfaces and the app routed
 * to the weaker of them: `WelcomePage` had per-platform install steps for iOS, Android and
 * desktop and **nothing linked to it** — its sole reference outside the route table was an
 * exclusion list keeping other code out of its way — while this component, which every
 * cold mobile visit and every `/join/:token` claim actually reached, had two holes:
 *
 * * **desktop got nothing at all**, because the controller in front of it returned `null`
 *   when the visitor was not on a phone; and
 * * **Android without `beforeinstallprompt` got nothing either** — the install button
 *   rendered on `canInstall` and the manual steps on `isIos`, so Firefox Android, Samsung
 *   Internet, or Chrome before the event fires satisfied neither and the explainer was
 *   followed by no install instruction of any kind.
 *
 * Two components answering the same question is how one of them went stale unnoticed, so
 * `WelcomePage` is gone and its per-platform content lives here. Five cold-visit cases —
 * iOS Safari, iOS elsewhere, Android with the install event, Android without it, and
 * desktop — all reach this, all get a description of the product, and the four mobile ones
 * all get an install instruction that does not depend on an event firing.
 *
 * **Desktop is a supported way to play**, not a prompt to install: the app runs in a
 * desktop browser, so the desktop case offers account creation and sign-in rather than
 * telling someone with no phone in their hand to install something.
 */
export function BrowserOnboarding({ landmark = false }: { landmark?: boolean }) {
  const { isIos, isIosSafari, isAndroid, isMobile, canInstall, prompt } = useInstallPrompt();
  // This component is a whole screen on `/welcome` and inside `/join/:token`, and a
  // full-screen overlay *on top of* another route everywhere else
  // (`InstallPromptController`). Only the first two may claim the document's `<main>`;
  // the overlay covers routes that already have one, and two <main>s is its own defect.
  const Root = landmark ? 'main' : 'div';

  return (
    <Root className="min-h-screen bg-bg flex flex-col items-center justify-center p-6 pt-safe pb-safe">
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
            Claim a priced football selection before the weekly lock. No two members can
            hold the same selection, and a winner scores its frozen odds multiplied by ten.
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

        {/*
          Rendered on every Android visit, with or without the button above. The button
          needs `beforeinstallprompt`, which Firefox Android and Samsung Internet never
          fire and Chrome fires late — so gating the only instructions on it left a whole
          class of visitor reading an explainer with no way to act on it.
        */}
        {isAndroid && (
          <div className="rounded-xl border border-border bg-surface px-5 py-5 space-y-3">
            <p className="text-sm font-sans font-semibold text-text-primary">
              Install on Android
            </p>
            <ol className="space-y-3">
              <li className="flex gap-3 text-sm font-sans text-text-secondary">
                <Menu className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                <span>Open your browser&rsquo;s menu.</span>
              </li>
              <li className="flex gap-3 text-sm font-sans text-text-secondary">
                <Plus className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                <span>
                  Choose <strong className="text-text-primary">Add to Home screen</strong>{' '}
                  (some browsers call it <strong className="text-text-primary">Install app</strong>
                  ), then open the new icon.
                </span>
              </li>
            </ol>
          </div>
        )}

        {!isMobile && (
          <div className="rounded-xl border border-border bg-surface px-5 py-5 space-y-3">
            <p className="text-sm font-sans font-semibold text-text-primary">
              On a computer
            </p>
            <p className="text-sm font-sans text-text-secondary leading-relaxed">
              The Coupon runs right here in your browser — there is nothing to install.
              On a phone it can be added to your home screen instead.
            </p>
            <div className="flex flex-col gap-2 pt-1">
              <Button asChild className="w-full">
                <Link to="/register">Create an account</Link>
              </Button>
              <Button asChild variant="outline" className="w-full">
                <Link to="/login">I already have an account</Link>
              </Button>
            </div>
          </div>
        )}

        {isMobile && (
          <p className="text-center text-xs font-sans text-text-muted">
            Once the app is installed, create your account — you choose your own display
            name and PIN — and join with your invite link or join code.
          </p>
        )}
      </div>
    </Root>
  );
}
