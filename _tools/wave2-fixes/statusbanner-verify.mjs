// StatusBanner 动作按钮实测（wave2 修到 >=44px 的证据）
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)) })
page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 160)))

const measure = () => page.evaluate(() => {
  const banners = [...document.querySelectorAll('.status-banner')].map((b) => ({
    cls: b.className,
    text: (b.textContent || '').trim().slice(0, 34),
    actions: [...b.querySelectorAll('.status-banner__actions .btn, .status-banner__actions .ws-text-button')]
      .map((a) => { const x = a.getBoundingClientRect(); const s = getComputedStyle(a); return { tag: a.tagName, text: (a.textContent || '').trim().slice(0, 10), box: `${Math.round(x.width)}x${Math.round(x.height)}`, minHeight: s.minHeight, display: s.display } }),
  }))
  const close = document.querySelector('.status-banner__close')
  const after = close ? getComputedStyle(close, '::after') : null
  return {
    banners,
    close: close ? { box: (() => { const b = close.getBoundingClientRect(); return `${Math.round(b.width)}x${Math.round(b.height)}` })(), hitArea: after ? `${after.width}x${after.height}` : null } : null,
  }
})

await page.goto(`${BASE}/#/intel?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
console.log('/intel 初始:', JSON.stringify(await measure(), null, 2))

// 造一条 error banner：空关键词提交检索
const clicked = await page.evaluate(() => {
  const form = document.querySelector('.remote-search')
  if (!form) return 'no-form'
  const b = [...form.querySelectorAll('button')].pop()
  if (!b) return 'no-button'
  b.click()
  return 'clicked:' + (b.textContent || '').trim()
})
await page.waitForTimeout(1800)
console.log('/intel 空检索后:', clicked)
console.log(JSON.stringify(await measure(), null, 2))

// ModuleCatalog 的 error banner（/tools）
await page.goto(`${BASE}/#/tools?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)
const t = await page.evaluate(() => {
  const b = [...document.querySelectorAll('.module-catalog button')].find((x) => /读取工具目录/.test(x.textContent || ''))
  if (b) b.click()
  return !!b
})
await page.waitForTimeout(2000)
console.log('/tools 点读取:', t)
console.log(JSON.stringify(await measure(), null, 2))
console.log('console errors:', errs)
await browser.close()
