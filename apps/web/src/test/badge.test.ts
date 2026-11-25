import { describe, it, expect } from 'vitest';
import { badgeVariants } from '../components/ui/badge';

/**
 * Batch 248 (25 Nov 2026): no badge fades its colours. The two-game stories flip the page
 * from dark to light and scan it at once; a badge whose text and background faded together
 * crossed over mid-fade and failed colour contrast one run in five.
 */
describe('badges', () => {
  it('never transition their colours, in any variant', () => {
    const variants = [
      'default', 'accent', 'gold', 'silver', 'bronze',
      'success', 'warning', 'error', 'muted', 'live',
    ] as const;
    for (const variant of variants) {
      const classes = badgeVariants({ variant }).split(/\s+/);
      expect(classes, variant).toContain('transition-none');
      expect(classes.filter((name) => name.startsWith('transition-') && name !== 'transition-none'), variant).toEqual([]);
    }
  });
});
