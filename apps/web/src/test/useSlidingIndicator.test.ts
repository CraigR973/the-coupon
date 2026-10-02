import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSlidingIndicator } from '@/hooks/useSlidingIndicator';

/** An element whose box jsdom reports as given, since jsdom lays nothing out. */
function boxed(left: number, width: number, clientLeft = 0): HTMLElement {
  const element = document.createElement('div');
  element.getBoundingClientRect = () => new DOMRect(left, 0, width, 40);
  Object.defineProperty(element, 'clientLeft', { value: clientLeft });
  return element;
}

// The bar's line drew from the bar's centre because it had no `left` of its own: an
// absolute box without one sits wherever the flex container's `justify-content` puts it.
// jsdom cannot show that, so these pin the two halves of the fix — the anchor travels with
// the style, and the offset is measured from the edge that anchor is measured from. The
// seeded browser journey checks the drawn result at phone width.
describe('useSlidingIndicator', () => {
  it('anchors the indicator at the left edge, measured or not', () => {
    const { result, rerender } = renderHook(({ active }) => useSlidingIndicator(active), {
      initialProps: { active: 'home' },
    });
    expect(result.current.measured).toBe(false);
    expect(result.current.style.left).toBe(0);

    result.current.containerRef.current = boxed(0, 390);
    result.current.activeRef.current = boxed(156, 78);
    rerender({ active: 'football' });

    expect(result.current.measured).toBe(true);
    expect(result.current.style).toEqual({ left: 0, transform: 'translateX(156px)', width: '78px' });
  });

  it('measures from inside the container border, where the anchor is', () => {
    const { result, rerender } = renderHook(({ active }) => useSlidingIndicator(active), {
      initialProps: { active: 'tables' },
    });

    // The segmented tabs: a 1px border, then 4px of padding before the first tab.
    result.current.containerRef.current = boxed(100, 200, 1);
    result.current.activeRef.current = boxed(105, 80);
    rerender({ active: 'results' });

    expect(result.current.style).toEqual({ left: 0, transform: 'translateX(4px)', width: '80px' });
  });
});
