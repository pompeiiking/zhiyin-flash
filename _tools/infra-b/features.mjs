import { pathToFileURL } from 'node:url'
import { mkdirSync } from 'node:fs'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
mkdirSync('_shots/infra-b', { recursive: true })
const browser = await chromium.launch()

const box = (page, sel) => page.evaluate((s) => {
  const d = document.querySelector(s)
  if (!d) return null
  const r = d.getBoundingClientRect()
  const cs = getComputedStyle(d)
  return { y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), bottomGap: Math.round(innerHeight - r.bottom), radius: cs.borderRadius, cls: d.className }
}, sel)

const out = {}

// 1) Esc / backdrop / 焦点 / Tab 环绕 / 滚动 —— 逐条功能回归（dialog 形态，门户登录）
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.pf-login', { timeout: 15000 })
  const t = page.locator('.pf-login')
  await t.focus(); await t.click()
  await page.waitForSelector('.ws-sheet[open]', { timeout: 15000 })
  await page.waitForTimeout(300)

  // Tab 环绕：从最后一个可聚焦元素 Tab 应回到第一个
  const trap = await page.evaluate(() => {
    const d = document.querySelector('.ws-sheet[open]')
    const f = [...d.querySelectorAll('button,a[href],input:not(:disabled),select,textarea,[tabindex="0"]')].filter(e => e.getClientRects().length)
    return { count: f.length, first: f[0]?.className || f[0]?.tagName, last: f[f.length - 1]?.className || f[f.length - 1]?.tagName }
  })
  await page.evaluate(() => {
    const d = document.querySelector('.ws-sheet[open]')
    const f = [...d.querySelectorAll('button,a[href],input:not(:disabled),select,textarea,[tabindex="0"]')].filter(e => e.getClientRects().length)
    f[f.length - 1].focus()
  })
  await page.keyboard.press('Tab')
  const afterTab = await page.evaluate(() => {
    const a = document.activeElement
    return typeof a.className === 'string' ? a.className : a.tagName
  })

  // 滚动：body 可滚且 overscroll 受控
  const scroll = await page.evaluate(() => {
    const b = document.querySelector('.ws-sheet[open] .ws-sheet__body')
    const before = b.scrollTop
    b.scrollTop = 9999
    const after = b.scrollTop
    return { before, after, canScroll: after > before, overscroll: getComputedStyle(b).overscrollBehavior }
  })

  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)
  const afterEsc = await page.evaluate(() => {
    const a = document.activeElement
    return { cls: typeof a.className === 'string' ? a.className : a.tagName, tag: a.tagName }
  })
  out.dialog = { trap, afterTab, scroll, afterEsc, box: await box(page, '.ws-sheet[open]').catch(() => null) }
  await ctx.close()
}

// 2) 移动端：确认类 dialog 仍居中；sheet 形态到底（用 --inspector 调用点）
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/?signin=1`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.ws-sheet--dialog[open]', { timeout: 15000 })
  await page.waitForTimeout(350)
  out.mobileDialog = await box(page, '.ws-sheet--dialog[open]')
  await ctx.close()
}

// 3) 旧 prop 兼容：wide → panel、inspector → sheet（真的打开来量）
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const hits = {}
  await page.goto(`${BASE}/#/academic`, { waitUntil: 'networkidle', timeout: 25000 })
  await page.waitForTimeout(700)
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(x => /导入课表|导入资料|上传|导入/.test(x.textContent || ''))
    if (b) b.click()
  })
  await page.waitForTimeout(800)
  hits.wide = await box(page, '.ws-sheet[open]')

  await page.goto(`${BASE}/#/chat`, { waitUntil: 'networkidle', timeout: 25000 })
  await page.waitForTimeout(900)
  try {
    await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')].find(x => (x.getAttribute('aria-label') || '').includes('个人画像'))
      if (b) b.click()
    })
    await page.waitForSelector('.ws-sheet--sheet[open]', { timeout: 8000 })
    await page.waitForTimeout(400)
    hits.inspector = await box(page, '.ws-sheet--sheet[open]')
  } catch (e) {
    hits.inspector = { err: String(e).slice(0, 120), hash: await page.evaluate(() => location.hash) }
  }
  out.compat = hits
  await ctx.close()
}

console.log(JSON.stringify(out, null, 2))
await browser.close()
