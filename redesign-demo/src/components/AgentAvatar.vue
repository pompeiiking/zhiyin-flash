<script setup lang="ts">
import { computed } from 'vue'
import { AGENT_VAR_NAMES, agentOf, agentVars } from '../lib/agents'

/**
 * AI 主理头像 —— 会动的那一个。
 *
 * 形体来自已选定方向 `c2-hbu`（design-review/v6-redesign/directions/c2-hbu/index.html 的
 * AVATAR_SVG）。移植只换"形体"这一层，机制全部沿用：
 *   1. **材质层砍到 2 层**：一层纯色底 + 一层很淡的"光从上面来"。
 *      上一版是 radialGradient 受光 + 顶部镜面高光 + 第二层小高光 + 边缘受光白描边 ——
 *      四层堆出来的体积正是"读起来像玻璃/像仪表盘"的来源。现在只留一条信息：光在上面。
 *   2. **眼睛是主角**：眼白 + 瞳 + 偏左上的高光点（高光**不在瞳孔正中心** ——
 *      正中读成"珠子"，偏左上才读成"朝一个方向看的眼睛"）。
 *      眼白外径 14u、瞳 9.2u、两眼各留 3.8u 空隙 —— 40px 下才不会被糊成两个灰点。
 *   3. **靠轮廓与比例区分，不靠明暗**：形体是圆角方块（rx/w 最大 0.33，**不是正圆**），
 *      外加一条 1.2u 主色轮廓线。五位主理各是一种"鹅卵石"（方 / 圆 / 竖 / 宽 / 切角），
 *      形状是第一线索，色相是第二线索 —— 色觉障碍下也不会五张一样的脸。
 *      **圆角一律交给 SVG 的 rx**：手算路径弧的第一版把 round 写成了 rx/w=40% 的正圆，
 *      8 倍特写才看出来 —— 几何交给浏览器算，就不给我算错的机会。
 *   4. 不低龄化的线（c2-hbu 自订）：不正圆、无腮红、无星星/心形/音符、无拟物金属玻璃。
 *
 * 动效纪律：
 *   · 循环动效由 key 派生的 --ag-period / --ag-shift 驱动（见 lib/agents.ts），
 *     同屏多个头像各演各的（不同步眨眼、不同步扫视）才像一群人而不是一排灯；
 *   · 幅度全部在 c2-hbu 的上限内：呼吸 1 → 1.055（守卫线 1.12）、眼睛平移 ≤1.4px、
 *     瞳孔抬起 1.4px、嘴 scaleY .78–1.3，位移 ≤2px；
 *   · 每一段动效都对应一个状态事实（"在看 / 在想 / 在说"），没有装饰性持续运动。
 *
 * 只用内联 SVG + CSS：不引第三方动画库，不引任何位图/字体文件 ——
 * 这个组件要出现在聊天流的每一行里，而且"全站零图像"的正确解法是"有形象"，
 * 不是"引入位图资产"。
 */
const props = withDefaults(
  defineProps<{
    /** AgentKey；未知值走 agentOf 兜底 */
    agent?: string
    /** 边长 px（viewBox 是正方的，宽高同值，头像列因此不会多出 7px 的空档） */
    size?: number
    state?: 'idle' | 'thinking' | 'speaking' | 'done'
    /** 头像下方是否带名字 */
    showName?: boolean
  }>(),
  { size: 40, state: 'idle', showName: false },
)

const identity = computed(() => agentOf(props.agent))

/**
 * 内联变量而不是把颜色/时长写进 CSS 常量：
 * 一个组件实例一个主理，颜色与节奏都是这一实例的私有参数。
 * 只在 inline style 里放**静态字符串**，动画名留在 <style> 里 —— vue-tsc 能校验前者。
 *
 * width 与 height **必须同时给**：viewBox 是正方的，只给 width 时 SVG 会按比例把
 * 高度算成 118/100 倍，头像列与消息正文就不再同一条基线
 * （上一版实测：40px 宽 / 47.2px 高，每条消息上方多出 7px 空档）。
 */
