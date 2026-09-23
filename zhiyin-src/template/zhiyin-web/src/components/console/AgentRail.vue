<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { STAGES, type FloatItem, type Notice } from '@/data/content'
import NextAsk from '@/components/console/NextAsk.vue'
import { useSessionStore } from '@/stores/session'

/**
 * 五层智能体的轨道 —— 放在顶栏，一直看得见。
 *
 * 为什么要有它：产品最强的能力是"五个环节各有一个角色自动接手"，
 * 但之前这件事只体现在一句状态文字里，用户根本感觉不到有人在替他做事。
 *
 * 所以这里把它做成一条**可见的轨道**：
 *   五个环节横向排开 → 现在在哪一环节亮起来 → 谁在这个环节里干活 →
 *   上一棒是谁、为什么交接（点开是完整时间轴）
 *
 * 再加上"自动介入"的播报：新数据进来（绑定学信网、课程导入、任务完成）时，
 * 轨道上会亮起一次交接动画，并说一句"我接手了，因为…"。
 */
const session = useSessionStore()
const open = ref(false)

/**
 * 有播报要说话时，把这件事告诉外面那片浮层 —— 它得先滑下来，话才说得出口。
 *
 * 这不是外观问题：这一片平时是**收起**的（整条滑出视口），而播报挂在它下面。
 * 它不收上去的时候，播报就会停在屏幕最上沿探出半个身子 —— 既难读，
 * 又会让浮层自己的展开判定来回打架。所以"要说话"= "自动现身"，说完再自己收回去。
 */
const emit = defineEmits<{ announce: [boolean] }>()

/**
 * 播报这一片占多高 —— 报给外面，让右上角的"消息"那一叠**让开**。
 *
 * 这里踩到的是一个实打实的重叠：两块推送都挂在右上角，播报（谁接手了 / 外部情报）
 * 从轨道下方长下来，消息叠固定在 top: 74px —— 两者在 74px 那一带叠在一起，
 * 而且是**消息叠压在播报上面**（消息叠的层级更高）。表现是播报卡看得见、
 * 点不动：它的按钮被上面那张卡吃掉了。
 *
 * 修法不是调数值，而是把高度报出去：`.pops` 一变高矮就量一次，写进
 * `--rail-pops-h`；消息叠用 `top: calc(74px + var(--rail-pops-h))` 往下让。
 * 一个变量、一处测量，两个推送系统就排成一列了。
 */
/*
 * `<transition-group>` 上的 ref 拿到的是**组件实例**，不是 DOM 节点 ——
 * 直接把它交给 ResizeObserver 会抛 "parameter 1 is not of type 'Element'"
 * （实测踩过）。所以这里取它的 `$el`。
 */
const pops = ref<{ $el?: Element } | null>(null)
let popsObserver: ResizeObserver | null = null

function reportPopsHeight() {
  const el = pops.value?.$el
  const height = el instanceof HTMLElement ? el.getBoundingClientRect().height : 0
  document.documentElement.style.setProperty('--rail-pops-h', `${Math.round(height)}px`)
}

/**
 * 五个环节 —— 这是业务结构（与后端 stage 一一对应），轨道上它只表示"走到哪了"。
 * 每一节由谁接手不由前端写死：那是后端回包里的主理展示名。
 */
const LAYERS = [
  { id: 'collect', label: '采集' },
  { id: 'diagnose', label: '诊断' },
  { id: 'decide', label: '决策' },
  { id: 'act', label: '行动' },
  { id: 'review', label: '复盘' },
]

/** 当前处在哪一环节：只认后端回包（TurnView.stage）—— 那是编排器的权威判定；
 *  没有回包就不猜（以前会按本地阶段推演出一个"正在干活"的假状态）。 */
const at = computed(() => {
  if (session.rail) {
    const idx = LAYERS.findIndex((l) => l.id === session.rail!.stage)
    if (idx >= 0) return idx
  }
  return -1
})

const stage = computed(() => STAGES.find((s) => s.id === session.stage) ?? null)

