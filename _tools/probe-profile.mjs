// Temporary verification probe for the reworked /profile page.
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const PW = process.env.PW_PATH || "playwright";
const { chromium } = require(PW);

const BASE = "http://127.0.0.1:5180/#/profile";
const OUT = "_shots/profile-v6";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const report = { console: [], errors: [], motion: {}, links: {}, feedback: {}, capture: {} };

async function newPage(reducedMotion = "no-preference") {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1400 }, reducedMotion, deviceScaleFactor: 1 });
  await context.addInitScript(() => localStorage.setItem("zhiyin-demo-auth", "mid"));
  const page = await context.newPage();
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") report.console.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => report.errors.push(String(e.message)));
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(900);
  return { context, page };
}

/* ---- 1. 运动检测：切视角后行元素是否真的在 FLIP ---- */
{
  const { context, page } = await newPage();
  report.capture.rows = await page.locator(".p6-row").count();
  report.capture.concls = await page.locator(".p6-concl").count();
  report.capture.gaps = await page.locator(".p6-gap").count();
  report.capture.ringText = await page.locator(".p6-meter__value strong").innerText();
  report.capture.status = await page.locator('[data-testid="status-line"]').innerText();

  const orderBefore = await page.locator(".p6-row").evaluateAll((els) => els.map((e) => e.dataset.key));
  await page.evaluate(() => {
    window.__flip = [];
    const tick = () => {
      window.__flip.push([...document.querySelectorAll(".p6-row")].map((e) => `${e.dataset.key}:${getComputedStyle(e).transform}`));
      if (window.__flip.length < 40) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await page.locator('[data-testid="view-mode"]').nth(2).click();
  await page.waitForTimeout(900);
  const orderAfter = await page.locator(".p6-row").evaluateAll((els) => els.map((e) => e.dataset.key));
  const frames = await page.evaluate(() => window.__flip);
  report.motion = {
    orderChanged: orderBefore.join(",") !== orderAfter.join(","),
    orderBefore,
    orderAfter,
    // 真实位移过（非单位矩阵）= 这段重排动画真的跑了
    framesWithTransform: frames.filter((f) => f.some((r) => /matrix\(1, 0, 0, 1, [^)]*[1-9]/.test(r))).length,
    sample: frames.filter((f) => f.some((r) => /matrix\(1, 0, 0, 1, [^)]*[1-9]/.test(r))).slice(0, 3),
    waapi: await page.evaluate(() => document.getAnimations().length),
  };
  await context.close();
}

/* ---- 2. 关联反馈 + 更正连锁 + ?gap= 链接 ---- */
{
  const { context, page } = await newPage();
  // B → A
  await page.locator(".p6-concl").first().locator(".p6-dep").first().hover();
  await page.waitForTimeout(150);
  report.feedback.depHoverLitsRow = await page.locator(".p6-row.p6-row--lit").count();
  await page.mouse.move(0, 0);
  await page.waitForTimeout(150);
  // A → B
  await page.locator(".p6-support").first().click();
  await page.waitForTimeout(150);
  report.feedback.supportClickLitsConcl = await page.locator(".p6-concl.p6-concl--lit").count();
  await page.locator(".p6-support").first().click();
  await page.waitForTimeout(100);
  // C → B jump
  await page.locator(".p6-gap__affect .p6-dep").first().click();
  await page.waitForTimeout(400);
  report.feedback.gapJumpFlash = await page.locator(".p6-concl--flash").count();
  // 缺口里的补充链接
  report.links.gapHref = await page.locator('.p6-gap__actions a').first().getAttribute("href");
  // 更正连锁
  const row = page.locator(".p6-row").first();
  await row.locator("summary").first().click();
  await page.waitForTimeout(200);
  report.capture.evidenceOpened = await page.locator(".p6-row__evidence[open]").count();
  await row.getByText("更正信息").click();
  await page.waitForTimeout(300);
  await page.locator("dialog[open] textarea").fill("河北大学 材料科学与工程（更正示例）");
  await page.locator('dialog[open] button[type="submit"]').click();
  await page.waitForTimeout(1200);
  report.feedback.trustAfter = await page.locator(".p6-meter__value strong").innerText();
  report.feedback.staleConcls = await page.locator(".p6-concl--stale").count();
  report.feedback.recomputeBanner = await page.locator(".p6-recompute strong").innerText().catch(() => "");
  report.feedback.editedMark = await page.locator(".p6-row__edited").count();
  report.feedback.statusAfter = await page.locator('[data-testid="status-line"]').innerText();
  await context.close();
}

/* ---- 3. reduced-motion：环直接给终值 ---- */
{
  const { context, page } = await newPage("reduce");
  report.capture.ringReduced = await page.locator(".p6-meter__value strong").innerText();
  report.capture.ringReducedAt60ms = await page.evaluate(() => document.querySelector(".p6-meter__value strong")?.textContent);
  await context.close();
}

await browser.close();
console.log(JSON.stringify(report, null, 2));