const rootStyle = computed(() => {
  const vars = agentVars(props.agent)
  return {
    [AGENT_VAR_NAMES.hue]: vars.hue,
    [AGENT_VAR_NAMES.period]: vars.period,
    [AGENT_VAR_NAMES.shift]: vars.shift,
    width: `${props.size}px`,
    height: `${props.size}px`,
  }
})

/**
 * 渐变 id 必须每个实例唯一。
 * 同一页里 5 个头像共用 id 时，浏览器只认文档里第一个 <linearGradient>：
 * 后 4 个会用第一位主理的颜色 —— 那正好是"五个人长得一样"的 bug。
 */
const uid = `av-${Math.random().toString(36).slice(2, 9)}`

/**
 * 五位主理 + 我 + 系统的形体。
 *
 * 全部是"不正圆"的圆角方块，**圆角一律用 SVG 的 rx 画，不用路径手算弧**：
 * 手算的圆弧写错一个数就是正圆（第一版 round 用了 rx/w = 40% 的路径，8 倍特写下
 * 量出来就是一颗正圆 —— 那正是 c2-hbu 风险评估里的红线）。rx 由浏览器按几何算，
 * 不给我算错的机会。
 *
 * 尺寸表（viewBox 100×100，形体占 8–92 这一格）：
 *   round   84×84 rx 27.5（rx/w = .33）—— 最柔的一位，仍不是正圆
 *   square  84×84 rx 17  （.20）      —— 基准形体
 *   shield  64×84 rx 20  （.31）      —— 窄高
 *   capsule 84×64 rx 22  （.26）      —— 矮宽
 *   flower  78×78 rx 27  （.35）      —— 切角最狠的一位
 *   person  76×76 rx 20  （.26）
 *   panel   72×64 rx 6   （.08）
 * 差异靠**宽高比 + 圆角**两件事叠加，形状是第一线索，色相是第二线索。
 */
interface BodyGeometry {
  x: number
  y: number
  w: number
  h: number
  rx: number
}

const BODIES: Record<string, BodyGeometry> = {
  /** 圆：rx/w = .33 的鹅卵石 —— 不是正圆（守卫线 .34） */
  round: { x: 8, y: 8, w: 84, h: 84, rx: 27.5 },
  /** 方：rx/w = .20 —— 基准形体（职业分析顾问） */
  square: { x: 8, y: 8, w: 84, h: 84, rx: 17 },
  /** 竖：窄高 —— "把路排成一条线"（路径规划师） */
  shield: { x: 18, y: 8, w: 64, h: 84, rx: 20 },
  /** 宽：矮宽 —— "陪着"的那位（陪伴教练） */
  capsule: { x: 8, y: 18, w: 84, h: 64, rx: 22 },
  /** 六边：切角最狠 —— "从外面带情报回来"的那位（就业情报员） */
  flower: { x: 11, y: 11, w: 78, h: 78, rx: 27 },
  /** 我（学生本人）：接近圆但仍然留方底 */
  person: { x: 12, y: 12, w: 76, h: 76, rx: 20 },
  /** 系统提示：一张窄面板（它是"流程说明"，本来就不是一个人） */
  panel: { x: 14, y: 18, w: 72, h: 64, rx: 6 },
}

const body = computed(() => BODIES[identity.value.shape] ?? BODIES.square)

/**
 * 识别件里的"半径刻度"：两段贴着形体右缘的弧（像一对括号，不是一圈光环）。
 *
 * 为什么要写成 path 而不是「整圆 + dash」或"半径 44 的大圆"：
 *   1. dash 的可见段以圆心为中心按比例摊开，"半圈"会摊到左上象限去（实测：弧从脸上穿过）；
 *   2. 半径一超过 46，弧就会跑出 100×100 的 viewBox —— 那个盒子**不裁**
 *      （overflow: visible），于是它会画到相邻的正文上面去（实测：96px 空态里
 *      一圈蓝色的大弧压住了右边的"你更关注…"）。
 * 所以端点写死在这一段里：圆心取 (50, 50)，半径 34/42，角度 −50°…50°，
 * 整段落在 x ≥ 77 的右缘空地上，和最宽（84）的形体边界不打架。
 */
