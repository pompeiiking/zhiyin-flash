// 补测 InfoSheet 剩下两个调用点 + chat 的 sheet 形态（临时工具）
import { pathToFileURL } from 'node:url'
import { mkdirSync, writeFileSync } from 'node:fs'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const results = {}

async function probe(tag, hash, width, height, finderSource) {
  const ctx = await browser.newContext({ viewport: { width, height } })
  const page = await ctx.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 200)))
  await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1400)
  // 列出所有候选按钮，方便挑
  const candidates = await page.evaluate(() =>
    [...document.querySelectorAll('button, a')]
      .filter((b) => (b.textContent || '').trim() && b.getClientRects().length)
      .map((b, i) => `${i}:${b.tagName}.${typeof b.className === 'string' ? b.className.slice(0, 30) : ''}«${(b.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24)}»`)
      .slice(0, 60))
  const clicked = await page.evaluate(new Function('return (' + finderSource + ')()'))
  await page.waitForTimeout(1000)
  const info = await page.evaluate(() => {
    const open = [...document.querySelectorAll('dialog.ws-sheet[open]')]
    const wi = [...document.querySelectorAll('.ws-sheet--wide, .ws-sheet--inspector')].map((d) => d.className)
    return {
      openCount: open.length,
      wi,
      sheets: open.map((d) => {
        const r = d.getBoundingClientRect(); const cs = getComputedStyle(d)
        return { cls: d.className, title: d.getAttribute('aria-label'), box: `${Math.round(r.width)}x${Math.round(r.height)}`, x: Math.round(r.x), y: Math.round(r.y), pos: cs.position, radius: cs.borderTopLeftRadius, bottomGap: Math.round(innerHeight - r.bottom) }
      }),
    }
  })
  results[tag] = { clicked, ...info, candidates, errors: errs }
  await page.screenshot({ path: `${OUT}/infosheet-${tag}.png` })
  await ctx.close()
}

// 核对学籍：找 aria/label 里带"核对学籍"
await probe('academic-verify-panel', '#/academic?as=mid', 1280, 900, `
  () => {
    const b = [...document.querySelectorAll('button')].find(x => /核对学籍/.test(x.textContent||''))
    if (!b) return 'no-button: 核对学籍'
    b.click(); return (b.textContent||'').trim().slice(0,24)
  }`)
// 资讯详情：点资讯卡标题
await probe('intel-detail-sheet', '#/intel?as=mid', 1280, 900, `
  () => {
    const b = document.querySelector('.intel-title') || [...document.querySelectorAll('button')].find(x => /详情/.test(x.textContent||''))
    if (!b) return 'no-intel-title'
    b.click(); return (b.textContent||'').trim().slice(0,24)
  }`)
// chat 检查器：先滚到侧栏再点
await probe('conversation-inspector-sheet', '#/chat?as=mid', 1280, 900, `
  () => {
    const b = [...document.querySelectorAll('button')].find(x => /^(个人画像|历史对话|咨询成果)$/.test((x.textContent||'').trim()))
    if (!b) return 'no-inspector-tab'
    b.click(); return (b.textContent||'').trim()
  }`)
// chat 方法依据弹层（第二个 InfoSheet，无 shape → dialog）
await probe('conversation-theory-dialog', '#/chat?as=mid', 1280, 900, `
  () => {
    const b = [...document.querySelectorAll('button')].find(x => /方法|理论/.test(x.textContent||''))
    if (!b) return 'no-theory-button'
    b.click(); return (b.textContent||'').trim().slice(0,24)
  }`)

await browser.close()
writeFileSync(`${OUT}/infosheet-probe-2.json`, JSON.stringify(results, null, 2), 'utf8')
for (const [k, v] of Object.entries(results)) {
  console.log(`--- ${k} clicked=${JSON.stringify(v.clicked)} errors=${v.errors.length} wide/inspector=${JSON.stringify(v.wi)}`)
  for (const s of v.sheets) console.log(`    ${s.cls} | ${s.title} | ${s.box} @(${s.x},${s.y}) pos=${s.pos} r=${s.radius} bottomGap=${s.bottomGap}`)
  if (!v.openCount) console.log('    candidates:', v.candidates.slice(0, 18).join('  '))
}
