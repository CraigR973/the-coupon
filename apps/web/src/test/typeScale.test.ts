import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { cn } from '@/lib/utils';

const WEB_ROOT = resolve(process.cwd(), 'src');
const TAILWIND = readFileSync(resolve(process.cwd(), 'tailwind.config.ts'), 'utf8');

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) && !path.includes('/test/') ? [path] : [];
  });
}

describe('type scale', () => {
  it('defines the named 12px caption floor', () => {
    expect(TAILWIND).toMatch(/caption:\s*\['0\.75rem',\s*\{\s*lineHeight:\s*'1rem'\s*}\]/);
  });

  it('does not let an interface node fall below the caption floor', () => {
    const undersized = sourceFiles(WEB_ROOT).flatMap((path) => {
      const matches = [...readFileSync(path, 'utf8').matchAll(/text-\[(?:[0-9]|1[01])px\]/g)];
      return matches.map((match) => `${path}:${match[0]}`);
    });

    expect(undersized).toEqual([]);
  });

  // The caption reached members at 16px wherever it went through `cn()`: tailwind-merge took
  // `text-caption` for a colour and dropped it beside a real one — the bottom bar's labels,
  // the form pips, the header wordmark. The sizes are read from the config, so a new one
  // cannot be added without being registered with the merge.
  it('keeps every custom font size beside a text colour, in either order', () => {
    const block = TAILWIND.match(/fontSize:\s*\{([\s\S]*?)\n\s*\}/)?.[1] ?? '';
    const sizes = [...block.matchAll(/^\s*['"]?([\w-]+)['"]?\s*:/gm)].map((match) => match[1]);
    expect(sizes).toContain('caption');

    for (const size of sizes) {
      const expected = [`text-${size}`, 'text-text-muted'].sort();
      expect(cn(`text-${size}`, 'text-text-muted').split(' ').sort()).toEqual(expected);
      expect(cn('text-text-muted', `text-${size}`).split(' ').sort()).toEqual(expected);
    }
  });
});
