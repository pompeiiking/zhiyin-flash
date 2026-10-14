// wave2 修复验收脚本（临时工具，不属于交付物）
// 用法：node _tools/wave2-fixes/audit.mjs <before|after>
// 量：8 路由 × 1280/390 的 <44px 命中区、控制台错误、InfoSheet 形态类名、Foldable 层级警告、inline 折叠头高度
import { mkdirSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)

const tag = process.argv[2] ?? 'run'
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const ROUTES = [
  ['home', '#/home?as=mid'],
  ['chat', '#/chat?as=mid'],
  ['profile', '#/profile?as=mid'],
  ['report', '#/report?as=mid'],
  ['plan', '#/plan?as=mid'],
  ['review', '#/review?as=mid'],
  ['academic', '#/academic?as=mid'],
  ['schedule', '#/schedule?as=mid'],
  ['notes', '#/notes?as=mid'],
  ['intel', '#/intel?as=mid'],
]

const SIZES = [
  ['1280', 1280, 900],
  ['390', 390, 844],
]

/** 页内量测：所有可见可交互元素的命中矩形，任何一边 < 44 都记一条 */
const MEASURE = () => {
  const SEL = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
    'summary', '[role=button]', '[role=link]', '[role=tab]', '[tabindex="0"]',
  ].join(',')
  const seen = new Set()
  const small = []
  let total = 0
  for (const el of document.querySelectorAll(SEL)) {
    if (el.closest('dialog:not([open])')) continue
    const cs = getComputedStyle(el)
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) continue
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) continue
    // 只算真正落在视口内的（滚出去的用 innerHeight 判断没有意义，这里记录整页，不做裁剪）
    total += 1
    const w = Math.round(r.width), h = Math.round(r.height)
    if (w >= 44 && h >= 44) continue
    // 命中区被 ::after 撑开的不算（例如任务勾选框：视觉 32px、命中 44px）
    const afterContent = getComputedStyle(el, '::after').content
    const afterW = parseFloat(getComputedStyle(el, '::after').width) || 0
    const afterH = parseFloat(getComputedStyle(el, '::after').height) || 0
    const hitPad = afterContent !== 'none' && afterW >= 44 && afterH >= 44
    if (hitPad) continue
    const key = `${el.tagName}.${(typeof el.className === 'string' ? el.className : '').split(/\s+/).filter(Boolean).slice(0, 3).join('.')}|${w}x${h}`
    if (seen.has(key)) continue
    seen.add(key)
    small.push({
      sel: key,
      w, h,
      text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 26),
      cls: typeof el.className === 'string' ? el.className : null,
    })
  }
  return { total, small }
}

const browser = await chromium.launch()
const report = { tag, base: BASE, routes: {} }

for (const [name, hash] of ROUTES) {
  for (const [wlabel, width, height] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })
    const page = await ctx.newPage()
    const errors = []
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)) })
    page.on('pageerror', (e) => errors.push('pageerror: ' + String(e.message).slice(0, 300)))
    await page.addInitScript(() => {
      window.__warns = []
      const orig = console.warn
      console.warn = function (...a) { try { window.__warns.push(a.map(String).join(' ')) } catch { /* noop */ } return orig.apply(this, a) }
    })
    try {
      await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle', timeout: 30000 })
      await page.waitForTimeout(1200)
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
      await page.waitForTimeout(500)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.waitForTimeout(300)
      const m = await page.evaluate(MEASURE)
      const extra = await page.evaluate(() => {
        const folds = [...document.querySelectorAll('.fold')]
        const statics = folds.filter((f) => f.classList.contains('fold--static'))
        const collapsibles = folds.filter((f) => !f.classList.contains('fold--static'))
        const nestedReal = collapsibles.filter((f) => f.parentElement?.closest('.fold:not(.fold--static)'))
        const staticWrapCollapsible = collapsibles.filter((f) => f.parentElement?.closest('.fold--static'))
        const inlineHead = document.querySelector('.fold--inline .fold__head')
        const sheets = [...document.querySelectorAll('dialog.ws-sheet')]
        return {
          warns: (window.__warns || []).filter((s) => s.includes('[Foldable]')),
          foldCount: folds.length,
          staticCount: statics.length,
          collapsibleCount: collapsibles.length,
          trulyNestedCount: nestedReal.length,
          collapsibleInsideStatic: staticWrapCollapsible.length,
          inlineHead: inlineHead ? {
            minHeight: getComputedStyle(inlineHead).minHeight,
            h: Math.round(inlineHead.getBoundingClientRect().height),
          } : null,
          sheetClasses: sheets.map((d) => d.className),
          hasWideInspector: !!document.querySelector('.ws-sheet--wide, .ws-sheet--inspector'),
          docWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
        }
      })
      report.routes[`${name}@${wlabel}`] = { ...m, ...extra, errors }
      await page.screenshot({ path: `${OUT}/${tag}-${name}-${wlabel}.png`, fullPage: false })
    } catch (e) {
      report.routes[`${name}@${wlabel}`] = { error: String(e).slice(0, 300), errors }
    }
    await ctx.close()
  }
}

await browser.close()
writeFileSync(`${OUT}/audit-${tag}.json`, JSON.stringify(report, null, 2), 'utf8')

// 摘要
console.log(`\n=== ${tag} ===`)
for (const [k, v] of Object.entries(report.routes)) {
  if (v.error) { console.log(`${k.padEnd(14)} ERROR ${v.error}`); continue }
  console.log(
    `${k.padEnd(14)} <44px:${String(v.small.length).padStart(2)}  total:${String(v.total).padStart(3)}` +
    `  consoleErr:${v.errors.length}  foldWarns:${v.warns.length}` +
    `  folds(collapsible/static)=${v.collapsibleCount}/${v.staticCount}` +
    `  nested=${v.trulyNestedCount} inStatic=${v.collapsibleInsideStatic}` +
    `  inlineHead=${v.inlineHead ? v.inlineHead.minHeight + '/' + v.inlineHead.h : '-'}` +
    `  wideInspector=${v.hasWideInspector}` +
    (v.docWidth > v.innerWidth ? `  OVERFLOW ${v.docWidth}>${v.innerWidth}` : ''),
  )
}
