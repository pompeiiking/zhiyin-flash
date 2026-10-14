// 临时验证脚本（不属于交付物；放在 _tools/infra-c/ 下，验证完保留作证据）
// 用法：PW_PATH=<playwright 包目录> node _tools/infra-c/verify.mjs
//
// 做四件事：
//   1. 打 3 张 spike 截图（浅色蓝 / 浅色红 / 深色）到 _shots/infra-c/
//   2. DOM 几何实测：刻度签 0/中点/1 的中心，是否与网格线、条起点重合（同刻度）
//   3. 对比度实测：从**计算样式**取真实前景/背景色，算 WCAG 比值
//   4. null / undefined 的渲染断言
import { mkdirSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const { chromium } = await import(pathToFileURL(`${process.env.PW_PATH}/index.mjs`).href)

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5180'
const PAGE = `${BASE}/__infra-c-spike.html`
const OUT = '_shots/infra-c'
mkdirSync(OUT, { recursive: true })

const log = []
const say = (s) => {
  log.push(s)
  console.log(s)
}

// ---------- WCAG 相对亮度与对比度 ----------
function srgb(c) {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}
function lum([r, g, b]) {
  return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)
}
function ratio(a, b) {
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}
function parse(css) {
  const m = /rgba?\(([^)]+)\)/.exec(css)
  if (!m) return null
  const p = m[1].split(/[,/]/).map((s) => parseFloat(s.trim()))
  return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }
}
/** 把可能带 alpha 的前景合成到背景上（浏览器实际就是这么画的） */
function flatten(fg, bg) {
  return fg.rgb.map((v, i) => Math.round(v * fg.a + bg[i] * (1 - fg.a)))
}

const browser = await chromium.launch()

// =============================================================================
// 1 + 2 + 4：浅色蓝主题
// =============================================================================
const ctx = await browser.newContext({ viewport: { width: 900, height: 1200 }, deviceScaleFactor: 2 })
const page = await ctx.newPage()
const consoleMsgs = []
page.on('console', (m) => consoleMsgs.push(`${m.type()}: ${m.text()}`))

await page.goto(PAGE, { waitUntil: 'networkidle' })
await page.waitForTimeout(700)
await page.screenshot({ path: `${OUT}/spike-light-blue.png`, fullPage: true })
say(`[shot] ${OUT}/spike-light-blue.png`)

// ---------- 2. 同刻度对齐实测 ----------
const align = await page.evaluate(() => {
  // 取第一行（呈现能力 0.46 / 要求 0.50 / 轴 0-25-50-75-100）
  const target = document.querySelector('.mtr')
  const ruler = target.querySelector('.mtr__ruler').getBoundingClientRect()
  const bar = target.querySelector('.mtr__fill').getBoundingClientRect()
  const track = target.querySelector('.mtr__track').getBoundingClientRect()
  const grids = [...target.querySelectorAll('.mtr__grid')].map((g) => {
    const r = g.getBoundingClientRect()
    return r.left + r.width / 2 - ruler.left
  })
  const ticks = [...target.querySelectorAll('.mtr__tick')].map((t) => {
    const mark = t.querySelector('.mtr__tick-mark').getBoundingClientRect()
    const text = t.querySelector('.mtr__tick-text').getBoundingClientRect()
    return {
      text: t.textContent.trim(),
      markCenter: mark.left + mark.width / 2 - ruler.left,
      textCenter: text.left + text.width / 2 - ruler.left,
    }
  })
  const gap = target.querySelector('.mtr__gap')?.getBoundingClientRect()
  const mark = target.querySelector('.mtr__mark')
  const markX = mark ? mark.getBoundingClientRect().left - ruler.left : null
  return {
    rulerW: ruler.width,
    trackW: track.width,
    barLeft: bar.left - ruler.left,
    barW: bar.width,
    gapLeft: gap ? gap.left - ruler.left : null,
    gapW: gap ? gap.width : null,
    grids,
    ticks,
    markX,
    legend: [...target.querySelectorAll('.mtr__legend-item')].map((e) => e.textContent.trim().replace(/\s+/g, ' ')),
  }
})
say('')
say('== 同刻度对齐（浅色蓝，第一行 呈现能力 0.46 / 要求 0.50 / 轴 0-25-50-75-100）==')
say(`  ruler 宽 ${align.rulerW.toFixed(2)} / track 宽 ${align.trackW.toFixed(2)}（应相等，说明尺子=轨道）`)
say(`  网格线 x（相对 ruler）：${align.grids.map((g) => g.toFixed(2)).join(', ')}`)
say(
  `  刻度线中心 x：${align.ticks
    .map((t) => `${t.text}@${t.markCenter.toFixed(2)}`)
    .join(', ')}`,
)
say(`  条起点 x = ${align.barLeft.toFixed(2)}（含 1px 内缩，应 = 1.00）`)
say(`  条宽 = ${align.barW.toFixed(2)}（应 ≈ ruler*0.46 = ${(align.rulerW * 0.46).toFixed(2)}，差 1px 内缩）`)
say(`  差距带 x=${align.gapLeft?.toFixed(2)} 宽=${align.gapW?.toFixed(2)}（应落在 0.46→0.50 之间 = ruler*0.04 = ${(align.rulerW * 0.04).toFixed(2)}）`)
say(`  要求线 x = ${align.markX == null ? 'n/a' : align.markX.toFixed(2)}（应 ≈ ${(align.rulerW * 0.5).toFixed(2)}）`)
say(`  图例文字：${align.legend.join(' | ')}`)