const ARC_RIGHT = 'M71.9 23.9A34 34 0 0 1 71.9 76.1'
const ARC_RIGHT_INNER = 'M77 17.8A42 42 0 0 1 77 82.2'

/**
 * 识别件：这一位"手里拿的那件东西"。
 * 全部是**线**（不填色块），画在头部右下角的外侧 —— 它交代身份，
 * 但不能跟眼睛抢第一眼，所以：细（1.6u）、次要色、位置偏。
 */
</script>

<template>
  <div
    class="ag"
    :class="[`ag--${identity.shape}`, `is-${state}`, showName ? 'ag--named' : '']"
    :data-state="state"
    :data-agent="identity.key"
    :data-shape="identity.shape"
    :style="rootStyle"
    role="img"
    :aria-label="identity.name"
    :title="`${identity.name} · ${identity.role}`"
  >
    <svg class="ag-svg" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <defs>
        <!-- 材质层第 2 层：光从上面来。这是形体上唯一的"体积"信息，不再有镜面高光。
             两端都取自 --ag-hue：上端全透明、下端压到 .3 —— 同色相内的明暗，不引入第二支色 -->
        <linearGradient :id="uid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--ag-hue, var(--c-text-3))" stop-opacity="0" />
          <stop offset="1" stop-color="var(--ag-hue, var(--c-text-3))" stop-opacity=".3" />
        </linearGradient>
      </defs>

      <!-- 呼吸：极轻微的缩放（1 → 1.055，**不超过 1.12 倍**）。所有状态都保留：
           "活着"的底噪就是它，而且它在 reduced-motion 下会停成一个静态圆 -->
      <g class="ag-breath">
        <!-- 点头：只在 done 的 620ms 里跑一次，跑完回到 0 度 -->
        <g class="ag-nod">
          <!-- ===== 说话时的涟漪：只画一圈线，不发光 ===== -->
          <circle class="ag-ring" cx="50" cy="50" r="38" />

          <!-- ===== 思考时的轨道 + 六点：把"念头"挂在一个明确的位置上 =====
               轨道 r=44、点在 r=42 环上：整组都在 viewBox 内，所以 40px 那一档
               不会被裁掉（c2-hbu 的原稿把点放在 r≈46，靠 overflow:visible 兜底） -->
          <g class="ag-whoosh">
            <circle class="ag-whoosh__track" cx="50" cy="50" r="44" />
            <g class="ag-dots">
              <circle cx="50" cy="6" r="2.4" />
              <circle cx="80.4" cy="16.8" r="2.7" />
              <circle cx="94" cy="38" r="3" />
              <circle cx="94" cy="62" r="2.7" />
              <circle cx="80.4" cy="83.2" r="3" />
              <circle cx="50" cy="94" r="2.4" />
            </g>
            <g class="ag-dots">
              <circle cx="19.6" cy="83.2" r="2.7" />
              <circle cx="6" cy="62" r="2.4" />
              <circle cx="6" cy="38" r="2.7" />
              <circle cx="19.6" cy="16.8" r="3" />
              <circle cx="33" cy="9.6" r="2.4" />
              <circle cx="67" cy="9.6" r="2.7" />
            </g>
          </g>

          <!-- ===== 形体 =====
               材质 2 层：① 纯色底 ② 上亮下暗。没有受光渐变、没有镜面高光、没有腮红。
               轮廓是 1.2u 的线 —— 那是"形"，不是"玻璃的厚度/边缘受光"。
               三个 rect 共用同一份几何：轮廓那一层是 1.2u 的**内缩**版本，
               所以描边压在形体内侧，形体总宽仍然是 84（不会因为描边溢出格子）。 -->
          <g class="ag-hull">
            <rect class="ag-hull__fill" :x="body.x" :y="body.y" :width="body.w" :height="body.h" :rx="body.rx" />
            <rect class="ag-hull__light" :x="body.x" :y="body.y" :width="body.w" :height="body.h" :rx="body.rx" :fill="`url(#${uid})`" />
            <rect
              class="ag-hull__edge"
              :x="body.x + 1.2"
              :y="body.y + 1.2"
              :width="body.w - 2.4"
              :height="body.h - 2.4"
              :rx="Math.max(0, body.rx - 1.2)"
            />
          </g>

          <!-- 眉：只在"思考"时出现，待命不堆表情。
               斜率是"内端抬高、外端压低"（读成在琢磨），不是内低外高（那读成生气）。 -->
          <g class="ag-brow">
            <path d="M32.4 32.6 41 29.6" />
            <path d="M59 29.6 67.6 32.6" />
          </g>

          <!-- ===== 脸：眼白 + 瞳 + 高光 =====
               gaze 负责左右扫视（±1.4px）、lift 负责思考时上移（1.4px），两个位移分两层挂 -->
          <g class="ag-face">
            <g class="ag-eye ag-eye--l">
              <ellipse class="ag-eye-white" cx="37.5" cy="47" rx="7" ry="7.6" />
              <ellipse class="ag-eye-rim" cx="37.5" cy="47" rx="7" ry="7.6" />
              <g class="ag-pupil">
                <g class="ag-gaze">
                  <g class="ag-lift">
                    <circle class="ag-pupil__ink" cx="38.4" cy="48.2" r="4.6" />
                    <circle class="ag-glint" cx="36.5" cy="45.9" r="1.7" />
                  </g>
                </g>
              </g>
            </g>
            <g class="ag-eye ag-eye--r">
              <ellipse class="ag-eye-white" cx="62.5" cy="47" rx="7" ry="7.6" />
              <ellipse class="ag-eye-rim" cx="62.5" cy="47" rx="7" ry="7.6" />
              <g class="ag-pupil">
                <g class="ag-gaze">
                  <g class="ag-lift">
                    <circle class="ag-pupil__ink" cx="63.4" cy="48.2" r="4.6" />
                    <circle class="ag-glint" cx="61.5" cy="45.9" r="1.7" />
                  </g>
                </g>
              </g>
            </g>

            <!-- 嘴：一条自信的弧线。说话时 scaleY 开合（.34s），思考时压扁，其他时候静息 -->
            <path class="ag-mouth" d="M43.5 65.5q6.5 6.2 13 0" />
          </g>

          <!-- ===== 识别件：主理"手里拿的那件东西"，思考时它是动态元素 =====
               全部画在**形体之外的右侧**（x ≥ 76）：它们是身份记号，
               不能压到眼白上（眼睛是主角），也不能读成一个把脸框起来的"外圈"。
               弧线用「整圆 + 只留一段可见的 dash」画 —— 不用手算弧的端点坐标。 -->
          <g class="ag-mark">
            <template v-if="identity.mark === 'ring'">
              <!-- 半径刻度：两段贴着形体右缘的弧（一对括号），交代"把情况量清楚"。
                   全部落在形体外的右侧空地，见上面 ARC_RIGHT 的说明 -->
              <path class="ag-mark__arc" :d="ARC_RIGHT" />
              <path class="ag-mark__arc ag-mark__arc--inner" :d="ARC_RIGHT_INNER" />
            </template>
            <template v-else-if="identity.mark === 'layers'">
              <path class="ag-mark__line" d="M79 62h13M79 69h13M79 76h8" />
            </template>
            <template v-else-if="identity.mark === 'steps'">
              <path class="ag-mark__line" d="M78 79h4v-5h5v-5h4" />
              <circle class="ag-mark__dot" cx="79.5" cy="79" r="1.8" />
              <circle class="ag-mark__dot" cx="90.5" cy="69.5" r="1.8" />
            </template>
            <template v-else-if="identity.mark === 'leaf'">
              <path class="ag-mark__line" d="M81 64q9 4 9 14" />
              <circle class="ag-mark__dot" cx="81" cy="64" r="2.4" />
              <circle class="ag-mark__dot" cx="90" cy="78" r="2.4" />
            </template>
            <template v-else-if="identity.mark === 'lens'">
              <circle class="ag-mark__line" cx="82" cy="68" r="7" />
              <path class="ag-mark__line" d="M87 73.5 93 80" />
            </template>
            <template v-else-if="identity.mark === 'bars'">
              <path class="ag-mark__line" d="M38 84h7M50 84h7M62 84h7" />
            </template>
          </g>
        </g>
      </g>
    </svg>

    <!-- 说话时的声波：三条错峰竖条。
         它**不使用 foreignObject**（c2-hbu 原稿用了）：foreignObject 里的 HTML 在
         Chromium 缩到 40px 时会因亚像素被丢掉，而且它在 SVG 里不可被 ::before 之类补样式。
         改成同级绝对定位的元素，靠 overflow 溢到形体右侧 —— 不占 40px 格子里的地面。 -->
    <span class="ag-wave" aria-hidden="true"><i /><i /><i /></span>

    <span v-if="showName" class="ag-name">{{ identity.name }}</span>
  </div>
