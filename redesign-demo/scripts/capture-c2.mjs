// Capture the interactive prototype and Vue app at identical dimensions.
// Run from redesign-demo: C2_URL=http://127.0.0.1:5199 node scripts/capture-c2.mjs
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
const require = createRequire(import.meta.url)
let chromium
for (const modulePath of [process.env.PW_PATH, 'playwright', join(process.env.LOCALAPPDATA || '', 'npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright')].filter(Boolean)) {
  try { chromium = require(modulePath).chromium; break } catch {}
}
if (!chromium) throw new Error('Set PW_PATH to an installed Playwright module.')
const base = process.env.C2_URL || 'http://127.0.0.1:5199'
const reference = new URL('../design-review/v6-redesign/directions/c2-hbu/index.html', import.meta.url)
const out = resolve(process.env.C2_SHOTS || '.tmp-shots/c2-pairs')
const routes = (process.env.C2_ROUTES || 'chat,profile,report,directions,home,plan,schedule,academic,notes,intel,review,tools').split(',')
const widths = (process.env.C2_WIDTHS || '1440,390').split(',').map(Number)
mkdirSync(out, {recursive:true})
const browser = await chromium.launch()
try {
 for (const width of widths) {
  const page = await browser.newPage({viewport:{width,height:width<768?844:1000},reducedMotion:'reduce'})
  for (const route of routes) {
   for (const side of ['target','app']) {
    await page.goto(side==='target' ? `${reference.href}#/${route}` : `${base}/#/${route}?as=mid&data=demo`)
    await page.waitForSelector(side==='target'?`.main__scroll[data-view="${route}"][data-active="true"]`:'.ws-page, .dialogue-page')
    await page.waitForTimeout(600)
    await page.evaluate(()=>{
      window.scrollTo(0,0)
      document.querySelector('.app__main')?.scrollTo(0,0)
      document.querySelector('.ws-chat-flow')?.scrollTo(0,0)
      document.querySelector('.main__scroll[data-active="true"]')?.scrollTo(0,0)
    })
    await page.screenshot({path:join(out,`${side}-${route}-${width}.png`)})
   }
  }
  await page.close()
 }
 console.log(`Saved ${routes.length * widths.length} matched pairs in ${out}`)
} finally {await browser.close()}
