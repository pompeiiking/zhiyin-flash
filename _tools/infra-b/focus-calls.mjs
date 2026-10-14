import { pathToFileURL } from 'node:url'
import { writeFileSync } from 'node:fs'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
const consoleLines = []
page.on('console', m => consoleLines.push(`${m.type()}: ${m.text()}`))
page.on('pageerror', e => consoleLines.push('pageerror: ' + e.message))
await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('.pf-login', { timeout: 15000 })

// 包装 HTMLElement.prototype.focus，记录每次调用与调用栈
await page.evaluate(() => {
  window.__focusCalls = []
  const orig = HTMLElement.prototype.focus
  HTMLElement.prototype.focus = function (...args) {
    window.__focusCalls.push({
      t: Math.round(performance.now()),
      el: `${this.tagName}.${typeof this.className === 'string' ? this.className.split(' ').join('.') : ''}`.slice(0, 60),
      stack: new Error().stack.split('\n').slice(1, 4).join(' | ').slice(0, 260),
    })
    return orig.apply(this, args)
  }
})

await page.locator('.pf-login').focus()
await page.locator('.pf-login').click()
await page.waitForSelector('.ws-sheet[open]', { timeout: 15000 })
await page.waitForTimeout(400)
await page.evaluate(() => { window.__focusCalls = []; window.__t0 = performance.now() })
await page.keyboard.press('Escape')
await page.waitForTimeout(1200)
const out = await page.evaluate(() => ({
  calls: window.__focusCalls,
  rafFired: window.__rafFired ?? null,
  final: document.activeElement ? document.activeElement.tagName + '.' + (typeof document.activeElement.className === 'string' ? document.activeElement.className : '') : null,
  hash: location.hash,
}))
console.log(JSON.stringify(out, null, 2))
console.log('--- console ---')
console.log(consoleLines.slice(-30).join('\n'))
writeFileSync('_shots/infra-b/focus-calls.json', JSON.stringify({ out, consoleLines }, null, 2), 'utf8')
await browser.close()
