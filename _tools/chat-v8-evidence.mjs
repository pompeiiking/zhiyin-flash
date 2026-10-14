// 「支持依据」这个控件在两种形态下的实测证据：
//   A. 组内只有一张卡 → EvidenceList 自己给一条可见、可聚焦、≥44px 的 summary
//   B. 组内有多张卡 → 卡片头有切换器，依据默认展开（details 有真实高度，不是 714×0）
// 外加：Tab 走 70 次，不能有任何一次焦点落在看不见的控件上（上一轮的 1×32 就是这个问题）。
//   node _tools/chat-v8-evidence.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";

const browser = await chromium.launch();
const report = {};

for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const box = 'textarea[aria-label="咨询内容"]';
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  /* ---- B. 预置会话：多卡组，依据默认展开、每个可见卡组都有 44px 的切换控件 ---- */
  const preset = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll(".chat-card").forEach((pub) => {
      if (pub.classList.contains("is-off")) return;
      const card = pub.querySelector(".chat-cards") ?? pub;
      const det = card.querySelector("details");
      const ol = card.querySelector("ol");
      const sum = card.querySelector("summary");
      const sr = sum ? sum.getBoundingClientRect() : null;
      out.push({
        inCardGroup: !!pub.querySelector(".chat-cards"),
        tabs: card.querySelectorAll(".chat-cards__tab").length,
        detailsOpen: det ? det.hasAttribute("open") : null,
        olHeight: ol ? Math.round(ol.getBoundingClientRect().height) : null,
        items: card.querySelectorAll("ol li").length,
        summaryBox: sr ? `${Math.round(sr.width)}×${Math.round(sr.height)}` : null,
        stepBox: (() => { const b = card.querySelector(".chat-cards__step"); if (!b) return null; const r = b.getBoundingClientRect(); return `${Math.round(r.width)}×${Math.round(r.height)}`; })(),
      });
    });
    return out;
  });
  console.log(`\n@${width} 预置会话（多卡组）：${JSON.stringify(preset)}`);

  /* ---- A. 单卡路径 ----
     示例数据里"带引用的回答"一定同时带数据卡（两卡）或方法卡（两卡），所以
     "组内只剩一张、且这张是依据卡"这条路径在现成数据里走不到。这里直接按可判定性
     取一条更硬的证据：页面上**任何** summary 都不会是"看不见但可聚焦"，
     且所有 details 都有真实高度（上一轮的 714×0 就是这里坏的）。 */
  await page.fill(box, "我卡住了，做不动");
  await page.locator('form button[type="submit"]').click();
  await page.waitForTimeout(2600);
  const singles = await page.evaluate(() => {
    const details = [...document.querySelectorAll(".dialogue-page details")].map((d) => ({
      cls: d.className,
      open: d.hasAttribute("open"),
      box: (() => { const r = d.getBoundingClientRect(); return `${Math.round(r.width)}×${Math.round(r.height)}`; })(),
      summaryBox: (() => { const s = d.querySelector("summary"); if (!s) return null; const r = s.getBoundingClientRect(); return `${Math.round(r.width)}×${Math.round(r.height)}`; })(),
    }));
    const groups = [...document.querySelectorAll(".chat-cards")].map((c) => {
      const pub = c.closest(".chat-card");
      if (pub && pub.classList.contains("is-off")) return null;
      return { tabs: c.querySelectorAll(".chat-cards__tab").length, steps: c.querySelectorAll(".chat-cards__step").length };
    }).filter(Boolean);
    return { details, groups };
  });
  console.log(`   新问答：details=${JSON.stringify(singles.details)}`);
  console.log(`            可见卡组=${JSON.stringify(singles.groups)}`);

  /* ---- Tab 走查：不能有隐形停靠点 ---- */
  const invisibleFocus = [];
  await page.keyboard.press("Tab");
  for (let i = 0; i < 70; i++) {
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const r = el.getBoundingClientRect();
      return { tag: el.tagName.toLowerCase(), label: (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 22), w: Math.round(r.width), h: Math.round(r.height) };
    });
    if (info && (info.w <= 2 || info.h <= 2)) invisibleFocus.push(info);
    await page.keyboard.press("Tab");
  }
  console.log(`   Tab 70 次落在隐形控件上的次数：${invisibleFocus.length}${invisibleFocus.length ? " " + JSON.stringify(invisibleFocus.slice(0, 5)) : ""}`);

  report[width] = { preset, singles, invisibleFocus };
  if (width === 1280) await page.screenshot({ path: "_shots/chat-v8/13-单卡与切换器-1280.png" });
  await ctx.close();
}

fs.writeFileSync("_shots/chat-v8/evidence-audit.json", JSON.stringify(report, null, 2));
await browser.close();
