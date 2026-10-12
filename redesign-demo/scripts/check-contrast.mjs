#!/usr/bin/env node
/**
 * 对比度校验 —— 浅色与深色各跑一遍。
 *
 * 设计规范页（/spec）把"正文与当文字用的令牌对纸面 ≥ 4.5:1"写成了硬约束，
 * 这个脚本是那条约束的执行者：色值直接从 src/styles/tokens.css 里读。
 *
 * 为什么要分主题跑：深色不是浅色的反相。同一支"说明文字"令牌在浅色下过线、
 * 在深色下经常掉到 4:1 —— 只跑一遍浅色，深色上线才发现，那时已经晚了。
 *
 * 用法：node scripts/check-contrast.mjs
 * 退出码 0 = 全部过线；1 = 有必过项破线（CI 可以直接拿它当门禁）。
 */

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const TOKENS = resolve(__dirname, '..', 'src', 'styles', 'tokens.css')
const css = readFileSync(TOKENS, 'utf8')

/** 抓出某个选择器的声明块（第一个匹配） */
function block(selector) {
  const i = css.indexOf(selector)
  if (i < 0) throw new Error(`tokens.css 里找不到选择器：${selector}`)
  const start = css.indexOf('{', i)
  const end = css.indexOf('\n}', start)
  return css.slice(start + 1, end < 0 ? css.length : end)
}

/** 把声明块解析成 { 令牌名: 值 } */
function parse(decls) {
  const out = {}
  for (const line of decls.split('\n')) {
    const m = line.match(/^\s*--([a-z0-9-]+)\s*:\s*([^;]+);/i)
    if (m) out[m[1]] = m[2].trim()
  }
  return out
}

const root = parse(block(':root {'))
const dark = parse(block("html[data-theme='dark'] {"))
const accentRed = parse(block("html[data-accent='red'] {"))
/**
 * 深色 + 红主色必须单独取这一块。
 * 它比 `html[data-accent='red']` 特异度更高（多一个属性选择器），所以真正生效的是它 ——
 * 校验脚本如果按"声明顺序"去合并，会漏掉这一块，把链接色当成 #96000E 报一个假失败。
 * （第一次就是这么报的，查下去才发现是脚本错了，不是 CSS 错了。）
 */
const darkRed = parse(block("html[data-theme='dark'][data-accent='red']"))

/** 在一个主题上下文里解析令牌：先看该主题的覆盖，再回落到 :root */
function resolveIn(ctx, name, depth = 0) {
  if (depth > 12) throw new Error(`令牌解析层数过深：--${name}`)
  const raw = ctx[name] ?? root[name]
  if (raw == null) throw new Error(`找不到令牌 --${name}`)
  const v = raw.match(/^var\(\s*--([a-z0-9-]+)\s*\)$/i)
  return v ? resolveIn(ctx, v[1], depth + 1) : raw
}

function isHex(v) {
  return /^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(v.trim())
}

function parseHex(hex) {
  const h = hex.replace('#', '').trim()
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16))
}