/**
 * "谁在干活"直接用后端回包里的主理展示名。
 *
 * 以前这里会拿后端给的名字去前端写死的角色表里查一次，查不到就退回一个本地角色 ——
 * 于是后端换人、改名、加角色，界面都显示同一个编出来的名字。
 * 名字是后端的事实，前端只负责显示。
 */
const workingName = computed(() => session.rail?.leadName ?? '')
/** 展开面板里那句"它在做什么" —— 收起状态不再显示它（见模板注释） */
const workingNote = computed(() => session.rail?.disclosure ?? '正在处理这一轮')

/*
 * 自动介入的播报。
 * 只要"数据/状态变了"（绑定完成、课程导入、采纳了推荐、解决了一件事），
 * 轨道就播一次交接 —— 这是"五个角色在轮班替你干活"最直接的体感。
 */
const interjections = ref<{ id: number; who: string; what: string; why: string; at: number }[]>([])
let seq = 0

function interject(who: string, what: string, why: string) {
  const item = { id: ++seq, who, what, why, at: Date.now() }
  interjections.value = [item, ...interjections.value].slice(0, 3)
  window.setTimeout(() => {
    interjections.value = interjections.value.filter((i) => i.id !== item.id)
  }, 9000)
}

/*
 * 外部情报 —— **归队**。
 *
 * 之前它单飞在右下角的浮窗叠里，和右上这套实时播报是两套长相、两个角落。
 * 现在它进 pops：和"谁接手了"同一套材质、同一个位置、同一条现身逻辑
 * （有话要说 → 整片轨道自动滑下来）。
 */
const intelFloats = computed(() =>
  session.floats.filter((f): f is Notice => f.tone === 'intel'),
)
const intelTimers = new Map<string, number>()
watch(
  intelFloats,
  (list) => {
    for (const item of list) {
      if (intelTimers.has(item.id)) continue
      intelTimers.set(item.id, window.setTimeout(() => {
        session.dismissFloat(item.id)
        intelTimers.delete(item.id)
      }, 16000))
    }
    for (const [id, timer] of intelTimers) {
      if (!list.some((f) => f.id === id)) {
        window.clearTimeout(timer)
        intelTimers.delete(id)
      }
    }
  },
  { immediate: true },
)

function intelOpen(id: string) {
  session.dismissFloat(id)
  session.openOverlay('intel')
}

/*
 * **一次只说一条。**
 *
 * 三个来源会同时往里塞：交接播报（最多留 3 条）、外部情报（每次轮询冒一条）、
 * 加上右上消息叠自己的四片 —— 一次拉取就"跳五个"。
 * 交接与情报本来就是"顺口说一句"的东西，不是待办清单：
 * 一条说完再说下一条，还剩几条用一行计数交代清楚。
 */
const queued = computed(() => [...interjections.value, ...intelFloats.value])
const shown = computed(() => queued.value[0] ?? null)
const waiting = computed(() => Math.max(0, queued.value.length - 1))

function isIntel(item: unknown): item is Notice {
  return (item as Notice | null)?.tone === 'intel'
}

/** 收起当前这条，让下一条顶上来（点"还有 N 条"就是走这里）。 */
function advance() {
  const head = shown.value
  if (!head) return
  if (isIntel(head)) session.dismissFloat(head.id)
  else interjections.value = interjections.value.filter((i) => i.id !== head.id)
}

/*
 * 播报上那三个动作：看这条、去看这批、知道了。
 *
 * 为什么都要先判一次空：这条卡片淡出时（transition 那几百毫秒）
 * **节点还在屏幕上**，而 `shown` 已经是 null 了 —— 这时候点下去，
 * 老写法 `shown.id` 会直接抛 `Cannot read properties of null (reading 'id')`。
 * 实测是核验脚本连点"知道了"撞上的（整支浏览器 e2e 因此报了一条页面级 JS 报错），
 * 真人手快也一样会撞上：看到卡片在消失、又点了一下。
 * 拿不到就当没点 —— 那一条本来就是已经被收走的那条。
 */
