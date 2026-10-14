// 定位 /review 的两个 38px 链接到底是什么、为什么矮（临时工具）
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/review?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)

const out = await page.evaluate(() => {
  const rows = []
  for (const el of document.querySelectorAll('a[href],button,[role=tab]')) {
    const r = el.getBoundingClientRect()
    if (r.height === 0) continue
    if (r.height >= 44) continue
    const cs = getComputedStyle(el)
    const parent = el.parentElement
    rows.push({
      tag: el.tagName,
      cls: typeof el.className === 'string' ? el.className : null,
      text: (el.textContent || '').trim().slice(0, 20),
      box: `${Math.round(r.width)}x${Math.round(r.height)}`,
      height: cs.height, minHeight: cs.minHeight, padding: cs.padding,
      lineHeight: cs.lineHeight, fontSize: cs.fontSize, display: cs.display,
      alignItems: cs.alignItems, boxSizing: cs.boxSizing,
      parent: parent ? `${parent.tagName}.${typeof parent.className === 'string' ? parent.className : ''}` : null,
      parentAlign: parent ? getComputedStyle(parent).alignItems : null,
      grandparent: parent?.parentElement ? `${parent.parentElement.tagName}.${typeof parent.parentElement.className === 'string' ? parent.parentElement.className : ''}` : null,
    })
  }
  const anyNav = [...document.querySelectorAll('nav')].map((n) => ({
    cls: typeof n.className === 'string' ? n.className : null,
    label: n.getAttribute('aria-label'),
    links: [...n.querySelectorAll('a')].map((a) => `${Math.round(a.getBoundingClientRect().width)}x${Math.round(a.getBoundingClientRect().height)}`),
    computedH: [...n.querySelectorAll('a')].map((a) => getComputedStyle(a).height),
  }))
  return { small: rows, navs: anyNav }
})
console.log(JSON.stringify(out, null, 2))
await browser.close()