// ---------- 4. null / undefined 断言 ----------
const empty = await page.evaluate(() => {
  const out = {}
  // MeterRow value=null
  const m = [...document.querySelectorAll('.mtr')].find((el) =>
    el.querySelector('.mtr__value')?.textContent.trim() === '暂无依据',
  )
  out.meterNull = m
    ? {
        valueText: m.querySelector('.mtr__value').textContent.trim(),
        hasFill: !!m.querySelector('.mtr__fill'),
        hasDashedTrack: getComputedStyle(m.querySelector('.mtr__track')).borderStyle,
        barWidth: null,
        aria: m.getAttribute('aria-label'),
        isClassEmpty: m.classList.contains('mtr--empty'),
      }
    : null
  // ConfidenceBadge confidence=undefined → 虚线方框 + "还没有依据"
  const unknown = [...document.querySelectorAll('.cf')].find((el) => el.classList.contains('cf--unknown'))
  out.confUnknown = unknown
    ? {
        label: unknown.querySelector('.cf__label').textContent.trim(),
        barCount: unknown.querySelectorAll('.cf__bar').length,
        barBorder: getComputedStyle(unknown.querySelector('.cf__bar')).borderStyle,
        hint: unknown.querySelector('.cf__none')?.textContent.trim(),
      }
    : null
  // 很低那枚（0.2）用于对照
  const low = [...document.querySelectorAll('.cf--low')][0]
  out.confLow = low
    ? { label: low.querySelector('.cf__label').textContent.trim(), barCount: low.querySelectorAll('.cf__bar').length }
    : null
  // StatTile score=null
  const tile = [...document.querySelectorAll('.tile')].find((el) => el.classList.contains('tile--empty'))
  out.tileNull = tile
    ? {
        value: tile.querySelector('.tile__value').textContent.trim(),
        hasTrack: !!tile.querySelector('.tile__track'),
        aria: tile.getAttribute('aria-label'),
      }
    : null
  return out
})
say('')
say('== null / undefined 的渲染 ==')
say(`  MeterRow value=null → ${JSON.stringify(empty.meterNull)}`)
say(`  ConfidenceBadge confidence=undefined → ${JSON.stringify(empty.confUnknown)}`)
say(`  ConfidenceBadge confidence=0.2（很低，作对照）→ ${JSON.stringify(empty.confLow)}`)
say(`  StatTile score=null → ${JSON.stringify(empty.tileNull)}`)

