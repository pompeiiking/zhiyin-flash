// Screenshot the enriched demo answer: scroll to the answer that carries the
// 4-evidence deck, capture it collapsed, then click "展开其余 N 条依据" and capture again.
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const out = "_shots/chat-v10";
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
for (const [w, h, tag] of [[1280, 1000, "1280"], [390, 844, "390"]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto("http://127.0.0.1:5180/#/chat", { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  const more = page.locator(".chat-block__more", { hasText: "展开其余" }).first();
  await more.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/${tag}-1-依据折叠.png` });

  await more.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}/${tag}-2-依据展开.png` });

  // 卡片组：切到第二张
  const next = page.locator('button[aria-label*="下一张"], .chat-cards__step').first();
  if (await next.count()) {
    await next.click().catch(() => {});
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${out}/${tag}-3-卡片第二张.png` });
  }
  console.log(`${tag} done`);
  await ctx.close();
}
await browser.close();
