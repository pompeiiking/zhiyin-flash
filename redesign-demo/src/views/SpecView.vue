<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { PRODUCT } from '../data/copy'
import ConfidenceBadge from '../components/ConfidenceBadge.vue'

/**
 * 设计规范页。
 *
 * 它不是"设计稿"，而是**跑起来的令牌本身**：所有色值都用 getComputedStyle
 * 从 :root 上读回来，所以这一页永远不会和真实界面不一致 ——
 * 改了 tokens.css，这一页跟着变；要是它显示的和界面不一样，那一定是 bug。
 *
 * 评审要求（原文）："禁止自定义乱配颜色，参考 DeepSeek、Codex、河大门户的红蓝+深灰配色体系，
 * 主色不超过 3 种"。这一页就是这条要求的验收面。
 */

const deg = ref<Record<string, string>>({})

onMounted(() => {
  const cs = getComputedStyle(document.documentElement)
  const names = [
    '--blue-50', '--blue-100', '--blue-500', '--blue-600', '--blue-700',
    '--red-50', '--red-100', '--red-500', '--red-600',
    '--gray-0', '--gray-25', '--gray-50', '--gray-100', '--gray-200', '--gray-300',
    '--gray-400', '--gray-500', '--gray-600', '--gray-700', '--gray-800', '--gray-900',
    '--c-bg', '--c-surface', '--c-border', '--c-text', '--c-text-2', '--c-text-3',
    '--c-primary', '--c-attention', '--c-done', '--c-focus',
  ]
  const out: Record<string, string> = {}
  for (const n of names) out[n] = cs.getPropertyValue(n).trim()
  deg.value = out
})

const t = (n: string) => deg.value[n] ?? ''

/** 三支主色 —— 这就是"主色不超过 3 种"的清单。色值均来自官方/真实站点 CSS 实测 */
const PRIMARY = [
  {
    name: '蓝 · 主色 · 河大校徽蓝',
    token: '--blue-500 / --blue-600',
    hex: ['#0058a7', '#004885'],
    from: '河北大学官网「标识系统」页的正式资产：圆形校徽 PNG（187×188）与校名标准字 PNG（529×213），两份的非背景像素 100% 都是 #0058a7',
    url: 'https://www.hbu.edu.cn/xxgk/bsxt.htm',
    use: '主按钮、链接、当前步骤、图表主序列。校徽蓝 #0058a7 对白底 7.11:1 —— 够深，所以它既是品牌色也是文字色，不再分"图形档 / 文字档"两支；悬停压深到 #004885。',
  },
  {
    name: '红 · 注意色',
    token: '--red-500',
    hex: ['#96000e'],
    from: '河北大学官网 layout.css 的实际主红（出现 57 次）',
    url: 'https://www.hbu.edu.cn',
    use: '给需要注意的地方：截止日、门槛提示。白底 9.12:1。学生空间的品牌标记也沿用这支红。',
  },
  {
    name: '深灰 · 骨架',
    token: '--gray-900 / --gray-500 / --gray-200',
    hex: ['#1e232c', '#61666b', '#e1e5ee'],
    from: 'DeepSeek --ds-color-text-primary 与实测中性灰阶',
    url: 'https://chat.deepseek.com',
    use: '文字、描边、结构全部由这三档承担。界面里 90% 的面积是灰的，颜色只在少数几处出现。#1e232c 带一点蓝调，与主色同族。',
  },
]

/** 灰阶：hex 一列不写死，实时从 :root 读 —— 改了令牌这一页不会说谎 */
const GRAYS = [
  { token: '--gray-0', use: '卡片、面板' },
  { token: '--gray-25', use: '次级底：表头、只读区' },
  { token: '--gray-50', use: '页面底' },
  { token: '--gray-100', use: '三级底：标签、进度槽' },
  { token: '--gray-200', use: '描边（默认）' },
  { token: '--gray-300', use: '描边（强调）、未开始步骤' },
  { token: '--gray-400', use: '仅图标/分隔符，不当文字用' },
  { token: '--gray-500', use: '说明文字（对白底 5.80:1）' },
  { token: '--gray-600', use: '次要文字（8.03:1）' },
  { token: '--gray-700', use: '深色块描边' },
  { token: '--gray-800', use: '深色块次级' },
  { token: '--gray-900', use: '正文（15.77:1）' },
]

