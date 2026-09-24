import { useCallback, useLayoutEffect, useRef, useState } from 'react';

/**
 * Position an indicator over whichever child is active, so it slides between them.
 *
 * Batch 164. This is what framer-motion's `layoutId` did: two indicators sharing an id
 * across a re-render were animated from one's box to the other's. It is the only thing in
 * the app that needed framer's shared-layout machinery, and it is also the only thing that
 * needed measuring — everything else was a keyframe.
 *
 * The measurement is deliberately the *element's own* box rather than an index-times-width
 * calculation: the tabs are not equal width ("This week" beside "All"), and the bottom bar
 * shows four items or five depending on the route.
 *
 * `useLayoutEffect` rather than `useEffect` so the first paint already has the indicator in
 * the right place; with `useEffect` it flashes at the container's left edge first.
 */
export interface IndicatorPlacement {
  /** Attach to the flex container the items live in. Must be positioned. */
  containerRef: React.MutableRefObject<HTMLElement | null>;
  /**
   * Attach to whichever item is currently active.
   *
   * Mutable on purpose. The bottom bar's More button is both the active tab and the
   * focus anchor its sheet restores to, so it needs two refs on one element — which
   * means a callback ref assigning to this one by hand.
   */
  activeRef: React.MutableRefObject<HTMLElement | null>;
  /** Spread onto the indicator element. */
  style: React.CSSProperties;
  /** False until the first measurement, so nothing slides in from the corner. */
  measured: boolean;
}

export function useSlidingIndicator(
  /** Anything that moves the indicator: the active value, the item count, a variant. */
  ...deps: unknown[]
): IndicatorPlacement {
  const containerRef = useRef<HTMLElement | null>(null);
  const activeRef = useRef<HTMLElement | null>(null);
  const [box, setBox] = useState<{ left: number; width: number } | null>(null);

  const measure = useCallback(() => {
    const container = containerRef.current;
    const active = activeRef.current;
    if (!container || !active) {
      // No active item is a real state — a tab bar on a route none of its tabs own.
      setBox(null);
      return;
    }
    const containerBox = container.getBoundingClientRect();
    const activeBox = active.getBoundingClientRect();
    setBox({ left: activeBox.left - containerBox.left, width: activeBox.width });
  }, []);

  useLayoutEffect(() => {
    measure();
    // The boxes move when the container does: a rotation, a font finishing loading, the
    // keyboard opening on iOS. ResizeObserver catches all of those; a window resize
    // listener catches only the first.
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    if (containerRef.current) observer.observe(containerRef.current);
    if (activeRef.current) observer.observe(activeRef.current);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measure, ...deps]);

  return {
    containerRef,
    activeRef,
    measured: box !== null,
    style: box
      ? { transform: `translateX(${box.left}px)`, width: `${box.width}px` }
      : { transform: 'translateX(0)', width: 0 },
  };
}
