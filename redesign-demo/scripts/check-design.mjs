#!/usr/bin/env node
/**
 * 设计语言门禁 —— 把 design-review/v6-redesign/DESIGN-LANGUAGE.md 里"可判定的说法"
 * 变成对**真实应用**的可复核测量。
 *
 * 【为什么要有这一条，以及它不管什么】
 * 项目已有的两道门禁各自守住一半：
 *   · scripts/check-contrast.mjs —— 颜色比值、令牌用途登记、字号令牌是否登记/是否真被用到；
 *   · scripts/check-classes.mjs  —— 全局样式与组件 scoped 的类名撞车。
 * 它们**都不看跑起来的界面**。而 DESIGN-LANGUAGE §6 的十条判定清单里，有一半
 * 只能在渲染出来的 DOM 上量：触控目标多大、加载后有没有动画在跑、静置时文本变不变、
 * 有没有东西溢出、以及"四个落点"在这页到底有没有显形。
 * 这份脚本就是那一半。**它不重复查字号令牌登记**（check-contrast 已经在查，
 * 且它按 `var(--fs-N)` 静态统计比运行时抽样更准）—— 这里只在运行时实测
 * "这一页到底出现了哪几档"，用来看"一屏几个字号"这种版面问题。
 *
 * 用法：
 *   node scripts/check-design.mjs                        # 1280 宽，逐路由一行
 *   node scripts/check-design.mjs --width 390            # 手机档
 *   node scripts/check-design.mjs --json > _shots/design-1280.json
 *   node scripts/check-design.mjs --url http://127.0.0.1:5273 --route /chat
 *   node scripts/check-design.mjs --no-start             # 只连已经在跑的 dev server
 *
 * 退出码：0 = 全过；1 = 有违规（可直接当门禁）；2 = 起不来 / 连不上（环境问题，不是界面问题）。
 *
 * 注：`--json` 时进度行走 stderr，stdout **只有一份 JSON** ——
 * 否则 `node ... --json > out.json` 拿到的文件前面会挂几行中文进度，
 * JSON.parse 直接失败（第一版就是这样，白跑一轮）。
 *
 * ---------------------------------------------------------------------------
 * 本脚本搬了 design-review/v6-redesign/directions/c2-hbu/_tools/audit.mjs 的**做法**，
 * 那版在 21 张样张上踩平的坑逐条写在对应函数头上（触控目标的 label 判定、
 * 禁用词必须先剥注释、`overflow=(?!ok)` 不能写成 `overflow=1`、静置检查、
 * 页面类型分档）。每一条都注明了"为什么这么量"，改之前先读那一段。
 * ---------------------------------------------------------------------------
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { spawn, spawnSync } from 'node:child_process'
import net from 'node:net'

const require = createRequire(import.meta.url)
const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`)
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : fallback
}
const has = (name) => process.argv.includes(`--${name}`)

const BASE = arg('url', 'http://127.0.0.1:5273').replace(/\/$/, '')
const WIDTH = Number(arg('width', '1280'))
const HEIGHT = Number(arg('height', String(WIDTH <= 700 ? 844 : 900)))
const JSON_OUT = has('json')
const ONLY_ROUTE = arg('route', null)
const NO_START = has('no-start')

/* ===========================================================================
 * 一、路由清单：从 src/router.ts 读，不写死
 * ---------------------------------------------------------------------------
 * 写死一份路由列表一定会过期 —— 而且过期的方式最坏：新加的页面自动"通过"。
 * 所以从路由表里机械地抓 path。抓不到新写法（例如将来用变量拼 path）时，
 * 下面的自检会把它报出来，而不是静默漏掉。
 * ======================================================================== */

function discoverRoutes() {
  const src = readFileSync(join(ROOT, 'src', 'router.ts'), 'utf8')
  // 路由对象里 path 与 name 一定成对出现；用 name 做锚，比单独扫 path: 更稳。
  const routes = []
  for (const m of src.matchAll(/path:\s*'([^']+)'[\s\S]{0,120}?name:\s*'([^']+)'/g)) {
    routes.push({ path: m[1], name: m[2] })
  }
  for (const m of src.matchAll(/name:\s*'([^']+)'[\s\S]{0,120}?path:\s*'([^']+)'/g)) {
    if (!routes.some((r) => r.name === m[1])) routes.push({ path: m[2], name: m[1] })
  }
  const staticRoutes = routes.filter((r) => !/[:*]/.test(r.path))
  const dynamic = routes.filter((r) => /[:*]/.test(r.path))
  // 静态路由数少于 10 说明匹配写法变了 —— 宁可报错也不要静默地少跑页面。
  if (staticRoutes.length < 10) {
    throw new Error(
      `只从 src/router.ts 解析出 ${staticRoutes.length} 条静态路由，像是匹配写法变了；` +
        `请更新 discoverRoutes()，不要拿一份会过期的清单凑合。`
    )
  }
  const list = staticRoutes.map((r) => ({
    route: r.path === '/' ? '#/' : `#${r.path}`,
    path: r.path,
    name: r.name,
  }))
  return { list, dynamic: dynamic.map((d) => d.path) }
}

const { list: ROUTES, dynamic: DYNAMIC_ROUTES } = discoverRoutes()

/* ===========================================================================
 * 二、页面类型分档
 * ---------------------------------------------------------------------------
 * 口径来自样张那一轮：四个落点是**数据页**的活法（DESIGN-LANGUAGE §3 明说
 * "照对话页那套做不成立"，反过来也一样 —— 门户与 404 页没有"组织权"可言）。
 * 拿"每页都要三个落点"一把尺子量全部路由，只会逼人往门户上堆假结构。
 *
 * 新增路由**默认按 data 算**（门槛最高的一项）——
 * 这样"忘了登记"的代价是需要补登记，而不是悄悄放过。
 * ======================================================================== */
const PAGE_KIND = {
  '/': 'entry',        // 门户：公开宣传页，没有"组织权"
  '/spec': 'doc',      // 设计规范：内部文档
  '/path': 'doc',      // 大一到大四：给评审看的施工说明
  '/tools': 'tool',    // 应用工具：入口目录
  '/not-found': 'state', // 由 /:pathMatch(.*)* 兜底渲染
  '/chat': 'dialogue', // 对话页：不按落点判，判"过程可见"
}
const REQUIRED_HITS = { data: 3, dialogue: 0, doc: 2, entry: 2, tool: 2, state: 2 }
const KIND_OF = (path) => PAGE_KIND[path] || 'data'
const KIND_LABEL = { data: '数据页', dialogue: '对话页', doc: '文档页', entry: '入口页', tool: '工具页', state: '状态页' }

/* 404 页的地址：走兜底路由，用一个肯定匹配不到的路径 */
const NOT_FOUND_ROUTE = { route: '#/__design-gate-404__', path: '/not-found', name: 'not-found' }

/* ===========================================================================
 * 三、动效政策（DISABLED / ALLOWED）
 * ---------------------------------------------------------------------------
 * DESIGN-LANGUAGE §5 反例表逐条点名：页面淡入 + 位移、数字滚动、指示线滑动、
 * 持续背景运动、粒子、发光边框、一进页面把动画播一遍、自动轮播、图表生长。
 * 这里把全仓库的 @keyframes **逐个登记**成"为什么允许"或"命中哪条禁令"。
 *
 * 为什么必须逐个登记、而不是拿关键词猜：
 *   · 猜不准 —— `chat-caret`（流式输入光标）名字里既没有"淡入"也没有"位移"，
 *     但它恰恰是**允许**的（DESIGN-LANGUAGE §2 进行时：正在生成）；
 *   · 反过来 `bar-grow` 名字人畜无害，它就是反例表点名的"图表生长"。
 * 所以：**运行时看到没登记的动画 = 失败**（见 classifyRunning）。
 * 这一条纪律是这份门禁最值钱的部分：它让"新加一个动画"必须先回答
 * §6 第 8 问 ——"这里发生了什么？"
 * ======================================================================== */
const ANIM_ALLOWED = {
  // —— 主体在场（对话页的"活"= 过程可见；§2 进行时）——
  'ag-breathe': '主体在场：顾问呼吸（进行时）',
  'ag-blink': '主体在场：眨眼（进行时）',
  'ag-look': '主体在场：扫视（进行时）',
  'ag-talk': '主体在场：说话开合（进行时）',
  'ag-sound': '主体在场：声波（进行时）',
  'ag-orbit': '主体在场：思考绕行（进行时）',
  'ag-ripple': '主体在场：说话涟漪（进行时）',
  'ag-nod': '主体在场：点头（进行时）',
  'dialogue-state-pulse': '在场状态点呼吸：在听 / 在想（进行时）',
  'stop-pulse': '生成中「停止」按钮脉冲（进行时：正在生成）',
  'chat-caret': '流式输入光标闪烁（进行时：文字正在出来）',
  // —— 加载态：只在"还没拿到数据"时出现，是状态而不是装饰（§6 第 2 问）——
  'sk-sweep': '骨架屏扫光（加载态）',
  // —— 明确由**用户动作**触发，不是进场装饰 ——
  'desk-expand': '桌面目录展开（用户点开才发生）',
  'desk-collapse': '桌面目录收起（用户点开才发生）',
  'skin-fade': '换肤时的整页淡入（用户点主题才发生）',
  'just-changed': '状态刚变过的高亮（回答"哪里动了"，§6 第 3 问）',
  'p7-flash': '画像页定位到某条时的短暂高亮（用户点进来看才发生）',
  'action-settle': '任务加入计划后的落定反馈（§6 第 4 问：即时且连锁的反馈）',
  'sheet-rise': 'inspector 面板入场（用户点开才发生）',
  'sheet-slide-in': 'inspector 侧滑入场（用户点开才发生）',
  'sheet-slide-up': '手机底部面板上滑（用户点开才发生）',
}

