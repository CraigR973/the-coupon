import { X } from 'lucide-react';
import barryScotlandJob from '@/assets/barry-scotland-job.png';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

interface Props {
  onClose: () => void;
}

const KNOCKOUT_UPDATES = [
  {
    title: 'Knockout picks are live',
    body: 'You can now fill in the bracket matches as they unlock, and keep editing any future tie right up until that specific kickoff.',
  },
  {
    title: 'Predicted a draw after 90? Pick who goes through',
    body: 'For knockout matches that finish all square in normal time, you now pick the team that advances as well as the 90-minute scoreline.',
  },
  {
    title: 'Old picks stay visible while you tweak',
    body: 'Future knockout cards keep your current picks on screen so it is easier to update them without losing track of what you had before.',
  },
];

export function KnockoutAnnouncementModal({ onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-2 pt-16 sm:items-center sm:p-4 sm:pt-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Knockout stage update"
    >
      <div
        className="relative flex max-h-[calc(100dvh-4rem)] w-full max-w-lg flex-col overflow-hidden rounded-[1.75rem] shadow-2xl sm:max-h-[90vh]"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className={cn(
            'relative shrink-0 overflow-hidden px-6 pb-6 pt-12',
            'bg-gradient-to-br from-[#0c2340] via-[#123a66] to-[#0f172a]',
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
            Knockout Update
          </p>
          <h2 className="text-2xl font-bold leading-tight text-white">
            The bracket is ready for business
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-white/80">
            You can now pick knockout winners and advance teams as the rounds unlock.
          </p>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain bg-surface">
          <div className="space-y-5 px-6 py-5">
            <ul className="space-y-3">
              {KNOCKOUT_UPDATES.map((item) => (
                <li
                  key={item.title}
                  className="rounded-2xl border border-border bg-surface-elevated/80 p-4"
                >
                  <p className="text-sm font-semibold text-text-primary">{item.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-text-secondary">{item.body}</p>
                </li>
              ))}
            </ul>

            <div className="overflow-hidden rounded-2xl border border-border bg-surface-elevated/70">
              <img
                src={barryScotlandJob}
                alt="Brother Barry unveiled as the new Scotland manager"
                className="h-56 w-full object-cover object-top"
              />
              <div className="space-y-2 p-4">
                <p className="text-xs font-mono uppercase tracking-[0.24em] text-text-muted">
                  Update 2
                </p>
                <p className="text-base font-semibold text-text-primary">
                  Brother Barry got the Scotland gig in the end.
                </p>
                <p className="text-sm leading-relaxed text-text-secondary">
                  Fair play to him. Hard to compete once he turned up with the shirt already printed.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="shrink-0 border-t border-border bg-surface px-6 py-4">
          <Button onClick={onClose} className="w-full" size="lg">
            Back to the knockouts
          </Button>
        </div>
      </div>
    </div>
  );
}
