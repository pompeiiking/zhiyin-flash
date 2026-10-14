// Capture the living states of the chat page by actually driving it:
// resting -> thinking -> streaming -> settled.
//   node _tools/chat-probe.mjs [baseUrl] [outDir]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const outDir = process.argv[3] || "_shots/chat-live";
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1500 }, deviceScaleFactor: 2 });
const page = await context.newPage();

const shot = async (label) => {
  const file = `${outDir}/${label}.png`;
  await page.screenshot({ path: file });
  console.log(`shot ${label} -> ${file} (${fs.statSync(file).size} B)`);
};

await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
await shot("1-resting");

// Drive one real turn.
const box = page.locator('textarea[aria-label="咨询内容"]');
await box.click();
await box.fill("我拿不准这个方向，该怎么选？");
await page.waitForTimeout(150);
await page.locator('form button[type="submit"]').click();

// The demo waits ~520ms before replying; grab the thinking state in that window.
await page.waitForTimeout(260);
await shot("2-thinking");

await page.waitForTimeout(900);
await shot("3-streaming");

// Wait for the stream to finish (send button returns to 发送 and stops being disabled by busy state).
await page.waitForTimeout(4500);
await shot("4-settled");

// Ask for a handoff-producing reply (different speaker) to capture the handoff card.
await box.fill("下一步我该做什么？");
await page.locator('form button[type="submit"]').click();
await page.waitForTimeout(5200);
await shot("5-after-second-turn");

await browser.close();
