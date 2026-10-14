// Shell v8 screenshots: desktop (sidebar + footer), mobile (topbar / bottom bar /
// "more" drawer), account sheet (with 外观 + 演示设置), demo sheet, portal toast,
// 404, ⌘K. All state is driven through the UI so the shots prove the real thing.
//   node _tools/shot-shell-v8.mjs
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PW_PATH || "playwright");
const base = "http://127.0.0.1:5180";
const OUT = "_shots/shell-v8";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

async function ctx(width, height) {
  const c = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const p = await c.newPage();
  p.on("pageerror", (e) => console.log("  !! pageerror", String(e).slice(0, 160)));
  p.on("console", (m) => { if (m.type() === "error") console.log("  !! console", m.text().slice(0, 160)); });
  return { c, p };
}
const shot = async (p, name) => { await p.screenshot({ path: `${OUT}/${name}.png` }); console.log("  ->", name); };
const go = (p, hash) => p.goto(`${base}/${hash}`, { waitUntil: "networkidle" }).then(() => p.waitForTimeout(700));

// 1. 桌面侧栏（含页脚：账号 + 返回门户）
{
  const { c, p } = await ctx(1280, 900);
  await go(p, "#/profile?as=mid");
  await shot(p, "desktop-sidebar-1280");
  await c.close();
}

// 2. 移动顶栏 + 底栏
{
  const { c, p } = await ctx(390, 844);
  await go(p, "#/profile?as=mid");
  await shot(p, "mobile-topbar-profile-390");
  await c.close();
}

// 3. 移动底栏 + 「更多」抽屉
{
  const { c, p } = await ctx(390, 844);
  await go(p, "#/chat?as=mid");
  await p.getByRole("button", { name: "更多功能" }).click();
  await p.waitForTimeout(600);
  await shot(p, "mobile-more-drawer-390");
  await c.close();
}

// 4. 账号抽屉（身份 / 外观 / 演示设置 / 退出）+ 展开里的演示设置
{
  const { c, p } = await ctx(390, 844);
  await go(p, "#/profile?as=mid");
  await p.getByRole("button", { name: "账号菜单" }).click();
  await p.waitForTimeout(600);
  await shot(p, "mobile-account-sheet-390");
  await p.locator(".ws-sheet__body .ws-account-row").first().click();
  await p.waitForTimeout(600);
  await shot(p, "mobile-demo-sheet-390");
  await c.close();
}

// 4b. 桌面折叠态：顶栏「账号」是唯一账号入口
{
  const { c, p } = await ctx(1280, 900);
  await go(p, "#/chat?as=mid");
  await p.getByRole("button", { name: "收起侧栏" }).click();
  await p.waitForTimeout(700);
  await shot(p, "desktop-sidebar-collapsed-1280");
  await p.getByRole("button", { name: "账号菜单" }).click();
  await p.waitForTimeout(600);
  await shot(p, "desktop-account-sheet-1280");
  await p.locator(".ws-appearance__summary").click();
  await p.waitForTimeout(500);
  await shot(p, "desktop-account-appearance-1280");
  await c.close();
}

// 5. 门户上触发一次 toast，证明公共层渲染（D6）
//    门户是公开布局（bare 分支），原来那条 toast 节点只挂在 app--workspace 里，
//    所以在门户上"登录成功 / 已退出"永远不会出现。这里在门户上走一次**真实登录**
//    （?signin=1 → 填密码 → 进入演示），登录成功后 App 的规则会把人送进对话页 ——
//    而"已登录：mid"这条 toast 属于公共层，跟着一起过去，所以趁跳转前截一张、跳转后补一张。
{
  const { c, p } = await ctx(1280, 900);
  await p.goto(`${base}/#/`, { waitUntil: "networkidle" });
  await p.evaluate(() => { try { localStorage.clear() } catch {} });
  await go(p, "#/");
  await go(p, "#/?signin=1");
  await shot(p, "portal-signin-sheet-1280");
  await p.getByLabel("密码").fill("demo");
  await p.getByRole("button", { name: "进入演示" }).click();
  // 等 toast 真的在 DOM 里再截（toast 3.2s 后自己消失）
  await p.waitForSelector(".toast", { state: "visible", timeout: 4000 }).catch(() => {});
  await shot(p, "portal-toast-1280");
  // 再补一张"登录后落在对话页"的（同一条 toast 跟着走到公共层）
  await p.waitForTimeout(500);
  await shot(p, "portal-toast-after-login-1280");
  await c.close();
}

// 6. 404 页（地址列表只有真实路由；/spec /path /tools 不再出现）
//     真实路径：登录后点「退出登录」→ App 把人送回门户并带上 ?signin=1，
//     此时「已退出登录」这条 toast 必须出现在**门户**上。
//     以前渲染节点只挂在 app--workspace 分支里，门户这条路径永远没有任何反馈。
{
  const { c, p } = await ctx(1280, 900);
  await p.goto(`${base}/#/chat?as=mid`, { waitUntil: "networkidle" });
  await p.waitForTimeout(600);
  await p.getByRole("button", { name: "账号菜单" }).click();
  await p.waitForTimeout(400);
  await p.getByRole("button", { name: "退出登录" }).click();
  await p.waitForTimeout(250);
  await shot(p, "portal-toast-1280");
  const st = await p.evaluate(() => {
    const t = document.querySelector('.toast');
    return { url: location.hash, toast: t ? t.textContent.trim() : null, bare: !document.querySelector('.ws-topbar') };
  });
  console.log("   门户 toast：", JSON.stringify(st));
  await c.close();
}

// 6. 404 页（地址列表只有真实路由；/spec /path /tools 不再出现）
{
  const { c, p } = await ctx(1280, 900);
  await go(p, "#/this-address-does-not-exist?as=mid");
  await shot(p, "notfound-1280");
  await c.close();
}

// 7. ⌘K 命令面板（内部页不再出现）
{
  const { c, p } = await ctx(1280, 900);
  await go(p, "#/profile?as=mid");
  await p.keyboard.press("Control+k");
  await p.waitForTimeout(600);
  await shot(p, "command-palette-1280");
  await c.close();
}

await browser.close();
console.log("done");