</template>

<style scoped>
/* =============================================================================
 * 主理头像 · 卡通形体
 * -----------------------------------------------------------------------------
 * 颜色走两层钩子，组件里**不写死任何色值**，也**不在 .ag 上声明变量**：
 *   --ag-hue                        ← 身份色，由 lib/agents.ts 内联进来
 *                                     （同亮度窄带，只换色相；填色是这一位"是谁"）
 *   --ag-ink / --ag-eye / --ag-line ← 结构色，由 styles/dialogue.css 的页面局部变量给
 *                                     （接 --c-text / --c-surface / --c-primary，
 *                                       所以深浅主题、蓝红主色都不必改这里一行）
 *
 * 为什么不在 .ag 上写兜底声明：Vue 的 scoped 样式会给选择器加一个属性选择器，
 * 于是 `.ag { --ag-line: ... }` 的优先级高于页面上的 `.dialogue-page { --ag-line: ... }` ——
 * 组件会把自己的兜底值"锁"在元素上，页面再也覆盖不进来（实测：切河大红后
 * 说话的涟漪仍是灰的）。兜底值改为写在每个 var() 的第二个参数里，
 * 只有变量真的没被定义时才生效。
 * ========================================================================== */

.ag {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-1);
  /* 尺寸只由内联的 width/height 决定：viewBox 是正方的，两者必须同值 */
  line-height: 1;
}

