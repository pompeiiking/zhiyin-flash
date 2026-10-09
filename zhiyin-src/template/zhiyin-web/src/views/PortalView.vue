<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { annotate } from 'rough-notation'
/* 包只导出 annotate / annotationGroup 两个函数，类型直接用它的返回值推 */
type RoughAnnotation = ReturnType<typeof annotate>
import ClickSpark from '@/components/vendor/vuebits/ClickSpark.vue'
import Magnet from '@/components/vendor/vuebits/Magnet.vue'
import BlurText from '@/components/vendor/vuebits/BlurText.vue'
import VariableProximity from '@/components/vendor/vuebits/VariableProximity.vue'
import InkField from '@/components/portal/InkField.vue'
import InkButton from '@/components/portal/InkButton.vue'
import HeroMap from '@/components/portal/HeroMap.vue'
import LookTrigger from '@/components/theme/LookTrigger.vue'
import { authToken, getPortal, type PortalContent } from '@/api/client'
import { CIRCLED, type StopCopy } from '@/data/portal'
import { useSessionStore } from '@/stores/session'
import { failureText } from '@/lib/failure'
import { THEME_EVENT } from '@/lib/theme'

/*
 * 门户 —— 一页，一屏，不滚动。
 *
 * 这一版的重点是**不再自己手搓动效**，能用成熟开源件的地方就用：
 *   主张入场   vue-bits · BlurText        （逐词去模糊落下，motion-v 驱动）
 *   圈住"下一步" rough-notation            （手绘圈，这是它的看家功能）
 *   说明句      vue-bits · VariableProximity（字重随光标变，吃自托管可变中文字体）
 *   主按钮      vue-bits · Magnet          （磁吸，越靠近越被吸过去）
 *   整页点击    vue-bits · ClickSpark      （点哪儿哪儿出墨点）
 *   底图        vue-bits · MagnetLines     （一片会跟着光标弯的线，压在擦痕下面）
 *
 * 剩下只有三件是我们自己的、也应当是我们自己的：内容（说给谁听）、
 * 手绘地图（叙述载体）、以及这一页不滚动的结构。
 *
 * v8 结构：顶栏整条拿掉。
 *
 * 原来左上角那个小标和"我已经用过 · 直接进"，是登录之后给自己用的近路，
 * 对第一次来的人没有意义 —— 它占着最贵的左上角，却不回答任何问题。
 * 现在左上角站的是主标题「职引」两个手绘字，它和右边那块被盖住的路一起
 * 说明这页要说的事：你知道要去哪，但中间那一段你还不知道怎么写。
 *
 * 一屏两栏（v10 起）：
 *   左栏 · 舞台：职引 + 主张 + 说明 + 入口
 *   右栏 · 地图：那张手绘的路，中间一段被擦掉，用笔写回来
 *
 * v10：地图从"整张纸的轴"收回右栏。
 *
 * 它原来铺满整页、压在文字底下，于是首屏要同时读三件事：一大片会动的墨、
 * 八个带字的站点、以及左边的主张与按钮。首屏只有一次"第一眼"，三者并列
 * 就没有第一眼（GitHub #15：入口页背景地图干扰主要入口）。
 * 现在舞台只占左栏，地图是右栏里的一张图：墨压到 0.72，图上那批在 0.37 倍
 * 缩放下读不成字的站名整组收起来（见 HeroMap 的小样模式）。
 * 地图没有被删、也没有变成静态图 —— 它仍是 roughjs 一笔一笔画的，
 * 中段那道擦痕照样写得回来，只是笔现在只在这张图上写。
 * 舞台排在地图前面：Tab 先走到右边那个"开始用"，再走到图上那几个站。
 *
 * v9：底下那一条整条拿掉。
 *
 * 它原来放两样东西：左边"这一页只出现一次 · 之后每次打开直接落在今天"，
 * 右边一个"开始用 →"。两样都是**自述**，不是给读者的话：
 *   · 读者不关心这页出现几次 —— 那是我们自己看结构的说明；
 *   · 一页上两个"开始用"（主按钮 + 右下角）互相削弱，第二个还更小、更容易被忽略。
 * 现在页面只有一个出口：主张下面的那个按钮。
 */
const router = useRouter()
const session = useSessionStore()

