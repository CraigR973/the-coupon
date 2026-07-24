import { X } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

interface Props {
  onClose: () => void;
}

const HIGHLIGHTS = [
  {
    title: 'League switching remembers your place',
    body: 'The league rail now stays scrolled where you left it and sits above each league page title.',
  },
  {
    title: 'Live home cards update faster',
    body: 'The live hub now refreshes more aggressively while matches are in play so scores and rank movement land sooner.',
  },
  {
    title: 'Head-to-head is easier to discover',
    body: 'Long-hold any player row in your league leaderboard to jump straight into a head-to-head comparison.',
  },
];

export function SurveyEnhancementsModal({ onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="New updates from your feedback"
    >
      <div
        className="relative w-full max-w-md overflow-hidden rounded-[1.5rem] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className={cn(
            'relative px-6 pb-6 pt-12',
            'bg-gradient-to-br from-[#0f2f28] via-[#163b5d] to-[#111827]',
          )}
        >
          <button
            onClick={onClose}
            className="absolute right-3 top-3 rounded-full p-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Close"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>

          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.3em] text-white/50">
            From Your Feedback
          </p>
          <h2 className="text-2xl font-bold leading-tight text-white">
            We shipped a few league upgrades
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-white/70">
            Thanks for the survey responses. These improvements are live now across the app.
          </p>
        </div>

        <div className="space-y-4 bg-surface px-6 py-5">
          <ul className="space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item.title} className="rounded-2xl border border-border bg-surface-elevated/80 p-3">
                <p className="text-sm font-semibold text-text-primary">{item.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-text-secondary">{item.body}</p>
              </li>
            ))}
          </ul>

          <Button onClick={onClose} className="w-full" size="lg">
            Got it
          </Button>
        </div>
      </div>
    </div>
  );
}