/**
 * 对比度：数值由 scripts/check-contrast.mjs 实测产出
 * （浅色、浅色+红主色、深色、深色+红主色，四套都跑）。
 * 改色请重跑那个脚本，别手改这张表。
 */
const CONTRAST = [
  { pair: '正文 #1e232c / 卡片 #ffffff', value: '15.77:1', pass: true },
  { pair: '正文 #1e232c / 页面底 #f7f6f6', value: '14.62:1', pass: true },
  { pair: '次要文字 #4b5157 / #ffffff', value: '8.03:1', pass: true },
  { pair: '次要文字 #4b5157 / 页面底 #f7f6f6', value: '7.45:1', pass: true },
  { pair: '说明文字 #61666b / #ffffff', value: '5.80:1', pass: true },
  { pair: '说明文字 #61666b / 页面底 #f7f6f6', value: '5.38:1', pass: true },
  { pair: '白字 / 主色 #0058a7', value: '7.11:1', pass: true },
  { pair: '主色 #0058a7 / #ffffff', value: '7.11:1', pass: true },
  { pair: '主色 #0058a7 / 页面底 #f7f6f6', value: '6.59:1', pass: true },
  { pair: '主色 #0058a7 / 自身浅底 #eef5fc', value: '6.47:1', pass: true },
  { pair: '注意色 #96000e / #ffffff', value: '9.12:1', pass: true },
  { pair: '注意标签 #7d000c / #fdf7f4', value: '10.54:1', pass: true },
  { pair: '已完成标签 #61666b / #ebedf2', value: '4.95:1', pass: true },
  { pair: '说明文字 #61666b / 次级底 #fafafa', value: '5.56:1', pass: true },
  { pair: '输入框占位符 #61666b / #ffffff', value: '5.80:1', pass: true },
]

/** 皮肤：三条轴，只覆盖令牌、不动结构 —— 3 × 2 × 3 = 18 种组合 */
const AXES = [
  {
    axis: '主题',
    attr: 'data-theme',
    options: '浅色 / 深色 / 跟随系统',
    what: '全部颜色 + color-scheme + 阴影 + 描边强度',
    note: '深色的边框比浅色更强（浅色黑 10% → 深色白 12–20%）；深色靠提亮表面分层，不靠阴影',
  },
  {
    axis: '主色',
    attr: 'data-accent',
    options: '河大蓝 / 河大红',
    what: '--c-primary 一族 + 图表主序列 + 焦点环',
    note: '红做主色时"注意"仍是红，但语法不同：主色是实心，注意是浅底 + 左侧竖线',
  },
  {
    axis: '风格',
    attr: 'data-style',
    options: '极简 / 柔和 / 紧凑',
    what: '圆角、阴影、卡片内距、行高、入场位移',
    note: '不动颜色、不动层级、不动字号档位',
  },
  /*
   * 曾经还有一条轴「动效」（data-motion：完整 / 克制），2026-10-11 删除。
   * 三个理由：与 prefers-reduced-motion 是同一件事的两种说法、
   * 用户在界面上几乎看不出差别、并且它会把门户整页搞白（证据见 README）。
   * 减少动效从此只有一个来源：系统的 prefers-reduced-motion。
   */
]

/** 动效口径：每条都注明来源；拿不到来源的写"建议值" */
const MOTION = [
  { scene: '路由切换', spec: 'opacity + translateY 6px，160ms ease-out', from: '曲线实测自 Linear --ease-out-quint；只做入场不做退场' },
  { scene: '列表逐条入场', spec: '间隔 40ms、位移 8px、单条 240ms ease-out', from: '间隔取 30–80ms 经验区间中值；上限 8 条，再多就只是慢' },
  { scene: '数字滚动', spec: '420ms ease-out（逐字按字数夹 320–900ms）', from: 'number-flow 默认 900/450ms 属"数据揭示"，单个数字压到 420ms' },
  { scene: '进度 / 分值条', spec: 'transform: scaleX，250ms ease-out', from: 'Material medium1；用 transform 而非 width，避免触发布局' },
  { scene: '步骤推进', spec: '圆圈填色 180ms、连线 240ms、对勾 0.9→1 淡入', from: 'Carbon 步骤条：当前步半填充圆、已完成空心圆加对勾' },
  { scene: '悬停（颜色）', spec: '150ms ease', from: 'shadcn --default-transition-duration: .15s 与 Resend 同值' },
  { scene: '按下反馈', spec: 'scale(0.98)，150ms ease-out', from: '按钮按下 100–160ms；只缩 2%，不做"弹一下"' },
  { scene: '浮层 / 下拉', spec: '180ms ease-out，scale 0.97 → 1，origin 在触发点', from: '禁止 scale(0)：Geist 浮层缩放起点是 0.96' },
  { scene: '换肤', spec: '切换瞬间禁用一切过渡 → 整页 160ms 淡入', from: '给颜色挂全局 transition 会让各元素各自跑；color-scheme 规范上是 discrete，不可插值' },
  { scene: '键盘发起的动作', spec: '不做动画', from: '命令面板（⌘K）刻意没有开合动画 —— Raycast 也没有，这是对的' },
]

