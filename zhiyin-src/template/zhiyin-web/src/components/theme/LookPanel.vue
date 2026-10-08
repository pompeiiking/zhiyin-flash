<script setup lang="ts">
/**
 * 外观台 —— 一张**矩阵**：一行一条轴，一列一个档位。
 *
 * 【为什么是矩阵，不是"一条轴一屏"】
 *
 * 外观有七条轴、二十八个档位。做成标签页（一次只看一条轴）其实丢掉了一件最要紧的事：
 * **一眼看全**。"我现在这套是怎么配的"、"还有哪几条轴可以动"，在标签页里要先点七次
 * 才拼得出来；摊成矩阵，七行一屏读完，当前那一列一眼就是一条竖线。
 *
 * 矩阵的代价是它比标签页宽（八列），所以这张台子开得大一点，并且**不做成模态**：
 * 面板落下来之后，后面那块真界面就是实时预览 —— 点一个格子，身后的页面当场变。
 * 这比在面板里画缩略图诚实得多，也省一套永远会跟真界面走样的预览图。
 *
 * 【入口在哪】
 *
 * 三个「外观台」字：控制台左上角（账号那颗的右边）、报告页顶栏、门户页右上角。
 * 开合与落点（左/右）在 `composables/useLookPanel`。
 *
 * 【它不做的事】
 *
 * 不发埋点：要给"换了哪套外观"计数，得先在 data/registry/track_events.json 登记事件码，
 * 否则后端会拒收（前端埋点是静默的）。那属于另一件事。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AXES,
  applyOption,
  optionOf,
  resetLook,
  selection,
  type Axis,
  type AxisOption,
} from '@/lib/theme'
import { useEscLayerManual } from '@/composables/useEscLayer'
import { lookPanelAnchor, lookPanelOpen } from '@/composables/useLookPanel'

const open = lookPanelOpen
const root = ref<HTMLElement | null>(null)
const copied = ref(false)

/** 列数 = 最宽的那条轴（现在是"组件"的八档）：所有行共用它，列才对得齐 */
const COLS = Math.max(...AXES.map((a) => a.options.length))

const esc = useEscLayerManual(() => (open.value = false))
// 面板一直挂着、层是开开关关：真正打开的那一刻才占住 Esc，
// 否则它会先注册，把 Esc 从后来打开的浮层手里夺走（见 useEscLayer 的说明）
watch(open, (on) => (on ? esc.activate() : esc.deactivate()))

/** 当前这套搭配，一行读完 */
const recipe = computed(() => AXES.map((a) => optionOf(a.id, selection[a.id]).name).join(' · '))

/** 哪些轴被改过（不是默认档）—— 底部那句人话与"复制链接"都认它 */
const changed = computed(() => AXES.filter((a) => selection[a.id] !== a.options[0].id))

const stateLine = computed(() =>
  changed.value.length
    ? `已改动 ${changed.value.length} 条轴：${changed.value.map((a) => a.name).join('、')}`
    : '当前是默认外观：七条轴都在默认档',
)

/** 只把**非默认**的档写进链接：默认档不写属性，链接里也就不必出现 */
const query = computed(() =>
  changed.value.map((a) => `${a.id}=${selection[a.id]}`).join('&')
    ? `?${changed.value.map((a) => `${a.id}=${selection[a.id]}`).join('&')}`
    : '',
)

const isDefault = (a: Axis) => selection[a.id] === a.options[0].id

function pick(axis: Axis, option: AxisOption) {
  applyOption(axis.id, option.id)
}

/** 单行回默认：改错了只退这一条，不用把整台重新配一遍 */
function clearAxis(a: Axis) {
  applyOption(a.id, a.options[0].id)
}

function reset() {
  resetLook()
}

/** 随便配一套：给演示用 —— "还有别的样子吗"这句话，一键回答 */
function surprise() {
  for (const a of AXES) {
    const at = Math.floor(Math.random() * a.options.length)
    applyOption(a.id, a.options[at].id)
  }
}

