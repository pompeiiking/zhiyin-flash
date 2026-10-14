import { pathToFileURL } from "node:url"
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5180"
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } })
const page = await ctx.newPage()
await page.goto(`${BASE}/#/home?as=mid`, { waitUntil: "networkidle" })
await page.waitForTimeout(1400)
const r = await page.evaluate(() => {
  const box = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return `${Math.round(b.width)}x${Math.round(b.height)}` }
  const badge = document.querySelector(".ws-demo-badge")
  return {
    badge: box(badge),
    badgeCS: badge ? { display: getComputedStyle(badge).display, minWidth: getComputedStyle(badge).minWidth, minHeight: getComputedStyle(badge).minHeight, pad: getComputedStyle(badge).padding, justify: getComputedStyle(badge).justifyContent } : null,
    guideBtn: box(document.querySelector(".ws-guide button")),
    topbarH: box(document.querySelector(".ws-topbar")),
    docW: document.documentElement.scrollWidth, vw: innerWidth,
  }
})
console.log("home@390:", JSON.stringify(r, null, 2))
await page.goto(`${BASE}/#/report?as=mid`, { waitUntil: "networkidle" })
await page.waitForTimeout(1200)
const r2 = await page.evaluate(() => {
  const box = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return `${Math.round(b.width)}x${Math.round(b.height)}` }
  const a = document.querySelector(".ws-subnav a")
  const t = document.querySelector(".exp-tabs__trigger")
  return { subnavA: box(a), tabsTrigger: box(t), subnavExists: !!document.querySelector(".ws-subnav") }
})
console.log("report@390:", JSON.stringify(r2, null, 2))
await page.goto(`${BASE}/#/review?as=mid`, { waitUntil: "networkidle" })
await page.waitForTimeout(1200)
const r3 = await page.evaluate(() => {
  const box = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return `${Math.round(b.width)}x${Math.round(b.height)}` }
  return { sectionNavLinks: [...document.querySelectorAll(".desk-section-nav a")].map(box), foldInlineHead: box(document.querySelector(".fold--inline .fold__head")) }
})
console.log("review@390:", JSON.stringify(r3, null, 2))
await browser.close()
