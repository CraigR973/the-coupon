import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// tailwind-merge knows only Tailwind's own font sizes and reads any other `text-*` as a
// colour. Batch 151's `text-caption` beside `text-text-muted` was therefore merged away as
// the earlier of two colours, and eight places fell back to the inherited 16px — the bottom
// bar's labels among them. Every key under `fontSize` in tailwind.config.ts belongs here;
// typeScale.test.ts fails when one is missing.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['caption'] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