async function copy() {
  const url = location.origin + location.pathname + query.value
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1600)
  } catch {
    /* 剪贴板被拒（非安全上下文/无权限）：链接就写在下面那行里，手动复制即可 */
    copied.value = false
  }
}

/**
 * 矩阵里的方向键：左右换这一条轴的档，上下换轴。
 * 用属性选择器找兄弟格子 —— 格子是平铺在表格里的，按"轴 + 档"定位最稳。
 */
function onCellKey(e: KeyboardEvent, a: Axis, o: AxisOption) {
  const keys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']
  if (!keys.includes(e.key)) return
  e.preventDefault()

  const ai = AXES.findIndex((x) => x.id === a.id)
  const oi = a.options.findIndex((x) => x.id === o.id)
  let targetAxis = ai
  let targetOption = oi

  if (e.key === 'ArrowLeft') targetOption = Math.max(0, oi - 1)
  if (e.key === 'ArrowRight') targetOption = Math.min(a.options.length - 1, oi + 1)
  if (e.key === 'ArrowUp') targetAxis = Math.max(0, ai - 1)
  if (e.key === 'ArrowDown') targetAxis = Math.min(AXES.length - 1, ai + 1)

  const next = AXES[targetAxis]
  const opt = next.options[Math.min(targetOption, next.options.length - 1)]
  const node = root.value?.querySelector<HTMLElement>(`[data-axis="${next.id}"][data-opt="${opt.id}"]`)
  node?.focus()
}

/**
 * 点面板以外的地方就收回。
 * 「外观台」那三个字要排掉：点在它上面是"开"，紧接着的这次 pointerdown 若把面板关掉，
 * 就会出现"点了没反应"。三处入口共用同一个类名，判定一次就够。
 */
function onPointerDown(e: PointerEvent) {
  if (!open.value) return
  const el = e.target as HTMLElement
  if (el.closest('.look-trigger')) return
  if (root.value && !root.value.contains(el)) open.value = false
}

onMounted(() => document.addEventListener('pointerdown', onPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onPointerDown))

/* ── 迷你示意图 ────────────────────────────────────────────────────────
 * 配色用三格色卡、组件用 CSS 画的真实圆角/描边/影；其余五条轴走下面这张 14×14 的路径表。
 * 颜色一律 currentColor —— 小图跟着配色轴走，所以它自己不会是第八种颜色。
 */
interface Glyph {
  d: string
  fill?: boolean
  dash?: string
}

const GLYPHS: Record<string, Glyph[]> = {
  'feedback:rise': [{ d: 'M7 12.5V3.6M3.4 7.1 7 3.5l3.6 3.6' }],
  'feedback:edge': [{ d: 'M2.5 3.5h9v7h-9z' }, { d: 'M2.5 5.5h9' }],
  'feedback:fill': [{ d: 'M2.5 3.5h9v7h-9z', fill: true }],
  'type:plain': [{ d: 'M2.5 4h9M2.5 7h9M2.5 10h5.5' }],
  'type:outline': [{ d: 'M2.5 2.8h9' }, { d: 'M2.5 6h9M2.5 9h9M2.5 12h5' }],
  'type:read': [{ d: 'M3.5 4.8h7M3.5 9.2h7' }],
  'shape:box': [{ d: 'M2.5 2.5h9v9h-9z' }],
  'shape:hand': [{ d: 'M4.4 2.5h5.9a2.4 2.4 0 0 1 2.2 2.6v5.4a1.3 1.3 0 0 0-1.2 1.4H4.7a1.9 1.9 0 0 1-1.7-2.1V4.2A1.6 1.6 0 0 1 4.4 2.5z' }],
  'skeleton:center': [{ d: 'M1.5 2.5h11v9h-11z' }, { d: 'M4 4.8h6v4.4H4z' }],
  'skeleton:drawer': [{ d: 'M1.5 2.5h11v9h-11z' }, { d: 'M7.2 2.5h5.3v9H7.2z', fill: true }],
  'skeleton:full': [{ d: 'M1.5 2.5h11v9h-11z', fill: true }],
}

