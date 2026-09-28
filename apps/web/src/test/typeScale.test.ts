import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

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
});