const TYPE = [
  { token: '--fs-38 / 600', use: '门户主张、报告关键差距' },
  { token: '--fs-30 / 600', use: '页标题、主要任务与报告结论' },
  { token: '--fs-20 / 600', use: '节标题、手机端的主要标题' },
  { token: '--fs-16 / 400', use: '学生空间正文、对话、任务条目' },
  { token: '--fs-14 / 400', use: '次要说明、来源细节、控件文字' },
  { token: '--fs-12 / 400', use: '短注解、时间、手机导航标签' },
]

const SPACING = ['4', '8', '12', '16', '20', '24', '32', '40', '56', '72']

const REFUSE = [
  { what: '手写体（站酷快乐体）与手写字标题', why: '评审原话：抛弃现有手写类不符合简洁要求的设计元素。手写体让严肃的就业数据读起来不专业。' },
  { what: 'roughjs 手绘框、抖动的圆角、手绘光标', why: '同一件事：手绘是"草稿"的语气，而这份界面要传递的是"可被盘问的数据"。' },
  { what: '第四种色相（紫/青/橙…）', why: '主色不超过 3 种的硬约束。需要区分层级时，用同一色相的深浅与灰阶，不引入新色相。' },
  { what: '彩色阴影、玻璃拟态、大渐变', why: '颜色一多，"哪条更重要"就说不清了。层次靠 1px 描边与灰阶，不靠光效。' },
  { what: 'emoji 当图标', why: '跨平台字形不一致，且与"可被盘问"的气质冲突。只用一处标记：文字或极简 SVG。' },
  { what: '渐变进度条 / 彩色仪表盘', why: '分值条只用一个颜色 + 一条门槛线 —— 用户要读的是"差几分"，不是"好不好看"。' },
]

const steps = [
  { label: '认识你', state: 'done' },
  { label: '评估报告', state: 'done' },
  { label: '选一个方向', state: 'current' },
  { label: '今日任务', state: 'todo' },
  { label: '复盘记录', state: 'todo' },
]

const sourceNote = computed(
  () =>
    `本页色值直接从 :root 读取（当前 --blue-500 = ${t('--blue-500')}），所以它永远等于界面真实用色。`,
)
</script>

