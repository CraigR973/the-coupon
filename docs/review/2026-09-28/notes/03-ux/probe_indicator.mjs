import { chromium, newContext, settle, WEB } from './lib.mjs';
const b = await chromium.launch();
for (const path of ['/leagues/the-coupon/predictions', '/leagues/the-coupon/leaderboard', '/football', '/', '/settings']) {
  const ctx = await newContext(b, { width: 390, theme: 'dark', persona: 'Alice' });
  const p = await ctx.newPage(); await p.goto(WEB + path); await settle(p); await p.waitForTimeout(800);
  const r = await p.evaluate(() => { const nav = document.querySelector('nav[aria-label="Primary"]');
    const items = [...nav.querySelectorAll('a,button')].map(a => ({ t: a.textContent.trim(), x: Math.round(a.getBoundingClientRect().x), cur: a.getAttribute('aria-current') }));
    const ind = [...nav.querySelectorAll('*')].filter(e => !e.matches('a,button') && !e.closest('a,button') && e.getBoundingClientRect().height <= 4 && e.getBoundingClientRect().width > 10).map(e => { const r = e.getBoundingClientRect(); return { x: Math.round(r.x), w: Math.round(r.width), cls: String(e.className).slice(0, 60), style: e.getAttribute('style') }; });
    return { items: items.map(i => `${i.t}@${i.x}${i.cur ? '*' : ''}`).join(' '), ind }; });
  console.log(path, JSON.stringify(r));
  await ctx.close();
}
await b.close();
