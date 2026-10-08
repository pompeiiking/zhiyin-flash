/*
 * 外观调配台 —— 全站外观的**唯一开关**（多轴）。
 *
 * 【为什么是多轴】
 *
 * "换一套样子"其实不是一件事，是一串互相独立的事：颜色、块的形、手感的反馈、
 * 排版的性格、角的处理、覆盖层怎么打开、线条是不是手绘。把它们挤成一条轴，
 * 用户只能选"整套"；拆成多条轴，他可以自己配 —— 这才是"调配台"。
 *
 * 每条轴 = 一个 `data-<轴>` 属性 + 一个 CSS 目录（`src/styles/<轴>/`）+ 下面 AXES 里的一段。
 *
 *   轴            属性              管什么                              选项
 *   配色 theme    data-theme        色、材质、质感、光标、动效节奏        4
 *   组件 ui       data-ui           形、密度、字号                       6
 *   交互 feedback data-feedback     反馈发生在哪一层（位移/描边/底色）    3
 *   排版 type     data-type         分节、行宽、对齐、段距                3
 *   形状 shape    data-shape        角的写法（手绘 / 直角）              2
 *   骨架 skeleton data-skeleton     覆盖层怎么打开（居中/抽屉/全幅）      3
 *   字体 font     data-font         字族与字形（手写/精修/衬线）          3
 *
 * 每条轴的**默认档都没有文件**（默认值就是 tokens.css 与 base.css 里今天的样子），
 * 也不写属性 —— 所以"不切"与改动前逐字一致，回退只有一条路：删掉属性。
 *
 * 【分工与优先级】
 *
 * 特异度全是 (0,1,1)，冲突时按 `base.css` 里的加载顺序定：主题 → 组件 → 交互 →
 * 排版 → 形状 → 骨架。守卫（`tests/test_theme_contract.py`）逐条钉着：
 * 每条轴只许声明自己那一类令牌（配色轴管色、组件轴管形/密度/字、交互/排版/形状/骨架
 * 这四条轴**一个自定义属性都不许声明**、字体轴只许声明 `--font-*`），
 * 且每条规则都必须挂在它自己的属性选择器下。
 *
 * 【谁来应用它】
 *
 * 首屏：`index.html` 里那段同步脚本（见文件末尾的 AX 表 —— 守卫会比对两处一致）。
 * 之后：这里。`applyOption()` 写属性 + 同步 `selection` + 抛事件。
 * 只在 JS 里落笔的消费方（ECharts 的 canvas、ClickSpark、rough-notation 的圈线）
 * 监听 `zhiyin:theme` 重读令牌。
 *
 * 【撤掉的那一条】
 *
 * 曾经还有一条"线条"轴（`data-draw`，手绘 ↔ 精确：改 roughjs 的抖动系数）。
 * 2026-10-08 撤掉：它的效果只出现在**门户地图**（以及报告里的趋势线）上 ——
 * 在控制台那屏点它，画面不会有任何变化，用户合理地判定"这条轴是坏的"。
 * 一条大部分屏幕上都没有反馈的轴，留着比去掉更糟。
 * 底下的能力还在（`lib/sketch.ts` 的 `setRoughnessScale`/`bumpSketch`、
 * tokens.css 的 `--sketch-rough`），只是暂时没有开关 —— 一处乘法，零成本。
 *
 * 【持久化】只写本机 localStorage（`zhiyin_<轴>`），不进账号；`?<轴>=<档>` 不落盘。
 *
 * 【为什么这个文件里有 vue】
 *
 * 它从"注册表 + 几个函数"长成了"外观的当前状态"：三处入口（右下角、账号面板、
 * 外观台）都要实时看到同一份选择。用 `reactive` 存这份状态，比让每个入口各记一份
 * 再用事件对齐要稳（那个坑本地已经踩过一次）。
 */

import { reactive } from 'vue'

export interface AxisOption {
  id: string
  name: string
  note: string
  /** 配色轴专用：三格色卡（桌面 / 纸面 / 强调） */
  swatch?: [string, string, string]
  /** 配色轴专用：是不是暗底（用来标「夜」） */
  dark?: boolean
}

export interface Axis {
  /** 轴 id：也是 localStorage 后缀、URL 参数名、`data-` 属性的后缀 */
  id: string
  /** 导航栏上的名字 */
  name: string
  /** 一句话说清这条轴在换什么 */
  note: string
  /** 选项；第一项必须是默认档（认不出的 id 一律落回它） */
  options: AxisOption[]
}

