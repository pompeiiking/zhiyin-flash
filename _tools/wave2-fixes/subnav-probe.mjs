// 定位 `.ws-subnav a` 在 390 下为什么只有 38px（临时工具）
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
for (const [w, h] of [[390, 844], [1280, 900]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/review?as=mid`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  const out = await page.evaluate(() => {
    const nav = document.querySelector('.ws-subnav')
    if (!nav) return { nav: null }
    const a = nav.querySelector('a')
    const cs = getComputedStyle(a)
    const r = a.getBoundingClientRect()
    return {
      navCls: nav.className,
      box: { w: Math.round(r.width), h: Math.round(r.height) },
      height: cs.height, minHeight: cs.minHeight, maxHeight: cs.maxHeight,
      boxSizing: cs.boxSizing, display: cs.display, alignItems: cs.alignItems,
      padding: cs.padding, borderBottom: cs.borderBottomWidth, lineHeight: cs.lineHeight,
      fontSize: cs.fontSize, flexBasis: cs.flexBasis, alignSelf: cs.alignSelf,
      parentAlign: getComputedStyle(nav).alignItems, parentDisplay: getComputedStyle(nav).display,
    }
  })
  console.log(w, JSON.stringify(out, null, 2))
  await ctx.close()
}
await browser.close()