const entered = ref(false)
const reveal = ref(false)
const pageEl = ref<HTMLElement | null>(null)
const claimEl = ref<HTMLElement | null>(null)

/*
 * 门户内容全部来自后端（公开接口 `GET /app/portal`）。
 *
 * 这里**不留一份兜底文案**：留了就等于有两份「主张」，改一处另一处不会跟着变 ——
 * 而"文案只有一份"正是这条链路的全部意义。拿不到就如实说拿不到，给一个重试。
 */
const content = ref<PortalContent | null>(null)
const loadError = ref('')
const loading = ref(true)

const copy = computed<Record<string, string>>(() => content.value?.copy_bundle ?? {})
const text = (key: string) => copy.value[key] ?? ''

/** 主张按 `//` 分行、`|` 分组：文案在后端，排版在前端 */
const claimLines = computed(() =>
  text('portal.claim_lines')
    .split('//')
    .map((line) => line.split('|'))
    .filter((line) => line.length > 0 && line[0] !== ''),
)

/** 地图八站的文案：`portal.stop.<id>.<字段>` */
const stopCopy = computed<Record<string, StopCopy>>(() => {
  const out: Record<string, StopCopy> = {}
  for (const [key, value] of Object.entries(copy.value)) {
    const match = /^portal\.stop\.(\w+)\.(label|at|more)$/.exec(key)
    if (!match) continue
    const [, id, field] = match
    out[id] = { ...(out[id] ?? {}), [field]: value }
  }
  return out
})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    content.value = await getPortal()
  } catch (cause) {
    loadError.value = failureText(cause)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  await nextTick()
  drawRing()
})

function enter() {
  entered.value = true
  session.enterPortal()
  /*
   * 门户就是登录发生的地方，不是"绕过登录"的地方。
   * 没有令牌就地掀开登录层；登录成功后 AuthLayer 自己推进控制台。
   * 这里绝不写本地假令牌 —— 曾经写过一次，把真实会话顶掉了。
   */
  if (!authToken()) {
    session.openAuth('login')
    return
  }
  router.push('/')
}

/* ── 手绘圈：由 rough-notation 画在被标出的那个词上 ───────────────── */
let ring: RoughAnnotation | null = null

const reduced = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/*
 * 颜色从令牌读出来（给已解析的值）。
 *
 * 这两个消费方都**不吃 CSS 变量**：ClickSpark 把它塞进 canvas 的 strokeStyle，
 * rough-notation 用它生成 SVG。所以令牌要由 JS 取一次再递进去；
 * 而"换皮肤"这件事必须让它们重取 —— 见下面的 THEME_EVENT。
 */
function token(name: string, fallback: string) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** 墨点颜色 = 记号笔绿，与那个手绘圈同一支笔（原来是写死的 #0a5842，上一版的绿） */
const sparkColor = ref(token('--mk-green', '#257040'))

function drawRing() {
  const el = claimEl.value?.querySelector<HTMLElement>('.bt__seg--mark')
  if (!el) return
  ring?.remove()
  ring = annotate(el, {
    type: 'circle',
    /* 圈线跟着皮肤走：默认是记号笔绿，暗色皮肤上是提亮过的那支 */
    color: token('--mk-green', '#257040'),
    strokeWidth: 2.4,
    padding: 9,
    iterations: 2,
    animate: !reduced(),
    animationDuration: 720,
  })
  ring.show()
}

/** 换皮肤：重取颜色，圈线按新色重画一次（rough-notation 不认 --var，只能重画） */
function onTheme() {
  sparkColor.value = token('--mk-green', '#257040')
  if (!loading.value && !loadError.value) drawRing()
}

onMounted(() => document.addEventListener(THEME_EVENT, onTheme))
onBeforeUnmount(() => document.removeEventListener(THEME_EVENT, onTheme))

onMounted(() => requestAnimationFrame(() => (reveal.value = true)))

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') reveal.value = true
}

onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  ring?.remove()
})
</script>

