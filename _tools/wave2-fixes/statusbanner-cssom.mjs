// StatusBanner 动作位 >=44px：从 CSSOM 直接验证规则 + 在真实弹层里找动作位
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
page.on('pageerror', (e) => console.log('pageerror:', String(e.message).slice(0, 160)))
await page.goto(`${BASE}/#/academic?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1600)
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => /提供在线验证码/.test(x.textContent || ''))
  b?.click()
})
await page.waitForTimeout(800)
await page.evaluate(() => {
  const service = [...document.querySelectorAll('dialog input[type=radio]')].find((r) => r.value === 'service')
  service?.click()
  const code = document.querySelector('dialog input[maxlength="80"]')
  if (code) { code.value = 'TEST-0000'; code.dispatchEvent(new Event('input', { bubbles: true })) }
  document.querySelector('dialog button[type=submit]')?.click()
})
await page.waitForTimeout(3500)

const out = await page.evaluate(() => {
  // 1) 从 CSSOM 找出 .status-banner__actions .btn 的实际生效声明
  const cssRules = []
  for (const sheet of document.styleSheets) {
    let rules
    try { rules = sheet.cssRules } catch { continue }
    for (const r of rules) {
      if (r.selectorText && /status-banner__actions/.test(r.selectorText)) {
        cssRules.push({ sel: r.selectorText, minHeight: r.style.minHeight, display: r.style.display })
      }
    }
  }
  // 2) 真实 DOM 里的动作位（有就量）
  const actions = [...document.querySelectorAll('.status-banner__actions .btn, .status-banner__actions .ws-text-button')]
    .map((a) => { const x = a.getBoundingClientRect(); return { tag: a.tagName, text: (a.textContent || '').trim().slice(0, 10), box: `${Math.round(x.width)}x${Math.round(x.height)}`, minHeight: getComputedStyle(a).minHeight } })
  // 3) 用真实类名 + 内容造一个离屏实例，量它在真实样式表下的高度
  const probe = document.createElement('div')
  probe.className = 'status-banner status-banner--error'
  probe.style.position = 'fixed'; probe.style.left = '-9999px'; probe.style.width = '420px'
  probe.innerHTML = '<span class="status-banner__icon"></span><div class="status-banner__body"><p class="status-banner__message">出错了</p><div class="status-banner__actions"><button class="btn status-banner__retry" type="button">重试</button><button class="ws-text-button" type="button">查看详情</button></div></div>'
  document.body.appendChild(probe)
  const synthetic = [...probe.querySelectorAll('.status-banner__actions .btn, .status-banner__actions .ws-text-button')]
    .map((a) => { const x = a.getBoundingClientRect(); return { tag: a.tagName, text: (a.textContent || '').trim(), box: `${Math.round(x.width)}x${Math.round(x.height)}`, minHeight: getComputedStyle(a).minHeight, display: getComputedStyle(a).display, align: getComputedStyle(a).alignItems } })
  probe.remove()
  return { cssRules, actions, synthetic, bannersOnPage: document.querySelectorAll('.status-banner').length }
})
console.log(JSON.stringify(out, null, 2))
await browser.close()
