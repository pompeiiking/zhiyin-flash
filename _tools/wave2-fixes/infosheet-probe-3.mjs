import { pathToFileURL } from 'node:url'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const browser = await chromium.launch()
const cases = [
  ['academic-verify-panel(shape=panel)', '#/academic?as=mid', 1280, 900, `[...document.querySelectorAll('button')].find(x=>/提供在线验证码/.test(x.textContent||''))`],
  ['chat-inspector-sheet(shape=sheet)', '#/chat?as=mid', 1280, 900, `document.querySelector('button[aria-label="个人画像"]')`],
  ['chat-inspector-sheet@390(shape=sheet)', '#/chat?as=mid', 390, 844, `document.querySelector('button[aria-label="个人画像"]')`],
  ['academic-verify-panel@390', '#/academic?as=mid', 390, 844, `[...document.querySelectorAll('button')].find(x=>/提供在线验证码/.test(x.textContent||''))`],
]
for (const [tag, hash, w, h, sel] of cases) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } })
  const page = await ctx.newPage()
  const errs = []
  page.on('console', m => { if (m.type()==='error') errs.push(m.text().slice(0,160)) })
  page.on('pageerror', e => errs.push('pageerror: '+String(e.message).slice(0,160)))
  await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  const clicked = await page.evaluate(new Function('return (()=>{const b='+sel+'; if(!b) return "NOT-FOUND"; b.click(); return (b.textContent||b.getAttribute("aria-label")||"").trim();})()'))
  await page.waitForTimeout(1000)
  const info = await page.evaluate(() => {
    const open=[...document.querySelectorAll('dialog.ws-sheet[open]')]
    return { openCount: open.length,
      wi: [...document.querySelectorAll('.ws-sheet--wide,.ws-sheet--inspector')].map(d=>d.className),
      sheets: open.map(d=>{const r=d.getBoundingClientRect(),cs=getComputedStyle(d)
        return {cls:d.className,title:d.getAttribute('aria-label'),box:`${Math.round(r.width)}x${Math.round(r.height)}`,x:Math.round(r.x),y:Math.round(r.y),radius:cs.borderTopLeftRadius,bottomGap:Math.round(innerHeight-r.bottom),vw:innerWidth}}) }
  })
  console.log(`--- ${tag}: clicked=${JSON.stringify(clicked)} err=${errs.length} wide/inspector=${JSON.stringify(info.wi)}`)
  for (const s of info.sheets) console.log(`    ${s.cls} | ${s.title} | ${s.box} @(${s.x},${s.y}) r=${s.radius} bottomGap=${s.bottomGap} vw=${s.vw}`)
  await page.screenshot({ path: `_shots/wave2-fixes/infosheet-${tag.replace(/[^\w.-]/g,'_')}.png` })
  await ctx.close()
}
await browser.close()