const ANIM_VIOLATION = {
  // —— 反例表第 1 行：页面淡入 + 位移 ——
  'workspace-arrive': '页面淡入 + 位移 5px（反例表：装饰，不影响截屏结果）',
  'enter-up': '元素位移进场（.stagger 逐条上移 8px；反例表：装饰）',
  'chat-rise': '消息位移进场（淡入 + 上移 8px；反例表：装饰）',
  'chat-handoff-in': '交接卡位移进场（淡入 + 上移 6px；反例表：装饰）',
  'chat-swap': '切换会话时整片淡入（反例表：装饰）',
  'block-grow': '回答分块逐块进场（§5：一进页面把动画播一遍 = 表演，播完就死了）',
  'card-grow': '卡片切换时位移进场（反例表：装饰）',
  'evidence-grow': '依据列表展开时进场（反例表：装饰）',
  'journey-record-enter': '时间线记录位移进场（反例表：装饰）',
  'pf-arrive': '门户主张位移进场（反例表：装饰）',
  'sk-cover-in': '骨架屏遮罩淡入（反例表：页面淡入）',
  // —— 反例表里点名的两类 ——
  'bar-grow': '图表条生长（反例表点名："数据页加图表 + 图表生长"，关系没变仍是装饰）',
}

/** 反例表剩余几类没有 @keyframes 形态，直接在 CSS/JS 源码里找实现。 */
const BANNED_SOURCE = [
  [/particle|confetti|sparkle/i, '粒子 / 彩带（§7 硬禁止）'],
  [/marquee|carousel|autoplay|autoSlide/i, '自动轮播（§7 硬禁止）'],
  [/\bsetInterval\s*\(/, 'setInterval（定时轮播 / 定时刷新的常见实现，要看它驱动什么）'],
]

/**
 * 数字滚动的专用判定 —— 这一类**不能**用词表匹配，两个方向都会错：
 *   · 正例：`src/lib/motion.ts` 的 `useCountUp` 是货真价实的数字滚动实现（0 → 值，首挂也跑）；
 *   · 反例：`src/views/SpecView.vue` 里"数字滚动"四个字出现在**规范页的场景表**里，
 *     那是文档在描述口径，不是实现了数字滚动。
 * 所以判据是"**定义了有没有人用**"，而不是"有没有出现这个词"。
 */
function countUpAudit(files) {
  const decl = []
  const uses = []
  for (const f of files) {
    const rel = f.slice(ROOT.length + 1)
    if (/\.(ts|mjs|js)$/.test(f)) {
      const code = stripComments(readFileSync(f, 'utf8'))
      for (const m of code.matchAll(/export\s+function\s+(\w*[Cc]ountUp\w*)\s*\(/g)) decl.push({ name: m[1], rel })
    }
    // 调用点：只看 .vue / .ts 的 import 与模板调用，规范页那种文案里的词不算
    if (/\.(vue|ts)$/.test(f) && !/\.d\.ts$/.test(f)) {
      const code = stripComments(readFileSync(f, 'utf8'))
      for (const m of code.matchAll(/useCountUp|countUp\s*\(/g)) {
        if (/lib[\\/]motion\.ts$/.test(rel)) continue // 定义处不算使用
        uses.push({ rel, evidence: code.slice(Math.max(0, m.index - 30), m.index + 30).replace(/\s+/g, ' ') })
      }
    }
  }
  return { decl, uses }
}
/** 发光边框：box-shadow 里带 accent 光晕 */
const GLOW_RE = /box-shadow\s*:[^;}]*?(glow|--sh-accent)/gi

/**
 * 归一化一个运行时动画名：剥掉 Vue scoped 样式追加的哈希后缀。
 *
 * 为什么必须这么做：源码里写 `@keyframes ag-breathe`，Vue scoped 会把它编译成
 * `ag-breathe-c09aab26`，`getAnimations()` 报的就是带哈希的那个名字。
 * 登记表按源码名字写（人读的是源码），比对前不剥哈希，每一个动画都会被判成
 * "未登记" —— 第一版就是这样，/chat 一页报了 6 条假违规。
 *
 * 两边的名字表都作为参数传进来（页面里那份由 probeInPage 自带，见那里的注释），
 * 保证"登记表"只有一处真相。
 */
function normalizeAnimName(raw) {
  const name = String(raw || '')
  if (!name) return name
  if (ANIM_ALLOWED[name] || ANIM_VIOLATION[name]) return name
  const m = name.match(/^(.*)-([0-9a-f]{6,})$/)
  if (m && (ANIM_ALLOWED[m[1]] || ANIM_VIOLATION[m[1]])) return m[1]
  return name
}

/* ===========================================================================
 * 四、注入浏览器执行的大函数
 * ---------------------------------------------------------------------------
 * 用 page.evaluate 传一个函数进去（而不是拼字符串）：这样脚本本身能被编辑器
 * 与 node --check 校验，也不会因为路径里的撇号（本仓库工作目录含 `'`）被拼坏。
 * 返回值必须可结构化克隆（JSON 安全）。
 *
 * ⚠ 这个函数会被**序列化成源码**丢进浏览器，所以它抓不到外层的任何变量
 *   （登记表也不例外）。需要在页面里用的常量必须写在函数体内部。
 * ======================================================================== */

/* eslint-disable no-undef */
function probeInPage() {
  /**
   * 页面容器。门户 / 规范 / 404 是裸布局（App.vue 的 `bare` 分支），内页在 .app__content 里。
   * 只量内容列，不量侧栏与顶栏 —— 它们的触控目标是"壳"，不是这一页的设计。
   */
  const root = document.querySelector('.app__content') || document.querySelector('.app') || document.body

  /* ------------------------- 可复核定位 ------------------------- */
  function describe(el) {
    if (!el || !el.tagName) return '?'
    if (el.id) return '#' + el.id
    let s = el.tagName.toLowerCase()
    const cls = (typeof el.className === 'string' ? el.className : '')
      .trim()
      .split(/\s+/)
      .filter((c) => c && !/^data-v-/.test(c))
      .slice(0, 2)
    if (cls.length) s += '.' + cls.join('.')
    const p = el.parentElement
    if (p) {
      const sib = [...p.children].filter((c) => c.tagName === el.tagName)
      if (sib.length > 1) s += `:nth-of-type(${sib.indexOf(el) + 1})`
    }
    return s
  }
  const box = (el) => {
    const r = el.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height) }
  }
  const pathOf = (el) => {
    const parts = []
    for (let n = el; n && n !== root && parts.length < 6; n = n.parentElement) parts.unshift(describe(n))
    return parts.join(' > ')
  }

  /* =========================================================================
   * A. 触控目标
   * -------------------------------------------------------------------------
   * 判定沿用样张那版 audit.mjs，逐条都是踩过的坑：
   *
   * 1) 候选集：a[href] / button / input / textarea / select / summary / label[for] / [tabindex]。
   *    跳过 w<2 || h<2 的（视觉隐藏的 1×1 开关、折叠容器），否则满屏假阳性。
   *
   * 2) `display:inline` 的 <a> 不算：WCAG 2.5.8 Target Size (Minimum) 对
   *    **正文行内链接**有明文豁免。第一版没豁免，把正文里的行内链接全报成了缺陷。
   *
   * 3) `<label for>` 算不算目标，**取决于它关联的那个控件**：
   *    · 控件本身 ≥36（例如 280×40 的输入框）→ 标签只是说明文字，点它是顺手聚焦，不算目标；
   *    · 控件很小或视觉隐藏（设置页把 input 藏成 1×1，可见的就是那个标签）→ 标签**就是**控件，必须算。
   *    第一版一刀切地把所有 label 都算成目标，于是登录页 357×21 的字段标题被报成缺陷（假阳性）。
   *
   * 4) 反向情形：小控件**被一个 ≥36 的 <label> 整块包着**（登录页协议勾选框：
   *    20×20 的 checkbox 包在 min-height:44px 的 .lg-agree 里）。真目标是那个标签，
   *    控件本身只是它的可见形状 —— 不算缺陷。
   *
   * 阈值：DESIGN-LANGUAGE 沿用的两档 —— 主要动作 ≥44，卡片内次要控件 ≥36。
   * 「主要动作」= .btn--primary / .btn / 页头与对话头的动作区 / 工具栏与命令项里的控件。
   * 这一档是 **warn**（不是违规）：44 是 WCAG 2.5.5 (AAA) 的口径，
   * 而项目自己的 DESIGN.md 写的是"普通按钮最小高 42px、小按钮 36px"。
   * 两套口径打架时报告要如实分档，而不是拿其中一套把另一套判死。
   * ====================================================================== */
  const TOUCH_SELECTOR =
    'a[href], button, input, textarea, select, summary, label[for], [tabindex]:not([tabindex="-1"])'
  const PRIMARY_RE = /btn--primary|ws-command-item|ws-chat-head|ws-heading|dialogue-chat-head|composer-(send|stop)|dialogue-action|exp-latest|ws-inline-actions|page__head|ws-page.*head/i

  const touch = { under36: [], under44Primary: [] }
  root.querySelectorAll(TOUCH_SELECTOR).forEach((el) => {
    const r = el.getBoundingClientRect()
    const cs = getComputedStyle(el)
    if (r.width < 2 || r.height < 2) return
    if (cs.visibility === 'hidden' || cs.display === 'none') return
    if (el.tagName === 'A' && cs.display === 'inline') return
    if (el.tagName === 'LABEL' && el.htmlFor) {
      let ctl = null
      try {
        ctl = root.querySelector('#' + CSS.escape(el.htmlFor))
      } catch (e) {
        ctl = null
      }
      if (ctl && ctl.getBoundingClientRect().height >= 36) return
    }
    if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
      const wrap = el.closest('label')
      if (wrap && wrap.getBoundingClientRect().height >= 36) return
    }
    const entry = {
      sel: describe(el),
      path: pathOf(el),
      w: Math.round(r.width),
      h: Math.round(r.height),
      text: (el.getAttribute('aria-label') || el.textContent || el.value || el.placeholder || '')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 22),
      tag: el.tagName.toLowerCase(),
    }
    if (r.height < 36) {
      touch.under36.push(entry)
      return
    }
    // ≥36 但 <44：只在它确实是"主要动作"时算第二档
    const primaryFrom =
      (el.closest('.btn--primary') && 'btn--primary') ||
      (el.classList.contains('btn') && 'btn') ||
      (el.closest('.ws-heading, .ws-chat-head, .dialogue-chat-head, .ws-inline-actions, .dialogue-action, .page__head') &&
        '页头/主行动区') ||
      (el.closest('.ws-command-item') && '命令面板项')
    if (r.height < 44 && (primaryFrom || PRIMARY_RE.test(String(el.className)))) {
      entry.why = primaryFrom || '类名像主要动作'
      touch.under44Primary.push(entry)
    }
  })

  /* =========================================================================
   * B. 加载后（未做任何交互）正在跑的动画
   * -------------------------------------------------------------------------
   * "一进页面把动画播一遍"就是这一条抓的：不做任何交互时页面上在跑的动画，
   * 只可能来自"进场装饰"或"持续动的东西"。两者都在反例表上。
   * 只取 effect.target 落在页面容器里的动画 —— 壳层（侧栏 / 顶栏）的动画
   * 不该记在某一页头上。
   * ====================================================================== */
  const running = []
  /* 登记名清单必须写在这里：这个函数被序列化后丢进浏览器，抓不到外层的 ANIM_ALLOWED。
     只回传**归一化后的短名**，判定与文案仍在 Node 侧做（那里才有完整的"为什么"）。 */
  const KNOWN = {
    'ag-breathe': 1, 'ag-blink': 1, 'ag-look': 1, 'ag-talk': 1, 'ag-sound': 1, 'ag-orbit': 1,
    'ag-ripple': 1, 'ag-nod': 1, 'dialogue-state-pulse': 1, 'stop-pulse': 1, 'chat-caret': 1,
    'sk-sweep': 1, 'desk-expand': 1, 'desk-collapse': 1, 'skin-fade': 1, 'just-changed': 1,
    'p7-flash': 1, 'action-settle': 1, 'sheet-rise': 1, 'sheet-slide-in': 1, 'sheet-slide-up': 1,
    'workspace-arrive': 1, 'enter-up': 1, 'chat-rise': 1, 'chat-handoff-in': 1, 'chat-swap': 1,
    'block-grow': 1, 'card-grow': 1, 'evidence-grow': 1, 'journey-record-enter': 1,
    'pf-arrive': 1, 'sk-cover-in': 1, 'bar-grow': 1, 'btn-fx': 1,
  }
  /** Vue scoped 会给 @keyframes 追加哈希后缀（源码 `ag-breathe` → 运行时 `ag-breathe-c09aab26`） */
  const normalize = (raw) => {
    const s = String(raw || '')
    if (!s || KNOWN[s]) return s
    const m = s.match(/^(.*)-[0-9a-f]{6,}$/)
    return m && KNOWN[m[1]] ? m[1] : s
  }
  try {
    for (const a of document.getAnimations()) {
      if (a.playState !== 'running') continue
      const t = a.effect && a.effect.target
      if (!t || !root.contains(t)) continue
      running.push({
        name: normalize(a.animationName),
        // 动画名抓不到时退回构造器名字（过渡会显示 CSSTransition）——
        // 这本身就是"它不是 keyframes 而是过渡"的证据，报告里照抄。
        kind: a.constructor ? a.constructor.name : '?',
        on: describe(t),
        path: pathOf(t),
        duration: a.effect && a.effect.getTiming ? Math.round(a.effect.getTiming().duration) : null,
        iterations: a.effect && a.effect.getTiming ? a.effect.getTiming().iterations : null,
      })
    }
  } catch (e) {
    /* getAnimations 在极老的浏览器里没有；这里不静默：报告里会写"这一项没查成" */
    running.push({ name: '__probe_error__', kind: String(e && e.message) })
  }

  /* =========================================================================
   * C. 四个落点是否显形
   * -------------------------------------------------------------------------
   * DESIGN-LANGUAGE §4 的四条落地方式，对应到本工程真实的零件名：
   *   ① 结构显形（§4.1 让结构显形，而不是让内容排队）
   *   ② 组织权（§4.2 多视角 + 重组）—— 必须有**能改变组织方式**的控件，
   *      不是"换个列表内容"的 tab。所以 org 只认 tab / 筛选 / 排序 / 对比 / 视角切换。
   *   ③ 粒度与溯源（§4.3）—— 每条信息能看到来历。SourceChip(.src)、
   *      EvidenceList(.exp-evidence)、Foldable(.fold，展开才看到详情)、
   *      MeterRow(.mtr，同刻度的自我/要求/差距)、<time> 时间戳都算。
   *   ④ 状态与不确定性显形（§4.4）—— ConfidenceBadge(.cf)、StatTile(.tile)、
   *      callout / status-banner / 空态都要算：它们把"这份认识有多结实"画出来。
   *
   * 每命中一类都记下**第一个命中的选择器**：报告要能复核，
   * 不能只给一个"命中 2/3"的数字让人自己找。
   * ====================================================================== */
  const n = (sel) => root.querySelectorAll(sel).length

  /* ── ① 结构显形：两条互补的判据 ───────────────────────────────────────
   * 第一版写的是 `.ws-section, .ws-subnav, table, dl, ...` 这种类名清单，两个毛病：
   *   · 漏：本工程真实的结构容器叫 `section.report-chapter` / `ul.p7-rows` /
   *     `ol.ws-timeline` / `div.detail__grid` / `ol.steps-list`，一个都不在清单里；
   *   · 滥：为了补漏把裸 `section` 加进去之后，门户立刻"命中 8 个" ——
   *     而门户整页一个关系容器都没有（靠 section.pf-promises 这种装饰块凑数）。
   * 所以改成两条与类名无关的判据，加起来算：
   *   (a) 关系标记（rel）：编码"谁靠哪几条证据 / 同刻度的自我-要求-差距"的容器
   *       —— table / dl / .mtr / .ws-facts / .ws-chart-grid / .exp-compare /
   *       .ws-two-columns / .ws-timeline / .calendar-layout / .fold--static / .links；
   *   (b) 成组的重复兄弟（groups）：容器里存在 ≥2 个"同名同类同尺寸"的子块，
   *       且每个子块自己够大（≥80×20）—— 这就是"结构"最朴素的样子：
   *       同一批东西按同一个形状排在一起（ul.ws-tasks / ol.ws-timeline / div.grades）。
   *       加尺寸下限是因为不加的话，页头两个动作按钮（div.ws-heading__actions）会被数成结构。
   * 两条都可能误判，所以命中的**具体选择器**一并回传，报告里能逐条复核。
   */
  const REL_SELECTORS = [
    'table', 'dl', 'ol.steps', '.exp-compare', '.mtr', '.ws-facts', '.ws-two-columns',
    '.ws-chart-grid', '.fold--static', '.ws-timeline', '.calendar-layout', '.links',
  ]
  const relHits = []
  for (const s of REL_SELECTORS) {
    const el = root.querySelector(s)
    if (!el) continue
    const r = el.getBoundingClientRect()
    if (r.width < 40 || r.height < 20) continue
    relHits.push(`${s}（${describe(el)} ${Math.round(r.width)}×${Math.round(r.height)}）`)
  }
  const groupHits = []
  root.querySelectorAll('*').forEach((el) => {
    const r = el.getBoundingClientRect()
    if (r.width < 240 || r.height < 60) return
    const kids = [...el.children]
    if (kids.length < 2) return
    const sig = new Map()
    for (const k of kids) {
      const kr = k.getBoundingClientRect()
      if (kr.width < 80 || kr.height < 20) continue
      const key = k.tagName + '|' + (typeof k.className === 'string' ? k.className.trim().split(/\s+/)[0] || '' : '')
      sig.set(key, (sig.get(key) || 0) + 1)
    }
    const repeats = [...sig.values()].filter((v) => v >= 2).length
    if (repeats === 0) return
    groupHits.push(`${describe(el)}（${repeats} 组重复子块 / 共 ${kids.length}）`)
  })
  const structureEvidence = { rel: relHits, groups: [...new Set(groupHits)].slice(0, 6) }

  const LANDING = [
    { key: 'structure', label: '①结构显形', sel: null },
    {
      key: 'organize',
      label: '②组织权',
      sel:
        '.exp-tabs, [role="tab"], [aria-pressed], .compare-filters, .compare-candidates, ' +
        'button[class*="sort"], button[class*="filter"], button[class*="view"], [class*="chip"][aria-pressed]',
    },
    {
      key: 'trace',
      label: '③溯源',
      sel: '.src, .exp-evidence, .fold, .mtr, time, [class*="evidence"], [class*="source"]',
    },
    {
      key: 'status',
      label: '④状态显形',
      sel:
        '.cf, .tile, .callout, .status-banner, .exp-empty, .chat-error, [class*="stale"], ' +
        '[class*="state"], [class*="status"], [aria-busy]',
    },
  ]
  const landing = {}
  const badSelectors = []
  for (const p of LANDING) {
    if (p.key === 'structure') {
      const count = structureEvidence.rel.length + structureEvidence.groups.length
      landing[p.key] = {
        label: p.label,
        count,
        hit: count > 0,
        first: [...structureEvidence.rel, ...structureEvidence.groups][0] || null,
        evidence: structureEvidence,
      }
      continue
    }
    let count = 0
    let sel = null
    for (const s of p.sel.split(',').map((x) => x.trim()).filter(Boolean)) {
      let c = 0
      try {
        c = root.querySelectorAll(s).length
      } catch (e) {
        // 选择器写错时**报出来**，不要静默跳过 —— 静默跳过会让一个落点永远"没命中"，
        // 报告里看起来像界面缺东西，实际是尺子坏了（这一条第一版就吃过：'.journey-*' 直接抛错）。
        badSelectors.push(s)
        continue
      }
      if (c > 0 && !sel) sel = `${s}（${describe(root.querySelector(s))}）`
      count += c
    }
    landing[p.key] = { label: p.label, count, first: sel, hit: count > 0 }
  }
  const landingHits = Object.values(landing).filter((x) => x.hit).length

  /* 组织权的"强度"：控件种类数。只有一个 aria-pressed 的按钮不算"能重组"。 */
  const orgKinds = {
    tabs: n('.exp-tabs, [role="tab"]'),
    pressed: n('[aria-pressed]'),
    selects: root.querySelectorAll('select').length,
    viewLabel: (root.innerText.match(/视角|按[^，。\n]{0,4}看|筛选|排序|对比|分组/g) || []).length,
  }
  landing.organize.kinds = orgKinds

  /* =========================================================================
   * D. 对话页的"过程可见"（§3：对话页的活 = 过程可见，不看四个落点）
   * -------------------------------------------------------------------------
   * 五问，逐问对应一个具体零件：
   *   主体在场三态 → .dialogue-presence（AgentAvatar 的 state）
   *   交接说明     → .chat-handoff（默认可见，不是折叠起来要点开）
   *   结论块       → .chat-block--lead
   *   后续问题可点 → .dialogue-options / .ws-chat-options
   *   输入区       → .ws-composer / .composer
   * 一条都不许省：少一条，这一页就退回"文字流"。
   * ====================================================================== */
  const presence = root.querySelector('.dialogue-presence')
  const handoff = root.querySelector('.chat-handoff')
  const dialogue = {
    presence: !!presence && root.querySelectorAll('[class*="dialogue-presence"], .ag').length >= 1,
    presenceStates: presence ? [...presence.classList].filter((c) => c.startsWith('is-')).join(',') : '',
    handoff: !!handoff,
    handoffHeight: handoff ? Math.round(handoff.getBoundingClientRect().height) : 0,
    conclusion: n('.chat-block--lead, .ws-report-lead, .chat-answer') > 0,
    follow: n('.dialogue-options, .ws-chat-options') > 0,
    composer: n('.ws-composer, .composer, textarea[placeholder]') > 0,
  }

  /* =========================================================================
   * E. 字号 / 字重实测档位
   * -------------------------------------------------------------------------
   * 只统计可见且有文字的**叶子**节点：有子元素的容器会把同一段文字重复计一遍，
   * 让"一屏几个字号"虚高。
   * 注意：这一步**不替代** check-contrast.mjs 的字号令牌登记（那是静态白名单，
   * 查的是"有没有偷偷加档"）；这里查的是"这一页实际画面里出现了几档"，
   * 用来发现"一屏 7–9 个字号"那种版面问题。
   * ====================================================================== */
  const sizes = {}
  const weights = {}
  root.querySelectorAll('*').forEach((el) => {
    if (el.children.length) return
    const t = (el.textContent || '').trim()
    if (!t) return
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2) return
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.2) return
    const fs = Math.round(parseFloat(cs.fontSize))
    sizes[fs] = (sizes[fs] || 0) + 1
    weights[cs.fontWeight] = (weights[cs.fontWeight] || 0) + 1
  })

  /* =========================================================================
   * F. 横向溢出（第一屏）
   * -------------------------------------------------------------------------
   * 判据是 scrollWidth > clientWidth，**不是**"出现了 400px 这样的值"。
   * 样张那版最后一轮用的是 /overflow=(?!ok)/ —— 因为更早一版写的 /overflow=1/
   * 只能匹配以 1 开头的数字，`423>390` 这种就漏掉了。这里直接比数值。
   *
   * 两类要分开报，因为性质完全不同：
   *   · clip  —— 祖先带 overflow-x: hidden/clip：内容**真的看不见**（缺陷）
   *   · scroll —— 祖先带 overflow-x: auto/scroll：内容能滚到（设计如此，提示）
   * 这就是 FORM 那份规范里"方向对照表最小宽 760px、仅在自身容器内横向滚动"
   * 那一类；把它报成缺陷是假阳性。
   * ====================================================================== */
  const overflow = { rootScroll: {}, clip: [], scroll: [] }
  const html = document.documentElement
  overflow.rootScroll = { scrollWidth: html.scrollWidth, clientWidth: html.clientWidth }
  root.querySelectorAll('*').forEach((el) => {
    if (el === root) return
    if (el.tagName === 'svg' || el.tagName === 'defs' || el.tagName === 'pattern' || el.tagName === 'STYLE' || el.tagName === 'SCRIPT') return
    const sw = el.scrollWidth
    const cw = el.clientWidth
    if (cw === 0 || sw - cw < 4) return
    const cs = getComputedStyle(el)
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2) return
    let mode = 'none'
    let byAncestor = null
    for (let p = el; p; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX
      if (ox === 'auto' || ox === 'scroll') {
        mode = 'scroll'
        byAncestor = describe(p)
        break
      }
      if (ox === 'hidden' || ox === 'clip') {
        mode = 'clip'
        byAncestor = describe(p)
        break
      }
    }
    if (mode === 'none') return
    const rec = {
      sel: describe(el),
      path: pathOf(el),
      // 记下**是哪个祖先决定的**：clip 说明内容真看不见，scroll 说明能滚到。
      // 复核时要能一眼看出尺子量的是哪一层（第一版没记，看到"可滚"也不知道该去看谁）。
      byAncestor,
      scrollWidth: sw,
      clientWidth: cw,
      over: sw - cw,
      rectW: Math.round(r.width),
      viewportW: document.documentElement.clientWidth,
      text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 24),
    }
    if (mode === 'clip') overflow.clip.push(rec)
    else overflow.scroll.push(rec)
  })
  overflow.clip.sort((a, b) => b.over - a.over)
  overflow.scroll.sort((a, b) => b.over - a.over)
  overflow.clip = overflow.clip.slice(0, 8)
  overflow.scroll = overflow.scroll.slice(0, 4)
  overflow.badSelectors = badSelectors

  /* 状态页（404）的三问一并在页内算好回传 —— 与四个落点同一层，判定留在 Node 侧。
     为什么状态页要单独一组判据：见 judgeRoute 里 state 分支的长注释。 */
  const statePage = {
    hasTitle: !!root.querySelector('.page__title, h1'),
    hasExplain: !!root.querySelector('.page__sub'),
    hasExit: !!root.querySelector('a[href="#/"], a[href="/"], a.btn'),
  }

  return { root: describe(root), touch, running, landing, landingHits, dialogue, statePage, sizes, weights, overflow }
}

