/**
 * Generate The Coupon's PWA icons from one inline ticket mark.
 *
 * Run with:
 *   node apps/web/generate-icons.mjs
 */

import { Resvg } from '@resvg/resvg-js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const outputDir = join(scriptDir, 'public');

const NAVY = '#071A3D';
const PAPER = '#F8F5ED';
const GOLD = '#D4A44B';

function ticketMark(background = NAVY) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="The Coupon ticket icon">
  <rect width="512" height="512" rx="96" fill="${background}"/>
  <path d="M104 150h304a32 32 0 0 1 32 32v44a30 30 0 0 0 0 60v44a32 32 0 0 1-32 32H104a32 32 0 0 1-32-32v-44a30 30 0 0 0 0-60v-44a32 32 0 0 1 32-32Z" fill="${PAPER}"/>
  <path d="M318 166v180" stroke="${GOLD}" stroke-width="12" stroke-linecap="round" stroke-dasharray="4 22"/>
  <path d="M132 218h126M132 266h96M132 314h72" stroke="${NAVY}" stroke-width="18" stroke-linecap="round"/>
  <circle cx="379" cy="256" r="30" fill="${GOLD}"/>
</svg>
`;
}

function render(svg, size) {
  return new Resvg(svg, {
    fitTo: { mode: 'width', value: size },
    font: { loadSystemFonts: false },
  }).render().asPng();
}

function pngToIco(png) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(1, 4);

  const entry = Buffer.alloc(16);
  entry.writeUInt8(32, 0);
  entry.writeUInt8(32, 1);
  entry.writeUInt16LE(1, 4);
  entry.writeUInt16LE(32, 6);
  entry.writeUInt32LE(png.length, 8);
  entry.writeUInt32LE(22, 12);
  return Buffer.concat([header, entry, png]);
}

mkdirSync(outputDir, { recursive: true });
const master = ticketMark();
writeFileSync(join(outputDir, 'coupon-icon.svg'), master);
writeFileSync(join(outputDir, 'favicon.svg'), master);

for (const size of [32, 64, 128, 192, 384, 512, 1024]) {
  writeFileSync(join(outputDir, `icon-${size}.png`), render(master, size));
}

writeFileSync(join(outputDir, 'apple-touch-icon.png'), render(master, 180));
writeFileSync(join(outputDir, 'icon-maskable-512.png'), render(master, 512));
writeFileSync(join(outputDir, 'favicon.ico'), pngToIco(render(master, 32)));

console.log('Generated The Coupon PWA icons.');
