// Measure whether the fixed bottom nav overlaps the chat composer on a phone viewport.
//   node _tools/measure-nav.mjs [baseUrl]
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const browser = await chromium.launch();

for (const [w, h] of [[390, 844], [360, 740], [414, 896]]) {
  const context = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);

  const data = await page.evaluate(() => {
    const pick = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height), display: cs.display, position: cs.position };
    };
    return {
      viewport: { w: innerWidth, h: innerHeight },
      composer: pick(".ws-composer"),
      nav: pick(".ws-bookmarks"),
      conversation: pick(".ws-conversation"),
      flow: pick(".ws-chat-flow"),
    };
  });

  const overlap = data.composer && data.nav ? Math.max(0, data.composer.bottom - data.nav.top) : null;
  console.log(`\n=== ${w}x${h} ===`);
  console.log(JSON.stringify(data, null, 1));
  console.log(`composer.bottom=${data.composer?.bottom} nav.top=${data.nav?.top} -> 重叠 ${overlap}px`);
  await context.close();
}

await browser.close();
