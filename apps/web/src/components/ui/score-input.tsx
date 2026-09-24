import { useEffect, useRef, useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ScoreInputProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  'aria-label': string;
  /** Visual variant — `default` = stacked chevrons (predictions/match-detail). */
  variant?: 'default';
}

const MIN = 0;
const MAX = 99;

/**
 * Score input with stacked ▲ / input / ▼ chevrons.
 *
 * U5.1: the digit briefly springs (1.0 → 1.1 → 1.0) when its value changes,
 * whether the change came from a chevron click, keyboard arrow, or typed
 * input. Skipped entirely under `prefers-reduced-motion: reduce`.
 */
export function ScoreInput({
  value,
  onChange,
  disabled = false,
  'aria-label': ariaLabel,
}: ScoreInputProps) {
  const num = value === '' ? null : Number(value);

  // Bump a key each time the displayed digit *actually* changes, so React re-mounts the
  // digit span and its CSS animation replays. A CSS animation only runs on mount, which
  // is exactly the behaviour wanted here and is why the key exists.
  const [pulseKey, setPulseKey] = useState(0);
  const lastValueRef = useRef(value);
  useEffect(() => {
    if (lastValueRef.current !== value) {
      lastValueRef.current = value;
      setPulseKey((k) => k + 1);
    }
  }, [value]);

  function step(delta: number) {
    if (disabled) return;
    if (num === null) {
      onChange(String(MIN));
      return;
    }
    const next = Math.max(MIN, Math.min(MAX, num + delta));
    onChange(String(next));
  }

  return (
    <div className="flex flex-col items-center gap-0.5">
      {!disabled && (
        <button
          type="button"
          onClick={() => step(1)}
          aria-label={`Increment ${ariaLabel}`}
          className="h-9 w-12 inline-flex items-center justify-center rounded-sm text-text-muted hover:text-primary press-down focus-visible:outline-none focus-visible:shadow-glow"
        >
          <ChevronUp className="h-5 w-5" aria-hidden />
        </button>
      )}

      <div className="relative w-12 h-14">
        <input
          type="number"
          min={MIN}
          max={MAX}
          inputMode="numeric"
          value={value}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '' || /^\d{1,2}$/.test(raw)) onChange(raw);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
              e.preventDefault();
              step(e.key === 'ArrowUp' ? 1 : -1);
            }
          }}
          disabled={disabled}
          aria-label={ariaLabel}
          className={cn(
            'absolute inset-0 w-full h-full text-center font-mono text-3xl font-semibold rounded-md border bg-surface tabular-nums leading-none',
            'transition-shadow duration-fast',
            'focus:outline-none focus-visible:border-primary focus-visible:shadow-glow',
            disabled
              ? 'text-text-muted border-border cursor-not-allowed opacity-50'
              : 'text-text-primary border-border hover:border-primary/50',
            // Hide the native digit so the painted span can show it instead.
            'text-transparent caret-text-primary',
          )}
        />
        {/* Batch 164. Was a framer-motion span rendered only when motion was allowed,
            with the native digit showing otherwise — two different renderings of the same
            number. Now there is one: the span always paints, and `index.css` collapses
            the pulse for anyone who asks for reduced motion. `pulseKey === 0` is the
            first render, which must not pulse at a value the reader never saw change. */}
        <span
          key={pulseKey}
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-3xl font-semibold tabular-nums leading-none',
            pulseKey > 0 && 'animate-value-pulse',
            disabled ? 'text-text-muted opacity-50' : 'text-text-primary',
          )}
        >
          {value}
        </span>
      </div>

      {!disabled && (
        <button
          type="button"
          onClick={() => step(-1)}
          aria-label={`Decrement ${ariaLabel}`}
          className="h-9 w-12 inline-flex items-center justify-center rounded-sm text-text-muted hover:text-primary press-down focus-visible:outline-none focus-visible:shadow-glow"
        >
          <ChevronDown className="h-5 w-5" aria-hidden />
        </button>
      )}
    </div>
  );
}
