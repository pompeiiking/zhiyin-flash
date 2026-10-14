// 桌面：把已打开的 dialog 临场换成 sheet/panel，验证桌面形态（右侧抽屉 / 宽面板）
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/?signin=1`, { waitUntil: 'networkidle' })
await page.waitForSelector('.ws-sheet--dialog[open]', { timeout: 15000 })
await page.waitForTimeout(300)

async function swap(to, file) {
  const info = await page.evaluate((target) => {
    const d = document.querySelector('.ws-sheet[open]')
    const proto = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'open')
    Object.defineProperty(d, 'open', { configurable: true, get: () => proto.get.call(d), set: () => {} })
    Object.defineProperty(d, 'close', { configurable: true, value: () => {} })
    d.className = 'ws-sheet ws-sheet--' + target
    d.getAnimations().forEach(a => a.cancel())
    d.animate([{ opacity: .6, transform: target === 'sheet' ? 'translateX(18px)' : 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 240, easing: 'ease-out', fill: 'forwards' })
    return new Promise(res => setTimeout(() => {
      const r = d.getBoundingClientRect()
      const cs = getComputedStyle(d)
      res({ box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, radius: cs.borderRadius, rightGap: Math.round(innerWidth - r.right) })
    }, 380))
  }, to)
  await page.screenshot({ path: file })
  return info
}

const sheet = await swap('sheet', '_shots/infra-b/final-desktop-sheet.png')
// 复位再试 panel
await page.reload({ waitUntil: 'networkidle' })
await page.waitForSelector('.ws-sheet--dialog[open]', { timeout: 15000 })
await page.waitForTimeout(300)
const panel = await swap('panel', '_shots/infra-b/final-desktop-panel.png')

console.log(JSON.stringify({ sheet, panel }, null, 2))
await browser.close()
