// Page-level acceptance harness: screenshot real pages at desktop + mobile widths.
//   node _tools/shot.mjs <baseUrl> <outDir> [--routes a,b,c] [--widths 1280,390]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const PW = process.env.PW_PATH || "playwright";
const { chromium } = require(PW);

const [, , baseUrl = "http://127.0.0.1:5180", outDir = "_shots"] = process.argv;
const arg = (flag, fallback) => {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : fallback;
};
const routes = arg("--routes", "/").split(",").map((s) => s.trim()).filter(Boolean);
const widths = arg("--widths", "1280,390").split(",").map(Number);
const heightOverride = Number(arg("--height", 0));

fs.mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
for (const width of widths) {
  const context = await browser.newContext({
    viewport: { width, height: heightOverride || (width < 600 ? 844 : 900) },
    deviceScaleFactor: 2
  });
  const page = await context.newPage();
  for (const route of routes) {
    const name = `${route.replace(/[^\w]+/g, "_").replace(/^_+|_+$/g, "") || "root"}-${width}`;
    try {
      await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle", timeout: 30000 });
      await page.waitForTimeout(600);
      const file = path.join(outDir, `${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      const size = fs.statSync(file).size;
      console.log(`ok   ${route} @${width} -> ${file} (${size} B)`);
    } catch (e) {
      console.log(`FAIL ${route} @${width}: ${e.message.split("\n")[0]}`);
    }
  }
  await context.close();
}
await browser.close();