function luminance(hex) {
  const [r, g, b] = parseHex(hex).map((c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a, b) {
  const la = luminance(a)
  const lb = luminance(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

const MIN = 4.5

/**
 * must = true：硬线，破线即失败
 * must = false：只允许当图形/描边，破线只提示不拦
 */
const CHECKS = [
  { fg: 'c-text', bg: 'c-surface', must: true, note: '正文' },
  { fg: 'c-text', bg: 'c-bg', must: true, note: '正文压页面底' },
  { fg: 'c-text-2', bg: 'c-surface', must: true, note: '次要文字' },
  { fg: 'c-text-2', bg: 'c-bg', must: true, note: '次要文字压页面底' },
  { fg: 'c-text-3', bg: 'c-surface', must: true, note: '说明文字' },
  { fg: 'c-text-3', bg: 'c-bg', must: true, note: '说明文字压页面底' },
  { fg: 'c-on-primary', bg: 'c-primary', must: true, note: '主按钮字色' },
  { fg: 'c-primary', bg: 'c-surface', must: true, note: '链接 / 选中态' },
  { fg: 'c-primary', bg: 'c-bg', must: true, note: '链接压页面底' },
  { fg: 'c-primary', bg: 'c-primary-weak', must: true, note: '主色压在自身浅底上（标签）' },
  { fg: 'c-attention-strong', bg: 'c-attention-weak', must: true, note: '注意标签字色' },
  { fg: 'c-attention', bg: 'c-surface', must: true, note: '注意色当文字' },
  { fg: 'c-done', bg: 'c-done-weak', must: true, note: '已完成标签' },
  { fg: 'c-text-3', bg: 'c-surface-2', must: true, note: '说明文字压次级底' },
  { fg: 'field-placeholder', bg: 'c-surface', must: true, note: '输入框占位符' },
  /* 焦点环是 UI 组件级要求（≥3:1），但破 3:1 就等于键盘用户看不见焦点，所以按 4.5 守 */
  { fg: 'c-focus', bg: 'c-surface', must: true, note: '焦点环压在卡片上' },
  { fg: 'c-focus', bg: 'c-bg', must: true, note: '焦点环压在页面底上' },
  /* 校徽蓝对白底 9.18:1 —— 它既是品牌色也是主色，所以这条从"仅图形"升成硬线 */
  { fg: 'blue-500', bg: 'gray-0', must: true, note: '主色 · 河大校徽蓝（也当文字用）' },
]

/* ===========================================================================
 * 令牌用途登记 —— 这一版门禁的核心改动
 * ---------------------------------------------------------------------------
 * 以前这份脚本只按**令牌名**猜用途：带 text / primary / attention 的才查。
 * 于是 --c-text-4 这种"名字看着就是文字"的令牌反而漏在检查之外 ——
 * 它的注释明明写着"只给图标／分隔符"，我却拿它排了 11px 的中文与页脚链接，
 * 对纸面只有 2.36:1，而门禁一声不响。错在"猜"，不在色值。
 *
 * 现在用途由下面两张表**显式登记**，并做两件机械检查：
 *   1. 登记为"承载文字"的令牌，必须在 CHECKS 里有 must:true 的条目（漏登记 = 失败）
 *   2. 登记为"仅装饰"的令牌，不许出现在任何 color: 上（白名单选择器除外）
 * 加一个新令牌时，你**必须**回答"它承不承载文字" —— 这正是以前漏掉的那一问。
 * ======================================================================== */

/** 允许承载文字的令牌。 */
const TEXT_TOKENS = [
  'c-text',
  'c-text-2',
  'c-text-3',
  'c-on-primary',
  'c-primary',
  'c-attention',
  'c-attention-strong',
  'c-done',
  'c-focus',
  'field-placeholder',
]

/** 只许当图形／描边／圆点，不许承载文字。 */
const DECORATIVE_ONLY = ['c-text-4']

/* ===========================================================================
 * 字号令牌登记 —— 与"令牌用途登记"同一件事，管的是另一半
 * ---------------------------------------------------------------------------
 * 上面那张表管的是"这支令牌是什么颜色、能不能压这个底"。它管不了字号，
 * 于是字号可以随便加：加一档没人拦，写了一个用不上的档也没人知道。
 * 版面改造新增 --fs-26 时正是这个处境 —— 加进去，门禁一声不响。
 *
 * 这里把每一档**字号**也登记成"用途 + 实际用在哪"，并做两件机械检查：
 *   1. tokens.css 里有、这张表里没有的 --fs-*  → 失败（谁加的谁登记）
 *   2. 这张表里登记了、但界面源文件里一次都没用的 → 失败（死档要删，不是留着好看）
 *
 * 另一条纪律写在注释里、由截图守着，脚本判不了：**一屏只出现一个 --fs-30**
 * （页标题一档）。
 *
 * 2026-10-11 收敛：原来 12 档里 11–16 六档全挤在 6px 之内（相邻只差 1px），
 * 一屏能数出 7–9 个字号 —— 那正是客户说的"不够清晰、乱糟糟"。
 * 现在只剩五档（12 / 14 / 20 / 30 / 38），**相邻档差 ≥6px**，每档只承担一件事。
 * 这张表就是那次收敛的守卫：谁想再加一档，必须在这里回答"它给谁用"。
 * ======================================================================== */

const FONT_SIZE_USES = [
  { tok: '16', use: '学生空间正文与对话，中文长句的阅读基准', where: 'workspace.css 的工作空间正文、对话与任务条目' },
  { tok: '12', use: '说明、注解、表头、标签、序号、行副标题（.t-note / .t-label / .chip）', where: 'base.css 的 .t-label / .t-note / .chip / .table th / .row__sub / .field__hint；各页的说明行' },
  { tok: '14', use: '正文基准（body / .t-body / .t-sm）、卡片标题、条目行、密集正文', where: 'base.css 的 body / .t-body / .t-sm / .card__title / .page__sub；各页的条目行' },
  { tok: '20', use: '块标题与节标题：.block__title / .rail-index__title / .focal .card__title / .t-h1~.t-h3 / .empty__title', where: 'base.css 的 .block__title / .rail-index__title / .focal .card__title / .t-h1 / .t-h2 / .t-h3 / .empty__title' },
  { tok: '30', use: '页标题（.page__title）—— **一屏只许一个**', where: 'base.css 的 .page__title' },
  { tok: '38', use: '展示字号：门户主张、报告关键差距', where: 'base.css 的 .t-display；PortalView；workspace.css 的 .ws-report-score' },
]

/** 抓出界面源文件里实际用到的字号令牌 */
function usedFontSizes() {
  const base = resolve(__dirname, '..')
  const used = new Set()
  for (const f of walk(resolve(base, 'src'))) {
    const text = readFileSync(f, 'utf8')
    for (const m of text.matchAll(/var\(\s*--fs-([0-9]+)\s*\)/g)) used.add(m[1])
  }
  return used
}

const fsDeclared = [...css.matchAll(/^\s*--fs-([0-9]+)\s*:/gm)].map((m) => m[1])
const fsRegistered = FONT_SIZE_USES.map((f) => f.tok)
const fsUnregistered = fsDeclared.filter((t) => !fsRegistered.includes(t))
const fsUnused = fsRegistered.filter((t) => !usedFontSizes().has(t))
const fsGhost = fsRegistered.filter((t) => !fsDeclared.includes(t))

/**
 * 装饰令牌允许用 color: 的选择器 —— 用字符画的圆点属于装饰，不是文字。
 * 这张白名单要短：每加一条，都得有人负责解释"它为什么不是文字"。
 */
const DECORATIVE_ALLOWED = [/\.dot\b/]

function walk(dir) {
  const out = []
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p))
    else if (/\.(vue|css)$/.test(e.name)) out.push(p)
  }
  return out
}

/** 找出"装饰令牌被当文字色用"的地方。tokens.css 是定义处，跳过。 */
function decorativeMisuse() {
  const base = resolve(__dirname, '..')
  const bad = []
  for (const f of walk(resolve(base, 'src'))) {
    if (f.endsWith('tokens.css')) continue
    const rel = f.slice(base.length + 1)
    const lines = readFileSync(f, 'utf8').split('\n')
    let selector = ''
    lines.forEach((raw, i) => {
      const line = raw.trim()
      const opened = raw.match(/([^{}]+)\{\s*$/)
      if (opened && !line.startsWith('@')) selector = opened[1].trim()
      for (const tok of DECORATIVE_ONLY) {
        if (new RegExp(`^color\\s*:\\s*var\\(--${tok}\\)`).test(line)) {
          if (!DECORATIVE_ALLOWED.some((re) => re.test(selector))) {
            bad.push({ rel, line: i + 1, selector, tok })
          }
        }
      }
    })
  }
  return bad
}

/**
 * 硬编码 `font-size: Npx` —— 绕过字号阶梯的地方。tokens.css 是定义处，跳过。
 * 为什么要拦：字号门禁只统计 `var(--fs-N)`，写死像素值可以神不知鬼不觉地
 * 多加一层层级。2026-10-11 就抓到一处 `font-size: 10px`（命令面板的快捷键角标），
 * 它比最小的登记档还小，而且门禁一声不响。
 */
function literalFontSizes() {
  const base = resolve(__dirname, '..')
  const bad = []
  for (const f of walk(resolve(base, 'src'))) {
    if (f.endsWith('tokens.css')) continue
    const rel = f.slice(base.length + 1)
    readFileSync(f, 'utf8').split('\n').forEach((raw, i) => {
      /* 两种绕过写法都要抓：CSS 的 `font-size: 10px`，以及 **SVG 的 `font-size="10"` 属性**
         （后者在 2026-10-11 真的漏过了门禁 —— 报告页图表里 7 处 10/11px 就是这么藏着的）。 */
      if (/font-size\s*:\s*[0-9.]+px\b/.test(raw) || /font-size\s*=\s*["']?\s*[0-9.]+/.test(raw)) {
        bad.push({ rel, line: i + 1, text: raw.trim() })
      }
    })
  }
  return bad
}

const mustFgs = new Set(CHECKS.filter((c) => c.must).map((c) => c.fg))
const unregistered = TEXT_TOKENS.filter((t) => !mustFgs.has(t))
const misuse = decorativeMisuse()
const literalFs = literalFontSizes()

const themes = [
  { id: 'light', label: '浅色（默认 · 蓝主）', ctx: root },
  { id: 'light-red', label: '浅色 + 河大红主色', ctx: { ...root, ...accentRed } },
  { id: 'dark', label: '深色（蓝主）', ctx: { ...root, ...dark } },
  { id: 'dark-red', label: '深色 + 河大红主色', ctx: { ...root, ...dark, ...darkRed } },
]

console.log(`对比度校验（阈值 ${MIN}:1，取自 src/styles/tokens.css）\n`)

let failed = 0
let skipped = 0

for (const t of themes) {
  console.log(`── ${t.label} ──`)
  console.log('  比值    结论   项'.padEnd(46) + '前景 / 背景')
  for (const c of CHECKS) {
    const fg = resolveIn(t.ctx, c.fg)
    const bg = resolveIn(t.ctx, c.bg)
    if (!isHex(fg) || !isHex(bg)) {
      skipped += 1
      console.log(`    —    跳过   ${c.note.padEnd(28)} ${fg} / ${bg}（非 hex，需人工判断）`)
      continue
    }
    const ratio = contrast(fg, bg)
    const pass = ratio >= MIN
    if (!pass && c.must) failed += 1
    const verdict = pass ? '过  ' : c.must ? '破线' : '仅图形'
    console.log(`  ${ratio.toFixed(2).padStart(5)}  ${verdict}  ${c.note.padEnd(28)} ${fg} / ${bg}`)
  }
  console.log('')
}

if (unregistered.length) {
  console.error('✗ 这些令牌登记为"承载文字"，但 CHECKS 里没有 must:true 的条目：')
  for (const t of unregistered) console.error(`    --${t}`)
  console.error('  —— 承载文字的令牌必须被逐条守住，否则它就是下一个 --c-text-4。')
}

if (misuse.length) {
  console.error('✗ 登记为"仅装饰"的令牌被拿去当文字色：')
  for (const m of misuse) console.error(`    ${m.rel}:${m.line}  --${m.tok}  选择器 ${m.selector}`)
  console.error('  —— 改用承载文字的令牌（如 --c-text-3）；若它真的只是圆点，')
  console.error('     就把它加进 DECORATIVE_ALLOWED 并说明理由。')
}

if (fsUnregistered.length) {
  console.error('✗ 这些字号令牌在 tokens.css 里，但 FONT_SIZE_USES 里没有登记：')
  for (const t of fsUnregistered) console.error(`    --fs-${t}`)
  console.error('  —— 加一档字号就是在加一层层级，必须说明它给谁用。')
}

if (fsGhost.length) {
  console.error('✗ 这些字号令牌登记了，但 tokens.css 里没有：')
  for (const t of fsGhost) console.error(`    --fs-${t}`)
}

if (fsUnused.length) {
  console.error('✗ 这些字号令牌登记了，但界面源文件里一次都没用（死档）：')
  for (const t of fsUnused) console.error(`    --fs-${t}`)
  console.error('  —— 没人用的档位只会让下一个人以为"这里还有一级层级"。')
}

if (literalFs.length) {
  console.error('✗ 这些地方硬编码了 font-size: Npx，绕过了字号阶梯：')
  for (const m of literalFs) console.error(`    ${m.rel}:${m.line}  ${m.text}`)
  console.error('  —— 改用 var(--fs-12 / 14 / 20 / 30)。写死像素值等于偷偷加了一档层级，')
  console.error('     而且它比最小的登记档还小的时候，没人会发现。')
}

if (failed || unregistered.length || misuse.length || fsUnregistered.length || fsGhost.length || fsUnused.length || literalFs.length) {
  if (failed) console.error(`✗ ${failed} 项必过项破线（< ${MIN}:1）。改 tokens.css 里的色值，或改这条硬线。`)
  process.exit(1)
}
console.log(`✓ ${themes.length} 套皮肤组合的必过项全部 ≥ ${MIN}:1${skipped ? `（另有 ${skipped} 项为非 hex，已跳过）` : ''}。`)
console.log(`✓ 令牌用途登记：${TEXT_TOKENS.length} 条承载文字、全部有 must:true 条目；`)
console.log(`  ${DECORATIVE_ONLY.map((t) => `--${t}`).join('、')} 未被当作文字色（白名单 ${DECORATIVE_ALLOWED.length} 条）。`)
console.log(`✓ 字号令牌登记：${fsRegistered.length} 档全部登记、全部在界面上真的用到（2026-10-12：内页正文恢复 16px）。`)
console.log('  提示：主色是**河大校徽蓝** --blue-500（#154494），对白底 9.18:1，')
console.log('        所以它既能画图形也能承载文字，不需要再降一档。')