<template>
  <!--
    内容没取到 = 如实说没取到，并给一次重试。
    不留一份本地兜底文案：留了就等于有两份主张，改一处另一处不会跟着变 ——
    而"文案只有一份"正是这条链路的全部意义。
  -->
  <div v-if="loading" class="gate">
    <span class="label">正在加载…</span>
  </div>

  <div v-else-if="loadError" class="gate">
    <h1 class="gate__t editorial">这一页没加载出来。</h1>
    <p class="gate__d label">{{ loadError }}</p>
    <button class="btn" type="button" @click="load">重试</button>
  </div>

  <template v-else>
  <!--
    整页点击出火花。sparkColor 走马克笔绿，和手绘圈是同一支笔。
    canvas 是 absolute inset-0 的子元素，所以这里给它一个撑满视口的盒子。
  -->
  <ClickSpark
    class="sparkwrap"
    :spark-color="sparkColor"
    :spark-size="11"
    :spark-radius="26"
    :spark-count="9"
    :duration="560"
  >
    <div ref="pageEl" class="paper" :class="{ 'paper--in': reveal }">
      <!-- 背景：被擦过一遍的纸 + 一片跟着光标弯的线 -->
      <InkField />

      <!--
        外观台：门户是访客看到的第一屏，也是"换一套给他看"最常发生的一屏，
        所以这里也得有一个入口。它落在右上角（面板从右边下来），一个字、不加框 ——
        门户是给人看主张的地方，入口越安静越好。

        它挂在纸这一层而不是舞台上：舞台收成左栏之后，再挂"舞台的右上角"
        就跑到页面中间去了（DESIGN.md 里写的是"门户页右上角"）。
      -->
      <!--
        外观台的入口在下面 `.mapcol` 之后（DOM 顺序即 Tab 顺序：
        「开始用」必须排在"配外观"这种配置入口之前 —— 键盘用户第一个 Tab 该落到主操作）。
      -->

      <!-- 主舞台：左栏。话都在这里，右栏整片留给那张图 -->
      <main class="stage">
        <div class="say">
          <!--
            主标题：手绘字（站酷快乐体，只取「职引」两个字的子集）。
            两个字各转一点角度、各错一点基线，再用一层噪声滤镜把手写的抖动做出来 ——
            这样它是"写上去的"，不是"排上去的"，和这一页的马克笔线同源。
            用 h1 而不是 div：这一页的标题就是品牌名。
          -->
          <!--
            标题和"写给谁"并排：一个很大的名字，旁边一句很小的话。
            标题右边原本会空出一块，把这句话放过去，那一块就有人站了。
          -->
          <div class="head">
            <h1 class="wordmark">
              <svg class="wordmark__defs" aria-hidden="true" focusable="false">
                <filter id="handJitter" x="-8%" y="-8%" width="116%" height="116%">
                  <feTurbulence type="fractalNoise" baseFrequency="0.035 0.05" numOctaves="2" seed="4" result="n" />
                  <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" xChannelSelector="R" yChannelSelector="G" />
                </filter>
              </svg>
              <span class="wordmark__row">
                <span class="wordmark__ch wordmark__ch--a">职</span>
                <span class="wordmark__ch wordmark__ch--b">引</span>
              </span>
            </h1>
    <p class="kicker">{{ text('portal.kicker') }}</p>
          </div>

          <!-- 主张 + 说明句是一段话的两层，所以合成一组 -->
          <div class="pitch">
            <p ref="claimEl" class="claim editorial">
              <!--
                一行一个 BlurText：as="span" 让两行各自成块，
                第二行把"下一步"标出来（markIndex），画完圈它再交给 rough-notation。
              -->
              <BlurText
                as="span"
                class="claim__line"
                :text="(claimLines[0] ?? []).join(' ')"
                :delay="120"
                :step-duration="0.44"
              />
              <BlurText
                as="span"
                class="claim__line"
                :text="(claimLines[1] ?? []).join(' ')"
                :mark-index="CIRCLED.word"
                :delay="120"
                :step-duration="0.44"
                @done="drawRing"
              />
            </p>

            <!-- 说明句：字重跟着光标走（需要可变字重，所以吃 --font-var） -->
            <VariableProximity
              class="lede"
              :label="text('portal.lede')"
              :container-ref="pageEl"
              :radius="170"
              falloff="gaussian"
              from-font-variation-settings="'wght' 360"
              to-font-variation-settings="'wght' 780"
            />
          </div>

          <div class="cta">
            <!-- 主按钮外面套磁吸：靠近时被光标拉过去，离开自己弹回 -->
            <Magnet :padding="80" :magnet-strength="5" wrapper-class-name="cta__magnet">
              <InkButton :label="entered ? '正在进入…' : text('portal.cta')" big @click="enter" />
            </Magnet>
            <span class="cta__cost">{{ text('portal.cost') }}</span>
          </div>
        </div>

      </main>

      <!--
        右栏：那张手绘地图。
        它不再是"整张纸的轴" —— 铺满整页的墨正是这一屏最吵的东西（GitHub #15）。
        包一层 .mapcol 是因为墨层自己是 absolute inset-0：定位上下文得先是"这一格"，
        它才会乖乖待在自己栏里，而不是又铺满整页。
        它仍然不吃指针事件（只有站点自己重新打开），所以这一栏之外点哪儿都还是纸。
        排在 </main> 之后：DOM 顺序就是 Tab 顺序，键盘先到"开始用"，再到图上那几个站。
      -->
      <div class="mapcol">
        <HeroMap class="inklayer" :copy="stopCopy" />
      </div>

      <!--
        开发者的第二个入口。
        账号面板里那颗（`AccountMenu`）只在角色是 developer/admin 时显示，而开发者第一屏
        通常落在门户 —— 这里再给一个，省得他为了找"组件开发平台"去翻账号面板
        （这个入口本来就是被问出来的：入口一直有，但找不到）。
        访客与学生看不到它（同一个角色判据），所以不影响第一屏。
      -->
      <div class="look-mount">
        <RouterLink
          v-if="session.identity?.role === 'developer' || session.identity?.role === 'admin'"
          to="/developer"
          class="dev-entry label"
        >模块开发工作台 →</RouterLink>
        <LookTrigger anchor="right" />
      </div>

    </div>
  </ClickSpark>
  </template>
