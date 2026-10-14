<script setup lang="ts">
import { computed } from 'vue'
import { AGENT_VAR_NAMES, agentOf, agentVars } from '../lib/agents'

/**
 * AI 主理头像 —— 会动的那一个。
 *
 * 三件事决定它长什么样：
 *   1. 造型靠**轮廓 + 眼睛 + 识别件**三层区分。只换颜色的话，一屏 5 个头像
 *      在色觉障碍下、或在缩到 24px 时，会退化成同一张脸。
 *   2. 所有循环动效都由 key 派生的 --ag-period / --ag-shift 驱动（见 lib/agents.ts）。
 *      目的是让同一屏里的头像各演各的：不同步眨眼、不同步扫视，才像一群人而不是一排灯。
 *   3. 动效全部是"微动"：位移不超过 3 个 viewBox 单位、旋转不超过 4.5°。
 *      这是角色感，不是强调动效 —— 把它做成持续摇头/发光，几十秒后就会变成干扰。
 *
 * 只用 SVG + CSS：不引第三方动画库，这个组件要能出现在聊天流的每一行里。
 */
const props = withDefaults(
  defineProps<{
    /** AgentKey；未知值走 agentOf 兜底 */
    agent?: string
    /** 直径 px */
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
 */
const rootStyle = computed(() => {
  const vars = agentVars(props.agent)
  return {
    [AGENT_VAR_NAMES.hue]: vars.hue,
    [AGENT_VAR_NAMES.period]: vars.period,
    [AGENT_VAR_NAMES.shift]: vars.shift,
    width: `${props.size}px`,
  }
})
</script>

<template>
  <div
    class="ag"
    :class="[`ag--${identity.shape}`, `is-${state}`, showName ? 'ag--named' : '']"
    :style="rootStyle"
    role="img"
    :aria-label="identity.name"
    :title="`${identity.name} · ${identity.role}`"
  >
    <svg class="ag-svg" viewBox="0 0 100 118" aria-hidden="true" focusable="false">
      <!-- 呼吸：极轻微的上下浮动。所有状态都保留，因为"活着"的底噪就是它 -->
      <g class="ag-breath">
        <!-- 点头：只在 done 的 620ms 里跑一次，跑完回到 0 度 -->
        <g class="ag-nod">
          <g class="ag-head">
            <!-- ===== 头部轮廓：5 主理 + 我 + 系统，形状各不相同 ===== -->
            <path
              v-if="identity.shape === 'round'"
              class="ag-shape"
              d="M28 50a22 22 0 0 1 44 0v12a24 24 0 0 1-44 0Z"
            />
            <path
              v-else-if="identity.shape === 'square'"
              class="ag-shape"
              d="M24 28h52v32a26 26 0 0 1-52 0Z"
            />
            <path
              v-else-if="identity.shape === 'shield'"
              class="ag-shape"
              d="M50 14 78 26v30a32 32 0 0 1-28 30 32 32 0 0 1-28-30V26Z"
            />
            <path
              v-else-if="identity.shape === 'capsule'"
              class="ag-shape"
              d="M50 16a26 26 0 0 0-26 26v8a26 26 0 0 0 52 0v-8a26 26 0 0 0-26-26Z"
            />
            <path
              v-else-if="identity.shape === 'flower'"
              class="ag-shape"
              d="M26 22h48a10 10 0 0 1 10 10v14a34 34 0 0 1-68 0V32a10 10 0 0 1 10-10Z"
            />
            <path
              v-else-if="identity.shape === 'person'"
              class="ag-shape"
              d="M50 18a19 19 0 0 0-19 19v9a19 19 0 0 0 38 0v-9a19 19 0 0 0-19-19Z"
            />
            <path v-else class="ag-shape" d="M22 30a8 8 0 0 1 8-8h40a8 8 0 0 1 8 8v26a8 8 0 0 1-8 8H30a8 8 0 0 1-8-8Z" />

            <!-- ===== 天线：顶部特征，也是"机器人"的第一眼线索 ===== -->
            <g class="ag-antenna">
              <template v-if="identity.shape === 'round'">
                <path class="ag-line" d="M50 28V14" />
                <circle class="ag-dot" cx="50" cy="11" r="3.4" />
              </template>
              <template v-else-if="identity.shape === 'square'">
                <path class="ag-line" d="M36 28V14M64 28V14" />
                <circle class="ag-dot" cx="36" cy="11" r="3" />
                <circle class="ag-dot" cx="64" cy="11" r="3" />
              </template>
              <template v-else-if="identity.shape === 'shield'">
                <path class="ag-line" d="M50 14V9" />
                <path class="ag-line" d="M43.5 8h13" />
              </template>
              <template v-else-if="identity.shape === 'capsule'">
                <path class="ag-line" d="M50 16V9" />
                <path class="ag-line ag-line--curve" d="M50 9c6 0 8-4 8-4" />
              </template>
              <template v-else-if="identity.shape === 'flower'">
                <path class="ag-line" d="M42 22V13M58 22V13" />
                <circle class="ag-dot" cx="42" cy="10.5" r="2.6" />
                <circle class="ag-dot" cx="58" cy="10.5" r="2.6" />
              </template>
              <template v-else-if="identity.shape === 'person'">
                <path class="ag-line" d="M50 18V11" />
                <circle class="ag-dot ag-dot--soft" cx="50" cy="8.6" r="2.6" />
              </template>
              <template v-else>
                <path class="ag-line" d="M36 24V17M50 24V15M64 24V17" />
                <circle class="ag-dot" cx="50" cy="12.6" r="2.4" />
              </template>
            </g>

            <!-- ===== 眼睛 =====
                 眨眼用的是整组 scaleY（object bounding box 的顶边作原点）而不是"眼皮"，
                 因为眼皮要按每种眼睛单独画，而 scaleY 对 7 种眼睛写法都成立。
                 gaze 负责左右扫视、lift 负责思考时上移，两个位移都挂在这一层。 -->
            <g class="ag-eyes">
              <g class="ag-gaze">
                <g class="ag-lift">
                  <template v-if="identity.eyes === 'round'">
                    <rect class="ag-socket" x="33.5" y="45" width="12.5" height="12.5" rx="4" />
                    <rect class="ag-socket" x="54" y="45" width="12.5" height="12.5" rx="4" />
                    <circle class="ag-pupil" cx="39.75" cy="51.5" r="3.1" />
                    <circle class="ag-pupil" cx="60.25" cy="51.5" r="3.1" />
                  </template>
                  <template v-else-if="identity.eyes === 'tall'">
                    <rect class="ag-socket" x="35" y="43" width="10" height="18" rx="3.4" />
                    <rect class="ag-socket" x="55" y="43" width="10" height="18" rx="3.4" />
                    <rect class="ag-pupil" x="38.1" y="48.6" width="3.8" height="6.8" rx="1.9" />
                    <rect class="ag-pupil" x="58.1" y="48.6" width="3.8" height="6.8" rx="1.9" />
                  </template>
                  <template v-else-if="identity.eyes === 'line'">
                    <rect class="ag-socket" x="34" y="49" width="12" height="6.6" rx="3.3" />
                    <rect class="ag-socket" x="54" y="49" width="12" height="6.6" rx="3.3" />
                    <circle class="ag-pupil" cx="44.4" cy="52.3" r="2.1" />
                    <circle class="ag-pupil" cx="55.6" cy="52.3" r="2.1" />
                  </template>
                  <template v-else-if="identity.eyes === 'single'">
                    <path class="ag-socket" d="M36 48a14 14 0 0 1 28 0" />
                    <circle class="ag-pupil" cx="50" cy="52.2" r="3.4" />
                    <circle class="ag-pupil" cx="43.6" cy="53.4" r="1.7" />
                    <circle class="ag-pupil" cx="56.4" cy="53.4" r="1.7" />
                  </template>
                  <template v-else-if="identity.eyes === 'scan'">
                    <rect class="ag-socket" x="34" y="47" width="10" height="9" rx="3" />
                    <rect class="ag-socket" x="56" y="47" width="10" height="9" rx="3" />
                    <rect class="ag-pupil" x="37.6" y="49.2" width="2.8" height="4.6" rx="1.4" />
                    <rect class="ag-pupil" x="59.6" y="49.2" width="2.8" height="4.6" rx="1.4" />
                  </template>
                  <template v-else-if="identity.eyes === 'dot'">
                    <!-- 学生本人：眼白比主理更大一圈、瞳孔更小，读起来是"人在听"而不是仪表 -->
                    <rect class="ag-socket" x="36.5" y="45.5" width="10" height="10.5" rx="4" />
                    <rect class="ag-socket" x="53.5" y="45.5" width="10" height="10.5" rx="4" />
                    <circle class="ag-pupil" cx="41.5" cy="51" r="2.4" />
                    <circle class="ag-pupil" cx="58.5" cy="51" r="2.4" />
                  </template>
                  <template v-else>
                    <path class="ag-line ag-line--light" d="M35 52h9M56 52h9" />
                  </template>
                </g>
              </g>
            </g>

            <!-- ===== 嘴 / 口型 =====
                 说话时才出现，随节拍开合；思考时只留一个很小的"嗯"，不抢戏 -->
            <template v-if="state === 'speaking'">
              <rect class="ag-mouth ag-talk" x="42" y="59" width="16" height="5" rx="2.5" />
            </template>
            <template v-else-if="state === 'thinking'">
              <circle class="ag-mouth" cx="50" cy="61" r="1.7" />
            </template>
            <!-- 学生本人没有嘴会显得"空"：给一条极浅的笑弧，保持"是我"的辨识度 -->
            <path v-else-if="identity.shape === 'person'" class="ag-line ag-line--soft" d="M45 61q5 3.5 10 0" />
            <path v-else-if="identity.eyes === 'single'" class="ag-line ag-line--soft" d="M44 61.4q6 4 12 0" />
            <!-- idle 也留一条极浅的嘴线：完全没有嘴会让"静止"和"动画停了"分不出来 -->
            <path v-else class="ag-line ag-line--faint" d="M45 61h10" />

            <!-- ===== 识别件：这个主理"手里拿的那件东西"，也是思考时的动态元素 ===== -->
            <g class="ag-mark">
              <template v-if="identity.mark === 'ring'">
                <!-- 半径贴着头部轮廓（头部横向 28–72、纵向约 27–86）：这是"光环"，
                     不是外框。圈太大头像会显小，看着像徽章而不是角色 -->
                <circle class="ag-mark-line ag-orbit" cx="50" cy="58" r="32" />
              </template>
              <template v-else-if="identity.mark === 'layers'">
                <path class="ag-mark-line" d="M66 62h14M66 69h14M66 76h9" />
              </template>
              <template v-else-if="identity.mark === 'steps'">
                <path class="ag-mark-line" d="M68 76h4v-5h5v-5h5" />
                <circle class="ag-mark-dot" cx="69.5" cy="76" r="1.8" />
                <circle class="ag-mark-dot" cx="81.5" cy="66.5" r="1.8" />
              </template>
              <template v-else-if="identity.mark === 'leaf'">
                <path class="ag-mark-line" d="M70.5 62q9 4 9 14" />
                <circle class="ag-mark-dot" cx="70.5" cy="62" r="2.4" />
                <circle class="ag-mark-dot" cx="79.5" cy="76" r="2.4" />
              </template>
              <template v-else-if="identity.mark === 'lens'">
                <circle class="ag-mark-line" cx="72" cy="65" r="7.5" />
                <path class="ag-mark-line" d="M77.5 70.5 84 78" />
              </template>
              <template v-else-if="identity.mark === 'bars'">
                <path class="ag-mark-line" d="M38 74h6M48 74h6M58 74h6" />
              </template>
            </g>

            <!-- ===== 思考指示：三个流动的小点（静态造型在 reduced-motion 下保留） ===== -->
            <g v-if="state === 'thinking'" class="ag-think">
              <circle class="ag-liquid" cx="42" cy="80" r="2.6" style="--ag-i: 0" />
              <circle class="ag-liquid" cx="50" cy="80" r="2.6" style="--ag-i: 1" />
              <circle class="ag-liquid" cx="58" cy="80" r="2.6" style="--ag-i: 2" />
            </g>

            <!-- 完成确认：点头结束后留下的一枚静态对勾 -->
            <g v-if="state === 'done'" class="ag-check">
              <circle class="ag-check-ring" cx="76" cy="34" r="9" />
              <path class="ag-check-line" d="M71.5 34.2 75 37.6 81 30.8" />
            </g>
          </g>
        </g>
      </g>
    </svg>

    <span v-if="showName" class="ag-name">{{ identity.name }}</span>
  </div>
</template>

<style scoped>
/* =============================================================================
 * 主理头像
 * -----------------------------------------------------------------------------
 * 颜色全部来自令牌 + 实例标识色：--ag-hue 只用来画"这个主理是谁"，
 * 结构面（底、描边）走 --c-surface / --c-border，所以深浅主题都不用改这里一行。
 * ========================================================================== */

.ag {
  /* 兜底：万一 --ag-hue 没被内联进来（例如有人在裸 HTML 里用），也要能画 */
  --ag-hue: var(--c-text-3);
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-1);
  vertical-align: middle;
  /* 尺寸只由内联 width 决定，高度交给 viewBox 的宽高比 */
  line-height: 1;
}

.ag-svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}

