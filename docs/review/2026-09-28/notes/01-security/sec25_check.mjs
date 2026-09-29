// SEC-25 re-drive: no league key survives logout or an identity switch.
//   . ~/.nvm/nvm.sh && nvm use 24 --silent && node sec25_check.mjs > sec25-check.txt
import { chromium } from '/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs';

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } });
const p = await ctx.newPage();
const dump = async (label) => {
  const s = await p.evaluate(() => Object.fromEntries(Object.keys(localStorage).map((k) => [k, (localStorage.getItem(k) || '').slice(0, 60)])));
  console.log(label, JSON.stringify(s));
};
async function signIn(name, pin) {
  await p.goto('http://127.0.0.1:4310/login', { waitUntil: 'networkidle' });
  await p.locator('input').first().fill(name);
  const boxes = p.locator('input[inputmode="numeric"], input[type="password"]');
  for (let i = 0; i < 4; i++) await boxes.nth(i).fill(pin[i]);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(2500);
}
await signIn('Erin', '1234');
await p.goto('http://127.0.0.1:4310/leagues/league-b/leaderboard', { waitUntil: 'networkidle' });
await p.waitForTimeout(1500);
await dump('after Erin views league-b:');
// The desktop top bar's account menu (TopBar.tsx), as a member would use it.
await p.getByRole('button', { name: /Account menu/ }).filter({ visible: true }).first().click();
await p.getByRole('menuitem', { name: 'Log out' }).click();
await p.waitForTimeout(1500);
console.log('url after logout:', p.url());
await dump('after logout:');
await signIn('Sadie', '1234');
await dump('after Sadie signs in on the same browser:');
console.log('home url for Sadie:', p.url());
const body = await p.locator('body').innerText();
console.log('"League B" visible to Sadie:', body.includes('League B'));
await b.close();
