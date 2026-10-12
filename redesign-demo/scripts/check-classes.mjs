#!/usr/bin/env node
/**
 * 类名撞车门禁。
 *
 * 【为什么要有这一条】
 * 这个项目已经**两次**栽在同一件事上，而且第二次是我自己刚犯的：
 *
 *   1. `CollectRail.vue`（对话页右栏）自己有 `.rail`，
 *      而方案 B 在 `base.css` 里加了全局 `.rail`（账页/索引栏版式）。
 *      → scoped 只覆盖它声明过的属性；全局那三条（`display:grid` /
 *        `grid-template-columns:248px 1fr` / `gap`）漏进去，
 *        右栏被压成两列，15 段进度条宽度变成 0 —— 客户报的"展示不全，要左右滑动"。
 *   2. `PlanView.vue`（两本账）自己有 `.ledger`，
 *      而四页重做时我在 `base.css` 里加了全局 `.ledger`（账页）。
 *      → 同一类事故，只是这次被尺子提前照出来了。
 *
 * 靠"加类名之前记得 grep 一下"是靠不住的（两次都没记得）。所以做成机械检查：
 *
 *   **同一个类名，不许同时出现在全局样式表和某个组件的 scoped 样式里。**
 *
 * scoped 样式的特异性更高（`.x[data-v-*]`），会赢下它声明过的属性；
 * 但**它没声明的属性照样从全局漏进来** —— 这正是事故的机制，也是这条门禁的由来。
 *
 * 用法：node scripts/check-classes.mjs   （退出码 1 = 有撞名）
 */

import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(__dirname, '..', 'src')

/** 全局样式表：这里的类名是全站共用的零件与版面 */
const GLOBAL_FILES = ['styles/base.css']

/**
 * 会"漏进去"的属性 —— 只有这些出现在全局规则里才真的会毁掉一个组件。
 * 撞名但全局只改颜色，风险低得多（只提示，不拦）。
 */
const LAYOUT_PROPS = /(^|[;{\s])(display|grid-template-columns|grid-template-rows|grid-column|grid-row|flex|flex-direction|flex-wrap|gap|max-width|min-width|width|position|padding|margin)\s*:/

function walk(dir) {
  const out = []
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p))
    else if (/\.(vue|css)$/.test(e.name)) out.push(p)
  }
  return out
}

function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

/**
 * 抓出 CSS 里**裸类名**的规则（`.x` / `.x:hover`），以及它那条规则的声明体。
 *
 * 关键：**带后代/子选择器的组合不算** —— `.rail > .main`、`.rail__split > .side`
 * 这些只在 `.rail` 里面生效，不会漏进别处的组件。把它们当成"全局 .main"会淹掉真信号。
 */
function rulesByClass(css) {
  const map = new Map()
  const clean = stripComments(css)
  for (const m of clean.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const body = m[2]
    for (const part of m[1].split(',')) {
      const p = part.trim()
      const head = p.split(':')[0]
      if (/[\s>+~]/.test(head)) continue          // 组合选择器：不算全局裸类
      const mm = p.match(/^\.(-?[A-Za-z_][\w-]*)/)
      if (!mm) continue
      map.set(mm[1], (map.get(mm[1]) || '') + body)
    }
  }
  return map
}

const globalRules = new Map()
for (const f of GLOBAL_FILES) {
  for (const [name, body] of rulesByClass(readFileSync(resolve(SRC, f), 'utf8'))) {
    globalRules.set(name, { file: f, body: (globalRules.get(name)?.body || '') + body })
  }
}

const collisions = []
const notes = []

for (const file of walk(SRC)) {
  if (!file.endsWith('.vue')) continue
  const src = readFileSync(file, 'utf8')
  const m = src.match(/<style[^>]*\bscoped\b[^>]*>([\s\S]*?)<\/style>/)
  if (!m) continue
  const rel = file.slice(SRC.length + 1)
  for (const [name, body] of rulesByClass(m[1])) {
    const g = globalRules.get(name)
    if (!g) continue
    const out = { rel, cls: name, globalFile: g.file, layout: LAYOUT_PROPS.test(body.replace(/\s+/g, ' ')) }
    if (out.layout) collisions.push(out)
    else notes.push(out)
  }
}

console.log(`类名撞门禁（全局样式表：${GLOBAL_FILES.join('、')}）\n`)

if (notes.length) {
  console.log('· 同名但全局那条只管外观（风险低，只提示）：')
  for (const n of notes) console.log(`    .${n.cls}   ${n.rel}  ↔  ${n.globalFile}`)
  console.log('')
}

if (collisions.length) {
  console.error('✗ 这些类名同时出现在全局样式表与某个组件的 scoped 样式里，且全局那条含版面属性：')
  for (const c of collisions) console.error(`    .${c.cls}   ${c.rel}  ↔  ${c.globalFile}`)
  console.error('')
  console.error('  机制：scoped 的 `.x[data-v-*]` 只赢下**它自己声明过**的属性，')
  console.error('        全局那几条（display / grid-template-columns / max-width / gap …）照样漏进去。')
  console.error('  修法：把组件那一侧改名（例如 `.rail` → `.collect`、`.ledger` → `.book`），')
  console.error('        或者把全局那一条收窄到只作用于它的页面容器。')
  process.exit(1)
}

console.log('✓ 没有撞名：全局样式表里的类名没有一个被组件在 scoped 样式里重复定义。')
