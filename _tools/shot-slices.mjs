import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH);
const out = "_shots/profile-v6";
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const [width, tag] of [[1280, "1280"], [390, "390"]]) {
  const ctx = await browser.newContext({ viewport: { width, height: 1400 }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => localStorage.setItem("zhiyin-demo-auth", "mid"));
  const page = await ctx.newPage();
  await page.goto("http://127.0.0.1:5180/#/profile", { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  const total = await page.evaluate(() => document.documentElement.scrollHeight);
  const slices = Math.ceil(total / 1400);
  for (let i = 0; i < slices; i++) {
    await page.evaluate((y) => window.scrollTo(0, y), i * 1400);
    await page.waitForTimeout(250);
    await page.screenshot({ path: `${out}/part-${tag}-${i + 1}.png` });
  }
  console.log(tag, total, slices);
  await ctx.close();
}
await browser.close();
