import { Skeleton } from './ui/skeleton';

/** The placeholder a route shows while its chunk — or the league it needs — arrives. */
export function RouteFallback() {
  return (
    <div className="space-y-4" aria-label="Loading page">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-[320px] w-full" />
    </div>
  );
}
