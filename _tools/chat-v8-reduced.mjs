// prefers-reduced-motion 降级：不能只是"关掉动画白屏"，静态形态必须仍然可用。
//   node _tools/chat-v8-reduced.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";

const browser = await chromium.launch();
const report = {};
for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  const idle = await page.evaluate(() => {
    const an = (sel) => [...document.querySelectorAll(sel)].map((el) => getComputedStyle(el).animationName).filter((n) => n && n !== "none");
    return { runningAnimations: an(".dialogue-page *").slice(0, 8), turnCount: document.querySelectorAll(".chat-turn").length };
  });

  // 走一轮：思考 → 流式 → 停止，确认静态形态可读
  await page.click(".ws-chat-head__tools button");
  await page.waitForTimeout(200);
  await page.fill('textarea[aria-label="咨询内容"]', "我拿不准这个方向，该怎么选？请对比一下备选方向。");
  await page.locator('form button[type="submit"]').click();
  await page.waitForTimeout(200);
  const thinking = await page.evaluate(() => ({
    skeleton: !!document.querySelector(".chat-skeleton"),
    skeletonSweep: getComputedStyle(document.querySelector(".chat-skeleton > span"), "::after").animationName,
    stopButton: !!document.querySelector(".composer-stop"),
    stopMarkAnim: document.querySelector(".composer-stop__mark") ? getComputedStyle(document.querySelector(".composer-stop__mark")).animationName : null,
  }));
  await page.waitForTimeout(1500);
  const settled = await page.evaluate(() => ({
    lead: document.querySelector(".chat-block--lead")?.textContent.trim().slice(0, 20) ?? null,
    bars: document.querySelectorAll(".chat-bars__fill").length,
    barAnim: document.querySelector(".chat-bars__fill") ? getComputedStyle(document.querySelector(".chat-bars__fill")).animationName : null,
  }));
  report[width] = { idle, thinking, settled };
  console.log(`\n@${width} reduced-motion`);
  console.log("   静止时仍在跑的动画：", JSON.stringify(idle.runningAnimations));
  console.log("   思考态：骨架在=", thinking.skeleton, " 骨架条纹动画=", thinking.skeletonSweep, " 停止按钮=", thinking.stopButton, " 方块呼吸=", thinking.stopMarkAnim);
  console.log("   落定后：结论=", JSON.stringify(settled.lead), " 数据条=", settled.bars, " 条生长动画=", settled.barAnim);
  await page.screenshot({ path: `_shots/chat-v8/15-reduced-motion-${width}.png` });
  await ctx.close();
}
fs.writeFileSync("_shots/chat-v8/reduced-motion.json", JSON.stringify(report, null, 2));
await browser.close();
