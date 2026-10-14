// Scoped target-size audit for the conversation page's own chrome
// (ConversationView.vue + EvidenceList.vue) — excludes the app shell
// (topbar / sidebar / mobile bottom bar) which belongs to other files.
//   node _tools/chat-a11y-probe.mjs [baseUrl] [--label=before|after]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const labelArg = process.argv.find((a) => a.startsWith("--label="));
const label = labelArg ? labelArg.split("=")[1] : "run";

const WIDTHS = [1280, 390];
const SCOPES = [
  ["头部", ".dialogue-page .ws-chat-head"],
  ["输入区", ".dialogue-page .ws-composer"],
  ["消息流", ".dialogue-page .ws-chat-flow"],
];

const browser = await chromium.launch();
const report = { label, at: new Date().toISOString(), widths: {} };

for (const width of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${baseUrl}/#/chat`, { waitUntil: "networkidle" });
  // 对话记录会持久化在浏览器里：先清掉，才能每次都量到同一份初始状态
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  const data = await page.evaluate((scopes) => {
    const sel = 'a[href], button, input, textarea, select, summary, [role="button"], [role="tab"]';    const scan = (root) => {
      const out = [];
      for (const el of root.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        // 隐藏的文件选择器与 tabindex="-1" 的输入不在键盘序里，不算触控目标
        if (el.type === "file" || el.getAttribute("tabindex") === "-1") continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none") continue;
        const label = (el.getAttribute("aria-label") || el.textContent || el.value || el.type || "").trim().replace(/\s+/g, " ").slice(0, 30);
        out.push({ tag: el.tagName.toLowerCase(), label, w: Math.round(r.width), h: Math.round(r.height), small: r.height < 44 || r.width < 44 });
      }
      return out;
    };
    const page = document.querySelector(".dialogue-page");
    const result = { page: page ? scan(page) : [], byScope: {} };
    for (const [name, q] of scopes) {
      const root = document.querySelector(q);
      result.byScope[name] = root ? scan(root) : [];
    }
    // 输入区不被 fixed 底栏压住 + 聚焦提示是否真的出现
    const composer = document.querySelector(".ws-composer");
    const note = document.querySelector(".ws-composer__note");
    const nav = document.querySelector(".ws-bookmarks");
    result.layout = composer
      ? {
          composerBottom: Math.round(composer.getBoundingClientRect().bottom),
          navTop: nav ? Math.round(nav.getBoundingClientRect().top) : null,
          viewportH: innerHeight,
          noteHeight: note ? Math.round(note.getBoundingClientRect().height) : null,
          noteOpacity: note ? getComputedStyle(note).opacity : null,
        }
      : null;
    return result;
  }, SCOPES);

  const summarize = (list) => ({
    total: list.length,
    small: list.filter((x) => x.small).length,
    smallList: list.filter((x) => x.small).map((x) => `${x.label}(${x.w}×${x.h})`),
  });

  report.widths[width] = {
    page: summarize(data.page),
    scopes: Object.fromEntries(Object.entries(data.byScope).map(([k, v]) => [k, summarize(v)])),
    layout: data.layout,
    errors,
  };

  // 聚焦时提示行必须真的出现（这是"常驻提示改为聚焦时出现"的验收点）
  await page.evaluate(() => document.querySelector('textarea[aria-label="咨询内容"]')?.focus());
  await page.waitForTimeout(400);
  const focusedLayout = await page.evaluate(() => {
    const note = document.querySelector(".ws-composer__note");
    const composer = document.querySelector(".ws-composer");
    const nav = document.querySelector(".ws-bookmarks");
    return {
      noteHeight: note ? Math.round(note.getBoundingClientRect().height) : null,
      noteOpacity: note ? getComputedStyle(note).opacity : null,
      noteText: note ? note.textContent.trim() : null,
      composerBottom: composer ? Math.round(composer.getBoundingClientRect().bottom) : null,
      navTop: nav ? Math.round(nav.getBoundingClientRect().top) : null,
      viewportH: innerHeight,
    };
  });
  report.widths[width].focusedLayout = focusedLayout;
  await ctx.close();
}

fs.mkdirSync("_shots/chat-v8", { recursive: true });
fs.writeFileSync(`_shots/chat-v8/audit-${label}.json`, JSON.stringify(report, null, 2));

for (const [w, d] of Object.entries(report.widths)) {
  console.log(`\n===== 对话页自身 @${w}（不含壳层）  <44px: ${d.page.small} / ${d.page.total} =====`);
  for (const [name, s] of Object.entries(d.scopes)) console.log(`   ${name}: ${s.small} / ${s.total}`);
  if (d.page.smallList.length) console.log("   小目标：" + d.page.smallList.join(" | "));
  if (d.layout) console.log(`   布局：输入区底 ${d.layout.composerBottom} / 底栏顶 ${d.layout.navTop} / 视口 ${d.layout.viewportH}；提示行高 ${d.layout.noteHeight}（未聚焦 opacity ${d.layout.noteOpacity}）`);
  if (d.focusedLayout) console.log(`   聚焦后：提示行「${d.focusedLayout.noteText}」高 ${d.focusedLayout.noteHeight} / opacity ${d.focusedLayout.noteOpacity}；输入区底 ${d.focusedLayout.composerBottom} / 底栏顶 ${d.focusedLayout.navTop} / 视口 ${d.focusedLayout.viewportH}`);
  if (d.errors.length) console.log("   !! errors:", d.errors.slice(0, 3));
}
await browser.close();
