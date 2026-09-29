// Screenshot each mockup at 390 and 1280 (dark) and 390 (light) in Chromium, beside the HTML.
import { chromium, NOTES } from './lib.mjs';
const names = (process.env.MOCKS || 'toasts,round,standings,settled').split(',');
const b = await chromium.launch();
for (const n of names) {
  for (const [w, h, theme] of [[390, 844, 'dark'], [390, 844, 'light'], [1280, 800, 'dark']]) {
    const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await p.goto(`file://${NOTES}/mockups/${n}.html${theme === 'light' ? '?light' : ''}`);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(300);
    const full = n === 'toasts';
    await p.screenshot({ path: `${NOTES}/mockups/${n}--${w}--${theme}.png`, fullPage: full });
    await p.close();
    console.log(`${n}--${w}--${theme}.png`);
  }
}
await b.close();
