<script setup lang="ts">
/**
 * 浮动块 —— 核心页上唯一的容器形态。
 *
 * 三件事决定了它"浮"得住：
 *   1. 半透明 + 背景模糊：盖住下面的内容，但仍能看见下面有什么；
 *   2. 大而软的投影 + 顶部高光：有厚度，不是一张贴纸；
 *   3. 极轻微的旋转：像真的摆在桌面上，而不是对齐到像素网格。
 *
 * 每个块都能被关掉 —— 关掉之后旁边的块会自动补位（由外层 TransitionGroup 负责），
 * 过一会儿它自己再飘回来。
 */
const props = withDefaults(
  defineProps<{
    size?: 'sm' | 'md' | 'lg'
    tone?: 'plain' | 'raised' | 'accent' | 'quiet'
    interactive?: boolean
    closable?: boolean
    /** 控制台上的块可以被"解决"：解决＝这件事办完了，让位给别的 */
    resolvable?: boolean
    /** 正在被解决：表层盖一层绿膜，手绘对勾画出来，然后才收缩让位 */
    resolved?: boolean
    /**
     * 表层那句话。
     *
     * 默认「已解决」对应"这件事办完了"；交接卡那种"读过了、别再提醒"按下去是**另一种结果**，
     * 用同一句话就分不出来 —— 用户会以为自己在宣布交接完结。
     */
    resolvedLabel?: string
    /** 每块一个很小的角度，让整屏不像表格 */
    tilt?: number
    label?: string
    /** 这一块是"现在该点的那一个"：深色边框呼吸，把用户的眼睛领过去 */
    next?: boolean
  }>(),
  { size: 'md', tone: 'plain', interactive: false, closable: true, resolvable: false, resolved: false, resolvedLabel: '已解决', tilt: 0, label: '', next: false }
)

const emit = defineEmits<{ (e: 'close'): void; (e: 'resolve'): void }>()
</script>

<template>
  <!--
    可"解决"的块，右下角有一个绝对定位的「解决」键（`.bubble__done`）。
    `has-done` 让块内页脚给那一角留位：不给的话，页脚右端的 CTA 正好被它压住、
    点不动 —— 待办块的「全部任务 →」实测就是这样（规则见 base.css）。
  -->
  <component
    :is="props.interactive ? 'button' : 'section'"
    class="bubble"
    :class="[
      `s-${props.size}`,
      `t-${props.tone}`,
      {
        interactive: props.interactive,
        'has-done': props.resolvable,
        'is-next': props.next,
      },
    ]"
    :type="props.interactive ? 'button' : undefined"
    :style="{ '--tilt': props.tilt + 'deg' }"
    :aria-label="props.label || undefined"
  >
    <slot />

    <!--
      已解决：不是另外盖一块东西，而是**这块自己表层的遮盖**。
      inset: 0 + border-radius: inherit，所以它跟着气泡的形状走（圆角、尺寸都对得上），
      对勾是手绘的一笔，画完这块才开始收缩让位。整层不吃点击。
    -->
    <span v-if="props.resolved" class="veil" aria-hidden="true">
      <svg class="veil__check" viewBox="0 0 64 64" fill="none">
        <path
          d="M17 34.5 C23.5 40.6 26.5 44.2 30.5 48 C38.1 36.4 44.2 27.6 55 15.5"
          pathLength="1"
          stroke="currentColor"
          stroke-width="5.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="label veil__label">{{ props.resolvedLabel }}</span>
    </span>

    <!-- 拖动把手：只是提示可拖，真正的拖动由画布统一接管 -->
    <span v-if="props.closable" class="bubble__grip" aria-hidden="true">
      <svg width="12" height="12" viewBox="0 0 12 12">
        <g fill="currentColor">
          <circle cx="4" cy="3" r="1" /><circle cx="8" cy="3" r="1" />
          <circle cx="4" cy="6" r="1" /><circle cx="8" cy="6" r="1" />
          <circle cx="4" cy="9" r="1" /><circle cx="8" cy="9" r="1" />
        </g>
      </svg>
    </span>

    <button
      v-if="props.closable"
      class="bubble__close"
      type="button"
      aria-label="关掉这块"
      @click.stop="emit('close')"
    >
      <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" stroke-width="1.5"
              stroke-linecap="round" />
      </svg>
    </button>

    <!-- 解决：这件事办完了。按下去它会收缩让位，过一会儿别的块补上来 -->
    <button
      v-if="props.resolvable"
      class="bubble__done"
      type="button"
      aria-label="解决这件事"
      @click.stop="emit('resolve')"
    >
      <svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2.6 7.4 5.6 10.4 11.4 3.8" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="label">解决</span>
    </button>
  </component>
