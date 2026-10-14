// 完整验收：service 路径（点"读取最新档案"）、空态、键盘焦点、折叠层数、长文本
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");

const browser = await chromium.launch();
const report = {};
const errs = [];

async function newPage(auth = "mid") {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1400 } });
  await ctx.addInitScript((a) => localStorage.setItem("zhiyin-demo-auth", a), auth);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errs.push(String(e.message)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto("http://127.0.0.1:5180/#/profile", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  return { ctx, page };
}

/* 1. service / 最新档案 读取后的 live 渲染 */
{
  const { ctx, page } = await newPage();
  await page.getByRole("button", { name: "读取最新档案" }).click();
  await page.waitForTimeout(1200);
  report.live = await page.evaluate(() => ({
    rows: document.querySelectorAll(".p6-row").length,
    gaps: document.querySelectorAll(".p6-gap").length,
    sources: [...new Set([...document.querySelectorAll(".p6-source")].map((e) => e.textContent.trim()))],
    hasAsk: document.querySelectorAll(".p6-gap__ask").length,
    trust: document.querySelector(".p6-meter__value strong")?.textContent,
    demoNote: document.querySelector(".ws-demo-note")?.textContent?.slice(0, 60),
    evidenceLists: document.querySelectorAll(".p6-row__evidence ul li").length,
    error: document.querySelector('[role="alert"]')?.textContent ?? "",
  }));
  await ctx.close();
}

/* 2. 空态（fresh 账号） */
{
  const { ctx, page } = await newPage("fresh");
  report.empty = await page.evaluate(() => ({
    empty: document.querySelector(".exp-empty h2")?.textContent,
    rows: document.querySelectorAll(".p6-row").length,
    gaps: document.querySelectorAll(".p6-gap").length,
    trust: document.querySelector(".p6-meter__value strong")?.textContent,
    status: document.querySelector('[data-testid="status-line"]')?.textContent,
  }));
  await ctx.close();
}

/* 3. 键盘：Tab 到依赖 chip 会聚焦并联动另一侧；一层折叠 */
{
  const { ctx, page } = await newPage();
  const chip = page.locator(".p6-concl").first().locator(".p6-dep").first();
  await chip.focus();
  await page.waitForTimeout(200);
  report.keyboard = {
    focused: await chip.evaluate((e) => document.activeElement === e),
    litRows: await page.locator(".p6-row.p6-row--lit").count(),
  };
  // 页面里所有 details 是否只有一层（内部不再嵌套 details）
  report.folds = await page.evaluate(() => ({
    details: document.querySelectorAll("details").length,
    nested: document.querySelectorAll("details details").length,
  }));
  await ctx.close();
}

/* 4. 更正校验：空值与超 40 字 */
{
  const { ctx, page } = await newPage();
  const row = page.locator(".p6-row").first();
  await row.locator("summary").first().click();
  await page.waitForTimeout(150);
  await row.getByText("更正信息").click();
  await page.waitForTimeout(250);
  await page.locator("dialog[open] textarea").fill("");
  await page.locator('dialog[open] button[type="submit"]').click();
  await page.waitForTimeout(200);
  report.validation = { empty: await page.locator("dialog[open] .ws-field-error").innerText().catch(() => "") };
  report.validation.maxlengthAttr = await page.locator("dialog[open] textarea").getAttribute("maxlength");
  await page.locator("dialog[open] textarea").fill("字".repeat(41)).catch(() => {});
  await page.locator('dialog[open] button[type="submit"]').click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(300);
  report.validation.tooLong = await page.locator("dialog[open] .ws-field-error").innerText().catch(() => "(dialog closed / no error)");
  report.validation.dialogStillOpen = await page.locator("dialog[open]").count();
  await ctx.close();
}

report.errors = errs;
await browser.close();
console.log(JSON.stringify(report, null, 2));