function openHead() {
  const item = shown.value
  if (!item || isIntel(item)) return
  session.openDrawer(item.who, item.what, [
    { source: '为什么由它接手', detail: item.why, confidence: 0.9, at: '刚刚' },
  ])
}

function intelHead() {
  const item = shown.value
  if (!item || !isIntel(item)) return
  intelOpen(String(item.id))
}

function dismissHead() {
  const item = shown.value
  if (!item) return
  session.dismissFloat(String(item.id))
}

/*
 * 情报轮询 —— 从画布那块「外部情报」搬过来的职责。
 *
 * 画布上不再摆一块情报卡（它归队到这里了），但"每 45 秒自己看一次公开渠道"
 * 这件事还在：取到新的（条数变了）就交给 pops 冒一条情报卡；没取到就不打扰。
 */
let intelTimer: number | null = null
let lastIntelCount = -1

async function pollIntel(auto: boolean) {
  /*
   * 取数交给 store（`loadIntel`）—— 画布上那一块和情报浮层读的是同一份。
   * 这里只负责"新到的要说一声"：条数变了才冒一条。
   */
  await session.loadIntel(auto)
  const items = session.intel?.items ?? []
  if (items.length && items.length !== lastIntelCount) {
    session.pushFloat({
      id: `intel-${Date.now()}`,
      type: 'notice',
      tone: 'intel',
      kicker: '外部情报',
      title: `取到 ${items.length} 条和你方向相关的公开信息`,
      body: items[0]?.title || items[0]?.text || '点开看这一批的来源。',
      action: { kind: 'intel', label: '看这一批' },
    } as FloatItem)
  }
  lastIntelCount = items.length
}

onMounted(async () => {
  await pollIntel(false)
  intelTimer = window.setInterval(() => void pollIntel(true), 45_000)
})
onBeforeUnmount(() => {
  if (intelTimer) window.clearInterval(intelTimer)
  popsObserver?.disconnect()
  document.documentElement.style.removeProperty('--rail-pops-h')
})

/* 播报一出现／一收走，就把它的高矮报出去（消息叠据此让位） */
onMounted(() => {
  const el = pops.value?.$el
  if (!(el instanceof HTMLElement)) return
  popsObserver = new ResizeObserver(reportPopsHeight)
  popsObserver.observe(el)
  reportPopsHeight()
})

/** 有话要说（交接播报或情报）→ 整片自动现身；说完/收完再自己回去 */
const announcing = computed(() => interjections.value.length > 0 || intelFloats.value.length > 0)
watch(announcing, (on) => emit('announce', on), { immediate: true })

/** 监听会触发"换人"的状态：绑定了学信网、或者用户有了新的选择 */
const bound = ref(session.chsiBound)
onMounted(() => {
  const timer = window.setInterval(() => {
    if (session.chsiBound !== bound.value) {
      bound.value = session.chsiBound
      if (bound.value) {
        interject('信息侦查员 → 路径规划师', '学信网的 9 门课已经排进课表', '采集环节从问卷换成了学籍数据，行动环节可以直接排时间了')
        window.setTimeout(() => interject('路径规划师 → 职业顾问', '空档算完，交回给判断方向的人', '时间有了，接下来该决定把哪一格缺口补上'), 3200)
      }
    }
  }, 800)
  onBeforeUnmount(() => window.clearInterval(timer))
})
</script>