.ag-svg {
  display: block;
  width: 100%;
  height: 100%;
  /* 识别件与涟漪画在形体之外，不能裁 */
  overflow: visible;
}

.ag-name {
  font-size: var(--fs-12);
  color: var(--c-text-2);
  white-space: nowrap;
}

/* ---- 形体：材质 2 层 ---- */

/* 第 1 层：纯色底。它同时是"这个主理是谁"的第一记号。
   兜底 --c-text-3 只给"这个组件被单独拿去渲染"的情况 —— 正常链路一定内联了 --ag-hue */
.ag-hull__fill {
  fill: var(--ag-hue, var(--c-text-3));
}

/* 第 2 层：光从上面来（0 → .3 的同色相压深）。没有镜像高光、没有第二层小高光 */
.ag-hull__light {
  /* fill 由模板里的 url(#uid) 给 */
}

/* 轮廓：形体的边。用标识色本身压到 .34 —— 它是"形"，不是"边缘受光" */
.ag-hull__edge {
  fill: none;
  stroke: var(--ag-hue, var(--c-text-3));
  stroke-opacity: 0.34;
  stroke-width: 1.2;
}

/* ---- 脸 ---- */

.ag-eye-white {
  fill: var(--ag-eye, var(--c-surface));
}

.ag-eye-rim {
  fill: none;
  stroke: var(--ag-ink, var(--c-text));
  /* .3 → .38：40px 下眼白只有 5.6px 宽，原稿的 .3（合成后对纸面约 1.39:1）
     正好落在"屏幕上看不见"的那一档（评审 P0-1 的口径）。提到 .38 后约 1.6:1，
     仍是一条极轻的边，但它开始真的存在 */
  stroke-opacity: 0.38;
  stroke-width: 1.3;
}