// ---------- 3. 对比度实测（从计算样式取真实颜色） ----------
const contrast = await page.evaluate(() => {
  const sample = (el, fgProp = 'color') => {
    if (!el) return null
    const cs = getComputedStyle(el)
    // 逐级向上找第一个不透明背景
    let node = el
    let bg = 'rgba(0, 0, 0, 0)'
    while (node && /rgba\(0, 0, 0, 0\)|transparent/.test(bg)) {
      bg = getComputedStyle(node).backgroundColor
      node = node.parentElement
    }
    return {
      fg: cs[fgProp],
      bg,
      weight: cs.fontWeight,
      size: cs.fontSize,
      text: (el.textContent || '').trim().slice(0, 20),
      border: cs.borderTopColor,
      borderStyle: cs.borderTopStyle,
    }
  }
  const out = {}
  out.chip = {}
  for (const s of ['verified', 'stated', 'measured', 'inferred', 'attested', 'ledger', 'edited']) {
    const el = document.querySelector(`.src--${s}`)
    if (el) out.chip[s] = { chip: sample(el), label: sample(el.querySelector('.src__label')), at: sample(el.querySelector('.src__at')) }
  }
  out.conf = {}
  for (const s of ['unknown', 'low', 'mid', 'high']) {
    const el = document.querySelector(`.cf--${s}`)
    if (el) out.conf[s] = sample(el.querySelector('.cf__label'))
  }
  const tile = document.querySelector('.tile')
  out.tile = { label: sample(tile?.querySelector('.tile__label')), value: sample(tile?.querySelector('.tile__value')), state: sample(tile?.querySelector('.tile__state')) }
  const att = [...document.querySelectorAll('.tile')].find((t) => t.querySelector('.tile__state--attention'))
  out.tileAttention = att ? sample(att.querySelector('.tile__state')) : null
  const meter = document.querySelector('.mtr')
  out.meter = {
    name: sample(meter?.querySelector('.mtr__name')),
    value: sample(meter?.querySelector('.mtr__value')),
    legend: sample(meter?.querySelector('.mtr__legend-item')),
    tick: sample(meter?.querySelector('.mtr__tick-text')),
  }
  const emptyMeter = document.querySelector('.mtr--empty')
  out.meterEmptyValue = emptyMeter ? sample(emptyMeter.querySelector('.mtr__value')) : null
  return out
})

say('')
say('== 对比度实测（浅色蓝；fg/bg 均取自 getComputedStyle）==')
const report = (name, s) => {
  if (!s) return say(`  ${name.padEnd(30)} n/a`)
  const f = parse(s.fg)
  const b = parse(s.bg)
  const fg = flatten(f, b.rgb)
  const r = ratio(fg, b.rgb)
  const hex = (x) => '#' + x.map((v) => v.toString(16).padStart(2, '0')).join('')
  say(
    `  ${name.padEnd(30)} ${hex(fg)} on ${hex(b.rgb)} = ${r.toFixed(2)}:1  ${r >= 4.5 ? 'PASS' : 'FAIL'}  (${s.size}/${s.weight} "${s.text}")`,
  )
  return r
}
for (const [k, v] of Object.entries(contrast.chip)) {
  report(`SourceChip.${k}.label`, v.label)
}
for (const [k, v] of Object.entries(contrast.conf)) report(`ConfidenceBadge.${k}`, v)
report('StatTile.label', contrast.tile.label)
report('StatTile.value', contrast.tile.value)
report('StatTile.state(默认)', contrast.tile.state)
report('StatTile.state(attention)', contrast.tileAttention)
report('MeterRow.name', contrast.meter.name)
report('MeterRow.value', contrast.meter.value)
report('MeterRow.legend', contrast.meter.legend)
report('MeterRow.tick', contrast.meter.tick)
report('MeterRow.value(缺依据)', contrast.meterEmptyValue)

say('')
say(`== 控制台输出（量纲守卫）==`)
consoleMsgs.filter((m) => /MeterRow|StatTile|ConfidenceBadge/.test(m)).forEach((m) => say(`  ${m}`))