<template>
  <div class="rail">
    <!-- 轨道本体：五个环节，现在那一节亮着 -->
    <button class="rail__bar" type="button" :aria-expanded="open" @click="open = !open">
      <span class="rail__track" aria-hidden="true">
        <i v-for="(l, i) in LAYERS" :key="l.id" :class="{ on: i === at, past: i < at }" />
      </span>
      <!--
        收起时只说一件事：**现在谁在替你干活**。

        这里原来塞了四段字（环节名 / 主理名 / 正在做什么 / 阶段名），
        加上五节轨道，"谁在干活、走到哪了、是不是轮到我"全挤在一颗胶囊里 ——
        读起来是一句话都没有重点。它不是内容，是一个**状态指示器**：
        轨道说走到哪，名字说谁在干，提示点说轮到你了。其余全在展开面板里。
      -->
      <span class="rail__agent">{{ workingName || '待开始' }}</span>
      <!-- 轮到你：一个点。真正的邀请在展开面板里（那里有可点的下一步） -->
      <span
        v-if="session.nextAsk"
        class="rail__turn-dot"
        :title="`轮到你 · ${session.nextAsk.cta}`"
        aria-hidden="true"
      />
    </button>

    <!-- 展开：谁在做、上一棒是谁、为什么交接 -->
    <transition name="fold">
      <div v-if="open" class="panel">
        <p class="label panel__head">{{ stage?.label ?? '当前' }}这一步，谁在替你做什么</p>

        <!-- 轮到你做什么：AI 推的那件事，展开就能直接做 -->
        <div v-if="session.nextAsk" class="panel__ask">
          <span class="label panel__ask-k">轮到你</span>
          <NextAsk />
        </div>

        <!-- 这一轮它在做什么：收起时不显示，展开才说 -->
        <p v-if="workingName" class="panel__note">{{ workingNote }}</p>

        <ol class="people">
          <li v-for="(l, i) in LAYERS" :key="l.id" :class="{ now: i === at, done: i < at }">
            <span class="people__dot" aria-hidden="true" />
            <span class="people__layer">{{ l.label }}</span>
            <span class="people__agent">{{ i === at && workingName ? workingName : '—' }}</span>
            <span class="label people__state">{{ i < at ? '已完成' : i === at ? '进行中' : '待接手' }}</span>
          </li>
        </ol>
        <button class="panel__more label" type="button" @click="session.openDrawer('谁在什么时候替你做了什么', '含每次为什么换人', [])">
          看完整交接记录 →
        </button>
      </div>
    </transition>

    <!-- 自动介入播报 + 外部情报：同一套实时体系，数据一进来就出现，到点自己走 -->
    <transition-group ref="pops" name="pop" tag="div" class="pops">
      <!-- 一次只有一条：交接播报与外部情报共用这一个位置（谁先来谁先说） -->
      <template v-if="shown">
        <button
          v-if="!isIntel(shown)"
          :key="shown.id"
          class="pop"
          type="button"
          @click="openHead"
        >
          <span class="pop__who">{{ shown.who }}</span>
          <span class="pop__what">{{ shown.what }}</span>
          <span class="pop__why">{{ shown.why }}</span>
        </button>

        <!-- 外部情报：带动作的一张卡，话不说半句 -->
        <div v-else :key="shown.id" class="pop pop--intel">
          <span class="pop__who">{{ shown.kicker }}<i class="pop__live" aria-hidden="true" /></span>
          <span class="pop__what">{{ shown.title }}</span>
          <span class="pop__why">{{ shown.body }}</span>
          <div class="pop__acts">
            <button
              v-if="shown.action"
              class="pop__act pop__act--go"
              type="button"
              @click="intelHead"
            >{{ shown.action.label }}</button>
            <button class="pop__act" type="button" @click="dismissHead">知道了</button>
          </div>
        </div>

        <!-- 还剩几条：点一下收起这条、看下一条 -->
        <button
          v-if="waiting"
          class="pop__rest label"
          type="button"
          @click="advance()"
        >还有 {{ waiting }} 条 · 看下一条</button>
      </template>
    </transition-group>
  </div>
</template>

<style scoped>
.rail { position: relative; }
.rail__bar {
  display: inline-flex; align-items: center; gap: var(--s3);
  /* 与顶栏其它控件同高：一排控件高度不一致，比任何装饰都更显乱 */
  height: 32px; padding: 0 var(--s3);
  border: 1px solid var(--line-2); border-radius: var(--r-pill);
  background: var(--n-1);
  transition: border-color var(--mo-fast) var(--mo-out);
}
.rail__bar:hover { border-color: var(--line-4); }

