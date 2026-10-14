// Foldable 层级检测验证：合法组合不报、真嵌套仍报（临时工具，用完即删）
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const mode = process.argv[2] ?? 'after' // after = 当前代码；before = 把祖先判据临时当成旧判据

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 200)))
await page.addInitScript(() => {
  window.__warns = []
  const orig = console.warn
  console.warn = function (...a) { try { window.__warns.push(a.map(String).join(' ')) } catch { /* noop */ } return orig.apply(this, a) }
})

await page.goto(`${BASE}/#/__fold-probe`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)

const out = await page.evaluate(() => {
  const warns = (window.__warns || []).filter((s) => s.includes('[Foldable]'))
  const q = (s) => document.querySelector(s)
  const a = q('#probe-a')
  const b = q('#probe-b')
  const headless = q('#probe-c')
  const text = (el) => (el ? el.tagName + ':' + (el.textContent || '').trim().slice(0, 30) : null)
  return {
    warns,
    legalStaticWrap: {
      outerTag: a?.querySelector('.fold')?.tagName,
      outerIsStatic: !!a?.querySelector('.fold--static'),
      outerHasButton: !!a?.querySelector('.fold--static button.fold__head'),
      innerExists: !!a?.querySelector('#probe-a-inner'),
      innerIsCollapsible: !!a?.querySelector('#probe-a-inner:not(.fold--static)'),
      innerHeadTag: a?.querySelector('#probe-a-inner .fold__head')?.tagName ?? null,
      innerInsideOuterBody: !!a?.querySelector('.fold--static .fold__body #probe-a-inner'),
    },
    trueNested: {
      outerCollapsible: !!b?.querySelector('.fold:not(.fold--static)'),
      innerExists: !!b?.querySelector('#probe-b-inner'),
      innerIsCollapsible: !!b?.querySelector('#probe-b-inner:not(.fold--static)'),
    },
    staticVariants: {
      headlessHasHeadEl: !!headless?.querySelector('.fold__static-head'),
      headlessTitleTag: headless?.querySelector('.fold__static-head, h2, h3, h4')?.tagName ?? null,
      titles: [...(headless?.querySelectorAll('.fold__static-head') ?? [])].map((h) => h.tagName),
      bareCounts: [...(headless?.querySelectorAll('.fold__static-bare') ?? [])].map((p) => p.textContent.trim()),
      inlineHeadMinH: getComputedStyle(document.querySelector('.fold--inline .fold__head')).minHeight,
    },
    foldCounts: {
      all: document.querySelectorAll('.fold').length,
      static: document.querySelectorAll('.fold--static').length,
      collapsible: document.querySelectorAll('.fold:not(.fold--static)').length,
    },
  }
})
console.log(`=== ${mode} ===`)
console.log(JSON.stringify(out, null, 2))
console.log('console errors:', errs)
await browser.close()
