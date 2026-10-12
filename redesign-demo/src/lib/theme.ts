/**
 * 皮肤系统。
 *
 * **三条轴**，只覆盖令牌、**不动任何结构**：
 *   theme   浅色 light / 深色 dark / 跟随系统 system
 *   accent  主色 blue（河大校徽蓝）/ red（河大校色红）
 *   style   风格 plain（极简）/ soft（柔和）/ dense（紧凑）
 *
 * 写在 <html> 上的 data-* 属性，CSS 里由 tokens.css 接管。
 * 组件一行都不用改 —— 这就是三层令牌里"语义层"存在的意义。
 *
 * 【曾经还有第四条轴：动效（完整 / 克制），2026-10-11 删除】
 * 删它的三个理由：
 *   1. 它和 `prefers-reduced-motion` 是同一件事的两种说法，而后者是无障碍刚需 ——
 *      把无障碍设置当风格选项卖（"克制"），是拿别人的刚需做皮肤，口径本来就不干净；
 *   2. 它带来的差别只有一组时长令牌，用户在控制台上几乎看不出变化，
 *      属于"一条看起来像坏了"的轴；
 *   3. 它还把门户搞白过：`data-motion="calm"` 下门户整页绘制成纯白（DOM 完好、零报错）。
 *      一个既看不出用、又会出致命 bug 的开关，删掉比修好更对。
 * 减少动效从此只有一个来源：系统的 prefers-reduced-motion。
 *
 * 首屏防闪（FOUC）在 index.html 的内联脚本里，不在这里：
 * 那一段必须在 CSS 之前、在任何 JS 之前跑完。
 */

import { reactive, readonly } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'
export type Accent = 'blue' | 'red'
export type StyleId = 'plain' | 'soft' | 'dense'

const KEY = 'zhiyin-demo-skin'

interface SkinState {
  theme: ThemeMode
  accent: Accent
  style: StyleId
  systemDark: boolean
}

const state = reactive<SkinState>({
  theme: 'system',
  accent: 'blue',
  style: 'plain',
  systemDark: false,
})

const media =
  typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function resolved(): 'light' | 'dark' {
  if (state.theme === 'system') return state.systemDark ? 'dark' : 'light'
  return state.theme
}

function apply() {
  if (typeof document === 'undefined') return
  const el = document.documentElement
  el.dataset.theme = resolved()
  el.dataset.accent = state.accent
  el.dataset.style = state.style
  el.style.colorScheme = resolved()
}

function persist() {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({
        theme: state.theme,
        accent: state.accent,
        style: state.style,
      }),
    )
  } catch {
    /* 隐私模式下 localStorage 会抛：皮肤不是关键功能，安静地用默认值 */
  }
}

let switching = false

/**
 * 切皮肤时的过渡 —— 用"先禁过渡、再整体淡入"，**不是**给颜色加全局补间。
 *
 * 为什么不用"给所有元素挂 transition"：那样每个元素会按自己的时长各自跑，
 * 视觉上像打翻的调色盘；而且会把之后每一次 hover 都拖成同样的慢速动画。
 * 正确做法（调研里可核实的那条）：切换瞬间禁用一切过渡 → 换属性 → 整页 160ms 淡入。
 *
 * 另外 `color-scheme` 在规范里的 animation type 是 discrete（不可插值），
 * 所以滚动条与表单控件永远是瞬变 —— 整页淡入正是为了让"一起变"看起来是一个动作。
 */
function withSwitch(fn: () => void) {
  if (typeof document === 'undefined') return fn()
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduce || switching) return fn()

  switching = true
  const el = document.documentElement
  el.classList.add('is-skin-switching', 'is-skin-fading')
  fn()
  // 双 rAF：确保新属性已经落到样式上，再撤掉"禁过渡"并让淡入开始
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      el.classList.remove('is-skin-switching')
      window.setTimeout(() => {
        el.classList.remove('is-skin-fading')
        switching = false
      }, 180)
    }),
  )
}

export const skin = {
  state: readonly(state) as Readonly<SkinState>,

  init() {
    if (typeof window === 'undefined') return
    try {
      const raw = localStorage.getItem(KEY)
      if (raw) {
        const saved = JSON.parse(raw) as Partial<SkinState>
        if (saved.theme === 'light' || saved.theme === 'dark' || saved.theme === 'system') {
          state.theme = saved.theme
        }
        if (saved.accent === 'blue' || saved.accent === 'red') state.accent = saved.accent
        if (saved.style === 'plain' || saved.style === 'soft' || saved.style === 'dense') {
          state.style = saved.style
        }
      }
    } catch {
      /* 存的东西坏了就用默认值，不拦启动 */
    }

    state.systemDark = media?.matches ?? false

    /*
     * 地址栏里的皮肤参数：?theme=dark&accent=red&style=dense
     * 优先级 ?query > localStorage > 系统 > 默认档；**query 不落盘** ——
     * 它只是"给别人发一条打开即某套皮肤的链接"，不该覆盖对方自己的选择。
     *
     * 注意：这是 hash 路由，参数在 `#` 之后（`#/home?theme=dark`），
     * `location.search` 是空的 —— 必须连 hash 里的查询串一起读。
     * 第一次就是踩了这个坑：参数怎么传都无效，页面纹丝不动而且没有任何报错。
     */
    const q = new URLSearchParams(window.location.search)
    const hashQuery = window.location.hash.split('?')[1]
    if (hashQuery) new URLSearchParams(hashQuery).forEach((v, k) => q.set(k, v))

    const qTheme = q.get('theme')
    if (qTheme === 'light' || qTheme === 'dark' || qTheme === 'system') state.theme = qTheme
    const qAccent = q.get('accent')
    if (qAccent === 'blue' || qAccent === 'red') state.accent = qAccent
    const qStyle = q.get('style')
    if (qStyle === 'plain' || qStyle === 'soft' || qStyle === 'dense') state.style = qStyle

    // 系统主题变化：只在用户"从没手动选过"时才跟随 ——
    // 否则用户手动切了浅色，系统一入夜就给他翻回去。
    media?.addEventListener('change', (e) => {
      state.systemDark = e.matches
      if (state.theme === 'system') withSwitch(apply)
    })

    // 多标签同步：另一个标签换了皮肤，这个也跟着换
    window.addEventListener('storage', (e) => {
      if (e.key !== KEY || !e.newValue) return
      try {
        const saved = JSON.parse(e.newValue) as Partial<SkinState>
        if (saved.theme) state.theme = saved.theme
        if (saved.accent) state.accent = saved.accent
        if (saved.style) state.style = saved.style
        apply()
      } catch {
        /* 别的标签写坏了不关我们的事 */
      }
    })

    // 打印时临时回浅色：暗色打印出来是一张黑纸，费墨且看不清
    window.addEventListener('beforeprint', () => {
      document.documentElement.dataset.theme = 'light'
    })
    window.addEventListener('afterprint', () => apply())

    apply()
  },

  setTheme(theme: ThemeMode) {
    withSwitch(() => {
      state.theme = theme
      persist()
      apply()
    })
  },

  setAccent(accent: Accent) {
    withSwitch(() => {
      state.accent = accent
      persist()
      apply()
    })
  },

  setStyle(style: StyleId) {
    withSwitch(() => {
      state.style = style
      persist()
      apply()
    })
  },

  reset() {
    withSwitch(() => {
      state.theme = 'system'
      state.accent = 'blue'
      state.style = 'plain'
      persist()
      apply()
    })
  },
}