/**
 * 静置采样：同一段文本 + 同一批元素的**几何**，隔 1.2s 是否自己变。
 *
 * 关键设计：**用遍历序号当键，不用选择器当键**。
 * 第一版拿 `describe(el)`（`span` / `h2` 这种）当键，而 `Map` 后写覆盖前写，
 * 于是"第 5 个 span 的文本"和"最后一个 span 的文本"被当成同一个键比对 ——
 * 每一页都恰好报 12 条"静置变化"（12 是报告上限），门户上甚至出现
 * `971,854 249×20` → `60,290 303×84` 这种把**文本和几何串在一起**的假证据。
 * 序号键的代价是"两次采样之间元素插入/删除会让后面全部错位"，
 * 所以外层必须用数量相等来兜底（数量不等就明说结论不可靠，而不是硬比）。
 *
 * 还要采几何：数字滚动会改文本，但**自动轮播**可能只换图/换卡位置
 * （`.chat-cards__track` 那种平移），文本一个字都不变 —— 只比文本会漏。
 *
 * 排除项（不排除就是一堆假阳性）：
 *   · 声明了 aria-live / role="log"，或祖先带它们的 —— 那是**故意的**实时区，
 *     "文本会变"正是它的功能（§2 进行时）；
 *   · 正在逐字流式的节点、骨架屏 —— 同上，是"正在生成 / 正在加载"的可视证据。
 *   · 几何采样同样套用这两条排除：第一版只在文本侧排除，几何侧照收，
 *     于是正在呼吸/绕行的顾问头像（SVG 子元素）被记成"几何静置变化"。
 * 这不是放水：判据是"变化**该不该**被看见"，而不是"变没变"。
 */