// =============================================================================
// 5：红主色 + 深色 两张截图
// =============================================================================
for (const [name, qs] of [
  ['spike-light-red', '?accent=red'],
  ['spike-dark-blue', '?theme=dark'],
  ['spike-dark-red', '?theme=dark&accent=red'],
]) {
  await page.goto(`${PAGE}${qs}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  say(`[shot] ${OUT}/${name}.png`)
}

// 深色下的对比度复核
await page.goto(`${PAGE}?theme=dark`, { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
const darkContrast = await page.evaluate(() => {
  const sample = (el) => {
    if (!el) return null
    const cs = getComputedStyle(el)
    let node = el
    let bg = 'rgba(0, 0, 0, 0)'
    while (node && /rgba\(0, 0, 0, 0\)|transparent/.test(bg)) {
      bg = getComputedStyle(node).backgroundColor
      node = node.parentElement
    }
    return { fg: cs.color, bg, size: cs.fontSize, weight: cs.fontWeight, text: (el.textContent || '').trim().slice(0, 16) }
  }
  return {
    chipVerified: sample(document.querySelector('.src--verified .src__label')),
    chipInferred: sample(document.querySelector('.src--inferred .src__label')),
    chipMeasured: sample(document.querySelector('.src--measured .src__label')),
    confHigh: sample(document.querySelector('.cf--high .cf__label')),
    confUnknown: sample(document.querySelector('.cf--unknown .cf__label')),
    tileValue: sample(document.querySelector('.tile__value')),
    meterName: sample(document.querySelector('.mtr__name')),
  }
})
say('')
say('== 对比度实测（深色主题，复核用）==')
for (const [k, v] of Object.entries(darkContrast)) report(`dark ${k}`, v)

// =============================================================================
// 几何复核：跨主题确认条与刻度依旧同源
// =============================================================================
say('')
say('== 结论 ==')
say(`  条起点 x = ${align.barLeft.toFixed(2)}px（= 1px 内缩，即条从 0 刻度起画）`)
say(`  条宽误差 = ${(align.barW - align.rulerW * 0.46).toFixed(2)}px（目标 0）`)
const tickDev = align.ticks.map((t, i) => Math.abs(t.markCenter - align.grids[i]))
say(`  刻度线中心 vs 网格线，逐档偏差 = ${tickDev.map((d) => d.toFixed(2)).join(', ')}px（全部 ≤0.5 = 同源）`)
say(`  最大偏差 = ${Math.max(...tickDev).toFixed(2)}px`)
// reduced-motion 降级复核
const rmCtx = await browser.newContext({ viewport: { width: 900, height: 1200 }, reducedMotion: 'reduce' })
const rmPage = await rmCtx.newPage()
await rmPage.goto(PAGE, { waitUntil: 'networkidle' })
await rmPage.waitForTimeout(500)
const rm = await rmPage.evaluate(() => {
  const m = document.querySelector('.mtr')
  const f = m.querySelector('.mtr__fill')
  const cs = getComputedStyle(f)
  return {
    fillTransition: cs.transitionDuration,
    fillWidthPct: f.style.width,
    renderedW: f.getBoundingClientRect().width,
    rulerW: m.querySelector('.mtr__ruler').getBoundingClientRect().width,
  }
})
say('')
say('== prefers-reduced-motion: reduce 降级复核 ==')
say(`  条 transition-duration = ${rm.fillTransition}（应 0s）`)
say(`  条仍按数值落位：width=${rm.fillWidthPct} 实测 ${rm.renderedW.toFixed(2)}px / ruler ${rm.rulerW.toFixed(2)}px（比值应 = 0.46）`)
say(`  实测比值 = ${(rm.renderedW / rm.rulerW).toFixed(3)}`)
await rmCtx.close()

// 390px 窄屏形态（确认徽标不撑破行、刻度签不溢出尺子）
const mCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
const mPage = await mCtx.newPage()
await mPage.goto(PAGE, { waitUntil: 'networkidle' })
await mPage.waitForTimeout(600)
await mPage.screenshot({ path: `${OUT}/spike-390.png`, fullPage: true })
const narrow = await mPage.evaluate(() => {
  const doc = document.documentElement
  const tickOut = []
  for (const m of document.querySelectorAll('.mtr')) {
    const r = m.querySelector('.mtr__ruler').getBoundingClientRect()
    for (const t of m.querySelectorAll('.mtr__tick-text')) {
      const tr = t.getBoundingClientRect()
      if (tr.left < r.left - 0.6 || tr.right > r.right + 0.6) {
        tickOut.push({ text: t.textContent.trim(), overLeft: +(r.left - tr.left).toFixed(1), overRight: +(tr.right - r.right).toFixed(1) })
      }
    }
  }
  const chipOverflow = [...document.querySelectorAll('.src')].filter((c) => c.getBoundingClientRect().right > doc.clientWidth)
  return { scrollW: doc.scrollWidth, clientW: doc.clientWidth, tickOut, chipOverflowCount: chipOverflow.length }
})
say('')
say('== 390px 窄屏 ==')
say(`  [shot] ${OUT}/spike-390.png`)
say(`  横向溢出：scrollWidth ${narrow.scrollW} vs clientWidth ${narrow.clientW}（应相等）`)
say(`  刻度签溢出尺子两端的实例：${narrow.tickOut.length} 个 ${narrow.tickOut.length ? JSON.stringify(narrow.tickOut.slice(0, 4)) : '（0 = 全部在尺内，轴也同刻度）'}`)
say(`  SourceChip 越出视口的实例：${narrow.chipOverflowCount} 个`)
await mCtx.close()

writeFileSync(`${OUT}/verify.log`, log.join('\n'), 'utf8')
await browser.close()
console.log(`\n[log] ${OUT}/verify.log`)