.ag-pupil__ink {
  fill: var(--ag-ink, var(--c-text));
}

/* 高光用近白而不是纯白：浅色主题下瞳孔是近黑，近白足够亮；
   深色主题下瞳孔会变浅，所以那里再换回纯白（见文件末的主题覆盖） */
.ag-glint {
  fill: #f7f9fc;
  opacity: 0.96;
}

.ag-brow {
  opacity: 0;
  stroke: var(--ag-ink, var(--c-text));
  stroke-opacity: 0.48;
  stroke-width: 2.4;
  stroke-linecap: round;
  fill: none;
  transition: opacity var(--dur-3) var(--ease-out);
}

.ag-mouth {
  fill: none;
  stroke: var(--ag-ink, var(--c-text));
  stroke-opacity: 0.68;
  stroke-width: 3.2;
  stroke-linecap: round;
  transform-box: fill-box;
  transform-origin: 50% 30%;
}

/* ---- 识别件：线，不是色块 ---- */

.ag-mark__line {
  fill: none;
  stroke: var(--ag-line, var(--c-border-strong));
  stroke-width: 1.6;
  stroke-linecap: round;
}

.ag-mark__dot {
  fill: var(--ag-line, var(--c-border-strong));
}

/* 半径刻度：两段弧（一对括号），比其余识别件细一档（1.4）—— 它是"刻度"不是"记号" */
.ag-mark__arc {
  fill: none;
  stroke: var(--ag-line, var(--c-border-strong));
  stroke-opacity: 0.6;
  stroke-width: 1.4;
  stroke-linecap: round;
  transform-box: fill-box;
  transform-origin: center;
}
.ag-mark__arc--inner {
  stroke-opacity: 0.34;
}

/* ---- 思考轨道 ---- */

.ag-whoosh {
  opacity: 0;
  transition: opacity var(--dur-3) var(--ease-out);
}

.ag-whoosh__track {
  fill: none;
  stroke: var(--ag-hue, var(--c-text-3));
  stroke-opacity: 0.2;
  stroke-width: 1.2;
  stroke-dasharray: 2.5 6;
}

/* 六点用标识色本身并压到 .5：默认 SVG 填充是纯黑，会读成"环绕的黑点"，
   压到 .5 才是"同色相上的念头" */
.ag-dots circle {
  fill: var(--ag-hue, var(--c-text-3));
  opacity: 0.5;
  transform-box: fill-box;
  transform-origin: center;
}

/* ---- 说话：涟漪 + 声波 ---- */

.ag-ring {
  fill: none;
  stroke: var(--ag-line, var(--c-border-strong));
  stroke-width: 1.6;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}

.ag-wave {
  position: absolute;
  top: 34%;
  left: 100%;
  display: flex;
  align-items: center;
  gap: 1.2px;
  height: 30%;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-3) var(--ease-out);
}

.ag-wave i {
  display: block;
  width: 1.6px;
  border-radius: 2px;
  background: var(--ag-line, var(--c-border-strong));
  transform-box: fill-box;
  transform-origin: center;
}
.ag-wave i:nth-child(1) { height: 42%; }
.ag-wave i:nth-child(2) { height: 68%; }
.ag-wave i:nth-child(3) { height: 34%; }

/* =============================================================================
 * 三态
 * -----------------------------------------------------------------------------
 * **只有四个类名参与状态**（is-idle / is-thinking / is-speaking / is-done）。
 * 元素上另外挂了 `data-state` —— 它是给测试与外部选择器读的（量的是"这一条现在
 * 是什么状态"），组件内部不再用它做选择器：`.ag.is-thinking .ag-pupil`（0,2,0）
 * 与 `.ag[data-state='thinking'] .ag-pupil`（0,2,0）同优先级、同属一张表，
 * 同时写两份只会把"降级规则该覆盖谁"这件事变成猜谜（实测 reduced-motion 就因此漏掉）。
 * ========================================================================== */