function sampleInPage() {
  const root = document.querySelector('.app__content') || document.querySelector('.app') || document.body
  const live = (el) => {
    for (let n = el; n && n !== root.parentElement; n = n.parentElement) {
      if (n.getAttribute && (n.getAttribute('aria-live') || n.getAttribute('role') === 'log')) return true
    }
    return false
  }
  function describe(el) {
    if (el.id) return '#' + el.id
    let s = el.tagName.toLowerCase()
    const cls = (typeof el.className === 'string' ? el.className : '')
      .trim()
      .split(/\s+/)
      .filter((c) => c && !/^data-v-/.test(c))
      .slice(0, 2)
    if (cls.length) s += '.' + cls.join('.')
    const p = el.parentElement
    if (p) {
      const sib = [...p.children].filter((c) => c.tagName === el.tagName)
      if (sib.length > 1) s += `:nth-of-type(${sib.indexOf(el) + 1})`
    }
    return s
  }
  const skip = (el) =>
    live(el) || !!el.closest('.chat-caret, .chat-turn--thinking, .sk, [class*="skeleton"]')
  const texts = []
  const geos = []
  root.querySelectorAll('*').forEach((el) => {
    if (el.tagName === 'STYLE' || el.tagName === 'SCRIPT' || el.tagName === 'svg') return
    if (skip(el)) return
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2) return
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none') return
    // 几何：所有可见元素都收（含 SVG 内部形状 —— 轮播/平移就藏在那里）
    geos.push({ sel: describe(el), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) })
    // 文本：只看叶子，且要有字
    if (el.children.length) return
    const t = (el.textContent || '').trim()
    if (!t) return
    texts.push({ sel: describe(el), cls: String(el.className).slice(0, 44), text: t.replace(/\s+/g, ' ').slice(0, 160) })
  })
  return { texts, geos }
}