</template>

<style scoped>
.bubble {
  position: relative;
  display: flex; flex-direction: column; gap: var(--s3);
  min-width: 0; min-height: 0;
  text-align: left;
  overflow: hidden;
  border-radius: var(--r-sketch-lg);
  /* 玻璃：模糊 16px（规范区间 10–20），饱和度略提，表面半透明 */
  border: var(--bw) solid var(--line-2);
  box-shadow: var(--e-3), var(--inner-hi);
  transform: rotate(var(--tilt));
  will-change: transform, opacity, filter;
  transition: transform var(--dur) var(--ease-spring),
              background var(--dur) var(--ease-out),
              border-color var(--dur) var(--ease-out),
              box-shadow var(--dur) var(--ease-out);
}

/*
 * 卡面干净：没有折角、没有纹理、没有高光（用户点名去除）。
 * 草稿的个性交给字体、涂鸦层和轻微的倾斜，框本身退到看不见。
 */

.s-sm { padding: var(--s4); border-radius: var(--r-sketch-md); }
.s-md { padding: var(--s5); }
.s-lg { padding: var(--s6); }

.t-plain { background: var(--glass-1); }
.t-raised { background: var(--c-paper); }
.t-accent { background: var(--g-10); border-color: var(--accent); }
.t-quiet { background: var(--n-0); border-style: dashed; border-color: var(--line-3); }

.interactive { cursor: pointer; }
.interactive:hover {
  transform: translateY(-4px) scale(1.008);
  border-color: var(--ink-1);
  box-shadow: var(--e-4);
}
.interactive:active { transform: translateY(-1px) scale(0.996); }

/*
 * 「现在该点这一块」。
 *
 * 一整屏都是能点的块，"下一步"靠读文字找出来太难了 —— 新手用户的第一句话
 * 常常是"我该点哪儿"。所以给它一圈深色描边 + 呼吸，把眼睛领过去。
 *
 * 三条约束：
 *   · 只动边框与阴影，不动位移 —— 位移会和拖拽/倾斜打架；
 *   · 动画走 opacity/box-shadow（合成层），不触发重排；
 *   · 系统开了"减少动态效果"就只留描边，不做呼吸。
 */
.is-next {
  border-color: var(--ink-1);
  border-width: 2px;
  animation: next-breath 2.4s var(--ease-out) infinite;
}
@keyframes next-breath {
  0%, 100% { box-shadow: var(--e-3), 0 0 0 0 rgba(15, 23, 42, 0.22); }
  50%      { box-shadow: var(--e-3), 0 0 0 10px rgba(15, 23, 42, 0); }
}
@media (prefers-reduced-motion: reduce) {
  .is-next { animation: none; box-shadow: var(--e-3), 0 0 0 6px rgba(15, 23, 42, 0.16); }
}

/* 关闭键：安静地待着，需要时才明显 */
.bubble__close {
  position: absolute; top: 12px; right: 12px; z-index: 2;
  width: 26px; height: 26px; border-radius: 50%;
  display: grid; place-items: center;
  color: var(--ink-3);
  background: var(--fill-subtle);
  border: 1px solid transparent;
  opacity: 0;
  transform: scale(0.9);
  transition: opacity var(--dur-fast) var(--ease-out),
              transform var(--dur) var(--ease-spring),
              color var(--dur-fast) var(--ease-out),
              background var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out);
}

