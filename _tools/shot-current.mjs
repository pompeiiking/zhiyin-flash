// 截当前真实页面（wave1/wave2 之后），给需求方判断"气质"用。
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const out = "_shots/current-pages";
fs.mkdirSync(out, { recursive: true });

const routes = [
  ["chat", "/#/chat"],
  ["report", "/#/report"],
  ["profile", "/#/profile"],
  ["plan", "/#/plan"],
  ["portal", "/#/"],
  ["intel", "/#/intel"],
];

const browser = await chromium.launch();
for (const [name, route] of routes) {
  for (const [w, h] of [[1280, 900], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto(`http://127.0.0.1:5180${route}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${out}/${name}-${w}.png` });
    await ctx.close();
    console.log(`ok ${name}@${w}`);
  }
}
await browser.close();