const glyphsOf = (axisId: string, optionId: string) => GLYPHS[`${axisId}:${optionId}`] ?? []

/*
 * 字体那一行的预览用**真字**显示：路径画不出"字面"的差别（衬线有没有脚、字腔松不松），
 * 而这一档要的正是让用户一眼看出"这几种字不一样"。
 * 每档给一条与 `styles/font/<档>.css` 里同一套的字栈 —— 不一致的话，
 * 预览就成了"面板里好看、点下去变样"。
 */
const FACES: Record<string, string> = {
  hand: '"ZCOOL KuaiLe", "MiSans VF", sans-serif',
  clean: '"MiSans VF", "MiSans", sans-serif',
  serif: '"Fraunces", "Songti SC", "Noto Serif SC", SimSun, serif',
}
</script>

<template>
  <!--
    面板挂到 body 上：控制台左上角那一条 chrome 会整块滑进滑出、带 transform，
    留在里面会被裁掉一角。挂在 body 上，落点只由 anchor 决定。
  -->
  <Teleport to="body">
    <transition name="drop">
      <section
        v-if="open"
        ref="root"
        class="look sheet"
        :class="`look--${lookPanelAnchor}`"
        role="dialog"
        aria-label="外观台"
      >
        <header class="head">
          <div class="head__text">
            <span class="label head__k">外观台</span>
            <p class="head__now">{{ recipe }}</p>
          </div>
          <p class="label head__hint">一行一条轴 · 点格子换这一条 · 身后那块界面就是实时预览</p>
          <button class="head__x" type="button" aria-label="收起" @click="open = false">✕</button>
        </header>

        <!-- 矩阵：列数取最宽的那条轴，所有行共用，列才对齐 -->
        <div class="scroll">
          <table class="matrix">
            <colgroup>
              <col class="matrix__c0" />
              <col v-for="n in COLS" :key="n" />
            </colgroup>
            <tbody>
              <tr v-for="a in AXES" :key="a.id">
                <th scope="row" class="rowhead">
                  <span class="rowhead__name">{{ a.name }}</span>
                  <span class="rowhead__note">{{ a.note }}</span>
                  <!-- 改过的那一行才有"退回去"：一行一行退，比整台重配省事 -->
                  <button
                    v-if="!isDefault(a)"
                    class="rowhead__reset"
                    type="button"
                    :aria-label="`把${a.name}退回默认`"
                    title="这一条退回默认"
                    @click="clearAxis(a)"
                  >
                    ↺
                  </button>
                </th>

                <td v-for="o in a.options" :key="o.id">
                  <button
                    class="cell"
                    type="button"
                    :data-axis="a.id"
                    :data-opt="o.id"
                    :aria-pressed="selection[a.id] === o.id"
                    :class="{ 'is-on': selection[a.id] === o.id }"
                    :title="o.note"
                    @click="pick(a, o)"
                    @keydown="onCellKey($event, a, o)"
                  >
                    <span class="cell__mark" aria-hidden="true">
                      <span v-if="a.id === 'theme'" class="sw">
                        <i v-for="c in o.swatch" :key="c" :style="{ background: c }" />
                      </span>
                      <i v-else-if="a.id === 'ui'" :class="`g g--${o.id}`" />
                      <!-- 字体：用这一档的真字显示 -->
                      <span v-else-if="a.id === 'font'" class="ff" :style="{ fontFamily: FACES[o.id] }">Aa 文</span>
                      <svg v-else class="mk" viewBox="0 0 14 14">
                        <path
                          v-for="(p, i) in glyphsOf(a.id, o.id)"
                          :key="i"
                          :d="p.d"
                          :fill="p.fill ? 'currentColor' : 'none'"
                          :stroke-dasharray="p.dash"
                          stroke="currentColor"
                          stroke-width="1.3"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </span>
                    <span class="cell__name">{{ o.name }}</span>
                    <span v-if="o.dark" class="cell__night">夜</span>
                  </button>
                </td>

                <!-- 补齐到 COLS：表格左右对齐靠的是列，不是空着不写 -->
                <td v-for="n in COLS - a.options.length" :key="`pad${n}`" class="pad" />
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="foot">
          <!--
            这里原来显示的是拼好的 `?theme=…&ui=…` 那一行。
            那是代码，不是话 —— 用户没有理由读一串查询参数。
            现在只说一件事：**改了几条、改了哪几条**；链接交给右边那颗按钮。
          -->
          <p class="label foot__state">{{ stateLine }}</p>
          <div class="foot__btns">
            <button class="btn ghost foot__b" type="button" title="给演示用：随机配一套" @click="surprise">随机一套</button>
            <button class="btn ghost foot__b" type="button" @click="reset">重置为默认</button>
            <button class="btn foot__b" type="button" :disabled="!changed.length" @click="copy">
              {{ copied ? '已复制链接' : '复制搭配' }}
            </button>
          </div>
        </footer>
      </section>
    </transition>
  </Teleport>