/* 五节轨道：走过的填绿、现在这节是紫的并轻微呼吸 */
.rail__track { display: flex; align-items: center; gap: 3px; }
.rail__track i { width: 14px; height: 5px; border-radius: 3px; background: var(--line-2); }
.rail__track i.past { background: var(--mk-green); }
.rail__track i.on { background: var(--mk-purple); width: 20px; animation: mo-breathe 2.4s var(--mo-out) infinite; }

.rail__now { display: inline-flex; align-items: baseline; gap: var(--s2); min-width: 0; }
.rail__layer { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
/* 收起时唯一的一句话：主理名。它变了，就是换人了 */
.rail__agent { font-size: var(--fs-small); color: var(--mk-purple); white-space: nowrap; }
.rail__what { font-size: var(--fs-small); color: var(--ink-3); max-width: 30ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* "轮到你"用强调色 —— 这是整个顶栏唯一一处该响的地方 */
.rail__turn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--fs-small); font-weight: 500; color: var(--accent);
}
/* 一个点就够：它只回答"是不是轮到我"，不承担解释 */
.rail__turn-dot {
  width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: var(--accent);
  animation: mo-breathe 2.2s var(--ease-out) infinite;
}
.rail__stage { color: var(--ink-3); }

.panel {
  /*
   * **右对齐**，不是左对齐。
   *
   * 这片浮层整个贴在屏幕右边（`.chrome--right` 是 right 定位），
   * 面板再按 left:0 展开、宽 460，右边缘就会从轨道左沿往右多出 460px ——
   * 直接跑出屏幕外，被 .console 的 overflow 裁掉一半。
   *
   * 宽度也用 min(...) 兜一层：窗口再窄一点时，460 的固定宽同样会溢出。
   * 播报气泡（.pops）本来就是右对齐的，两处口径现在一致。
   */
  position: absolute; right: 0; top: calc(100% + 8px); z-index: var(--z-float);
  width: min(460px, calc(100vw - 2 * var(--s5))); padding: var(--s3);
  /* 展开面板：白纸 + 1px 套版线。粗框与投影在这一稿里全部作废 */
  border: var(--bw) solid var(--line-3); border-radius: var(--r-md);
  background: var(--n-1);
  transform: rotate(-0.2deg);
}
.panel__head { margin-bottom: var(--s2); color: var(--ink-3); }
.panel__ask {
  display: flex; flex-direction: column; gap: 6px;
  padding: var(--s3);
  margin-bottom: var(--s3);
  border: 1px solid var(--accent);
  border-radius: var(--r-md);
  background: var(--accent-soft);
}
.panel__ask-k { color: var(--accent); }
.panel__note { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.6; margin-bottom: var(--s3); }
.people { list-style: none; margin: 0; padding: 0; display: grid; }
.people li { display: grid; grid-template-columns: 8px 56px 90px minmax(0, 1fr); align-items: center; gap: var(--s3); padding: 6px var(--s3); border-radius: var(--r-sm); }
.people li.now { background: var(--fill-subtle); }
.people__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--line-4); }
.people li.done .people__dot { background: var(--mk-green); }
.people li.now .people__dot { background: var(--mk-purple); }
.people__layer { font-size: var(--fs-small); color: var(--ink-2); }
.people__agent { font-size: var(--fs-small); color: var(--ink-1); }
.people li.now .people__agent { color: var(--mk-purple); font-weight: 600; }
.people__state { text-align: right; }
.panel__more { margin-top: var(--s2); color: var(--ink-3); transition: color var(--mo-fast) var(--mo-out); }
.panel__more:hover { color: var(--accent); }

