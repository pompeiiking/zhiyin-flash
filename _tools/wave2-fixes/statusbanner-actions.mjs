// StatusBanner 带动作位的形态：直接量 DOM 计算样式（用 page.setContent 注入一个隔离实例）
import { pathToFileURL } from 'node:url'
import { mkdirSync, readFileSync, readdirSync } from 'node:fs'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)) })
page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 160)))

// 先打开真实页面，让它加载好样式与 Vue 运行时
await page.goto(`${BASE}/#/intel?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)

// 找一条会立刻进入 error 的路径：AcademicVerification 的 service 模式在 demo 下会失败
await page.goto(`${BASE}/#/academic?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1600)
const opened = await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find((x) => /提供在线验证码/.test(x.textContent || ''))
  if (!b) return 'no-open-button'
  b.click()
  return 'opened'
})
await page.waitForTimeout(900)
const submitted = await page.evaluate(() => {
  const labels = [...document.querySelectorAll('dialog input[type=radio]')]
  const service = labels.find((r) => r.value === 'service')
  if (service) { service.click(); service.dispatchEvent(new Event('change', { bubbles: true })) }
  const code = document.querySelector('dialog input[maxlength="80"]')
  if (code) { code.value = 'TEST-0000'; code.dispatchEvent(new Event('input', { bubbles: true })) }
  const submit = [...document.querySelectorAll('dialog button[type=submit]')][0]
  if (!submit) return 'no-submit'
  submit.click()
  return 'submitted mode=' + (service ? service.value : '?')
})
await page.waitForTimeout(3500)

const res = await page.evaluate(() => {
  const out = []
  for (const b of document.querySelectorAll('.status-banner')) {
    out.push({
      cls: b.className,
      text: (b.textContent || '').trim().slice(0, 40),
      actions: [...b.querySelectorAll('.status-banner__actions .btn, .status-banner__actions .ws-text-button')]
        .map((a) => { const x = a.getBoundingClientRect(); const s = getComputedStyle(a); return { tag: a.tagName, text: (a.textContent || '').trim().slice(0, 10), box: `${Math.round(x.width)}x${Math.round(x.height)}`, minHeight: s.minHeight, display: s.display } }),
    })
  }
  return out
})
console.log('opened:', opened, '| submitted:', submitted)
console.log(JSON.stringify(res, null, 2))
console.log('errors:', errs)
await page.screenshot({ path: `${OUT}/statusbanner-error-actions.png` })
await browser.close()