export const AXES: Axis[] = [
  {
    id: 'theme',
    name: '配色',
    note: '色、材质、质感、光标、动效节奏',
    options: [
      { id: 'sketch', name: '草稿台', note: '暖纸、记号笔绿、手写字（默认）', dark: false, swatch: ['#f4efe1', '#fffdf4', '#1f6b3d'] },
      { id: 'exam', name: '阅卷', note: '试卷白、印刷黑、一支阅卷红：把诊断当一次批改', dark: false, swatch: ['#edeef0', '#fbfbfc', '#bd2b24'] },
      { id: 'darkroom', name: '暗房', note: '安全灯下的显影：画像随证据一点点显出来', dark: true, swatch: ['#0b0b0c', '#141416', '#ffb43a'] },
      { id: 'transit', name: '线路图', note: '站牌与线路色：每一步都落在下一站', dark: true, swatch: ['#0e1113', '#15191c', '#3fd07a'] },
    ],
  },
  {
    id: 'ui',
    name: '组件',
    note: '形、密度、字号（字族归"字体"那条轴）',
    options: [
      { id: 'card', name: '卡片', note: '细边、柔影、中圆角（默认）' },
      { id: 'float', name: '浮片', note: '无边框、大圆角、重柔影，控件成药丸' },
      { id: 'sticker', name: '贴纸', note: '2px 墨边 + 偏右下的柔影，按下去压到桌面上' },
      { id: 'plain', name: '极简', note: '没有框也没有影，只靠底色与留白' },
      { id: 'dense', name: '紧凑', note: '间距与字号各收一档，一屏多看几条' },
      { id: 'roomy', name: '舒展', note: '间距行高放大，适合把屏幕转过去讲' },
    ],
  },
  {
    id: 'feedback',
    name: '交互',
    note: '反馈发生在哪一层：位移、描边，还是底色 · 悬停或按下时才看得见',
    options: [
      { id: 'rise', name: '抬升', note: '悬停抬起 1px、按下压回（默认）' },
      { id: 'edge', name: '描边', note: '块不动，只有线与字的深浅在变' },
      { id: 'fill', name: '填色', note: '线不动，只有底色在变；选中用左竖条' },
    ],
  },
  {
    id: 'type',
    name: '排版',
    note: '分节、行宽、对齐、段距 · 主要在报告页这种长文里',
    options: [
      { id: 'plain', name: '常规', note: '就是今天的样子（默认）' },
      { id: 'outline', name: '分节', note: '标题上有分节线，留白上下有别，长文好扫' },
      { id: 'read', name: '阅读体', note: '行宽收窄、行距放开、页首标题居中' },
    ],
  },
  {
    id: 'shape',
    name: '形状',
    note: '角的写法：手绘（四个角长短不一）· 只管角，不管圆角多大',
    options: [
      { id: 'box', name: '直角', note: '四角照旧，交给组件轴（默认）' },
      { id: 'hand', name: '手绘', note: '四个角各给一个半径，像用笔框出来的' },
    ],
  },
  {
    id: 'skeleton',
    name: '骨架',
    note: '覆盖层怎么打开 · 要打开任一浮层才看得见',
    options: [
      { id: 'center', name: '居中', note: '居中弹出，浮在遮罩上（默认）' },
      { id: 'drawer', name: '抽屉', note: '从右边推进来，通高一条' },
      { id: 'full', name: '全幅', note: '铺满整屏，像翻到一整页' },
    ],
  },
  {
    id: 'font',
    name: '字体',
    note: '字族与字形 · 字只归这一条轴，组件轴只决定形与密度',
    options: [
      { id: 'hand', name: '手写', note: '标题站酷快乐体、正文 MiSans、数字 Fraunces（默认）' },
      { id: 'clean', name: '精修', note: '标题改用正文字体，去掉手写味，字距收紧' },
      { id: 'serif', name: '衬线', note: '标题与数字走衬线（拉丁 Fraunces + 中文宋体）' },
    ],
  },
]

/** 当前选择：轴 id → 档 id。三处入口都读它，所以不会各记一份 */
export const selection = reactive<Record<string, string>>(
  Object.fromEntries(AXES.map((axis) => [axis.id, axis.options[0].id])),
)

/** 皮肤（配色）变了就抛它 —— 图表/画布/手绘这些 JS 落笔的消费方听着它 */
export const THEME_EVENT = 'zhiyin:theme'
/** 任意一条轴变了都抛它，detail 是 `{ axis, option }` */
export const LOOK_EVENT = 'zhiyin:look'

