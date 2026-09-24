import { type ReactNode } from 'react';
import { useSlidingIndicator } from '@/hooks/useSlidingIndicator';
import { cn } from '@/lib/utils';

export interface TabItem<T extends string = string> {
  value: T;
  label: ReactNode;
}

interface TabsProps<T extends string> {
  items: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  className?: string;
  /** Segmented = pill-style on a surface (settings, filters). Default is underlined bottom-border style. */
  variant?: 'default' | 'segmented';
}

/**
 * Lightweight roving-tab control. The active indicator slides between tabs rather than
 * cutting — a single measured element in the container, not one per tab.
 *
 * Batch 164 replaced framer-motion's `layoutId` here with `useSlidingIndicator`. The
 * behaviour is the same; the ease is a CSS cubic-bezier rather than a spring, which on a
 * 260ms slide of a few hundred pixels is not a difference anybody can see.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className,
  variant = 'default',
}: TabsProps<T>) {
  const isSegmented = variant === 'segmented';
  const indicator = useSlidingIndicator(value, items.length, variant);

  return (
    <div
      role="tablist"
      ref={indicator.containerRef as React.RefObject<HTMLDivElement>}
      className={cn(
        'relative inline-flex items-center font-sans',
        isSegmented
          ? 'rounded-md bg-surface p-1 gap-1 border border-border'
          : 'gap-1 border-b border-border',
        className,
      )}
    >
      {/* One indicator for the control, positioned over the active tab. Behind the
          buttons for the segmented variant, where it is a filled pill; the underline
          variant draws it along the bottom edge. */}
      <span
        aria-hidden
        data-testid="tab-indicator"
        data-measured={indicator.measured}
        style={indicator.style}
        className={cn(
          'sliding-indicator pointer-events-none absolute',
          isSegmented
            ? 'top-1 bottom-1 rounded-sm bg-surface-elevated'
            : 'bottom-0 h-0.5 bg-primary',
        )}
      />
      {items.map((item) => {
        const isActive = item.value === value;
        return (
          <button
            key={item.value}
            ref={isActive ? (indicator.activeRef as React.Ref<HTMLButtonElement>) : undefined}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(item.value)}
            className={cn(
              'relative px-4 py-2 text-sm font-medium tracking-tight transition-colors focus-visible:outline-none focus-visible:shadow-glow press-down',
              isSegmented ? 'rounded-sm tap-target' : 'tap-target',
              isActive
                ? 'text-text-primary'
                : 'text-text-secondary hover:text-text-primary',
            )}
          >
            <span className="relative z-10">{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