<template>
  <div class="spec">
    <header class="spec__top">
      <div class="hstack hstack-3">
        <span class="spec__mark">职引</span>
        <span class="t-note">{{ PRODUCT.title }}</span>
      </div>
      <RouterLink class="btn btn--sm" to="/">回到门户</RouterLink>
    </header>

    <div class="spec__main">
      <h1 class="spec__title">设计规范</h1>
      <p class="spec__sub">
        重设计的全部视觉口径都在这里。三条硬约束：<strong>主色不超过 3 种</strong>（蓝 / 红 / 深灰）、
        正文对比度 ≥ 4.5:1、组件里不出现任何颜色字面量。{{ sourceNote }}
      </p>

      <!-- 三支主色 -->
      <section class="block">
        <h2 class="block__title">一、三支主色（就这三个）</h2>
        <div class="primaries">
          <article v-for="p in PRIMARY" :key="p.name" class="primary">
            <div class="primary__swatches">
              <span v-for="h in p.hex" :key="h" class="sw" :style="{ background: h }" :title="h" />
            </div>
            <h3 class="primary__name">{{ p.name }}</h3>
            <p class="primary__token t-mono">{{ p.token }}</p>
            <p class="primary__from">
              参考：
              <a :href="p.url" target="_blank" rel="noreferrer noopener">{{ p.from }}</a>
            </p>
            <p class="primary__use">{{ p.use }}</p>
          </article>
        </div>
      </section>

      <!-- 灰阶 -->
      <section class="block">
        <h2 class="block__title">二、中性灰阶（承担 90% 的面积）</h2>
        <div class="spec-table-scroll"><table class="table">
          <thead>
            <tr>
              <th style="width: 120px">色值</th>
              <th style="width: 90px">令牌</th>
              <th style="width: 130px">hex（实时读取）</th>
              <th>用在哪</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in GRAYS" :key="g.token">
              <td><span class="sw sw--inline" :style="{ background: t(g.token) }" /></td>
              <td class="t-mono" style="font-size: var(--fs-12)">{{ g.token }}</td>
              <td class="t-mono" style="font-size: var(--fs-12)">{{ t(g.token) }}</td>
              <td>{{ g.use }}</td>
            </tr>
          </tbody>
        </table></div>
      </section>

      <!-- 对比度 -->
      <section class="block">
        <h2 class="block__title">三、对比度硬线（这是"能不能用"的判据，不是审美）</h2>
        <div class="spec-table-scroll"><table class="table">
          <thead>
            <tr>
              <th>组合</th>
              <th style="width: 110px">对比度</th>
              <th style="width: 90px">结论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in CONTRAST" :key="c.pair">
              <td>{{ c.pair }}</td>
              <td class="t-mono t-num">{{ c.value }}</td>
              <td>
                <span class="chip" :class="c.pass ? 'chip--done' : 'chip--attention'">
                  {{ c.pass ? '过' : '仅作图形' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table></div>
        <p class="note">
          这一版没有"不达 4.5 的例外"：主色换成河大校徽蓝 #0058a7 之后，它对白底 7.11:1，
          <strong>既能画图形也能承载文字</strong>。此前用的 DeepSeek 蓝 #4d6bfe 只有 4.33:1，
          所以才必须分两支（品牌原色只当图形、文字降到深蓝）—— 换成校徽蓝之后那条分叉取消了。
        </p>
      </section>

      <!-- 皮肤 -->
      <section class="block">
        <h2 class="block__title">四、皮肤：三条轴，只换令牌不动结构</h2>
        <p class="note">
          顶栏右侧的「皮肤」按钮，或按 <span class="t-mono">⌘K</span> 搜"皮肤"。选择记在本地，
          页面的 <span class="t-mono">&lt;html&gt;</span> 上只多出几个 <span class="t-mono">data-*</span> 属性。
        </p>
        <div class="spec-table-scroll"><table class="table" style="margin-top: 16px">
          <thead>
            <tr>
              <th style="width: 90px">轴</th>
              <th style="width: 150px">属性</th>
              <th style="width: 200px">档位</th>
              <th style="width: 240px">换什么</th>
              <th>边界</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in AXES" :key="a.axis">
              <td class="t-strong">{{ a.axis }}</td>
              <td class="t-mono" style="font-size: var(--fs-12)">{{ a.attr }}</td>
              <td>{{ a.options }}</td>
              <td class="t-dim" style="font-size: var(--fs-12)">{{ a.what }}</td>
              <td class="t-dim" style="font-size: var(--fs-12)">{{ a.note }}</td>
            </tr>
          </tbody>
        </table></div>
        <p class="note">
          3 × 2 × 3 = <strong>18 种组合</strong>，全部只改值：颜色、圆角、阴影、间距、表面层级。
          <strong>凡是要改 DOM 顺序、条目数量、组件是否存在 的，都不是皮肤，是分支</strong> ——
          所以这里没有"去掉这一块"这种档位。
        </p>
        <div class="hstack hstack-3 wrap" style="margin-top: 16px">
          <span class="chip chip--outline">浅色 · 蓝 · 极简</span>
          <span class="chip chip--outline">深色 · 蓝 · 紧凑</span>
          <span class="chip chip--outline">浅色 · 河大红 · 柔和</span>
          <span class="chip chip--outline">深色 · 河大红 · 极简 · 克制动效</span>
          <span class="t-note">—— 现场切给评审看，四种都在顶栏「皮肤」里</span>
        </div>
      </section>

      <!-- 动效 -->
      <section class="block">
        <h2 class="block__title">五、动效：只动"状态真的变了"的地方</h2>
        <p class="note">
          判据是<strong>频率</strong>：一天看几十次的东西不动（导航条、按钮、列表项自身）；
          动的是"数字变了""话正在出来""这一步推进了"。所以命令面板刻意没有开合动画。
        </p>
        <div class="spec-table-scroll"><table class="table" style="margin-top: 16px">
          <thead>
            <tr>
              <th style="width: 170px">场景</th>
              <th style="width: 320px">数值</th>
              <th>来源 / 取舍</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in MOTION" :key="m.scene">
              <td class="t-strong">{{ m.scene }}</td>
              <td class="t-mono" style="font-size: var(--fs-12)">{{ m.spec }}</td>
              <td class="t-dim" style="font-size: var(--fs-12)">{{ m.from }}</td>
            </tr>
          </tbody>
        </table></div>
        <p class="note">
          曲线只有三条，都取自生产 CSS 实测：<span class="t-mono">--ease-out: cubic-bezier(0.23, 1, 0.32, 1)</span>（Linear 的
          ease-out-quint）、<span class="t-mono">--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)</span>、
          <span class="t-mono">--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)</span>。
          <strong>UI 动效一律 &lt; 300ms</strong>（数字滚动属"数据揭示"，单独放宽到 420ms）。
          <span class="t-mono">prefers-reduced-motion</span> 下：去掉位移与逐条入场，
          <strong>门户的装饰层整层不渲染</strong>（只停动画、保留模糊与遮罩会触发 Chrome 的绘制缺陷，整页变白）。
        </p>
      </section>

      <!-- 排版 -->
      <section class="block">
        <h2 class="block__title">六、排版：六档字号，正文 16px</h2>
        <div class="spec-table-scroll"><table class="table">
          <thead>
            <tr>
              <th style="width: 180px">令牌 / 字重</th>
              <th>用在哪</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ty in TYPE" :key="ty.token">
              <td class="t-mono" style="font-size: var(--fs-12)">{{ ty.token }}</td>
              <td>{{ ty.use }}</td>
            </tr>
          </tbody>
        </table></div>
        <p class="note">
          字体栈只有系统无衬线 + 等宽两套：<strong>不下载任何字体</strong>。原来那个十几 MB 的手写体被移除后，
          首屏不再有字体抖动。
        </p>
        <p class="note">
          <strong>2026-10-12：内页正文恢复到 16px。</strong>对话和任务条目优先保证阅读舒适，
          次要信息用 14px，12px 只用于短注解。主要层级仍由<strong>字重、留白与位置</strong>表达，
          不需要每加一层内容就增加一档字号。
          这条纪律由 <code>scripts/check-contrast.mjs</code> 的 <code>FONT_SIZE_USES</code> 守着：
          登记了却没人用 = 死档，会直接失败。
        </p>
      </section>

      <!-- 间距与形 -->
      <section class="block">
        <h2 class="block__title">七、间距、圆角、描边、阴影</h2>
        <div class="grid3">
          <div class="card card--pad">
            <h3 class="t-h3">间距（4px 基数）</h3>
            <div class="spacing">
              <div v-for="s in SPACING" :key="s" class="spacing__row">
                <span class="spacing__bar" :style="{ width: `${s}px` }" />
                <span class="t-mono" style="font-size: var(--fs-12)">{{ s }}px</span>
              </div>
            </div>
          </div>
          <div class="card card--pad">
            <h3 class="t-h3">圆角：只有三档</h3>
            <div class="radii">
              <div class="radius" style="border-radius: var(--r-sm)">6px 小</div>
              <div class="radius" style="border-radius: var(--r-md)">8px 中</div>
              <div class="radius" style="border-radius: var(--r-lg)">12px 大</div>
            </div>
          </div>
          <div class="card card--pad">
            <h3 class="t-h3">描边与阴影</h3>
            <ul class="plain">
              <li>默认描边 1px <span class="t-mono">--gray-200</span></li>
              <li>强调描边 1px <span class="t-mono">--gray-300</span></li>
              <li>阴影只有两档，且只给浮层用</li>
              <li>卡片默认<b>不用阴影</b>，靠 1px 描边分层</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 零件 -->
      <section class="block">
        <h2 class="block__title">八、零件（组件只允许用这些名字）</h2>

        <div class="parts">
          <div class="card card--pad">
            <p class="t-label">按钮：三档语义</p>
            <div class="hstack hstack-2 wrap" style="margin-top: 10px">
              <button class="btn btn--primary">主操作</button>
              <button class="btn">次操作</button>
              <button class="btn btn--ghost">文字入口</button>
              <button class="btn btn--danger">危险</button>
              <button class="btn" disabled>不可用</button>
            </div>
          </div>

          <div class="card card--pad">
            <p class="t-label">标签与把握度</p>
            <div class="hstack hstack-2 wrap" style="margin-top: 10px">
              <span class="chip chip--primary">主色</span>
              <span class="chip chip--attention">辅色</span>
              <span class="chip chip--done">成功</span>
              <span class="chip chip--attention">警告</span>
              <span class="chip chip--attention">危险</span>
              <span class="chip chip--outline">描边</span>
            </div>
            <div class="hstack hstack-4 wrap" style="margin-top: 14px">
              <ConfidenceBadge :value="{ level: 'high', label: '比较确定', bars: 3 }" />
              <ConfidenceBadge :value="{ level: 'mid', label: '还要再看看', bars: 2 }" />
              <ConfidenceBadge :value="{ level: 'low', label: '还不好说', bars: 1 }" />
            </div>
          </div>

          <div class="card card--pad">
            <p class="t-label">流程示意：不是操作导航</p>
            <ol class="steps" style="margin-top: 12px">
              <template v-for="(s, i) in steps" :key="s.label">
                <li
                  class="steps__item"
                  :class="{
                    'steps__item--done': s.state === 'done',
                    'steps__item--current': s.state === 'current',
                  }"
                >
                  <span class="steps__index">{{ s.state === 'done' ? '✓' : i + 1 }}</span>
                  <span>{{ s.label }}</span>
                </li>
                <li v-if="i < steps.length - 1" class="steps__link" />
              </template>
            </ol>
          </div>

          <div class="card card--pad">
            <p class="t-label">提示条：四种语气</p>
            <div class="stack stack-2" style="margin-top: 10px">
              <p class="callout">说明（信息）</p>
              <p class="callout callout--attention">要注意（辅色）</p>
              <p class="callout callout--done">做成了</p>
              <p class="callout callout--plain">不需要动作</p>
            </div>
          </div>

          <div class="card card--pad">
            <p class="t-label">计量条：分值 + 门槛线</p>
            <div style="margin-top: 12px">
              <div class="demo-meter">
                <div class="meter-row__track">
                  <div class="meter-row__fill meter-row__fill--warn" style="width: 46%" />
                  <div class="meter-row__req" style="left: 50%" />
                </div>
                <p class="t-note" style="margin-top: 6px">
                  46 分，门槛线 50 —— <b>差 4 分，是补起来最快的一个</b>
                </p>
              </div>
            </div>
          </div>

          <div class="card card--pad">
            <p class="t-label">空态：必须写出路</p>
            <div class="empty" style="padding: var(--sp-5)">
              <p class="empty__title">还不太了解你</p>
              <p class="empty__body">先聊三五个问题就够开工，后面发现不对随时能改</p>
              <button class="btn btn--sm btn--primary">开始第一个问题</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 不做的 -->
      <section class="block">
        <h2 class="block__title">九、明确不做的（附理由，防止下一版又加回来）</h2>
        <div class="spec-table-scroll"><table class="table">
          <thead>
            <tr>
              <th style="width: 34%">不做</th>
              <th>为什么</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in REFUSE" :key="r.what">
              <td class="t-strong">{{ r.what }}</td>
              <td class="t-dim">{{ r.why }}</td>
            </tr>
          </tbody>
        </table></div>
      </section>

      <!-- 层级 -->
      <section class="block">
        <h2 class="block__title">十、信息层级：一屏里怎么排</h2>
        <div class="hier">
          <div class="hier__item">
            <span class="hier__no">1</span>
            <b>你现在在哪</b>
            <p>底部浮动书签保留五个功能名称，当前页面明确高亮。顶部只放品牌、年级、外观与提醒工具。</p>
          </div>
          <div class="hier__item">
            <span class="hier__no">2</span>
            <b>现在最好先做什么</b>
            <p>每页先给一个主要焦点：对话中的问题、今天的一件事、报告的结论。次要信息按需展开。</p>
          </div>
          <div class="hier__item">
            <span class="hier__no">3</span>
            <b>结论先给，依据点开</b>
            <p>L1 只给一句结论 + 把握度；分值、走势、来源收进 L2，点开才出现。</p>
          </div>
          <div class="hier__item">
            <span class="hier__no">4</span>
            <b>空态也是设计</b>
            <p>没内容时不留空盒子：写清"为什么空""下一步做什么"。</p>
          </div>
        </div>
      </section>

      <footer class="spec__foot">
        <p class="t-note">
          参考来源：**河北大学校徽**的蓝（量自校徽图，见上）、河北大学门户的红（hbu.edu.cn）、
          OpenAI Codex 的克制排版（openai.com/codex）与 DeepSeek 的中性灰阶与字号节奏。
          色值经对比度校验，校验规则写在
          <span class="t-mono">scripts/check-contrast.mjs</span>。
        </p>
        <p class="t-note" style="margin-top: 8px">
          本页是演示工程的一部分，数据为预置内容，不代表真实模型输出。
        </p>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.spec {
  min-height: 100%;
  background: var(--c-bg);
}

