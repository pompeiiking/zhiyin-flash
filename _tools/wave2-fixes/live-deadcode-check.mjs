// 证明 .ws-context / .desk-status 仍是活代码（不能按死代码删），并验证 Foldable 的 chevron 在打印样式下不受旧规则影响
import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/notes?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1600)
const out = await page.evaluate(() => ({
  wsContextLive: document.querySelectorAll('.ws-context').length,
  wsContextDetails: [...document.querySelectorAll('details.ws-context')].map((d) => (d.querySelector('summary')?.textContent || '').trim().slice(0, 20)),
  wsContextSummaryMinH: (() => { const s = document.querySelector('.ws-context > summary'); return s ? getComputedStyle(s).minHeight : null })(),
  wsContextBodyLive: document.querySelectorAll('.ws-context__body').length,
  deskStatusLive: document.querySelectorAll('.desk-status').length,
  foldChevron: document.querySelectorAll('.fold__chevron').length,
  foldChevronDisplay: (() => { const c = document.querySelector('.fold__chevron'); return c ? getComputedStyle(c).display : null })(),
}))
console.log('/notes:', JSON.stringify(out, null, 2))
await page.goto(`${BASE}/#/profile?as=mid`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1600)
const p = await page.evaluate(() => ({
  wsContextBodyLive: document.querySelectorAll('.ws-context__body').length,
  foldChevrons: document.querySelectorAll('.fold__chevron').length,
  inlineHeadMinH: (() => { const h = document.querySelector('.fold--inline .fold__head'); return h ? getComputedStyle(h).minHeight : null })(),
}))
console.log('/profile:', JSON.stringify(p, null, 2))
await browser.close()