</template>

<style scoped>
/*
 * 落点：字在左上角就从左边落，在门户右上角就从右边落。
 * 宽度按"八列 + 行头"给足（880px），窄屏退回可用宽度；高度封顶后中间那段自己滚。
 */
.look {
  position: fixed; top: 54px; z-index: var(--z-overlay);
  width: min(880px, calc(100vw - 32px));
  max-height: min(78vh, 720px);
  display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
  gap: var(--s3);
  padding: var(--s4);
  border-radius: var(--r-md);
  /*
   * 面板略透：它盖住的正是"被改的那块界面"，而外观台的全部价值就是**边改边看**。
   * 纯不透明的面板把预览遮掉一半，用户只能关掉面板再看 —— 那就不是"实时预览"了。
   * 只让**底**透（文字仍是不透明的 --ink-*），所以读起来清楚、看下去也能看见身后在变。
   */
  background: color-mix(in srgb, var(--c-paper) 88%, transparent);
  animation: sheet-in 320ms var(--ease-expo) both;
}
.look--left { left: 22px; }
.look--right { right: 22px; }

.head { display: flex; align-items: baseline; gap: var(--s3); flex-wrap: wrap; }
.head__text { display: grid; gap: 2px; min-width: 0; }
.head__k { color: var(--ink-faint); }
.head__now { font-size: var(--t-sm); color: var(--ink-1); font-weight: 600; }
.head__hint { margin-left: auto; color: var(--ink-faint); }
.head__x {
  flex: 0 0 auto; align-self: flex-start;
  width: 26px; height: 26px; border-radius: 50%;
  color: var(--ink-3); font-size: var(--t-sm);
  transition: color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.head__x:hover { color: var(--ink-1); background: var(--fill-hover); }

.scroll { overflow: auto; min-height: 0; }

/* ── 矩阵本体 ──────────────────────────────────────────────────────── */
.matrix {
  width: 100%;
  border-collapse: separate;
  border-spacing: 4px 4px;
  table-layout: fixed;
}
.matrix__c0 { width: 132px; }

/* 行头：轴名 + 一句话 + 退回默认。压在上边线里，像表格的栏目 */
.rowhead {
  position: relative;
  text-align: left; vertical-align: top;
  padding: var(--s2) var(--s2) var(--s2) 0;
  border-right: 1px solid var(--line-1);
}
.rowhead__name { display: block; font-size: var(--t-sm); font-weight: 600; color: var(--ink-1); }
.rowhead__note { display: block; margin-top: 2px; font-size: var(--t-label); line-height: 1.45; color: var(--ink-3); }
.rowhead__reset {
  position: absolute; right: 6px; top: var(--s2);
  width: 20px; height: 20px; border-radius: 50%;
  color: var(--ink-3); font-size: var(--t-label);
  transition: color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.rowhead__reset:hover { color: var(--accent); background: var(--accent-soft); }

/* 格子：小图在上、名字在下，选中时整格点亮 */
.cell {
  width: 100%; height: 100%;
  display: grid; justify-items: center; align-content: center; gap: 3px;
  padding: 7px 4px;
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--n-1);
  color: var(--ink-2);
  transition: border-color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out),
              color var(--dur-micro) var(--ease-out),
              box-shadow var(--dur-micro) var(--ease-out);
}
.cell:hover { border-color: var(--line-4); background: var(--fill-hover); color: var(--ink-1); }
.cell.is-on {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.cell__mark { display: grid; place-items: center; height: 16px; }
.cell__name { font-size: var(--t-label); font-weight: 600; }
.cell__night {
  font-size: var(--t-label); font-weight: 500; color: var(--ink-3);
}
.cell.is-on .cell__night { color: var(--accent); }

.sw { display: inline-flex; gap: 2px; }
.sw i { width: 9px; height: 9px; border-radius: 2px; box-shadow: inset 0 0 0 1px var(--line-2); }
.g { width: 13px; height: 13px; display: block; }
.g--card { border: 1px solid var(--line-3); border-radius: 4px; }
.g--float { border: 0; border-radius: 8px; background: var(--fill-hover); }
.g--sticker { border: 2px solid var(--ink-1); border-radius: 2px; box-shadow: 2px 2px 0 var(--ink-1); }
.g--plain { border: 0; border-radius: 3px; background: var(--n-3); }
.g--dense {
  width: 9px; height: 9px; border: 1px solid var(--line-2); border-radius: 1px;
  background: repeating-linear-gradient(180deg, var(--line-3) 0 1px, transparent 1px 3px);
}
.g--roomy { width: 14px; height: 14px; border: 1px solid var(--line-2); border-radius: 7px; }
.mk { width: 15px; height: 15px; display: block; }
/* 字体档的预览：一小句真字，用那一档的字栈排出来 */
.ff { font-size: 13px; line-height: 1; color: var(--ink-1); white-space: nowrap; }

.pad { border: 0; }

/* ── 脚：当前这条链接 + 三个动作 ───────────────────────────────────── */
.foot {
  display: flex; align-items: center; gap: var(--s3);
  padding-top: var(--s2);
  border-top: 1px solid var(--line-1);
}
.foot__state { flex: 1 1 auto; min-width: 0; color: var(--ink-3); }
.foot__btns { display: flex; gap: var(--s2); flex: 0 0 auto; }
.foot__b { min-height: 30px; padding: 4px 12px; font-size: var(--t-xs); }
.foot__b:disabled { opacity: 0.5; cursor: default; transform: none; }

.drop-enter-active { transition: opacity 160ms var(--ease-out), transform 220ms var(--ease-expo); }
.drop-leave-active { transition: opacity 120ms var(--ease-in), transform 120ms var(--ease-in); }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-8px) scale(0.995); }

/*
 * 窄屏：八列摊不开，矩阵改成"每行自己折行"。
 * 表格元素的 display 改掉之后，列宽约束随之失效 —— 这正是我们要的：
 * 一列一个档，能放几个放几个。
 */
@media (max-width: 860px) {
  .look { top: 48px; left: 12px; right: 12px; width: auto; padding: var(--s3); max-height: 74vh; }
  .matrix, .matrix tbody, .matrix tr, .matrix th, .matrix td { display: block; width: auto; }
  .matrix tr { padding-bottom: var(--s2); }
  .rowhead { border-right: 0; border-bottom: 1px solid var(--line-1); padding-right: 0; }
  .rowhead__reset { position: static; float: right; }
  .matrix td { display: inline-block; width: auto; padding: 3px 3px 0 0; }
  .matrix td.pad { display: none; }
  .cell { padding: 6px 10px; grid-auto-flow: column; align-items: center; gap: 6px; }
  .foot { flex-direction: column; align-items: stretch; }
}

@media print {
  .look { display: none; }
}
</style>