/* 把手：和关闭键并排，静止时很淡，悬停或键盘进入时亮起 */
.bubble__grip {
  position: absolute; top: 15px; right: 44px; z-index: 2;
  display: grid; place-items: center;
  color: var(--ink-4);
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
  pointer-events: none;
}
.bubble:hover .bubble__grip,
.bubble:focus-within .bubble__grip { opacity: 1; }
/* 键盘用户 Tab 进来时也要看得见，不能只靠 hover */
.bubble:hover .bubble__close,
.bubble:focus-within .bubble__close { opacity: 1; transform: scale(1); }
.bubble__close:hover {
  color: var(--ink-1);
  background: var(--fill-press);
  border-color: var(--line-3);
}

/*
 * 解决键：不是"关掉"，是"办完了"。
 * 所以它比关闭键更显眼（有字、有对勾、悬停变绿），
 * 而关闭键继续安静地待在角落里当"先挪开"。
 */
.bubble__done {
  position: absolute; right: 12px; bottom: 12px; z-index: 2;
  display: inline-flex; align-items: center; gap: 5px;
  height: 30px; padding: 0 11px 0 9px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--n-1);
  color: var(--ink-2);
  opacity: 0;
  transform: translateY(3px);
  transition: opacity var(--dur-fast) var(--ease-out),
              transform var(--dur) var(--mo-spring),
              color var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out),
              background var(--dur-fast) var(--ease-out);
}
.bubble__done .mono { color: inherit; }
.bubble:hover .bubble__done,
.bubble:focus-within .bubble__done { opacity: 1; transform: translateY(0); }
.bubble__done:hover {
  color: var(--accent-ink);
  background: var(--accent);
  border-color: var(--accent);
}

/*
 * 已解决的遮盖：贴在气泡表层，不是一个浮在上面的块。
 * 一层半透绿膜 + 一道内描边，让"这块被处理过了"读起来像是它的状态，
 * 而不是屏幕上多了一张纸。对勾一笔画出来（走 motion.css 的 mo-draw）。
 */
.veil {
  position: absolute; inset: 0;
  z-index: 3;
  border-radius: inherit;          /* 跟着气泡的圆角走 */
  display: grid; place-items: center;
  gap: var(--s2);
  align-content: center;
  pointer-events: none;
  color: var(--mk-green);
  background: rgba(15, 122, 88, 0.1);
  box-shadow: inset 0 0 0 2px rgba(15, 122, 88, 0.34);
  animation: mo-pop var(--mo-fast) var(--mo-out) both;
}
.veil__check {
  width: clamp(34px, 22%, 64px);
  height: auto;
  overflow: visible;
}
.veil__check path {
  stroke-dasharray: 1;
  animation: mo-draw var(--mo-base) var(--mo-out) 60ms both;
}
.veil__label {
  color: var(--mk-green);
  letter-spacing: 0.2em;
}

/* 关掉 / 回来时的动效：位移 + 缩放 + 模糊对焦 */
.block-enter-active {
  transition: transform var(--dur-enter) var(--ease-spring),
              opacity calc(var(--dur-enter) * 0.7) var(--ease-out),
              filter var(--dur-enter) var(--ease-out);
}
.block-leave-active {
  transition: transform var(--dur-exit) var(--ease-in),
              opacity calc(var(--dur-exit) * 0.8) var(--ease-out),
              filter var(--dur-exit) var(--ease-out);
}
/*
 * 入场/出场不再动 filter。
 * 一块气泡有几百像素见方，blur 动画会让它每帧重做一次全尺寸模糊；
 * 位移 + 缩放已经能说明"从下面浮上来"，加模糊只是把开合拖慢。
 */
.block-enter-from { opacity: 0; transform: translateY(26px) scale(0.93); }
.block-leave-to { opacity: 0; transform: translateY(-12px) scale(0.95); }
.block-move { transition: transform var(--dur-enter) var(--ease-spring); }
</style>
