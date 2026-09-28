import { RotateCcw, TriangleAlert } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';

interface QueryErrorStateProps {
  title: string;
  description: string;
  onRetry: () => void;
  className?: string;
}

/** A failed request is actionable, unlike a successful request with nothing to show. */
export function QueryErrorState({ title, description, onRetry, className }: QueryErrorStateProps) {
  return (
    <section
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-error/40 bg-error/10 px-4 py-10 text-center',
        className,
      )}
      data-testid="query-error-state"
    >
      <div className="mb-3 rounded-full bg-error/15 p-3 text-error" aria-hidden="true">
        <TriangleAlert className="h-6 w-6" />
      </div>
      <h2 className="font-sans text-base font-semibold tracking-tight text-text-primary">{title}</h2>
      <p className="mt-1 max-w-sm font-sans text-sm text-text-muted">{description}</p>
      <Button type="button" variant="outline" className="mt-5" onClick={onRetry}>
        <RotateCcw className="h-4 w-4" aria-hidden="true" />
        Try again
      </Button>
    </section>
  );
}