const keyOf = (axis: string) => `zhiyin_${axis}`

export function axisOf(id: string): Axis {
  return AXES.find((a) => a.id === id) ?? AXES[0]
}

/** 认不出的 id 一律落回默认档 —— 与"默认档没有文件、不写属性"是同一条口径 */
export function optionOf(axisId: string, optionId: string | null | undefined): AxisOption {
  const axis = axisOf(axisId)
  return axis.options.find((o) => o.id === optionId) ?? axis.options[0]
}

export function currentOptionId(axisId: string): string {
  return selection[axisId] ?? axisOf(axisId).options[0].id
}

/* ── 应用 ─────────────────────────────────────────────────────────────── */

function paintAxis(axis: Axis, option: AxisOption) {
  const root = document.documentElement
  const attr = `data-${axis.id}`

  if (option.id === axis.options[0].id) root.removeAttribute(attr)
  else root.setAttribute(attr, option.id)

  /*
   * 手机上那条状态栏颜色只认配色轴：桌面色才是"这一屏的底色"。
   * 在属性写完**之后**读计算值 —— 改属性会让样式失效，这里读到的就是新值。
   */
  if (axis.id === 'theme') {
    const plaster = getComputedStyle(root).getPropertyValue('--c-plaster').trim()
    if (plaster) document.querySelector('meta[name="theme-color"]')?.setAttribute('content', plaster)
  }

  document.dispatchEvent(new CustomEvent(LOOK_EVENT, { detail: { axis: axis.id, option: option.id } }))
  if (axis.id === 'theme') document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: option.id }))
}

export function applyOption(axisId: string, optionId: string | null | undefined, persist = true): AxisOption {
  const axis = axisOf(axisId)
  const option = optionOf(axisId, optionId)
  selection[axis.id] = option.id
  if (persist) {
    try {
      localStorage.setItem(keyOf(axis.id), option.id)
    } catch {
      /* 隐私模式：选择只在这一会话里生效，不报错 */
    }
  }
  paintAxis(axis, option)
  return option
}

/** 一次配好整套（面板的"重置"与 `?…` 参数走它） */
export function applyLook(config: Record<string, string>, persist = false) {
  for (const axis of AXES) {
    if (config[axis.id] !== undefined) applyOption(axis.id, config[axis.id], persist)
  }
}

/** 全部回到默认档（默认档不写属性，所以这就是"删掉属性"） */
export function resetLook(persist = true) {
  for (const axis of AXES) applyOption(axis.id, axis.options[0].id, persist)
}

/** 启动：`?<轴>=` > 本机记住的 > 默认；参数不落盘 */
export function initLook() {
  const query = new URLSearchParams(location.search)
  for (const axis of AXES) {
    let remembered: string | null = null
    try {
      remembered = localStorage.getItem(keyOf(axis.id))
    } catch {
      remembered = null
    }
    const asked = query.get(axis.id)
    const fromQuery = !!asked && axis.options.some((o) => o.id === asked)
    applyOption(axis.id, fromQuery ? asked : remembered, !fromQuery && !!remembered)
  }

  /*
   * 打印：暗色配色打印出来是一张黑纸 —— 费墨，字也看不清。
   * 报告页的「打印 / 存 PDF」走的就是 window.print()，所以在打之前临时切回默认配色，
   * 打完再换回来。只回切配色轴：其余几条是形与字，打印没有理由改它们。
   * 不做成 @media print 的令牌副本：那会让浅色那一套有第二份拷贝，改一处另一处不跟。
   */
  window.addEventListener('beforeprint', () => applyOption('theme', AXES[0].options[0].id, false))
  window.addEventListener('afterprint', () => applyOption('theme', selection.theme, false))
  window.matchMedia('print').addEventListener('change', (e) => {
    applyOption('theme', e.matches ? AXES[0].options[0].id : selection.theme, false)
  })
}

/*
 * 只到这里。这里**不导出** `SKINS` / `UI_STYLES` / `applySkin` 那套旧接口：
 * 它们是"两条轴"时代的产物，用来给右下角浮片与账号面板各记一份选择再对齐。
 * 现在三处入口都读同一个 `selection`，旧接口一个使用者都没有 —— 留着就是第二份真相。
 * （2026-10-08 随账号面板里的外观行一起删掉。）
 */