/* 待命：眼睛慢慢扫视（"在看"） */
.ag.is-idle .ag-gaze {
  animation: ag-look calc(7.4s + var(--ag-period)) var(--ease-out) infinite;
  animation-delay: var(--ag-shift);
}

/* 呼吸：全状态常驻，1 → 1.055（守卫线 1.12） */
.ag-breath {
  transform-box: view-box;
  transform-origin: 50px 50px;
  animation: ag-breathe calc(4.2s + var(--ag-period)) var(--ease-in-out) infinite;
  animation-delay: var(--ag-shift);
}

/* 眨眼：整只眼 scaleY。origin 取自身包围盒中心，任何眼型都成立。
   steps(1) 的"啪"是必需的：补间会变成慢慢眯眼，那是困了不是眨眼 */
.ag-eye {
  transform-box: fill-box;
  transform-origin: center;
  animation: ag-blink calc(6.4s + var(--ag-period)) steps(1, end) infinite;
  animation-delay: var(--ag-shift);
}
.ag-eye--r {
  /* 两只眼差 90ms：同步眨眼会读成"仪表"，错开才是活物。
     90ms 是绝对量，不加 --ag-shift 的秒级相位 —— 那会把两眼拉开好几秒，
     变成"两只眼睛各眨各的"，比同步更糟 */
  animation-delay: 90ms;
}

/* 思考：瞳孔上抬 1.4px + 眉抬起 + 脸整体收 .96（约 2px，不外扩）+ 六点依次亮起 */
.ag.is-thinking .ag-pupil {
  transform: translateY(-1.4px);
}
.ag.is-thinking .ag-brow {
  opacity: 1;
}
.ag.is-thinking .ag-face {
  transform: translateY(-1px) scale(0.96);
}
.ag.is-thinking .ag-whoosh {
  opacity: 1;
}
.ag.is-thinking .ag-dots circle {
  animation: ag-orbit calc(1.7s + var(--ag-period)) var(--ease-in-out) infinite;
}
/* 错峰：一处一处亮起来（同时亮会读成"六个指示灯"，不是"念头一件件成形"） */
.ag.is-thinking .ag-dots circle:nth-of-type(2) { animation-delay: 0.12s; }
.ag.is-thinking .ag-dots circle:nth-of-type(3) { animation-delay: 0.24s; }
.ag.is-thinking .ag-dots:nth-of-type(2) circle { animation-delay: 0.36s; }
.ag.is-thinking .ag-dots:nth-of-type(2) circle:nth-of-type(2) { animation-delay: 0.48s; }
.ag.is-thinking .ag-dots:nth-of-type(2) circle:nth-of-type(3) { animation-delay: 0.6s; }
.ag.is-thinking .ag-mouth {
  transform: scaleY(0.78);
}
/* 思考时六点轨道（r44 虚线圆）也扫过这一带：外弧让位给它，内弧留着 ——
   两段弧和轨道挤在同一个半径上会读成脏。"正在想"已经由六点的依次亮起承担，
   同一个状态不必由两处动效同时表达，第二处只会稀释第一处 */
.ag.is-thinking .ag-mark__arc:not(.ag-mark__arc--inner) {
  opacity: 0;
}

/* 说话：嘴开合 + 声波 + 涟漪 = "热"。
   声波与涟漪走 --ag-line（页面把它接到 --c-primary），所以换主色时它们是唯一
   跟着变色的一层 —— 这正好：说话是"此刻"，此刻属于主题，不属于某个人的身份 */
.ag.is-speaking .ag-mouth {
  animation: ag-talk 0.34s var(--ease-in-out) infinite;
}
.ag.is-speaking .ag-wave {
  opacity: 1;
}
.ag.is-speaking .ag-wave i {
  animation: ag-sound calc(0.74s + var(--ag-period)) var(--ease-in-out) infinite;
}
.ag.is-speaking .ag-wave i:nth-child(2) { animation-delay: 0.11s; }
.ag.is-speaking .ag-wave i:nth-child(3) { animation-delay: 0.22s; }
.ag.is-speaking .ag-ring {
  opacity: 1;
  animation: ag-ripple 2.2s var(--ease-out) infinite;
}

