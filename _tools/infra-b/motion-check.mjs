import { pathToFileURL } from 'node:url'
const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const browser = await chromium.launch()
const out = {}
for (const [label, reduce] of [['normal', 'no-preference'], ['reduced', 'reduce']]) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: reduce, isMobile: true, hasTouch: true })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/#/?signin=1`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.ws-sheet[open]', { timeout: 15000 })
  await page.waitForTimeout(500)
  out[label] = await page.evaluate(() => {
    const d = document.querySelector('.ws-sheet[open]')
    const r = d.getBoundingClientRect()
    const cs = getComputedStyle(d)
    return {
      visible: r.width > 0 && r.height > 0,
      display: cs.display,
      visibility: cs.visibility,
      opacity: cs.opacity,
      animationName: cs.animationName,
      animations: d.getAnimations().map(a => a.animationName || 'inline'),
      h: Math.round(r.height),
    }
  })
  await page.screenshot({ path: `_shots/infra-b/motion-${label}.png` })
  await ctx.close()
}
console.log(JSON.stringify(out, null, 2))
await browser.close()
