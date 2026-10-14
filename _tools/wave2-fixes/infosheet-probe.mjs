// InfoSheet 删 prop 后：5 个调用点的 shape 仍生效（DOM 类名 + 计算几何），且零 --wide/--inspector
import { pathToFileURL } from 'node:url'
import { mkdirSync, writeFileSync } from 'node:fs'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const results = {}

async function openSheet({ tag, hash, width = 1280, height = 900, click }) {
  const ctx = await browser.newContext({ viewport: { width, height } })
  const page = await ctx.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 200)))
  await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1300)
  const clicked = await page.evaluate(click)
  await page.waitForTimeout(900)
  const info = await page.evaluate(() => {
    const open = [...document.querySelectorAll('dialog.ws-sheet[open]')]
    const anyWideInspector = [...document.querySelectorAll('.ws-sheet--wide, .ws-sheet--inspector')]
      .map((d) => d.className)
    return {
      openCount: open.length,
      sheets: open.map((d) => {
        const r = d.getBoundingClientRect()
        const cs = getComputedStyle(d)
        return {
          cls: d.className,
          title: d.getAttribute('aria-label'),
          box: `${Math.round(r.width)}x${Math.round(r.height)}`,
          x: Math.round(r.x),
          y: Math.round(r.y),
          position: cs.position,
          width: cs.width,
          radius: cs.borderTopLeftRadius,
          bottom: Math.round(innerHeight - r.bottom),
          vw: innerWidth,
        }
      }),
      anyWideInspector,
      allSheetClasses: [...document.querySelectorAll('dialog.ws-sheet')].map((d) => d.className),
    }
  })
  results[tag] = { clicked, ...info, errors: errs }
  await page.screenshot({ path: `${OUT}/infosheet-${tag}-${width}.png` })
  await ctx.close()
}

// 1 AcademicView: 导入课表与成绩 → panel（宽表单）
await openSheet({
  tag: 'academic-import-panel',
  hash: '#/academic?as=mid',
  click: () => {
    const b = [...document.querySelectorAll('button')].find((x) => /导入|课表/.test(x.textContent || ''))
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 20)
  },
})
// 2 AcademicView: 核对学籍 → panel
await openSheet({
  tag: 'academic-verify-panel',
  hash: '#/academic?as=mid',
  click: () => {
    const b = [...document.querySelectorAll('button')].find((x) => /核对学籍|学籍/.test(x.textContent || ''))
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 20)
  },
})
// 3 IntelView: 资讯详情 → sheet
await openSheet({
  tag: 'intel-detail-sheet',
  hash: '#/intel?as=mid',
  click: () => {
    const b = [...document.querySelectorAll('button')].find((x) => /详情|查看|打开|标题/.test(x.textContent || ''))
      ?? document.querySelector('.intel-title')
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 24)
  },
})
// 4 ProfileInsights（在 /profile 或 /chat 的弹层里）
await openSheet({
  tag: 'profile-insights-sheet',
  hash: '#/profile?as=mid',
  click: () => {
    const b = [...document.querySelectorAll('button')]
      .find((x) => /画像|深入了解|补充/.test(x.textContent || ''))
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 24)
  },
})
// 5 ConversationView: 右侧检查器 → sheet（panel !== null）
await openSheet({
  tag: 'conversation-inspector-sheet',
  hash: '#/chat?as=mid',
  click: () => {
    const b = [...document.querySelectorAll('button, a')]
      .find((x) => /个人画像|历史对话|咨询成果|检查器/.test(x.textContent || ''))
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 24)
  },
})
// 5b 同样一个检查器在 390 下应是底部面板
await openSheet({
  tag: 'conversation-inspector-sheet-mobile',
  hash: '#/chat?as=mid',
  width: 390,
  height: 844,
  click: () => {
    const b = [...document.querySelectorAll('button, a')]
      .find((x) => /个人画像|历史对话|咨询成果/.test(x.textContent || ''))
    if (!b) return 'no-button'
    b.click()
    return (b.textContent || '').trim().slice(0, 24)
  },
})

await browser.close()
writeFileSync(`${OUT}/infosheet-probe.json`, JSON.stringify(results, null, 2), 'utf8')
for (const [k, v] of Object.entries(results)) {
  console.log(`--- ${k}  clicked=${JSON.stringify(v.clicked)} errors=${v.errors.length}`)
  console.log(`    wide/inspector classes: ${JSON.stringify(v.anyWideInspector)}`)
  for (const s of v.sheets) console.log(`    open: ${s.cls} | ${s.title} | ${s.box} @(${s.x},${s.y}) pos=${s.position} r=${s.radius} bottomGap=${s.bottom}`)
}
