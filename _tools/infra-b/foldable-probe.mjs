import { pathToFileURL } from 'node:url'
import { mkdirSync, writeFileSync } from 'node:fs'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
mkdirSync('_shots/infra-b', { recursive: true })

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
const logs = []
page.on('console', m => logs.push(`${m.type()}: ${m.text()}`))
page.on('pageerror', e => logs.push('pageerror: ' + e.message))

// 必须在导航前就装好，console.warn 发生在组件 setup 期
await page.addInitScript(() => {
  window.__warns = []
  const orig = console.warn
  console.warn = function (...args) { window.__warns.push(args.map(String).join(' ')); return orig.apply(this, args) }
})

await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#fold-probe', { timeout: 15000 })
await page.waitForTimeout(600)

const probe = await page.evaluate(() => {
  const q = (s) => document.querySelector(s)
  const outer = q('#probe-outer')
  const inner = q('#probe-inner')
  const stat = q('#probe-static')
  const head = outer?.querySelector('.fold__head')
  const body = outer?.querySelector('.fold__body')
  return {
    warns: window.__warns,
    outer: {
      tag: outer?.tagName,
      headTag: head?.tagName,
      ariaExpanded: head?.getAttribute('aria-expanded'),
      ariaControls: head?.getAttribute('aria-controls'),
      controlsResolves: !!(head?.getAttribute('aria-controls') && document.getElementById(head.getAttribute('aria-controls'))),
      bodyVisible: !!body && body.getClientRects().length > 0,
      bodyId: body?.id,
    },
    inner: {
      exists: !!inner,
      headAria: inner?.querySelector('.fold__head')?.getAttribute('aria-expanded'),
      // 嵌套：内层是不是长在外层 body 里
      nestedInsideOuter: !!outer && !!inner && outer.contains(inner),
      // 内层默认收起时其自身 body 是否存在（v-if）
      hasOwnBody: !!inner?.querySelector('.fold__body'),
    },
    staticForm: {
      tag: stat?.tagName,
      hasButton: !!stat?.querySelector('button.fold__head'),
      contentVisible: q('#probe-static-body')?.getClientRects().length > 0,
      bodyHiddenAttr: stat?.querySelector('.fold__body') ? null : 'body missing',
    },
    actionsVariant: {
      cls: q('#probe-actions')?.className,
      actionBtnVisible: !!q('#probe-actions .btn') && q('#probe-actions .btn').getClientRects().length > 0,
    },
    classes: {
      section: q('#probe-section')?.className,
      sectionHeadMinH: q('#probe-section .fold__head') ? getComputedStyle(q('#probe-section .fold__head')).minHeight : null,
    },
    staticComputed: stat ? { class: stat.className, bodyDisplay: getComputedStyle(stat.querySelector('.fold__body')).display } : null,
  }
})

// 键盘可达性：Tab 到外层头部后回车 / 空格切换
const kb = await page.evaluate(async () => {
  const outer = document.querySelector('#probe-outer')
  const head = outer.querySelector('.fold__head')
  const before = head.getAttribute('aria-expanded')
  head.focus()
  const focused = document.activeElement === head
  head.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
  // 原生 button 的 click 由浏览器产生，jsdom 式派发不会触发；直接点它等价于键盘激活
  head.click()
  await new Promise(r => setTimeout(r, 60))
  const after = head.getAttribute('aria-expanded')
  return { focused, before, after, controlledStillWorks: before !== after }
})

// 页内按钮触发的重挂载：此刻 console.warn 的钩子一定已经装好
await page.evaluate(() => { window.__warns.length = 0 })
await page.evaluate(() => document.querySelector('#probe-devflag').click())
await page.evaluate(() => document.querySelector('#probe-remount').click())
await page.waitForTimeout(700)
const remountWarns = await page.evaluate(() => window.__warns.slice())

console.log(JSON.stringify({ probe, kb, remountWarns, logs: logs.slice(0, 40) }, null, 2))
writeFileSync('_shots/infra-b/foldable-probe.json', JSON.stringify({ probe, kb, remountWarns, logs }, null, 2), 'utf8')
await page.screenshot({ path: '_shots/infra-b/foldable-probe.png', fullPage: false })
await browser.close()
