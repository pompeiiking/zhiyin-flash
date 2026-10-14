// EmptyState / SourceChip / SkeletonBlock 的向后兼容 + 新能力 + reduced-motion（对 isolated build 跑）
import { pathToFileURL } from 'node:url'
import { mkdirSync, writeFileSync } from 'node:fs'
const PW = process.env.PW_PATH || "C:/Users/y'm'y/AppData/Roaming/npm/node_modules/playwright"
const { chromium } = await import(pathToFileURL(`${PW}/index.mjs`).href)
const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:5281'
const OUT = '_shots/wave2-fixes'
mkdirSync(OUT, { recursive: true })

const OLD = ['chat', 'notes', 'intel', 'profile', 'report', 'academic', 'schedule', 'review', 'search-empty']
const NEW = ['plan', 'direction', 'notice', 'tools']
const SOURCES = ['resume', 'conversation', 'assessment', 'behavior_inference', 'mentor', 'record', 'user_edit']

const browser = await chromium.launch()
const out = {}

for (const [tag, opts] of [['normal', {}], ['reduced', { reducedMotion: 'reduce' }]]) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, ...opts })
  const page = await ctx.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  page.on('pageerror', (e) => errs.push('pageerror: ' + String(e.message).slice(0, 200)))
  await page.goto(`${BASE}/#/__compat`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)

  const data = await page.evaluate(({ OLD, NEW, SOURCES }) => {
    const emptyOf = (sel) => {
      const root = document.querySelector(sel)
      const es = root?.querySelector('.exp-empty')
      if (!es) return null
      const title = es.querySelector('.exp-empty__title')
      const next = es.querySelector('.exp-empty__next')
      const motif = es.querySelector('.exp-motif') ? 'canvas' : (es.querySelector('svg') ? 'workspace-motif' : 'none')
      return {
        cls: es.className,
        titleTag: title?.tagName ?? null,
        titleText: (title?.textContent ?? '').trim(),
        descText: (es.querySelector('.exp-empty__desc')?.textContent ?? '').trim(),
        motif,
        // 图形里的语义分支：数一下 <g> 下的直接子节点特征（用第一个 shape 的标签+属性粗略指纹）
        glyph: (es.querySelector('svg g')?.innerHTML ?? '').replace(/\s+/g, ' ').slice(0, 90),
        nextText: (next?.textContent ?? '').trim(),
        nextHasLink: !!next?.querySelector('a'),
        nextLinkTo: next?.querySelector('a')?.getAttribute('href') ?? null,
      }
    }
    const chipOf = (sel) => {
      const root = document.querySelector(sel)
      const c = root?.querySelector('.src')
      if (!c) return null
      return {
        cls: c.className,
        title: c.getAttribute('title'),
        label: (c.querySelector('.src__label')?.textContent ?? '').trim(),
        at: (c.querySelector('.src__at')?.textContent ?? '').trim(),
        glyph: (c.querySelector('.src__glyph')?.innerHTML ?? '').replace(/\s+/g, ' ').trim(),
        // 形态指纹：底色 / 边框样式 / 边框宽度 / 圆角
        bg: getComputedStyle(c).backgroundColor,
        borderStyle: getComputedStyle(c).borderTopStyle,
        borderLeftWidth: getComputedStyle(c).borderLeftWidth,
        radius: getComputedStyle(c).borderTopLeftRadius,
        color: getComputedStyle(c).color,
      }
    }
    const emptyResults = {}
    for (const k of [...OLD, ...NEW]) emptyResults[k] = emptyOf(`#es-${OLD.includes(k) ? 'old' : 'new'}-${k}`)
    const chipResults = {}
    for (const s of SOURCES) chipResults[s] = chipOf(`#sc-old-${s}`)
    chipResults.__labelOnly = chipOf('#sc-label-only')
    chipResults.__citation = chipOf('#sc-citation')
    chipResults.__transcript = chipOf('#sc-transcript')
    chipResults.__sourcePlusLabel = chipOf('#sc-source-plus-label')

    const skRoot = document.querySelector('#sk-default .sk')
    const skInlineSpan = document.querySelector('#sk-inline span.sk')
    const skInlineBtn = document.querySelector('#sk-in-button .sk')
    const skInButtonDefault = document.querySelector('#sk-in-button > .sk')
    return {
      emptyResults,
      chipResults,
      skeleton: {
        defaultTag: skRoot?.tagName ?? null,
        defaultCls: skRoot?.className ?? null,
        inlineSpanTag: skInlineSpan?.tagName ?? null,
        inlineSpanCls: skInlineSpan?.className ?? null,
        inlineSpanDisplay: skInlineSpan ? getComputedStyle(skInlineSpan).display : null,
        inlineButtonChildTag: skInButtonDefault?.tagName ?? null,
        // as="span" 在 button 里是否合法（button 的直接子元素只有 phrasing content 才合法）
        buttonChildren: [...(document.querySelector('#sk-in-button')?.children ?? [])].map((c) => c.tagName),
      },
      reducedMotion: {
        sweepAnimation: skRoot ? getComputedStyle(skRoot.querySelector('.sk__bar'), '::after').animationName : null,
      },
    }
  }, { OLD, NEW, SOURCES })

  out[tag] = { ...data, errors: errs }
  await page.screenshot({ path: `${OUT}/compat-${tag}.png`, fullPage: true })
  await ctx.close()
}

