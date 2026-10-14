// Verify the FLIP reorganisation animation actually runs (samples every frame).
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1200 } });
await context.addInitScript(() => localStorage.setItem("zhiyin-demo-auth", "mid"));
const page = await context.newPage();
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE-ERR", m.text()); });
await page.goto("http://127.0.0.1:5180/#/profile", { waitUntil: "networkidle" });
await page.waitForTimeout(900);

// 用 rAF 在页面内采样，避开 CDP 往返延迟
await page.evaluate(() => {
  window.__samples = [];
  const tick = () => {
    window.__samples.push({
      t: Math.round(performance.now()),
      rows: [...document.querySelectorAll(".p6-row")].map((e) => {
        const s = getComputedStyle(e);
        return { k: e.dataset.key, tr: s.transform, y: Math.round(e.getBoundingClientRect().top) };
      }),
      anims: document.getAnimations().length,
    });
    if (window.__samples.length < 40) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
await page.locator('[data-testid="view-mode"]').nth(2).click();
await page.waitForTimeout(900);
const out = await page.evaluate(() => {
  const s = window.__samples;
  const withMatrix = s.filter((f) => f.rows.some((r) => r.tr !== "none" && !/matrix\(1, 0, 0, 1, 0, 0\)/.test(r.tr)));
  const moving = s.filter((f) => f.rows.some((r) => /matrix\(1, 0, 0, 1, [^)]*[1-9]/.test(r.tr)));
  return {
    frames: s.length,
    framesWithTransform: withMatrix.length,
    maxAnims: Math.max(...s.map((f) => f.anims)),
    sampleFrames: withMatrix.slice(0, 5).map((f) => ({
      t: f.t,
      anims: f.anims,
      moves: f.rows.filter((r) => r.tr !== "none").slice(0, 4).map((r) => `${r.k} ${r.tr} y=${r.y}`),
    })),
    orderAfter: [...document.querySelectorAll(".p6-row")].map((e) => e.dataset.key),
  };
});
console.log(JSON.stringify(out, null, 2));

// reduced motion：不应有位移，但结构照样重组
const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 1200 }, reducedMotion: "reduce" });
await ctx2.addInitScript(() => localStorage.setItem("zhiyin-demo-auth", "mid"));
const p2 = await ctx2.newPage();
await p2.goto("http://127.0.0.1:5180/#/profile", { waitUntil: "networkidle" });
await p2.waitForTimeout(700);
await p2.evaluate(() => {
  window.__r = [];
  const t0 = performance.now();
  const tick = () => {
    window.__r.push({ t: Math.round(performance.now() - t0), rows: [...document.querySelectorAll(".p6-row")].map((e) => e.style.transform || "none") });
    if (performance.now() - t0 < 700) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
await p2.locator('[data-testid="view-mode"]').nth(2).click();
await p2.waitForTimeout(900);
console.log("reduced-motion:", JSON.stringify(await p2.evaluate(() => ({
  matches: matchMedia("(prefers-reduced-motion: reduce)").matches,
  groups: [...document.querySelectorAll(".p6-group")].map((g) => g.querySelector("h3").textContent + ":" + g.querySelectorAll(".p6-row").length),
  framesWithTransform: window.__r.filter((f) => f.rows.some((r) => r !== "none")).length,
  frames: window.__r.length,
}))));
await browser.close();