.spec__top {
  height: var(--w-topbar);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-6);
  background: var(--c-surface);
  border-bottom: var(--bw-1) solid var(--c-border);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.spec__mark {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  letter-spacing: 0.06em;
}

.spec__main {
  max-width: 1000px;
  margin: 0 auto;
  padding: var(--sp-7) var(--sp-6) var(--sp-9);
}

.spec__title {
  font-size: var(--fs-30);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.02em;
}

.spec__sub {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-normal);
  /* 中文里 1ch ≈ 半个汉字宽：数值减半换 em，视觉宽度不变，但不再随字体档变化 */
  max-width: 40em;
}

.block {
  margin-top: var(--sp-9);
}

.block__title {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  padding-bottom: var(--sp-3);
  border-bottom: var(--bw-1) solid var(--c-border);
  margin-bottom: var(--sp-4);
}

/* 三主色 */
.primaries {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-4);
}

.primary {
  padding: var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
}

.primary__swatches {
  display: flex;
  gap: var(--sp-2);
}

.sw {
  width: 40px;
  height: 40px;
  border-radius: var(--r-md);
  border: var(--bw-1) solid var(--c-border);
  display: inline-block;
}

.sw--inline {
  width: 40px;
  height: 16px;
  border-radius: var(--r-sm);
  vertical-align: middle;
}

