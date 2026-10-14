// Capture the conversation page's living states after the v8 header/composer rework.
// Also reports, per state, how many interactive elements are under 44px inside the page
// itself (the app shell — topbar / sidebar / bottom bar — is excluded).
//   node _tools/chat-v8-shots.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const outDir = "_shots/chat-v8";
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const report = {};
const box = 'textarea[aria-label="咨询内容"]';

async function open(width) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  return { ctx, page, errors };
}

function makeShot(page, tag) {
  return async (name) => {
    const file = `${outDir}/${name}-${tag}.png`;
    await page.screenshot({ path: file });
    const audit = await page.evaluate(() => {
      const sel = 'a[href], button, input, textarea, select, summary, [role="button"], [role="tab"]';
      const root = document.querySelector(".dialogue-page");
      if (!root) return { total: 0, small: 0, list: [] };
      const out = [];
      for (const el of root.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (el.type === "file" || el.getAttribute("tabindex") === "-1") continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none") continue;
        const label = (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 26);
        out.push({ label, w: Math.round(r.width), h: Math.round(r.height), small: r.height < 44 || r.width < 44 });
      }
      const small = out.filter((x) => x.small);
      return { total: out.length, small: small.length, list: small.map((x) => `${x.label}(${x.w}×${x.h})`) };
    });
    report[`${name}-${tag}`] = { bytes: fs.statSync(file).size, ...audit };
    console.log(`shot ${name}-${tag}  <44px: ${audit.small}/${audit.total}${audit.list.length ? "  " + audit.list.join(" | ") : ""}`);
  };
}

/* ---------- 卡片切换：预置会话里 c6 那条回答有三条依据 + 数据对比 = 两张支撑卡 ---------- */
for (const width of [1280, 390]) {
  const { ctx, page, errors } = await open(width);
  const shot = makeShot(page, String(width));
  const next = page.locator('button[aria-label="下一张卡片"]').last();
  if (await next.count()) {
    await next.scrollIntoViewIfNeeded();
    await shot(`${width === 1280 ? "8" : "6"}-卡片切换前`);
    await next.click();
    await page.waitForTimeout(400);
    await shot(`${width === 1280 ? "9" : "7"}-卡片切换`);
  } else {
    console.log(`  !! @${width} 没有找到卡片切换器`);
  }
  report[`errors-card-${width}`] = errors;
  await ctx.close();
}

/* ---------- 主流程：开新会话 → 空态 / 聚焦 / 思考 / 流式 / 停止 / 完整 / 附件 ---------- */
for (const width of [1280, 390]) {
  const tag = String(width);
  const { ctx, page, errors } = await open(width);
  const shot = makeShot(page, tag);
  // 先开一个新会话拿到真正的空态（顺带验证「新对话」还有效）
  await page.click(".ws-chat-head__tools button");
  await page.waitForTimeout(300);
  await shot("1-空态");
  await page.click(box);
  await page.waitForTimeout(400);
  await shot("2-聚焦输入区");

  // 选一条长回答：逐字播放按字数算，长回答才留得住"流式中"那一帧
  await page.fill(box, "我拿不准这个方向，该怎么选？请对比一下备选方向。");
  await page.locator('form button[type="submit"]').click();
  await page.waitForTimeout(300);
  await shot("3-思考态");
  await page.waitForSelector(".composer-stop", { timeout: 8000 });
  await shot("4-流式中-停止生成");
  // 停一次，看"停在当下"是否成立（用 dispatch 而不是 click：DOM 可能刚好被替换）
  await page.evaluate(() => document.querySelector(".composer-stop")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  await page.waitForTimeout(400);
  await shot("5-已停止生成");
  await page.waitForTimeout(1800);
  await shot("6-完整回答");

  // 附件态
  await page.setInputFiles('input[type="file"]', { name: width === 1280 ? "材料实验报告.pdf" : "简历草稿.docx", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 demo") });
  await page.waitForTimeout(250);
  await shot("7-附件态");

  // 依据展开（只点依据卡里那个按钮：方法卡里同名按钮会开 InfoSheet）
  const more = page.locator(".chat-evidence .chat-block__more").first();
  if (await more.count()) {
    await more.scrollIntoViewIfNeeded();
    await more.click();
    await page.waitForTimeout(400);
  }
  await shot("8-依据展开");

  // 回到最新：程序性滚动不会触发 scroll 事件，手动派发一次
  await page.evaluate(() => {
    const f = document.querySelector(".ws-chat-flow");
    if (!f) return;
    f.scrollTop = 0;
    f.dispatchEvent(new Event("scroll"));
  });
  await page.waitForTimeout(500);
  await shot("10-回到最新");

  if (errors.length) console.log(`  !! ${tag} errors:`, errors.slice(0, 3));
  report[`errors-live-${tag}`] = errors;
  await ctx.close();
}

/* ---------- 错误态：只由 ?demo-error=1 触发，界面上没有按钮 ---------- */
for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(`${baseUrl}/#/chat?demo-error=1`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.click(".ws-chat-head__tools button");
  await page.waitForTimeout(300);
  await page.fill(box, "我想问一个会失败的问题");
  await page.locator('form button[type="submit"]').click();
  await page.waitForTimeout(1200);
  const file = `${outDir}/11-错误态-${width}.png`;
  await page.screenshot({ path: file });
  console.log(`shot 11-错误态-${width} (trigger: ?demo-error=1)  ${fs.statSync(file).size} B`);
  await ctx.close();
}

fs.writeFileSync(`${outDir}/audit.json`, JSON.stringify(report, null, 2));
console.log(`\n${outDir}/audit.json`);
await browser.close();
