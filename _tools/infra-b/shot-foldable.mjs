import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 760, height: 900 }, deviceScaleFactor: 2 })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('#fold-probe', { timeout: 15000 })
await page.waitForTimeout(500)
// 把验证台挪到可见位置再截图（只为留证）
await page.evaluate(() => {
  const s = document.querySelector('#fold-probe')
  s.style.cssText = 'position:fixed;left:40px;top:40px;width:640px;z-index:99999;background:var(--c-surface);padding:24px;border:1px solid var(--c-border);border-radius:12px'
})
await page.waitForTimeout(250)
await page.screenshot({ path: '_shots/infra-b/foldable-variants.png' })
await browser.close()
console.log('ok')
