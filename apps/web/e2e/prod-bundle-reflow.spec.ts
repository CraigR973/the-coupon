import { expect, test, type Page } from '@playwright/test';

// UX-15. Two reflow conditions the automated sweep never ran, both from WCAG:
//
//   * **320 CSS px** (SC 1.4.10 Reflow) — the narrowest width the guideline asks
//     content to survive. The pick screen's market labels were measured clipping
//     here: "No — not both score" wanting 106px in the 68px two-up leaves it.
//   * **The text-spacing override** (SC 1.4.12) — line-height 1.5, letter-spacing
//     0.12em, word-spacing 0.16em, paragraph spacing 2em, applied over everything.
//     Content has to survive it with nothing lost or cut off.
//
// axe runs neither: both are measurements of rendered geometry, not of markup, so
// 88 clean sweeps had nothing to say about them. This is the only place in the
// suite that measures either.
//
// Scope: the routes reachable without a session, which is what the prod-bundle
// harness serves. The pick screen's own labels are a class contract held in
// `src/test/PickCard.test.tsx`, because nothing here can sign in.

/** WCAG 2.2 SC 1.4.12, applied exactly as the success criterion states it. */
const TEXT_SPACING = `
  * {
    line-height: 1.5 !important;
    letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important;
  }
  p { margin-bottom: 2em !important; }
`;

const ROUTES = ['/login', '/register', '/forgot-pin', '/set-pin', '/join/INVITE', '/welcome'];

/**
 * Elements whose own content overflows the box drawn for it.
 *
 * Deliberately not "anything that scrolls": a scroll *container* is a design
 * decision and the strips on this app are built as one. What this looks for is
 * content cut off with no way to reach it — overflow hidden or clipped, and the
 * element is not scrollable by the member.
 */
async function clipped(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of Array.from(document.body.querySelectorAll<HTMLElement>('*'))) {
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      const hiddenX = style.overflowX === 'hidden' || style.overflowX === 'clip';
      const hiddenY = style.overflowY === 'hidden' || style.overflowY === 'clip';
      const cutX = hiddenX && el.scrollWidth > el.clientWidth + 1;
      const cutY = hiddenY && el.scrollHeight > el.clientHeight + 1;
      if (!cutX && !cutY) continue;
      const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 60);
      out.push(`<${el.tagName.toLowerCase()} class="${el.className}"> ${text}`);
    }
    return out;
  });
}

for (const route of ROUTES) {
  test(`${route} loses nothing at 320px`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(route);
    await expect(page.locator('main')).toBeVisible();
    expect(await clipped(page)).toEqual([]);
    // The page itself must not scroll sideways either — the layout holds today and
    // this is the check that says so when it stops.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test(`${route} loses nothing under the text-spacing override`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(route);
    await expect(page.locator('main')).toBeVisible();
    await page.addStyleTag({ content: TEXT_SPACING });
    expect(await clipped(page)).toEqual([]);
  });
}