/*
 * 自动介入播报 + 情报卡。
 *
 * 它是**贴在桌面右边的一张便条**：比上一版窄（380 → 320），
 * 轻微歪着，用平涂 + 1px 墨线。上一版是"2px 粗框 + 大投影"的大卡片，
 * 从右上角压下来，正好盖住右边一列的两个块 —— 那是用户说的"组件重叠"里
 * 最扎眼的一处。窄一档之后它只压住一块的右上角，而且一眼看得出是"贴上去的"，
 * 不是"排坏了的卡片"。
 */
.pops { position: absolute; right: 0; top: calc(100% + 8px); display: grid; gap: var(--s2); width: 320px; }
.pop {
  display: grid; gap: 2px; text-align: left;
  padding: 10px var(--s3) 10px var(--s4);
  border: var(--bw) solid var(--line-2); border-left: 5px solid var(--mk-purple);
  border-radius: var(--r-sketch-md);
  background: var(--mk-purple-soft);
  box-shadow: var(--e-2);
  transform: rotate(0.4deg);
}
.pop__who { font-family: var(--font-display); font-size: var(--t-xs); color: var(--mk-purple); }
/*
 * 一行摘要，展开才说细节。
 *
 * 上一版这条便条是三段文字摞在一起（谁 / 什么 / 为什么），高 200px ——
 * 从右上角压下来正好盖住右边一列的两块。现在收成一行：
 * 谁做的事 + 一句什么，`为什么` 悬停或聚焦时才展开。
 * 播报的职责是"让你知道有这么回事"，不是"在这里把话说完"。
 */
.pop__what {
  font-family: var(--font-display); font-size: var(--t-h4); line-height: 1.32; color: var(--ink-1);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pop__why {
  font-size: var(--t-xs); color: var(--ink-2); line-height: 1.6;
  /* 推送必须能说清"为什么"，所以这句一直在（只压到两行，不靠悬停才显示） */
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

/* 情报卡：蓝色的那一档，自带动作排 */
.pop--intel {
  border-left-color: var(--mk-blue);
  background: var(--paper-lit);
  transform: rotate(-0.5deg);
}
.pop--intel .pop__who { color: var(--mk-blue); display: inline-flex; align-items: center; gap: 6px; }
.pop__live {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--mk-blue); animation: mo-breathe 2.2s var(--ease-out) infinite;
}
.pop__acts { display: flex; gap: var(--s2); margin-top: var(--s1); }
.pop__act {
  height: 28px; padding: 0 12px;
  border: 1px solid var(--line-3); border-radius: var(--r-sketch-sm);
  background: var(--n-1); font-size: var(--t-xs); color: var(--ink-2);
  transition: color var(--dur-micro) var(--ease-out), border-color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out);
}
.pop__act:hover { color: var(--ink-1); border-color: var(--line-4); }
.pop__act--go { border-color: var(--mk-blue); color: var(--mk-blue); font-weight: 600; }
/*
 * "还有 N 条 · 看下一条"：一次只说一条之后，这一行是**唯一的入口**，
 * 所以它得看得出来能点，又不能在卡片里抢戏 —— 用一条安静的说明。
 */
.pop__rest {
  justify-self: start;
  margin-top: 2px;
  padding: 0;
  border: 0; background: none;
  color: var(--ink-3);
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}
.pop__rest:hover { color: var(--ink-1); }
.pop__act--go:hover { background: var(--mk-blue-soft); }

.fold-enter-active { transition: opacity 200ms var(--mo-out), transform 240ms var(--mo-out); }
.fold-leave-active { transition: opacity 140ms var(--mo-in), transform 140ms var(--mo-in); }
.fold-enter-from, .fold-leave-to { opacity: 0; transform: translateY(-6px); }
.pop-enter-active { transition: opacity 240ms var(--mo-out), transform 320ms var(--mo-spring); }
.pop-leave-active { transition: opacity 200ms var(--mo-in), transform 200ms var(--mo-in); }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(-8px) scale(0.97); }

@media (max-width: 1100px) {
  .rail__what { max-width: 16ch; }
  .panel, .pops { width: min(360px, calc(100vw - 2 * var(--s5))); }
}
</style>