.ag-name {
  font-size: var(--fs-12);
  color: var(--c-text-2);
  white-space: nowrap;
}

/* ---- 造型层 ---- */

/* 头部：浅底 + 3 单位描边（viewBox 是 100 宽，缩到 24px 时约 0.7px，刚好还看得见）。
   填充比标识色淡得多，保证眼白和瞳孔永远读得出来 */
.ag-shape {
  fill: var(--c-surface-2);
  stroke: var(--ag-hue);
  stroke-width: 3;
  stroke-linejoin: round;
}

/* 眼睛、天线、识别件里的"实心件"用标识色本身，形成第二层轮廓 */
.ag-dot,
.ag-pupil,
.ag-mark-dot,
.ag-liquid {
  fill: var(--ag-hue);
}

.ag-line,
.ag-mark-line {
  fill: none;
  stroke: var(--ag-hue);
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ag-line--light {
  stroke-width: 2.8;
  opacity: 0.75;
}

/* 笑弧：比结构线轻一档，不然会像个"嘴框"而不是表情 */
.ag-line--soft {
  stroke-width: 2.2;
  opacity: 0.8;
}

/* 静息嘴线：只用来交代"有嘴"，不能抢过眼睛 */
.ag-line--faint {
  stroke-width: 1.8;
  opacity: 0.45;
}

.ag-dot--soft {
  opacity: 0.7;
}

.ag-socket {
  fill: var(--c-surface);
  stroke: var(--ag-hue);
  stroke-width: 2;
}

.ag-mouth,
.ag-talk {
  fill: var(--ag-hue);
}

/* 完成确认角标：必须先铺 surface 作底再描边。
   漏掉 fill 时 SVG 默认填充是黑色 —— 浅色主题下会出现一个纯黑圆点，深色下更是糊成一团 */
.ag-check-ring {
  fill: var(--c-surface);
  stroke: var(--ag-hue);
  stroke-width: 2;
}

/* 对勾是描边而不是填充：它是一条折线，填充会把它变成一个实心三角 */
.ag-check-line {
  fill: none;
  stroke: var(--ag-hue);
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ---- 动效层 ----
 * 所有循环时长都乘上 --ag-period 的微调档，delay 统一加 --ag-shift：
 * 同屏多个头像因此不同相位，也不会永远保持同一个相对相位。 */

.ag-breath {
  animation: ag-breath calc(4.2s + var(--ag-period)) ease-in-out infinite;
  animation-delay: var(--ag-shift);
  transform-box: view-box;
  transform-origin: 50px 60px;
}

/* 眼睛：眨眼。origin 取自身包围盒顶边，scaleY 收缩即"合眼" */
.ag-eyes {
  transform-box: fill-box;
  transform-origin: center top;
  animation: ag-blink calc(5.6s + var(--ag-period)) steps(1, end) infinite;
  animation-delay: var(--ag-shift);
}

/* 扫视：慢速左右移动 + 长停顿（关键帧里 0%–30% 都在原位） */
.ag-gaze {
  animation: ag-gaze calc(7.8s + var(--ag-period)) ease-in-out infinite;
  animation-delay: var(--ag-shift);
}

@keyframes ag-breath {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1.8px);
  }
}