</template>

<style scoped>
/* 整页点击的火花需要一块撑满视口的画布（canvas 是它的 inset-0 子元素） */
.sparkwrap { display: block; height: 100dvh; }

/* 加载 / 失败态：同样是"一页一屏"，只是中间一句话 */
.gate {
  height: 100dvh; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: var(--s3);
  background: var(--n-0);
}
.gate__t { font-size: var(--fs-lg); color: var(--ink-1); }
/* 失败原因是要读的一句话，不是标签：按正文走，颜色提到 --ink-2 */
.gate__d {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--ink-2);
  max-width: 46ch;
  text-align: center;
  line-height: 1.75;
}

/*
 * 一页一屏：高度锁死、不滚动。
 * 只有一行、两栏 —— 左边是话，右边是那张手绘地图。
 *
 * 两栏是这一页的层级本身：地图的宽度在这里就被限死（它再也不可能占满整页），
 * 左栏因此成为唯一一片"有字的地方"，第一眼只能落在主张和按钮上。
 * 宽度给到 42%：再窄，地图缩得连"这是一张画出来的路"都读不出来；
 * 再宽，它就重新开始和文字抢第一眼。
 */
.paper {
  position: relative;
  height: 100%;
  overflow: hidden;
  /* 门户是一张纸，光标是一支圆珠笔（见 tokens.css 的 --cursor-pen） */
  cursor: var(--cursor-pen);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 42%);
  grid-template-rows: minmax(0, 1fr);
  column-gap: var(--s7);
  /* 四周留同一条边距：没有任何东西贴着视口边 */
  padding: var(--s5) var(--s7) var(--s5);
}

/* ── 顶栏、底栏都已拿掉：左上角交给主标题，唯一出口是主张下面那个按钮 ── */

/*
 * 主标题：手绘字。
 * 不加负字距 —— 手绘字本来就宽，挤了会变成黑块。
 * line-height 收到 0.94 是因为字上下本来就有墨的留白。
 */
.wordmark {
  margin: 0;
  opacity: 0; transform: translateY(12px); filter: blur(7px);
  transition: opacity 900ms var(--mo-out) 40ms, transform 900ms var(--mo-out) 40ms, filter 900ms var(--mo-out) 40ms;
}
.paper--in .wordmark { opacity: 1; transform: none; filter: none; }

.wordmark__defs { position: absolute; width: 0; height: 0; }

