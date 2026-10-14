// 改造后逐条复核「硬性纪律」里的功能是否还在：查询参数入口、草稿保存、键盘行为、
// 面板、回到最新、交接卡、复制、错误重试。都是"改完还要能用"的既有能力。
//   node _tools/chat-v8-features.mjs [baseUrl]
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const baseUrl = process.argv[2] || "http://127.0.0.1:5180";
const out = {};
const ok = (name, value) => { out[name] = value; console.log(`${value === true ? "✓" : typeof value === "string" ? "✓" : "✗"} ${name}${typeof value === "string" ? " = " + value : ""}`); };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const box = 'textarea[aria-label="咨询内容"]';
const fresh = async (url) => {
  await page.goto(`${baseUrl}${url}`, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(900);
};

/* 查询参数入口 */
await fresh("/#/chat?question=%E6%88%91%E8%AF%A5%E6%80%8E%E4%B9%88%E9%80%89&topic=%E6%96%B9%E5%90%91&gap=grade&collected=3");
ok("?question= 写进草稿", await page.inputValue(box));
await fresh("/#/chat?topic=%E6%96%B9%E5%90%91");
ok("?topic= 写进草稿", await page.inputValue(box));
await fresh("/#/chat?gap=grade&label=%E5%B9%B4%E7%BA%A7");
ok("?gap= 写进草稿", await page.inputValue(box));
await fresh("/#/chat?collected=3");
ok("?collected= 不报错（已计入收集数）", await page.locator("textarea").count() === 1);
await fresh("/#/chat?demo-error=1");
await page.click(".ws-chat-head__tools button");
await page.fill(box, "触发错误态");
await page.locator('form button[type="submit"]').click();
await page.waitForTimeout(1200);
ok("?demo-error=1 触发错误态", await page.locator(".chat-error").first().isVisible());
ok("错误态可重试", await page.locator(".chat-error button", { hasText: "重试这一条" }).count() > 0);

/* 错误态触发口子已从界面移走 */
await fresh("/#/chat");
const headerButtons = await page.locator(".ws-chat-head__tools button").allTextContents();
ok("头部只有两个会话操作", JSON.stringify(headerButtons));
const pageText = await page.locator(".dialogue-page").innerText();
ok("对话页上找不到「错误态演示」", !pageText.includes("错误态演示"));
ok("对话页上找不到「数据设置」", !pageText.includes("数据设置"));
ok("演示数据区分仍在（标题旁标识）", await page.locator(".ws-chat-head__demo").count() === 1);
ok("产出与依据入口在页面内（rail）", await page.locator(".dialogue-rail__item").count() === 2);

/* 键盘：Enter 发送 / Shift+Enter 换行 / 合成态不发送 */
await page.click(box);
await page.keyboard.type("第一行");
await page.keyboard.down("Shift");
await page.keyboard.press("Enter");
await page.keyboard.up("Shift");
await page.keyboard.type("第二行");
ok("Shift+Enter 换行", JSON.stringify(await page.inputValue(box)));
const before = await page.locator(".chat-turn").count();
// 合成态：真实输入法给 keydown 事件带 isComposing=true，Playwright 的合成按键没有这个标志位
await page.dispatchEvent(box, "compositionstart");
await page.dispatchEvent(box, "keydown", { key: "Enter", code: "Enter", keyCode: 13, isComposing: true, bubbles: true });
await page.waitForTimeout(250);
ok("中文合成态 Enter 不发送", (await page.locator(".chat-turn").count()) === before);
await page.dispatchEvent(box, "compositionend");
await page.click(box);
await page.keyboard.press("Enter");
await page.waitForTimeout(600);
ok("Enter 发送", (await page.locator(".chat-turn").count()) > before);

/* 草稿保存：切会话再切回来 */
await page.fill(box, "这是一段草稿");
await page.click(".ws-chat-head__tools button"); // 新对话
await page.waitForTimeout(400);
ok("新对话后草稿清空", (await page.inputValue(box)) === "");
await page.click(".ws-chat-head__tools button:nth-child(2)"); // 历史会话
await page.waitForTimeout(400);
ok("历史会话面板打开", await page.locator(".ws-sheet--inspector").isVisible());
const sessions = await page.locator(".desk-session").count();
ok("历史会话有内容", sessions > 0);
if (sessions > 1) {
  // 列表项自己带 title（会话名），用 title 选，避免 nth 选到当前会话
  const titles = await page.locator(".desk-session").evaluateAll((els) => els.map((e) => e.getAttribute("title")));
  ok("历史会话列表", JSON.stringify(titles));
  const target = titles.find((t) => t && t !== "新的咨询对话") ?? titles[1];
  await page.evaluate((name) => {
    const el = [...document.querySelectorAll(".desk-session")].find((e) => e.getAttribute("title") === name);
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }, target);
  await page.waitForTimeout(700);
  ok(`切换会话后草稿恢复（切到「${target}」）`, (await page.inputValue(box)).length > 0);
}
await page.keyboard.press("Escape");
await page.waitForTimeout(300);

/* 询咨成果面板 + 方法卡面板 */
await page.locator(".dialogue-rail__item").first().click();
await page.waitForTimeout(400);
ok("咨询成果面板打开", await page.locator(".ws-sheet--inspector").isVisible());
await page.keyboard.press("Escape");
await page.waitForTimeout(300);
await page.locator(".dialogue-rail__item").nth(1).click();
await page.waitForTimeout(400);
ok("个人画像面板打开", (await page.locator(".ws-sheet--inspector").innerText()).includes("待补充"));
await page.keyboard.press("Escape");
await page.waitForTimeout(300);

/* 交接卡 / 复制 / 回到最新 / 卡片切换键盘 */
await fresh("/#/chat");
ok("交接卡默认展开且带依据", (await page.locator(".chat-handoff").first().innerText()).includes("依据"));
await page.locator(".exp-copy").first().click();
await page.waitForTimeout(300);
ok("复制有反馈", (await page.locator(".exp-copy").first().innerText()).includes("复制"));
const cards = await page.locator(".chat-cards__tab").count();
ok("卡片组有切换器", cards > 1);
if (cards > 1) {
  const group = page.locator(".chat-cards").filter({ has: page.locator(".chat-cards__tabs") }).first();
  await group.locator(".chat-cards__tab").first().focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  const on = await group.locator(".chat-cards__tab.is-on").innerText();
  ok("→ 键切换卡片", on.trim().length > 0);
  await page.keyboard.press("End");
  await page.waitForTimeout(300);
  ok("End 键切到最后一张", (await group.locator(".chat-cards__pos").innerText()).includes("/ 2"));
}
await page.evaluate(() => {
  const f = document.querySelector(".ws-chat-flow");
  if (!f) return;
  f.scrollTop = 0;
  f.dispatchEvent(new Event("scroll"));
});
await page.waitForTimeout(400);
const latest = await page.locator(".exp-latest").count();
ok("回到最新按钮出现", latest === 1);
if (latest) { await page.locator(".exp-latest").click(); await page.waitForTimeout(400); }

fs.writeFileSync("_shots/chat-v8/features.json", JSON.stringify(out, null, 2));
await page.screenshot({ path: "_shots/chat-v8/14-功能复核-1280.png" });
await browser.close();
