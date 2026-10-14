import { pathToFileURL } from "node:url"
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5180"
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/academic?as=mid`, { waitUntil: "networkidle" })
await page.waitForTimeout(1600)
const out = await page.evaluate(() => {
  const SCOPE = "data-v-54ab2a9c"
  const mk = (html) => { const d = document.createElement("div"); d.className="app app--workspace"; d.style.position="fixed"; d.style.left="-9999px"; d.style.width="460px"; d.innerHTML=html; document.body.appendChild(d); return d }
  const banner = `<div class="status-banner status-banner--error" ${SCOPE}><span class="status-banner__icon" ${SCOPE}></span><div class="status-banner__body" ${SCOPE}><p class="status-banner__message" ${SCOPE}>出错了</p><div class="status-banner__actions" ${SCOPE}><button class="btn status-banner__retry" ${SCOPE} type="button">重试</button><button class="ws-text-button" ${SCOPE} type="button">查看详情</button></div></div></div>`
  const host = mk(banner)
  const rows = [...host.querySelectorAll(".status-banner__actions .btn, .status-banner__actions .ws-text-button")].map(a => { const x=a.getBoundingClientRect(); const s=getComputedStyle(a); return { tag:a.tagName, text:(a.textContent||"").trim(), box:`${Math.round(x.width)}x${Math.round(x.height)}`, minHeight:s.minHeight, display:s.display } })
  // 同一段结构，去掉 scoped 属性（对照组：证明 44px 来自 scoped 规则而不是别处）
  const host2 = mk(banner.replace(new RegExp(` ${SCOPE}`, "g"), ""))
  const rows2 = [...host2.querySelectorAll(".status-banner__actions .btn, .status-banner__actions .ws-text-button")].map(a => { const x=a.getBoundingClientRect(); const s=getComputedStyle(a); return { tag:a.tagName, text:(a.textContent||"").trim(), box:`${Math.round(x.width)}x${Math.round(x.height)}`, minHeight:s.minHeight } })
  host.remove(); host2.remove()
  return { withScopeAttr: rows, withoutScopeAttr: rows2, scopeId: SCOPE }
})
console.log(JSON.stringify(out, null, 2))
await browser.close()
