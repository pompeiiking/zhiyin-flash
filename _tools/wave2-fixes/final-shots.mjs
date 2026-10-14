// 交付截图（wave2 修复）：把改动前后的关键位置各拍一张
import { pathToFileURL } from 'node:url'
import { mkdirSync } from 'node:fs'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const shots = [
  ['badge-390-home', '#/home?as=mid', 390, 844, null],
  ['subnav-390-report', '#/report?as=mid', 390, 844, null],
  ['sectionnav-390-review', '#/review?as=mid', 390, 844, null],
  ['foldinline-1280-review', '#/review?as=mid', 1280, 900, null],
  ['guide-390-home', '#/home?as=mid', 390, 844, null],
  ['statusbanner', '#/intel?as=mid', 1280, 900, null],
]
for (const [name, hash, w, h, sel] of shots) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } })
  const page = await ctx.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 160)))
  await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  if (sel) await page.click(sel).catch(() => {})
  await page.screenshot({ path: `${OUT}/final-${name}.png` })
  console.log(`${name.padEnd(26)} err=${errs.length}`)
  await ctx.close()
}
await browser.close()