/* ---- done：点头一次（跑完即回 idle，不用 JS 改回来） ---- */
.ag.is-done .ag-nod {
  transform-box: view-box;
  transform-origin: 50px 50px;
  animation: ag-nod 0.62s var(--ease-out) 1 both;
}

@keyframes ag-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.055); }
}

@keyframes ag-blink {
  0%, 92%, 100% { transform: scaleY(1); }
  95.5% { transform: scaleY(0.1); }
}

/* 扫视：左右各一次短移 + 长停顿（0–20% 就在原位）。
   位移量是 c2-hbu 定死的 ±1.4 / 1.1，不随尺寸放大 */
@keyframes ag-look {
  0%, 20%, 100% { transform: translateX(0); }
  34% { transform: translateX(-1.4px); }
  56% { transform: translateX(1.1px); }
  76% { transform: translateX(0); }
}

@keyframes ag-talk {
  0%, 100% { transform: scaleY(0.55); }
  45% { transform: scaleY(1.3); }
}

/* 声波：抬 1.18 / 落 0.40 */
@keyframes ag-sound {
  0%, 100% { transform: scaleY(0.4); }
  50% { transform: scaleY(1.18); }
}

/* 念头：一点一点成形（不是同时亮） */
@keyframes ag-orbit {
  0%, 100% { opacity: 0.28; transform: translateY(0) scale(0.82); }
  50% { opacity: 1; transform: translateY(-1.6px) scale(1.08); }
}

@keyframes ag-ripple {
  0% { transform: scale(0.9); opacity: 0.5; }
  70%, 100% { transform: scale(1.18); opacity: 0; }
}

@keyframes ag-nod {
  0%, 100% { transform: rotate(0deg); }
  35% { transform: rotate(2.4deg); }
  70% { transform: rotate(-0.8deg); }
}

/* 深色主题：瞳色变浅，眼白上那颗近白高光就不再是"最亮的一点"。
   这是唯一一处按主题改的**字面色** —— 因为高光只有"比瞳孔亮"这一个要求，
   它不属于任何一支色相，也就无法走语义令牌。 */
html[data-theme='dark'] .ag-glint {
  fill: #ffffff;
}

/* =============================================================================
 * 减少动效降级 —— 保留静态表情与状态色，**不隐藏任何一层**
 * -----------------------------------------------------------------------------
 * 逐条 animation: none，不能只靠全局那条"时长压到 0.01ms"的兜底：
 * 无限循环的动画会停在最后一个关键帧上 —— 扫视停在偏视、六点停在半透明、
 * 嘴停在一个固定的开合姿态，全是"卡住的半动作"，比不动更糟。
 * 关掉之后各状态仍有**静态且互不相同**的形态：
 *   idle     睁眼（瞳孔居中）+ 静息嘴弧
 *   thinking 瞳孔上抬 1.4px + 眉出现 + 六点轨道静止可见 + 嘴压扁
 *   speaking 涟漪环 + 三条声波静止在 .75 + 嘴开 1.1
 * 这正是"状态变化必须仍被看得见"的落点：状态不靠动效承载，动效只是加强。
 * ========================================================================== */
@media (prefers-reduced-motion: reduce) {
  .ag-breath,
  .ag-eye,
  .ag-gaze,
  .ag-face,
  .ag-mouth,
  .ag-whoosh,
  .ag-dots circle,
  .ag-wave i,
  .ag-ring,
  .ag-nod {
    animation: none;
  }
  .ag.is-idle .ag-gaze { transform: none; }
  .ag.is-thinking .ag-dots circle { opacity: 0.75; }
  .ag.is-thinking .ag-whoosh { opacity: 0.75; }
  .ag.is-speaking .ag-wave { opacity: 0.75; }
  .ag.is-speaking .ag-mouth { transform: scaleY(1.1); }
}
</style>