/* ===========================================================================
 * 五、静态扫描：禁用词必须先剥注释
 * ---------------------------------------------------------------------------
 * 样张那版第一遍就吃过亏：本项目大量注释在**解释为什么不做**数字滚动 / 淡入，
 * 不去注释就会把"我们不做 X"的说明当成"我们做了 X"。
 * 所以这里对 .vue / .css / .ts / .mjs 统一剥掉 /* *\/ 与 // 再匹配。
 * ======================================================================== */
function stripComments(s) {
  return s
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1 ')
    // Vue 模板注释同理：<!-- 我们不做数字滚动 -->
    .replace(/<!--[\s\S]*?-->/g, ' ')
}

function walkSource(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name.startsWith('.')) continue
      walkSource(p, out)
    } else if (/\.(vue|css|ts|mjs|js)$/.test(e.name)) out.push(p)
  }
  return out
}

function staticScan() {
  const files = walkSource(join(ROOT, 'src'))
  const found = { keyframes: new Map(), banned: [], glow: [] }
  for (const f of files) {
    const rel = f.slice(ROOT.length + 1)
    const code = stripComments(readFileSync(f, 'utf8'))
    // 只认真正的定义（排除注释里提到名字的写法；注释已在上面剥掉，这里再要求后面紧跟 `{`）
    for (const m of code.matchAll(/@keyframes\s+([A-Za-z0-9_-]+)\s*\{/g)) {
      if (!found.keyframes.has(m[1])) found.keyframes.set(m[1], rel)
    }
    for (const [re, label] of BANNED_SOURCE) {
      const hit = code.match(re)
      if (hit) found.banned.push({ rel, label, evidence: hit[0] })
    }
    for (const m of code.matchAll(GLOW_RE)) {
      found.glow.push({ rel, evidence: m[0].slice(0, 60) })
    }
  }
  return found
}

/* ===========================================================================
 * 六、起 / 找 dev server
 * ======================================================================== */
function portOpen(url) {
  return new Promise((res) => {
    let u
    try {
      u = new URL(url)
    } catch (e) {
      return res(false)
    }
    const s = net.createConnection({ host: u.hostname, port: Number(u.port || 80) })
    const done = (v) => {
      s.destroy()
      res(v)
    }
    s.setTimeout(1200)
    s.on('connect', () => done(true))
    s.on('timeout', () => done(false))
    s.on('error', () => done(false))
  })
}

/**
 * 自己起 `npm run dev`。
 *
 * 为什么用 spawnSync（同步）而不是 spawn + 轮询：同步调用会被 Node 的事件循环
 * 阻塞，所以脚本里的轮询代码一句也跑不到 —— 不能一边 spawnSync 一边等它。
 * 做法是：另起一个 `node -e` 子进程，它在**自己的**事件循环里轮询 dev server，
 * 就绪或超时后自己退出。父进程同步等它，拿到确定的结果再继续。
 */
function startDevServer(url) {
  const port = Number(new URL(url).port || 5273)
  /**
   * Windows 上起 npm 有两条弯路，都踩过：
   *   1. 直接 `spawn('npm.cmd', ...)` → **EINVAL**。Node 20+ 对 .cmd/.bat 不再隐式套 shell
   *      （CVE-2024-27980 的修复），必须显式给 shell。
   *   2. `spawn('npm.cmd', ..., { shell: true })` → 能起来，但 Node 发 **DEP0190**
   *      （shell 下参数不转义，只有拼接），stderr 会多一行警告污染输出。
   * 这里走第三条：`cmd.exe /d /s /c` 显式起一个命令解释器，参数始终是数组、不经 shell 拼接。
   * 起不来时报明错误，而不是让调用方看一句"等超时"。
   */
  console.log(`· ${url} 没在跑，自己起一个（vite --port ${port} --strictPort）…`)
  const child =
    process.platform === 'win32'
      ? spawn('cmd.exe', ['/d', '/s', '/c', 'npm', 'run', 'dev', '--', '--port', String(port), '--strictPort'], {
          cwd: ROOT,
          detached: true,
          stdio: 'ignore',
        })
      : spawn('npm', ['run', 'dev', '--', '--port', String(port), '--strictPort'], {
          cwd: ROOT,
          detached: true,
          stdio: 'ignore',
        })
  child.on('error', (e) => console.error('  ! 起 dev server 失败：' + e.message))
  child.unref()
  const waiter = `
    const net = require('net');
    const deadline = Date.now() + 60000;
    (function poll() {
      const s = net.createConnection({ host: '127.0.0.1', port: ${port} });
      s.on('connect', () => { s.destroy(); process.exit(0); });
      s.on('error', () => { s.destroy();
        if (Date.now() > deadline) process.exit(1);
        setTimeout(poll, 500);
      });
    })();
  `
  const r = spawnSync(process.execPath, ['-e', waiter], { stdio: 'ignore', timeout: 90000 })
  if (r.status !== 0) throw new Error(`等 dev server 起来超时（${url}）。手动跑 npm run dev 之后再用 --no-start。`)
  console.log('· dev server 就绪')
}

/** Playwright 只在 npm 的 npx 缓存里（这个工程不装 puppeteer，也不该多一个依赖）。 */
function loadPlaywright() {
  const candidates = [
    join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx', '9833c18b2d85bc59', 'node_modules', 'playwright'),
    join(ROOT, 'node_modules', 'playwright'),
  ]
  for (const c of candidates) {
    if (existsSync(c)) return require(c)
  }
  // 兜底：让 node 自己去找（万一装在别处）
  try {
    return require('playwright')
  } catch (e) {
    throw new Error(
      '找不到 playwright。它不在项目的依赖里（有意为之：scripts/shots.mjs 用的是系统 Chrome）。\n' +
        `试过：${candidates.join(' / ')}`
    )
  }
}

/**
 * 三次采样之间的差异。
 *
 * 为什么要三次而不是两次：**只比两次会把"页面还在加载"记成"静置变化"**。
 * 异步数据落地（骨架屏 → 内容）、逐字输出收尾都发生在 2.4s 内，
 * 只采两点时它们全部落在窗口里，/profile 一页报了 322 条"静置变化"（第一版）。
 * 取"窗口 A 内变过、窗口 B 内也还在变"的交集，剩下的才是**持续**在变的东西
 * —— 也就是反例表真正点名的数字滚动 / 自动轮播。
 * 一次性变化不是不管：它单独报一条 info 级提示，写清"这次变化像是加载收尾"。
 */
function segmentSorted(a) {
  const text = new Map()
  const geo = new Map()
  for (const t of a.texts) if (!text.has(t.sel)) text.set(t.sel, t)
  for (const g of a.geos) if (!geo.has(g.sel)) geo.set(g.sel, g)
  return { text, geo }
}

function diffSamples(a, b) {
  const A = segmentSorted(a)
  const B = segmentSorted(b)
  const nDiff = a.texts.length - b.texts.length
  const changed = []
  if (Math.abs(nDiff) > 8) {
    return {
      unstable: true,
      nDiff,
      textChanged: [],
      moved: [],
      detail: `文本节点数从 ${a.texts.length} 变成 ${b.texts.length}（差 ${nDiff}）——` +
        `页面在这 1.2s 里自己增删了节点，按序号比对不可靠，本条不予判定`,
    }
  }
  for (let i = 0; i < Math.min(a.texts.length, b.texts.length); i++) {
    const x = a.texts[i]
    const y = b.texts[i]
    if (x.text !== y.text) changed.push({ sel: y.sel, cls: y.cls, from: x.text.slice(0, 60), to: y.text.slice(0, 60) })
  }
  const moved = []
  for (let i = 0; i < Math.min(a.geos.length, b.geos.length); i++) {
    const x = a.geos[i]
    const y = b.geos[i]
    if (x.x !== y.x || x.y !== y.y || x.w !== y.w || x.h !== y.h) {
      moved.push({ sel: y.sel, from: `${x.x},${x.y} ${x.w}×${x.h}`, to: `${y.x},${y.y} ${y.w}×${y.h}` })
    }
  }
  return { unstable: false, nDiff, textChanged: changed, moved }
}

/**
 * 取两个窗口的**交集**：两次都在变的才判定为"持续在变"。
 * 交集的键用 `描述符+变化内容`，而不是纯描述符 —— 同一个元素在两个窗口里
 * 从 A→B、再从 B→C，要算同一处持续变化，不能被去重掉。
 */
function intersectSettle(dA, dB) {
  if (dA.unstable || dB.unstable) {
    return {
      unstable: true,
      textChanged: [],
      moved: [],
      detail: [dA.unstable ? dA.detail : '', dB.unstable ? dB.detail : ''].filter(Boolean).join('；'),
    }
  }
  const key = (x) => `${x.sel}::${x.from}::${x.to}`
  const bText = new Set(dB.textChanged.map(key))
  const bMoved = new Set(dB.moved.map(key))
  return {
    unstable: false,
    textChanged: dA.textChanged.filter((x) => bText.has(key(x))),
    moved: dA.moved.filter((x) => bMoved.has(key(x))),
    // 只在一个窗口里出现的变化 = 一次性（加载/流式收尾），交给调用方当提示
    oneShot: dA.textChanged.length + dA.moved.length - dA.textChanged.filter((x) => bText.has(key(x))).length - dA.moved.filter((x) => bMoved.has(key(x))).length,
  }
}

/* ===========================================================================
 * 七、判定
 * ======================================================================== */
const findings = [] // { level: 'fail'|'warn', route, kind, what, detail }
const notes = []

/** 把每一类发现整理成"路由 / 选择器 / 实测值 / 为什么 / 怎么修" */
function fail(route, kind, what, detail, fix, evidence) {
  findings.push({ level: 'fail', route, kind, what, detail, fix, evidence })
}
function warn(route, kind, what, detail, fix, evidence) {
  findings.push({ level: 'warn', route, kind, what, detail, fix, evidence })
}

/**
 * 运行时动画分类。
 * 没登记的动画 = 失败 —— 这条纪律逼着"新加动画"必须先回答 §6 第 8 问。
 * 名字里带 inflight 的（例如 `chat-caret`）已经登记过；这里只判登记表。
 */
function classifyRunning(route, running) {
  const seen = new Set()
  for (const a of running) {
    if (a.name === '__probe_error__') {
      warn(route, '禁用动效', 'getAnimations() 探测失败', a.kind, '换一个 Chromium 版本或改用 CSS 静态判据', a)
      continue
    }
    const name = normalizeAnimName(a.name)
    if (!name || name === 'none') {
      // 过渡（CSSTransition）没有 animationName。它是"过渡"而不是"关键帧动画"：
      // 过渡通常由用户动作触发，但也可能是自动播放的进场 —— 报成待人工判断。
      const key = `transition:${a.on}`
      if (seen.has(key)) continue
      seen.add(key)
      warn(
        route,
        '禁用动效',
        `加载后有过渡在跑：${a.on}`,
        `duration=${a.duration}ms iterations=${a.iterations}（${a.kind}，没有 animationName）`,
        '确认它是用户动作触发的；若是"一进页面自己播"，改成状态驱动的过渡',
        a
      )
      continue
    }
    if (ANIM_ALLOWED[name]) continue
    if (ANIM_VIOLATION[name]) {
      const key = `v:${name}`
      if (seen.has(key)) continue
      seen.add(key)
      fail(
        route,
        '禁用动效',
        `加载后就在跑 ${name}`,
        `${ANIM_VIOLATION[name]}；作用在 ${a.path}；duration=${a.duration}ms iterations=${a.iterations}`,
        `删掉这条动画，或把它绑到用户动作上（点开/滚动/输入才发生）；` +
          `若它确实承载状态，就在 scripts/check-design.mjs 的 ANIM_ALLOWED 里登记并写明"这里发生了什么"`,
        { animation: name, on: a.path, duration: a.duration, iterations: a.iterations }
      )
      continue
    }
    const key = `u:${name}`
    if (seen.has(key)) continue
    seen.add(key)
    fail(
      route,
      '禁用动效',
      `加载后在跑未登记的动画 ${name}`,
      `作用在 ${a.path}；duration=${a.duration}ms iterations=${a.iterations}`,
      `在 ANIM_ALLOWED（承载状态）或 ANIM_VIOLATION（装饰）里登记它，并写明理由 —— ` +
        `§6 第 8 问：这一处动效回答"这里发生了什么"？`,
      { animation: name, on: a.path, duration: a.duration }
    )
  }
}

function judgeRoute(r, m, settle) {
  const route = r.route
  const kind = KIND_OF(r.path)
  const need = REQUIRED_HITS[kind]
  const row = {
    route,
    name: r.name,
    kind,
    kindLabel: KIND_LABEL[kind],
    touchUnder36: m.touch.under36.length,
    touchUnder44: m.touch.under44Primary.length,
    anim: m.running.filter((a) => a.name && a.name !== '__probe_error__').length,
    settleChanged: 0,
    settleGeoChanged: 0,
    overflowClip: m.overflow.clip.length,
    overflowScroll: m.overflow.scroll.length,
    landingHits: m.landingHits,
    landingNeed: need,
    // 落点判据只对数据/文档/入口/工具页成立；对话页按"过程可见"判、状态页按三问判。
    landingApplicable: kind !== 'dialogue' && kind !== 'state',
    landingMissing: Object.entries(m.landing).filter(([, v]) => !v.hit).map(([, v]) => v.label),
    dialogue: kind === 'dialogue' ? m.dialogue : undefined,
    sizes: Object.keys(m.sizes).map(Number).sort((a, b) => a - b),
    weights: Object.keys(m.weights).sort(),
    rootScroll: m.overflow.rootScroll,
    ok: true,
  }

  /* ---- 触控目标 ---- */
  for (const t of m.touch.under36) {
    fail(
      route,
      '触控目标',
      `<36px 的控件 ${t.sel}`,
      `${t.w}×${t.h}px「${t.text}」`,
      '把可点区域撑到 ≥36（卡片内次要控件）/ ≥44（主要动作）：加 padding 或 min-height，不要放大图标',
      t
    )
  }
  for (const t of m.touch.under44Primary) {
    warn(
      route,
      '触控目标',
      `主要动作只有 ${t.h}px 高：${t.sel}`,
      `${t.w}×${t.h}px「${t.text}」（判定依据：${t.why}）`,
      '主要动作按 44px 撑高（DESIGN-lANGUAGE 口径）；项目 DESIGN.md 写的是 42px，两者取严',
      t
    )
  }

  /* ---- 禁用动效 ---- */
  classifyRunning(route, m.running)

  /* ---- 静置变化 ---- */
  row.settleUnstable = !!settle.unstable
  row.settleLoadingTail = settle.textChanged.length || settle.moved.length
  row.settleChanged = settle.textChanged.length + settle.moved.length
  if (settle.unstable) {
    warn(route, '静置变化', '静置检查结论不可靠', settle.detail, '让它静下来再量，或把这段变化收进 aria-live 区域', settle)
  } else {
    for (const c of settle.textChanged.slice(0, 8)) {
      fail(
        route,
        '静置变化',
        `静置 1.2s 文本自己在变：${c.sel}`,
        `「${c.from}」→「${c.to}」（两个连续 1.2s 窗口里都在变）`,
        '反例表：数字滚动 / 自动轮播 / 指示线滑动都属装饰。' +
          '若是真·进行时（正在生成、正在推进），把它放进 aria-live 区域并在报告里说明；否则改成状态驱动',
        c
      )
    }
    for (const c of settle.moved.slice(0, 6)) {
      fail(
        route,
        '静置变化',
        `静置 1.2s 位置自己在动：${c.sel}`,
        `${c.from} → ${c.to}`,
        '持续位移 = 自动轮播 / 持续背景运动（§7.3 硬禁止）。若是用户动作引起的过渡，确认它在静置时不跑',
        c
      )
    }
    if (row.settleLoadingTail) {
      notes.push(`${route}：第一次采样窗口内有 ${row.settleLoadingTail} 处变化、第二个窗口没有 —— 像是加载/流式收尾，已按"一次性"处理（不计违规）`)
    }
  }

  /* ---- 横向溢出 ---- */
  if (m.overflow.rootScroll.scrollWidth > m.overflow.rootScroll.clientWidth) {
    fail(
      route,
      '横向溢出',
      '页面出现横向滚动条',
      `documentElement.scrollWidth=${m.overflow.rootScroll.scrollWidth} > clientWidth=${m.overflow.rootScroll.clientWidth}`,
      '找出超出的一列（下方 clip/scroll 列表给的就是候选），改成换行或给容器 overflow-x:auto',
      m.overflow.rootScroll
    )
  }
  for (const o of m.overflow.clip) {
    fail(
      route,
      '横向溢出',
      `内容被裁掉（祖先 overflow-x: hidden/clip）：${o.sel}`,
      `scrollWidth=${o.scrollWidth} > clientWidth=${o.clientWidth}（超出 ${o.over}px）「${o.text}」`,
      '这是"看不见的内容"：改宽度/换行，或让容器可横向滚动（overflow-x:auto）',
      o
    )
  }
  for (const o of m.overflow.scroll) {
    warn(
      route,
      '横向溢出',
      `横向可滚容器（设计如此？）：${o.sel}`,
      `scrollWidth=${o.scrollWidth} > clientWidth=${o.clientWidth}（超出 ${o.over}px）`,
      '确认它是刻意的（如方向对照表最小宽 760px、仅在自身容器内滚动）；否则改成换行',
      o
    )
  }

  /* ---- 落点 ---- */
  if (kind === 'dialogue') {
    const d = m.dialogue
    const checks = [
      ['主体在场', d.presence, '.dialogue-presence'],
      ['交接说明默认可见', d.handoff, '.chat-handoff'],
      ['结论块', d.conclusion, '.chat-block--lead / .chat-answer'],
      ['后续问题可点', d.follow, '.dialogue-options / .ws-chat-options'],
      ['输入区', d.composer, '.ws-composer'],
    ]
    for (const [label, ok, sel] of checks) {
      if (!ok) {
        fail(
          route,
          '对话页过程可见',
          `缺项：${label}`,
          `页面上找不到 ${sel}（在场状态类：${d.presenceStates || '无'}）`,
          'DESIGN-LANGUAGE §3：对话页的活 = 过程可见，五问缺一不可',
          { label, selector: sel }
        )
      }
    }
    notes.push(`${route}：对话页五问 —— ` + checks.map(([l, ok]) => `${l}=${ok ? '有' : '缺'}`).join(' · '))
  } else if (kind === 'state') {
    /**
     * 状态页（404）**不套四个落点**，理由与对话页同一类：
     * DESIGN-LANGUAGE §4 的落点讲的是"数据页怎么把静态信息组织活"，
     * 而 404 页的设计目标是"说清发生了什么 + 给一条退路"，它压根没有那批数据。
     * 用同一把尺子量，只会逼人往 404 上堆假结构（第一版就是这样把它判成 1/2）。
     * 换成三条与页面目的对应的检查 —— 缺哪条都是真的缺：
     */
    const hasWhy = m.statePage.hasExplain
    const hasExit = m.statePage.hasExit
    const exits = [['说清是什么情况', m.statePage.hasTitle], ['给一句解释', hasWhy], ['给一条退路', hasExit]]
    for (const [label, ok] of exits) {
      if (!ok) {
        fail(route, '状态页', `缺项：${label}`, '这一页没做到"说清情况 + 给一条退路"', '补齐"什么情况 / 为什么 / 怎么走"三件事', { label })
      }
    }
    notes.push(`${route}：状态页三问 —— ` + exits.map(([l, ok]) => `${l}=${ok ? '有' : '缺'}`).join(' · '))
    if (m.touch.under36.length >= 3) {
      const h = m.touch.under36[0].h
      notes.push(
        `${route}：这一页有 ${m.touch.under36.length} 个 <36px 的可点链接（实测 ${m.touch.under36[0].w}×${h}）——` +
          `它们是"现在有效的地址"那一列，是这一页**唯一的实际功能**。`
      )
    }
  } else if (m.landingHits < need) {
    fail(
      route,
      '四个落点',
      `只命中 ${m.landingHits}/${need} 个落点`,
      `缺：${row.landingMissing.join('、')}；组织权控件种类：${JSON.stringify(m.landing.organize.kinds || {})}`,
      '按 DESIGN-LANGUAGE §4 把缺的那一类做出来（结构显形 / 组织权 / 溯源 / 状态显形）；' +
        '注意：组织权要真能重组，不是"换个列表内容"的 tab',
      { landing: m.landing }
    )
  }

  /**
   * 落点的**测量口径**必须写在报告里，否则读的人不知道这个数字是什么状态下量的。
   * 这一条对本工程的 `/tools` 尤其重要：它首屏只渲染"读取工具目录"按钮，
   * 目录、空态、状态条都是点下去之后才有 —— 所以 0/2 里有一部分是"还没取数"。
   * 门禁不做点击（那会把"测量"变成"操作"，且脚本要注入动作才知道点什么），
   * 所以这里如实标注，并把"是否需要点一下才显形"留给作者判断。
   */
  if (kind === 'doc' || kind === 'tool' || kind === 'entry') {
    notes.push(
      `${route}（${KIND_LABEL[kind]}）：落点是在**加载完成、未做任何点击**的状态下量的；` +
        `本类型页有一部分内容要点一下才出现（例如 /tools 的目录与状态条），报告只反映首屏。`
    )
  }

  /* ---- 字号 / 字重（只看"一屏几档"，不重复令牌登记） ---- */  if (row.sizes.length > 6) {
    warn(
      route,
      '字号档位',
      `这一屏实测出现 ${row.sizes.length} 档字号`,
      row.sizes.join('/'),
      'DESIGN.md：一屏数得出 7–9 个字号就是"不够清晰、乱糟糟"的根因；收敛到 5–6 档',
      { sizes: m.sizes }
    )
  }
  const fsOut = row.sizes.filter((s) => ![12, 14, 16, 20, 30, 38].includes(s))
  if (fsOut.length) {
    warn(route, '字号档位', `出现登记档位之外的字号 ${fsOut.join('/')}`, `实测全部：${row.sizes.join('/')}`, '登记档位见 DESIGN.md frontmatter 与 tokens.css 的 --fs-*', { sizes: fsOut })
  }
  const fwOut = row.weights.filter((w) => !['400', '500', '600', '700'].includes(w))
  if (fwOut.length) {
    warn(route, '字重档位', `出现四档之外的字重 ${fwOut.join('/')}`, `实测全部：${row.weights.join('/')}`, '字重只有 400/500/600/700', { weights: fwOut })
  }

  row.ok = !findings.some((f) => f.level === 'fail' && f.route === route)
  return row
}

/* ===========================================================================
 * 八、主流程
 * ======================================================================== */
async function main() {
  const started = Date.now()
  /**
   * 人类可读的进度一律走 stderr；`--json` 时 stdout 必须只有 JSON 本身。
   * 不这么做的话 `--json > out.json` 拿到的文件前面挂着进度行，JSON.parse 必炸。
   */
  const log = JSON_OUT ? (...a) => console.error(...a) : (...a) => console.log(...a)
  log(`设计语言门禁 · ${BASE} · ${WIDTH}×${HEIGHT}\n`)

  const scan = staticScan()
  notes.push(`@keyframes 全仓库 ${scan.keyframes.size} 个：允许 ${[...scan.keyframes.keys()].filter((k) => ANIM_ALLOWED[k]).length} · 命中禁令 ${[...scan.keyframes.keys()].filter((k) => ANIM_VIOLATION[k]).length} · 未登记 ${[...scan.keyframes.keys()].filter((k) => !ANIM_ALLOWED[k] && !ANIM_VIOLATION[k]).length}`)
  log('── 静态扫描（已剥注释）──')
  for (const b of scan.banned) {
    fail('(静态)', '禁用词', b.label, `${b.rel} 命中 /${b.evidence}/`, '反例表 / §7 硬禁止项：删掉实现，或证明它承载状态', b)
  }
  if (!scan.banned.length) log('  ✓ 粒子 / 自动轮播 / setInterval 的实现都没匹配到')
  const countUp = countUpAudit(walkSource(join(ROOT, 'src')))
  for (const d of countUp.decl) {
    if (countUp.uses.length === 0) {
      fail(
        '(静态)',
        '禁用动效',
        `${d.name} 定义了但全站没人调用`,
        `${d.rel} 里 ${d.name}() 的实现是从 0 滚到目标值的数字滚动，而 src 里没有任何 import / 调用`,
        '二选一，别留着：① 删掉实现（反例表：数字滚动是装饰）；' +
          '② 若确认要做，就在 ANIM_ALLOWED 之外单独登记"它回答了什么"并真用起来',
        { decl: d }
      )
    } else {
      notes.push(`${d.name} 被 ${countUp.uses.length} 处调用：${countUp.uses.map((u) => u.rel).join('、')}`)
    }
  }
  log(`  · 数字滚动：定义 ${countUp.decl.length} 处 · 调用 ${countUp.uses.length} 处（判据是"定义了有没有人用"，不是有没有出现这个词）`)
  log(`  · 含 accent 光晕的 box-shadow：${scan.glow.length} 处（焦点环与 select 高亮属允许项，逐条看）`)
  for (const k of [...scan.keyframes.keys()]) {
    if (!ANIM_ALLOWED[k] && !ANIM_VIOLATION[k]) {
      warn('(静态)', '禁用动效', `@keyframes ${k} 未登记`, `${scan.keyframes.get(k)}（该名字只在定义处出现，运行时不一定被用到）`, '在 ANIM_ALLOWED / ANIM_VIOLATION 里登记', { keyframes: k, file: scan.keyframes.get(k) })
    }
  }
  log('')

  if (!(await portOpen(BASE))) {
    if (NO_START) {
      console.error(`✗ ${BASE} 连不上，而且带了 --no-start。先跑 npm run dev。`)
      process.exit(2)
    }
    startDevServer(BASE)
  } else {
    log(`· ${BASE} 已在运行，直接用\n`)
  }

  const { chromium } = loadPlaywright()
  let browser
  try {
    browser = await chromium.launch({
      args: ['--disable-gpu', '--no-sandbox', '--no-first-run', '--hide-scrollbars'],
    })
  } catch (e) {
    console.error('✗ Chromium 起不来：' + e.message)
    console.error('  （playwright 装好了但浏览器二进制没下过：npx playwright install chromium）')
    process.exit(2)
  }

  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT },
    deviceScaleFactor: 1,
    reducedMotion: 'no-preference',
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(`${page.url()} :: ${e.message}`))
  page.on('console', (msg) => {
    if (msg.type() === 'error') pageErrors.push(`${page.url()} :: console.error ${msg.text()}`)
  })

  const routes = (ONLY_ROUTE ? ROUTES.filter((r) => r.path === ONLY_ROUTE) : ROUTES).concat(
    ONLY_ROUTE ? [] : [NOT_FOUND_ROUTE]
  )
  const rows = []
  const detail = []

  for (const r of routes) {
    // 带 ?as=mid：路由守卫在没有登录态时会静默落到演示账号，但显式带上更稳，
    // 也避免"未登录 → 弹回门户"那条路径在审计里混进来。
    const url = `${BASE}/${r.route}${r.route.includes('?') ? '&' : '?'}as=mid`
    try {
      await page.goto(url, { waitUntil: 'load', timeout: 20000 })
    } catch (e) {
      fail(r.route, '加载', '页面没加载成功', e.message, '先修加载错误', {})
      rows.push({ route: r.route, name: r.name, kind: KIND_OF(r.path), loadFailed: true, ok: false })
      continue
    }
    // 等挂载 + 首屏动画播完（1.2s 也是静置检查的采样间隔，顺手复用）
    await page.waitForTimeout(1200)
    let m
    try {
      m = await page.evaluate(probeInPage)
    } catch (e) {
      fail(r.route, '探测', '页内探测抛错', e.message, '检查页面是否有无限循环或超大 DOM', {})
      rows.push({ route: r.route, name: r.name, kind: KIND_OF(r.path), probeFailed: true, ok: false })
      continue
    }
    /**
     * 静置检查要**三个**采样点、两个窗口：
     *   A = [t0, t0+1.2s]，B = [t0+1.2s, t0+2.4s]；只把"两个窗口里都在变"的算违规。
     * 一次性变化（异步数据落地、逐字收尾）只记 info，不进违规 ——
     * 只比两个点会把它们全算成"静置变化"（第一版 /profile 因此报了 322 条）。
     */
    const s0 = await page.evaluate(sampleInPage)
    await page.waitForTimeout(1200)
    const s1 = await page.evaluate(sampleInPage)
    await page.waitForTimeout(1200)
    const s2 = await page.evaluate(sampleInPage)
    const dA = diffSamples(s0, s1)
    const dB = diffSamples(s1, s2)
    const settle = intersectSettle(dA, dB)

    const before = findings.length
    const row = judgeRoute(r, m, settle)
    rows.push(row)
    detail.push({
      route: r.route,
      kind: row.kind,
      landing: m.landing,
      orgKinds: m.landing.organize.kinds,
      touchSamples: m.touch.under36.slice(0, 6),
      touch44Samples: m.touch.under44Primary.slice(0, 6),
      runningAnimations: m.running,
      settleWindowA: { texts: dA.textChanged.length, moved: dA.moved.length, unstable: dA.unstable },
      settleWindowB: { texts: dB.textChanged.length, moved: dB.moved.length, unstable: dB.unstable },
      overflowClip: m.overflow.clip,
      overflowScroll: m.overflow.scroll,
      dialogue: m.dialogue,
      sizes: m.sizes,
      weights: m.weights,
    })
    row.findingsAdded = findings.length - before
    // 落点一栏：对话页与状态页**不按落点判**（判据见 judgeRoute），
    // 显示 4/0 或 1/2 会让人以为"没达标"，所以直接写"不适用"。
    const landingCell = row.kind === 'dialogue' || row.kind === 'state' ? '不适用' : `${row.landingHits}/${row.landingNeed}`
    log(
      `${r.route.padEnd(12)} ${row.kindLabel.padEnd(5)} 触控<36:${String(row.touchUnder36).padEnd(3)} <44:${String(row.touchUnder44).padEnd(3)} 禁用动效:${String(row.anim).padEnd(3)} 静置变化:${String(row.settleChanged).padEnd(3)} 裁切:${String(row.overflowClip).padEnd(3)} 可滚:${String(row.overflowScroll).padEnd(3)} 落点:${landingCell}${row.ok ? '' : '  ✗'}`
    )
  }

  await browser.close()

  for (const e of [...new Set(pageErrors)]) {
    fail('(全站)', 'JS 异常', '页面报错', e, '有报错时页面可能只渲染了一半，先修错再谈设计', {})
  }

  const fails = findings.filter((f) => f.level === 'fail')
  const warns = findings.filter((f) => f.level === 'warn')

  /* ------------------------------- 输出 ------------------------------- */
  const elapsed = ((Date.now() - started) / 1000).toFixed(1)
  if (JSON_OUT) {
    console.log(
      JSON.stringify(
        {
          meta: {
            url: BASE,
            width: WIDTH,
            height: HEIGHT,
            elapsedSec: Number(elapsed),
            routesDiscovered: ROUTES.length,
            dynamicRoutes: DYNAMIC_ROUTES,
            thresholds: { touchHard: 36, touchPrimary: 44, requiredHits: REQUIRED_HITS },
            pageKind: PAGE_KIND,
            exitCode: fails.length ? 1 : 0,
          },
          rows,
          detail,
          staticScan: {
            keyframes: Object.fromEntries(scan.keyframes),
            banned: scan.banned,
            glow: scan.glow,
            allowed: ANIM_ALLOWED,
            violations: ANIM_VIOLATION,
          },
          findings,
          notes,
        },
        null,
        2
      )
    )
  } else {
    console.log('\n════════ 发现（按严重度）════════')
    if (!fails.length) console.log('  ✓ 没有违规')
    const byKind = new Map()
    for (const f of fails) {
      if (!byKind.has(f.kind)) byKind.set(f.kind, [])
      byKind.get(f.kind).push(f)
    }
    for (const [kind, list] of byKind) {
      console.log(`\n── ${kind}（${list.length}）──`)
      for (const f of list) {
        console.log(`  ✗ [${f.route}] ${f.what}`)
        console.log(`      实测：${f.detail}`)
        console.log(`      为什么是问题：${whyItMatters(f.kind)}`)
        console.log(`      怎么修：${f.fix}`)
      }
    }
    if (warns.length) {
      console.log(`\n════════ 待人工判断（${warns.length}，不影响退出码）════════`)
      for (const f of warns) {
        console.log(`  ! [${f.route}] ${f.kind} · ${f.what}`)
        console.log(`      ${f.detail}`)
      }
    }
    console.log('\n════════ 汇总 ════════')
    console.log(`路由 ${rows.length} 条（router.ts 里解析出 ${ROUTES.length} 条静态 + ${DYNAMIC_ROUTES.length} 条动态兜底） · 视口 ${WIDTH}×${HEIGHT} · 耗时 ${elapsed}s`)
    console.log(`违规 ${fails.length} 条 · 待人工判断 ${warns.length} 条`)
    const tally = {}
    for (const f of fails) tally[f.kind] = (tally[f.kind] || 0) + 1
    console.log('分类：' + (Object.entries(tally).map(([k, v]) => `${k}=${v}`).join(' · ') || '—'))
    console.log('提示：')
    for (const n2 of notes) console.log('  · ' + n2)
  }

  process.exit(fails.length ? 1 : 0)
}