/* steps(1) 而不是 ease：眨眼必须"啪"地闭合。用补间会变成慢慢眯眼，那是困了不是眨眼。
   两组眨眼之间隔 2.4s 和 2.6s，形成不规则的间隔感 */
@keyframes ag-blink {
  0%,
  92.9%,
  96.5%,
  100% {
    transform: scaleY(1);
  }
  93%,
  96.4% {
    transform: scaleY(0.08);
  }
}

@keyframes ag-gaze {
  0%,
  30% {
    transform: translateX(0);
  }
  40%,
  56% {
    transform: translateX(-2.2px);
  }
  66%,
  84% {
    transform: translateX(2.2px);
  }
  94%,
  100% {
    transform: translateX(0);
  }
}

/* ---- thinking ---- */

/* 眼睛整体上移 + 压扁：人在想事情时视线会往上走、眼睛会眯。
   上移挂在 .ag-lift（子层），因为 .ag-gaze 已经占用了水平方向的那次位移 */
.ag.is-thinking .ag-lift {
  animation: ag-lift 3.4s ease-in-out infinite;
}

.ag.is-thinking .ag-eyes {
  animation: ag-squint 3.4s ease-in-out infinite;
}

.ag.is-thinking .ag-head {
  animation: ag-tilt 6.2s ease-in-out infinite;
}