await browser.close()
writeFileSync(`${OUT}/compat-probe.json`, JSON.stringify(out, null, 2), 'utf8')

const n = out.normal
console.log('=== EmptyState 既有 9 档 ===')
for (const k of OLD) { const e = n.emptyResults[k]; console.log(`  ${k.padEnd(14)} ${e ? `${e.cls} | ${e.titleTag} | motif=${e.motif} | next=${JSON.stringify(e.nextText).slice(0, 46)} link=${e.nextHasLink}${e.nextLinkTo ? '(' + e.nextLinkTo + ')' : ''}` : 'MISSING'}`) }
console.log('=== EmptyState 新增 4 档 ===')
for (const k of NEW) { const e = n.emptyResults[k]; console.log(`  ${k.padEnd(14)} ${e ? `${e.cls} | ${e.titleTag} | motif=${e.motif} | next=${JSON.stringify(e.nextText).slice(0, 50)} link=${e.nextHasLink}${e.nextLinkTo ? '(' + e.nextLinkTo + ')' : ''}` : 'MISSING'}`) }
console.log('=== SourceChip 既有 7 值（形态指纹）===')
for (const s of SOURCES) { const c = n.chipResults[s]; console.log(`  ${s.padEnd(19)} ${c ? `${c.cls.padEnd(24)} label=${c.label.padEnd(7)} at=${c.at} bg=${c.bg} bs=${c.borderStyle} blw=${c.borderLeftWidth} r=${c.radius}` : 'MISSING'}`) }
console.log('=== SourceChip 新逃生口 ===')
for (const k of ['__labelOnly', '__citation', '__transcript', '__sourcePlusLabel']) { const c = n.chipResults[k]; console.log(`  ${k.padEnd(19)} ${c ? `${c.cls.padEnd(24)} label=${c.label.padEnd(12)} title=${JSON.stringify(c.title)} bg=${c.bg} r=${c.radius}` : 'MISSING'}`) }
console.log('=== SkeletonBlock 根标签 ===')
console.log('  ', JSON.stringify(n.skeleton, null, 2))
console.log('=== reduced-motion ===')
console.log('  normal sweep animation :', n.reducedMotion.sweepAnimation)
console.log('  reduced sweep animation:', out.reduced.reducedMotion.sweepAnimation)
console.log('  errors normal/reduced  :', n.errors.length, out.reduced.errors.length, n.errors, out.reduced.errors)