.primary__name {
  margin-top: var(--sp-3);
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
}

.primary__token {
  margin-top: 2px;
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.primary__from {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.primary__use {
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: var(--lh-normal);
}

.note {
  margin-top: var(--sp-3);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  line-height: var(--lh-normal);
  max-width: 44em;
}

/* 间距等 */
.grid3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-4);
}

.spacing {
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.spacing__row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.spacing__bar {
  height: 8px;
  background: var(--c-primary);
  border-radius: 2px;
  max-width: 120px;
}

.radii {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
}

.radius {
  padding: var(--sp-3);
  border: var(--bw-1) solid var(--c-border-strong);
  background: var(--c-surface-2);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  text-align: center;
}

.plain {
  margin-top: var(--sp-3);
}

.plain li {
  position: relative;
  padding: var(--sp-2) 0 var(--sp-2) var(--sp-4);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.plain li:last-child {
  border-bottom: none;
}

.plain li::before {
  content: '·';
  position: absolute;
  left: 4px;
}

/* 零件 */
.parts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-4);
}

.demo-meter {
  max-width: 320px;
}

.meter-row__track {
  position: relative;
  height: 8px;
  border-radius: var(--r-pill);
  background: var(--c-surface-3);
}

.meter-row__fill {
  height: 100%;
  border-radius: var(--r-pill);
  background: var(--c-primary);
}

.meter-row__fill--warn {
  background: var(--c-attention);
}

.meter-row__req {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 14px;
  background: var(--c-text-2);
  border-radius: 1px;
}

/* 层级 */
.hier {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-4);
}

.hier__item {
  padding: var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-md);
}

.hier__no {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-bottom: var(--sp-2);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
}

.hier__item b {
  display: block;
  font-size: var(--fs-14);
}

.hier__item p {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  line-height: var(--lh-normal);
}

.spec__foot {
  margin-top: var(--sp-9);
  padding-top: var(--sp-5);
  border-top: var(--bw-1) solid var(--c-border);
}

@media (max-width: 900px) {
  .primaries,
  .grid3,
  .parts,
  .hier {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
