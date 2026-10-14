// Shell-only control inventory, for the before/after table in the hand-off.
//
// The generic probe (`probe-elements.mjs`) reports a 200px-tall "top" band, which on
// /chat also contains buttons that belong to the conversation cards. This script
// counts **only elements the shell owns**: `.ws-topbar`, the demo band, `.ws-bookmarks`
// and the desktop sidebar. Run it on the current tree, and on the base commit
// (`git stash` / `git checkout fa8edc9 -- <shell files>`) to get both columns.
//   node _tools/probe-shell.mjs
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const base = process.argv[2] || "http://127.0.0.1:5180";
const SEL = 'a[href], button, select, summary, [role="button"]';

const browser = await chromium.launch();
for (const width of [1280, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`${base}/#/profile?as=mid`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const r = await page.evaluate((sel) => {
    const grab = (root) => root
      ? [...root.querySelectorAll(sel)].map((e) => {
          const b = e.getBoundingClientRect();
          return { label: (e.getAttribute("aria-label") || e.textContent || "").trim().replace(/\s+/g, " ").slice(0, 22), w: Math.round(b.width), h: Math.round(b.height) };
        }).filter((x) => x.w > 0 && x.h > 0)
      : [];
    const parts = {
      "顶栏": grab(document.querySelector(".ws-topbar")),
      "演示带": grab(document.querySelector(".demo-data-label")),
      "桌面侧栏": grab(document.querySelector(".desk-sidebar")),
      "移动底栏": grab(document.querySelector(".ws-bookmarks")),
    };
    const shell = Object.values(parts).flat();
    return { parts, total: shell.length, small: shell.filter((x) => x.h < 44).length };
  }, SEL);
  console.log(`\n===== shell 控件 @${width} =====  合计 ${r.total} 个，<44px ${r.small} 个`);
  for (const [name, list] of Object.entries(r.parts)) {
    if (!list.length) continue;
    console.log(`  [${name}] ${list.length} 个，<44px ${list.filter((x) => x.h < 44).length}`);
    for (const e of list) console.log(`     ${String(e.w).padStart(4)}×${String(e.h).padStart(3)}  ${e.label}`);
  }
  await ctx.close();
}
await browser.close();
