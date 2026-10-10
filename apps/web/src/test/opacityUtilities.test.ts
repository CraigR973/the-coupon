import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postcss from 'postcss';
import tailwindcss from '@tailwindcss/postcss';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const sourceRoot = resolve(root, 'src');

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) && !path.includes('/test/') ? [path] : [];
  });
}

describe('opacity-modified colour utilities', () => {
  it('emits a CSS rule for every utility used by the app', async () => {
    const classes = new Set<string>();
    const utility = /(?:[a-z-]+:)*(?:bg|border|text|from|to)-[a-z0-9-]+\/(?:\[[0-9.]+\]|[0-9]+)/g;
    for (const path of sourceFiles(sourceRoot)) {
      for (const match of readFileSync(path, 'utf8').matchAll(utility)) classes.add(match[0]);
    }

    // Tailwind 4 (Batch 202) is no longer a PostCSS plugin itself and reads the v3 config
    // through `@config`, resolved from `from` exactly as index.css resolves it.
    const result = await postcss([tailwindcss()])
      .process("@import 'tailwindcss/theme';\n@import 'tailwindcss/utilities';\n@config '../tailwind.config.ts';", {
        from: resolve(root, 'src/index.css'),
      });
    const missing = [...classes].filter((name) => {
      const selector = `.${name.replace(/[^a-zA-Z0-9_-]/g, (character) => `\\${character}`)}`;
      return !result.css.includes(selector);
    });

    expect(classes.size).toBeGreaterThan(50);
    expect(missing, 'opacity utilities with no generated CSS').toEqual([]);
  });
});