.ag.is-thinking .ag-liquid {
  animation: ag-liquid calc(1.5s + var(--ag-period)) ease-in-out infinite;
  animation-delay: calc(var(--ag-shift) + var(--ag-i) * 0.24s);
}

.ag.is-thinking .ag-orbit {
  animation: ag-orbit 7.5s linear infinite;
}

@keyframes ag-lift {
  0%,
  100% {
    transform: translateY(-1px);
  }
  50% {
    transform: translateY(-2.4px);
  }
}

@keyframes ag-squint {
  0%,
  100% {
    transform: scaleY(1);
  }
  50% {
    transform: scaleY(0.82);
  }
}

@keyframes ag-tilt {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(2.4deg);
  }
}

/* 流动的小点：低位 → 抬起 → 落回，逐点延迟形成"流" */
@keyframes ag-liquid {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  50% {
    transform: translateY(-2.6px);
    opacity: 1;
  }
}

/* 思考环：只转，不发光。0° 与 360° 同形，所以即使被降到单次播放也不会跳位 */
@keyframes ag-orbit {
  to {
    transform: rotate(360deg);
  }
}

/* ---- speaking ---- */

/* 浮动幅度比呼吸大一档：三个状态里只有"正在说话"需要在余光里被认出来 */
.ag.is-speaking .ag-breath {
  animation: ag-bob 2.6s ease-in-out infinite;
  animation-delay: var(--ag-shift);
}

