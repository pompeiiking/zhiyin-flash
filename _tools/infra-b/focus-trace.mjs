import { mkdirSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
mkdirSync('_shots/infra-b', { recursive: true })

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' })
await page.waitForSelector('.pf-login', { timeout: 15000 })
await page.locator('.pf-login').focus()
await page.locator('.pf-login').click()
await page.waitForSelector('.ws-sheet[open]', { timeout: 15000 })
await page.waitForTimeout(400)

// 装一个记录器：任何 focus/blur 都记下来，看是谁把焦点拿走的
const log = await page.evaluate(async () => {
  const events = []
  const tag = (el) => el ? `${el.tagName}.${typeof el.className === 'string' ? el.className.split(' ').join('.') : ''}`.slice(0, 60) : 'null'
  const t0 = performance.now()
  const stamp = () => Math.round(performance.now() - t0)
  document.addEventListener('focusin', (e) => events.push([stamp(), 'focusin', tag(e.target)]), true)
  document.addEventListener('focusout', (e) => events.push([stamp(), 'focusout', tag(e.target)]), true)
  const d = document.querySelector('.ws-sheet[open]')
  return { events, note: 'listeners installed' }
})

await page.evaluate(() => {
  window.__focusTrace = []
  const t0 = performance.now()
  const tag = (el) => el ? `${el.tagName}.${typeof el.className === 'string' ? el.className.split(' ').join('.') : ''}`.slice(0, 60) : 'null'
  const push = (label) => window.__focusTrace.push([Math.round(performance.now() - t0), label, tag(document.activeElement)])
  document.addEventListener('focusin', (e) => window.__focusTrace.push([Math.round(performance.now() - t0), 'focusin', tag(e.target)]), true)
  document.addEventListener('focusout', (e) => window.__focusTrace.push([Math.round(performance.now() - t0), 'focusout', tag(e.target)]), true)
  const dialog = document.querySelector('.ws-sheet[open]')
  dialog.addEventListener('close', () => push('dialog.close-event'))
})

await page.keyboard.press('Escape')
await page.waitForTimeout(1500)
const trace = await page.evaluate(() => ({
  trace: window.__focusTrace,
  final: document.activeElement ? `${document.activeElement.tagName}.${typeof document.activeElement.className === 'string' ? document.activeElement.className : ''}` : null,
}))
console.log(JSON.stringify(trace, null, 2))
writeFileSync('_shots/infra-b/focus-trace.json', JSON.stringify(trace, null, 2), 'utf8')
await browser.close()
