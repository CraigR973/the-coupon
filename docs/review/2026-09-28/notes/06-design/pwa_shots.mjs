import { chromium, NOTES } from './lib.mjs';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1180, height: 1180 }, deviceScaleFactor: 1 });
await p.goto(`file://${NOTES}/pwa/icon-masks.html`);
await p.waitForTimeout(500);
await p.screenshot({ path: `${NOTES}/pwa/icon-masks.png`, fullPage: true });
await b.close();