/* 整行套一层"手描抖动"：字的边因此不是印刷边，而是被描过一遍的边 */
.wordmark__row {
  display: flex; align-items: baseline;
  /* 字号放在这一层：两个字都用 em 相对它算，换字时才不会一大一小 */
  font-size: clamp(96px, 11.2vw, 182px);
  filter: url(#handJitter);
}
.wordmark__ch {
  font-family: var(--font-hand);
  font-weight: 400;
  font-size: 1em;
  line-height: 0.94;
  letter-spacing: 0.005em;
  color: var(--ink-1);
}
/* 两个字各转一点、各错一点：手写不会把两个字摆在同一条基线上 */
.wordmark__ch--a { transform: rotate(-1.8deg) translateY(3px); }
.wordmark__ch--b { font-size: 0.93em; transform: rotate(1.2deg) translateY(-4px); margin-left: -0.02em; }

/* ── 舞台（左栏） ───────────────────────────────────────────────── */
.stage {
  grid-area: 1 / 1;
  position: relative; z-index: 2; min-height: 0;
  /* 文字列靠左坐；这一栏的右边不再有东西可让，留白就是留白 */
  display: flex; align-items: center;
}
/*
 * 外观台入口：门户页右上角一个字，绝对定位，不参与这一屏的排版。
 * 窄屏不再把它改成 static：它是纸这一层的子元素，static 会让它变成一个网格项，
 * 一页纸就被拆成两行。它落在纸的右上角、字很小，压不到居中的文字列。
 */
.look-mount { position: absolute; top: var(--s5); right: var(--s7); z-index: 3; display: flex; align-items: center; gap: var(--s4); }
/*
 * 开发者入口：只有 developer/admin 会渲染（见模板里的 v-if），所以这一行
 * 对访客与学生完全不存在 —— 不会把"给内部人用的东西"摆到第一屏上。
 * 悬停仍然按全站规矩 gate 到真的能悬停的设备（触屏上不留悬停色）。
 */
.dev-entry { color: var(--ink-2); text-decoration: none; white-space: nowrap; }
@media (hover: hover) and (pointer: fine) {
  .dev-entry:hover { color: var(--accent); }
}
/*
 * 地图那一栏。
 *
 * 包一层是为了给它一个"自己的区域"：墨层自己是 absolute inset-0，
 * 所以定位上下文必须先是这一格，它才会待在自己栏里。
 *
 * 这一格按地图自己的比例定高（1512:950）并居中，而不是撑满整列 ——
 * 撑满的话，图只占这一列的三分之一，剩下三分之二是一片空纸，
 * 而那条路的右上端会停在这片空纸中间（一个没有出处的"断头"）。
 * 按比例收窄之后，路的左端从格子的左边缘进来、右端从右上角出去，
 * 两端都在格子的边上被裁掉 —— 读起来是"这张画外面还有一段"。
 *
 * overflow: hidden 就是那道裁切：一是收住两端冲出画布的墨，
 * 二是挡住它任何越界到左边文字上的可能。
 */
.mapcol {
  grid-area: 1 / 2;
  align-self: center;
  aspect-ratio: 1512 / 950;
  max-height: 100%;
  position: relative;
  overflow: hidden;
  min-width: 0;
}
/*
 * 地图的墨整体压到 0.72。
 *
 * 它现在尺寸上已经让位（一格四成宽、按地图自己的比例收起高度），
 * 但那条 `--ink-1` 的近黑主笔和一圈马克笔色的站点，在缩小的尺寸下依然是
 * 全页第二黑的东西。压一档透明度，是让"这张图是纸上的底子"这件事在眼睛里成立；
 * 提示那句（.tip）不跟着压 —— 它是地图上唯一要读的文字。
 */
.inklayer :deep(.ink__svg) { opacity: 0.72; }
/*
 * 文字列：左栏里的一列，整体居中，三段之间留大间距。
 * 它不再压在任何墨上 —— 地图退到右栏之后，这一列是全页唯一有字的地方。
 */
.say {
  display: flex; flex-direction: column; justify-content: center;
  height: 100%; gap: var(--s6); min-width: 0;
  max-width: 595px;
}
.pitch { display: flex; flex-direction: column; gap: var(--s4); }

/* 标题那一行：左边一大一小两个字，右边一句"写给谁" */
.head { display: flex; align-items: flex-end; gap: var(--s5); flex-wrap: wrap; }
/*
 * "写给谁"那行。
 *
 * 它原来是 11.5px / 字距 0.03em 的通用小标签 —— 中文在这个尺寸下不是"小"，
 * 是"糊"：笔画密的字（"求职""大学生"）会糊成一片灰，而它偏偏是这一页
 * **唯一一句说清楚"这是写给谁的"**的话。所以它按正文对待：13.5px、600 字重、
 * 字距几乎不拉（中文不吃字距），行高 1.75 让两行之间不挤。
 */
.kicker {
  color: var(--accent);
  max-width: 15ch;
  padding-bottom: 10px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.75;
  font-variant-numeric: tabular-nums;
  opacity: 0; transform: translateY(8px);
  transition: opacity 600ms var(--mo-out) 60ms, transform 600ms var(--mo-out) 60ms;
}
.paper--in .kicker { opacity: 1; transform: none; }

/*
 * 主张：外框是 flex 列，两行各占一行；行内由 BlurText 自己排词。
 * 行距、字距都由这里管，词不再各自带外边距 —— 中文就不会"漂"。
 */
.claim {
  margin: 0;
  display: flex; flex-direction: column;
  /*
   * 字号必须和栏宽一起算：最长的一行（你只要知道 下一步 做什么。）是
   * 13.5 个全角字，左列变窄之后要按 2.75vw 算才放得下，且不折行。
   */
  font-size: clamp(26px, 2.75vw, 44px);
  line-height: 1.16;
  letter-spacing: -0.03em;
  max-width: 100%;
}
/* 被圈的那个词：换颜色；position: relative 给 rough-notation 当坐标系 */
.claim :deep(.bt__seg--mark) { position: relative; color: var(--mk-green); }

.lede {
  display: inline-block; max-width: 26ch;
  /* 说明句是给人读的一句话，不是标签：按正文再上一档（16px），行高放松 */
  font-size: 16px; line-height: 1.85; color: var(--ink-2);
  opacity: 0; transform: translateY(8px);
  transition: opacity 640ms var(--mo-out) 760ms, transform 640ms var(--mo-out) 760ms;
}
.paper--in .lede { opacity: 1; transform: none; }

.cta { display: flex; align-items: center; gap: var(--s5); padding-top: var(--s2); opacity: 0; transform: translateY(10px); transition: opacity 640ms var(--mo-out) 880ms, transform 640ms var(--mo-out) 880ms; }
.paper--in .cta { opacity: 1; transform: none; }
.cta__magnet { display: inline-block; }
/*
 * 按钮旁边那句话（"第一次 5 分钟 · 不用填表 · 随时可以停"）。
 * 同样按正文字号走，颜色从 --ink-3 提到 --ink-2 —— 它是**承诺**，
 * 不是装饰性的脚注，读者真的会拿它决定要不要点下去。
 */
.cta__cost {
  color: var(--ink-2);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
  line-height: 1.7;
  max-width: 16ch;
  font-variant-numeric: tabular-nums;
}

/* ── 窄屏：一屏只剩"话 + 按钮"，地图整块收起来 ─────────────────── */
/*
 * 1100px 以下不再分两栏。
 *
 * 不是"地图藏起来"这么简单：这一档再分两栏，右栏只剩三百多像素，
 * 那条路缩到 0.22～0.28 倍 —— 站点圈小到认不出是圈，主笔细到像纸上的脏印。
 * 与其在右边留一块"看不出是地图的装饰"，不如把整屏让给主张与按钮
 * （这也正是 820 以下原本收掉墨层的那个判断，只是那条线抬到了 1100）。
 * 地图没有从页面上消失：它在这一格能占住四成宽、按自己的比例摊开时才出现。
 */
@media (max-width: 1100px) {
  .paper { grid-template-columns: minmax(0, 1fr); column-gap: 0; }
  .mapcol { display: none; }
  .claim { font-size: clamp(24px, 2.75vw, 36px); }
  .wordmark__row { font-size: clamp(72px, 8.4vw, 120px); }
}
@media (max-width: 820px) {
  .paper { padding: var(--s4) var(--s5); }
  .wordmark__row { font-size: clamp(64px, 20vw, 92px); }
  .head { gap: var(--s4); }
  .claim { font-size: clamp(24px, 7vw, 34px); }
}

/* 降低动效：一切直接给终态（rough-notation 那边也在 drawRing 里读了同一个偏好） */
@media (prefers-reduced-motion: reduce) {
  .wordmark, .kicker, .lede, .cta { opacity: 1; transform: none; filter: none; transition: none; }
}
</style>