/** 给报告里的每条发现配一句"为什么这是问题"，免得读的人只看到数字。 */
function whyItMatters(kind) {
  const M = {
    触控目标: '手指点不中就等于这个功能不存在 —— 手机上 36px 以下的可点区域错误率明显上升（WCAG 2.5.5 / 2.5.8 的由来）。',
    禁用动效: 'DESIGN-LANGUAGE 反例表：不影响截屏结果的动效全是装饰；§7.3 明文禁止持续背景运动、粒子、发光边框、自动轮播。',
    静置变化: '不做任何操作时页面自己在动，就是"数字滚动 / 自动轮播"这一类装饰；真正的进行时应当放在 aria-live 区域里并说明。',
    横向溢出: '被裁掉的内容用户永远看不到（不是"要滑一下"，是根本滑不到）；页面级横向滚动条在手机上会让整页失去稳定感。',
    四个落点: 'DESIGN-LANGUAGE §4：数据页的活 = 组织可见。落点不足的页面，截屏测试一定不丢信息 —— 也就是"死的"。',
    对话页过程可见: 'DESIGN-LANGUAGE §3：对话页的活 = 过程可见。五问缺一，这一页就退回"单列文字流"。',
    禁用词: '§7.3 硬禁止项；实现存在就意味着有人在往这个方向做。',
    'JS 异常': '页面报错时 Vue 可能只挂载了一半，之后所有测量都不可信。',
    加载: '页面没加载成功，本题无数据 —— 不能当成"通过"。',
    探测: '页内探测抛错，通常意味着页面里有无限循环或超大 DOM。',
    字号档位: '字号层级是"清晰 / 乱糟糟"的第一变量（DESIGN.md 记录了 11–16 六档挤在 6px 内的那次收敛）。',
    字重档位: '字重档位失控会让标题与正文抢重量，主次就没了。',
  }
  return M[kind] || '见 DESIGN-LANGUAGE.md'
}

main().catch((e) => {
  console.error('✗ 门禁自己崩了：' + (e && e.stack ? e.stack : e))
  process.exit(2)
})