.ag.is-speaking .ag-talk {
  /* 口型不挂 --ag-shift：那个相位是为几秒级循环算的，0.34s 的节拍套上去
     会变成固定错拍。错开靠 --ag-period 已经足够（每个主理浮动周期不同） */
  animation: ag-talk 0.34s ease-in-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}

@keyframes ag-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

@keyframes ag-talk {
  0%,
  100% {
    transform: scaleY(0.55) scaleX(0.95);
  }
  50% {
    transform: scaleY(1.25) scaleX(1.05);
  }
}

/* ---- done ---- */

/* 点头跑一次就回到 0°（关键帧首尾都是 0），所以 620ms 后视觉上就是 idle，
   不需要 JS 去把 state 改回来 —— 组件可以一直停在 done 上 */
.ag.is-done .ag-nod {
  transform-box: view-box;
  transform-origin: 50px 56px;
  animation: ag-nod 0.62s var(--ease-out) 1 both;
}

.ag.is-done .ag-check {
  animation: ag-check 0.62s var(--ease-out) 1 both;
}

@keyframes ag-nod {
  0%,
  100% {
    transform: rotate(0deg);
  }
  35% {
    transform: rotate(4.5deg);
  }
  70% {
    transform: rotate(-1.2deg);
  }
}

@keyframes ag-check {
  0% {
    opacity: 0;
    transform: translateY(3px);
  }
  45%,
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

/* =============================================================================
 * 减少动效降级
 * -----------------------------------------------------------------------------
 * 这里必须**逐条 animation: none**，不能只靠 styles/base.css 里那条全局兜底：
 * 那条把时长压成 0.01ms、迭代锁成 1 次并保留 forwards 填充，
 * 于是无限循环的动画会停在最后一个关键帧上 —— 扫视停在偏视、思考点停在半透明、
 * 说话波形停在一个开合姿态，全是"卡住的半动作"，比不动更糟。
 * 关掉之后各元素回到 CSS 里写死的静态造型，状态差异仍然读得出来：
 * 眼睛的位置、思考点、对勾、口型都是模板里就存在的结构，不依赖动画。
 * 眨眼与点头本身就是一次性事件，即使被压成瞬时完成，终态也与静态一致，所以不额外处理。
 */
@media (prefers-reduced-motion: reduce) {
  .ag-breath,
  .ag-eyes,
  .ag-gaze,
  .ag-lift,
  .ag-head,
  .ag-liquid,
  .ag-orbit,
  .ag-talk,
  .ag-nod,
  .ag-check {
    animation: none;
  }
}
</style>
