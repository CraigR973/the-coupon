import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from './ui/button';
import { EmptyState } from './EmptyState';
import { isChunkLoadError } from '../lib/lazyRoute';

interface Props {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('render failed', error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.reset);

    // A chunk this build no longer serves — the tab is running an older version
    // than the deployment. `lazyRoute` reloads on its own; reaching here means
    // it declined to (offline, or it has already reloaded once), so say what
    // actually happened and offer the only thing that fixes it. "Try again" is
    // deliberately absent: React caches a rejected `lazy` payload, so resetting
    // the boundary re-throws the same error without re-attempting the import.
    if (isChunkLoadError(error)) {
      return (
        <EmptyState
          title="The Coupon has been updated"
          description={
            <span>
              This tab is still running an older version, so that screen could not load. Reload to
              pick up the latest.
            </span>
          }
          action={<Button onClick={() => window.location.reload()}>Reload</Button>}
        />
      );
    }

    return (
      <EmptyState
        title="Something went wrong"
        description={
          <span>
            We hit an unexpected error rendering this view. Try reloading — if it keeps happening,
            let an admin know.
          </span>
        }
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={this.reset}>
              Try again
            </Button>
            <Button onClick={() => window.location.reload()}>Reload</Button>
          </div>
        }
      />
    );
  }
}
