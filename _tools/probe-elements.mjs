// Element-level inventory of the two reworked pages: every visible interactive
// element with its region, size, and state — so "did you check the header and the
// composer?" can be answered with numbers instead of impressions.
//   node _tools/probe-elements.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";

const PAGES = [
  ["chat", "/#/chat"],
  ["profile", "/#/profile"],
];
const WIDTHS = [1280, 390];

const browser = await chromium.launch();
const report = {};

for (const [name, route] of PAGES) {
  report[name] = {};
  for (const width of WIDTHS) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    report[name][width] = await page.evaluate(() => {
      const sel = 'a[href], button, input, textarea, select, summary, [role="button"], [role="tab"]';
      const regionOf = (r) => {
        const h = innerHeight;
        if (r.bottom < 200) return "① 顶端";
        if (r.top > h - 220) return "③ 底端";
        return "② 主体";
      };
      const out = [];
      for (const el of document.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;          // hidden
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.display === "none") continue;
        const label = (el.getAttribute("aria-label") || el.textContent || el.value || el.placeholder || el.type || "").trim().replace(/\s+/g, " ").slice(0, 34);
        out.push({
          tag: el.tagName.toLowerCase(),
          label,
          region: regionOf(r),
          w: Math.round(r.width),
          h: Math.round(r.height),
          fs: cs.fontSize,
          disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
          small: r.height < 44,
        });
      }
      const count = (f) => out.filter(f).length;
      return {
        total: out.length,
        byRegion: { 顶端: count((x) => x.region === "① 顶端"), 主体: count((x) => x.region === "② 主体"), 底端: count((x) => x.region === "③ 底端") },
        smallTargets: count((x) => x.small),
        smallList: out.filter((x) => x.small).map((x) => `${x.label}(${x.w}×${x.h})`).slice(0, 12),
        header: out.filter((x) => x.region === "① 顶端"),
        footer: out.filter((x) => x.region === "③ 底端"),
        docHeight: document.documentElement.scrollHeight,
      };
    });
    report[name][width].errors = errors;
    await ctx.close();
  }
}

fs.mkdirSync("_shots/elements", { recursive: true });
fs.writeFileSync("_shots/elements/inventory.json", JSON.stringify(report, null, 2));

for (const [name] of PAGES) {
  for (const w of WIDTHS) {
    const d = report[name][w];
    console.log(`\n===== ${name} @${w} =====  可点元素 ${d.total}（顶端 ${d.byRegion.顶端} / 主体 ${d.byRegion.主体} / 底端 ${d.byRegion.底端}）  <44px: ${d.smallTargets}  页高 ${d.docHeight}`);
    if (d.errors.length) console.log("  !! console/page errors:", d.errors.slice(0, 3));
    console.log("  --- 顶端 ---");
    for (const e of d.header) console.log(`   ${e.disabled ? "·禁用" : "     "} ${e.tag.padEnd(8)} ${String(e.w).padStart(4)}×${String(e.h).padStart(3)}  ${e.fs.padStart(5)}  ${e.label}`);
    console.log("  --- 底端 ---");
    for (const e of d.footer) console.log(`   ${e.disabled ? "·禁用" : "     "} ${e.tag.padEnd(8)} ${String(e.w).padStart(4)}×${String(e.h).padStart(3)}  ${e.fs.padStart(5)}  ${e.label}`);
    if (d.smallList.length) console.log("  --- 小于 44px 的 ---\n   ", d.smallList.join("  |  "));
  }
}
await browser.close();
