// 确定性验证「流式生成中 → 停止生成」这一段：
// useStreaming 的逐字播放靠 requestAnimationFrame，时长只有 320–900ms，
// 普通截图经常在"没有正在生成的回答"时按快门，于是拍不到停止按钮。
// 这里在页面加载前把 rAF 的时间轴放慢 25 倍，让"正在生成"成为稳定状态。
//   node _tools/chat-v8-stream.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const outDir = "_shots/chat-v8";
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const report = {};

for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2 });
  await ctx.addInitScript(() => {
    const raw = window.requestAnimationFrame.bind(window);
    let t = 0;
    window.requestAnimationFrame = (cb) => raw((now) => cb(t + (now - t) / 25));
  });
  const page = await ctx.newPage();
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(700);
  await page.click(".ws-chat-head__tools button");
  await page.waitForTimeout(200);
  await page.fill('textarea[aria-label="咨询内容"]', "我拿不准这个方向，该怎么选？请对比一下备选方向。");
  await page.locator('form button[type="submit"]').click();
  await page.waitForSelector(".composer-stop", { timeout: 10000 });
  await page.waitForTimeout(800);

  const state = await page.evaluate(() => {
    const stop = document.querySelector(".composer-stop");
    const r = stop.getBoundingClientRect();
    const text = document.querySelector(".chat-answer .chat-block--lead");
    return {
      stopLabel: stop.textContent.trim(),
      stopW: Math.round(r.width),
      stopH: Math.round(r.height),
      caretVisible: !!document.querySelector(".chat-caret"),
      leadSoFar: text ? text.textContent.trim().slice(0, 24) : null,
      sendGone: !document.querySelector(".composer-send"),
    };
  });
  const file1 = `${outDir}/4-流式中-停止生成-${width}.png`;
  await page.screenshot({ path: file1 });

  // 点停止：逐字必须停住，已生成的部分留在原地，块立刻落位
  const before = await page.evaluate(() => document.querySelector(".chat-block--lead")?.textContent.trim() ?? "");
  await page.locator(".composer-stop").click();
  await page.waitForTimeout(600);
  const after = await page.evaluate(() => ({
    lead: document.querySelector(".chat-block--lead")?.textContent.trim() ?? "",
    caret: !!document.querySelector(".chat-caret"),
    stopGone: !document.querySelector(".composer-stop"),
    sendBack: !!document.querySelector(".composer-send"),
    support: !!document.querySelector(".chat-block--support"),
  }));
  const file2 = `${outDir}/5-已停止生成-${width}.png`;
  await page.screenshot({ path: file2 });

  report[width] = { ...state, after };
  console.log(`\n@${width} 停止按钮：${state.stopLabel} ${state.stopW}×${state.stopH}，发送按钮已让位=${state.sendGone}`);
  console.log(`   点停止后：光标消失=${!after.caret} 停止按钮让位=${after.stopGone} 发送回来=${after.sendBack} 支撑块落位=${after.support}`);
  console.log(`   已生成的内容整段保留："${after.lead}"`);
  await ctx.close();
}

fs.writeFileSync(`${outDir}/stream-audit.json`, JSON.stringify(report, null, 2));
await browser.close();
