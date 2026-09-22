<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import SketchPath from '@/components/charts/SketchPath.vue'
import MagnetLines from '@/components/vendor/vuebits/MagnetLines.vue'
import { sCircle, sLine, sPath, sPolyline, sRect, type SketchOp } from '@/lib/sketch'

/*
 * 纸面的底子 —— 它不是"一张干净的纸 + 一圈光晕"，而是**擦过一遍的纸**。
 *
 * 做法（三层叠出来）：
 *   1. 先画一层极淡的旧笔迹（曾经画过的东西，压在下面）
 *   2. 用两块奶油色的补丁盖上去，补丁的边缘交给 feTurbulence + feDisplacementMap 打毛
 *      —— 于是边界是"擦出来的毛边"，不是一个圆
 *   3. 在补丁边缘留下几段**没被擦干净的残笔**，再加两道橡皮拖过的痕
 *
 * 所以画面上的空白不是空的：它是"这里原来有东西，被擦掉了，还剩一点印子"。
 *
 * v7 加了一层：压在擦痕**下面**的一整片线场（vue-bits · MagnetLines），
 * 会跟着光标弯折。它代表"这页纸上原本印着的东西"，被擦掉之后只在边缘露出来 —— 
 * 于是那片空白不是留白，是擦痕；边缘那些线不是装饰，是没擦掉的部分。
 */
const root = ref<HTMLElement | null>(null)

/* ── 第一层：旧笔迹（很淡，大部分会被擦掉） ─────────────────────── */
const GHOST: SketchOp[] = [
  // 一段没画完的图
  ...sRect(300, 150, 220, 150, { seed: 3001, stroke: 'currentColor', strokeWidth: 1.6 }),
  ...sLine(300, 205, 520, 205, { seed: 3002, stroke: 'currentColor', strokeWidth: 1.2 }),
  ...sLine(410, 150, 410, 300, { seed: 3003, stroke: 'currentColor', strokeWidth: 1.2 }),
  // 几张草稿
  ...sPath('M 760 120 C 800 96, 860 100, 880 140 C 900 180, 856 214, 812 206', { seed: 3004, stroke: 'currentColor', strokeWidth: 1.5 }),
  ...sPolyline([[980, 170], [1020, 132], [1052, 188], [1092, 148]], { seed: 3005, stroke: 'currentColor', strokeWidth: 1.5 }),
  ...sCircle(1180, 220, 34, { seed: 3006, stroke: 'currentColor', strokeWidth: 1.5 }),
  ...sCircle(1180, 220, 12, { seed: 3007, stroke: 'currentColor', strokeWidth: 1.2 }),
  // 下半页：一串日期与勾
  ...sLine(180, 420, 420, 420, { seed: 3008, stroke: 'currentColor', strokeWidth: 1.4 }),
  ...sLine(180, 470, 380, 470, { seed: 3009, stroke: 'currentColor', strokeWidth: 1.4 }),
  ...sLine(180, 520, 440, 520, { seed: 3010, stroke: 'currentColor', strokeWidth: 1.4 }),
  ...sPath('M 500 452 L 516 470 L 546 430', { seed: 3011, stroke: 'currentColor', strokeWidth: 1.8 }),
  ...sPath('M 500 506 L 516 524 L 546 484', { seed: 3012, stroke: 'currentColor', strokeWidth: 1.8 }),
  // 右下角：一个没写完的表
  ...sRect(900, 470, 300, 170, { seed: 3013, stroke: 'currentColor', strokeWidth: 1.5 }),
  ...sLine(900, 526, 1200, 526, { seed: 3014, stroke: 'currentColor', strokeWidth: 1.2 }),
  ...sLine(900, 582, 1200, 582, { seed: 3015, stroke: 'currentColor', strokeWidth: 1.2 }),
  ...sLine(1000, 470, 1000, 640, { seed: 3016, stroke: 'currentColor', strokeWidth: 1.2 }),
  ...sCircle(220, 640, 26, { seed: 3017, stroke: 'currentColor', strokeWidth: 1.4 }),
  ...sLine(640, 700, 860, 700, { seed: 3018, stroke: 'currentColor', strokeWidth: 1.4 }),
]

/* ── 第三层：擦不干净的残笔（露在补丁外面的那几段） ───────────────── */
const REST: { ops: SketchOp[]; tone: string; delay: number }[] = [
  { tone: 'var(--mk-green)', delay: 1.5, ops: [...sPath('M 520 205 C 560 196, 600 214, 648 202', { seed: 3101, stroke: 'currentColor', strokeWidth: 1.8 }), ...sLine(524, 300, 596, 288, { seed: 3102, stroke: 'currentColor', strokeWidth: 1.4 })] },
  { tone: 'var(--mk-orange)', delay: 1.7, ops: [...sPolyline([[1096, 150], [1140, 128], [1176, 168]], { seed: 3103, stroke: 'currentColor', strokeWidth: 1.8 }), ...sCircle(1214, 176, 16, { seed: 3104, stroke: 'currentColor', strokeWidth: 1.5 })] },
  { tone: 'var(--mk-purple)', delay: 1.9, ops: [...sLine(190, 372, 320, 360, { seed: 3105, stroke: 'currentColor', strokeWidth: 1.6 }), ...sPath('M 196 466 L 212 484 L 250 440', { seed: 3106, stroke: 'currentColor', strokeWidth: 1.7 })] },
  { tone: 'var(--mk-blue)', delay: 2.1, ops: [...sLine(244, 636, 380, 620, { seed: 3107, stroke: 'currentColor', strokeWidth: 1.5 }), ...sCircle(430, 610, 14, { seed: 3108, stroke: 'currentColor', strokeWidth: 1.4 })] },
  { tone: 'var(--mk-teal)', delay: 2.3, ops: [...sLine(868, 700, 1004, 686, { seed: 3109, stroke: 'currentColor', strokeWidth: 1.5 })] },
  { tone: 'var(--mk-pink)', delay: 2.5, ops: [...sPath('M 1188 700 C 1214 676, 1246 692, 1268 664', { seed: 3110, stroke: 'currentColor', strokeWidth: 1.6 })] },
]

/*
 * 这里原来还有两道"橡皮拖过的痕"（26px / 20px 宽的奶油色粗线）。
 * 它们和墨层里那三道一样，读出来就是"纸上横着几道浅色粗线"，没有意义 —— 一并去掉。
 * 擦过的感觉交给补丁本身的毛边去表达就够了。
 */

/*
 * ── 视差：只做一件事，而且每帧最多算一次 ──────────────────────────
 *
 * 上一版这里还顺手画了一条手绘墨迹（每次移动都跑一遍 roughjs 生成路径）。
 * 那条墨迹和墨层里的圆珠笔迹是同一件事，两个都画既重复又费 —— 现在只留墨层里那条。
 * 视差本身也不再直接改响应式变量：写进 CSS 变量，交给合成层去动。
 */
/*
 * 这一层现在是**完全静态**的 —— 连视差也撤了。
 *
 * 原因：这层里有两块大面积擦痕补丁，带着 feTurbulence + feGaussianBlur。
 * 只要层里任何东西在动（哪怕只平移 6px），浏览器就可能每帧把滤镜重跑一遍。
 * 底图是背景质感、不参与交互，让它画好一次，之后再也不动。
 */
onMounted(() => {})
onBeforeUnmount(() => {})
</script>

<template>
  <div ref="root" class="sheet" aria-hidden="true">
    <!--
      线场：MagnetLines 原件是 9×9 的 80vmin 方块，这里摊成整页（100%），
      用一道斜向的、两端淡出的 mask 收边，整个盒子不参与指针事件。
    -->
    <div class="field">
      <MagnetLines
        :rows="9"
        :columns="14"
        container-size="100%"
        line-color="var(--ink-1)"
        line-width="2px"
        line-height="16px"
        :base-angle="-8"
      />
    </div>

    <svg class="sheet__svg" viewBox="0 0 1440 860" preserveAspectRatio="xMidYMid slice">
      <defs>
        <!--
          擦出来的毛边：把补丁的边缘用噪声推动一下。
          于是它不是一条光滑的曲线，而是"擦到一半停手"的那种边界。
        -->
        <filter id="eraseEdge" x="-12%" y="-12%" width="124%" height="124%">
          <feTurbulence type="fractalNoise" baseFrequency="0.021 0.03" numOctaves="3" seed="11" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="42" xChannelSelector="R" yChannelSelector="G" />
          <feGaussianBlur stdDeviation="1.6" />
        </filter>
      </defs>

      <!-- ① 旧笔迹：压在下面，很淡；随指针轻微平移（值走 CSS 变量，不动 Vue） -->
      <g class="ghost">
        <SketchPath :ops="GHOST" />
      </g>

      <!-- ② 擦掉的两块：奶油补丁，边缘是毛的 -->
      <g filter="url(#eraseEdge)" class="erase">
        <path d="M 236 96 C 520 56, 700 84, 906 60 C 1140 34, 1330 84, 1364 220 C 1396 350, 1348 430, 1150 452 C 930 476, 760 430, 560 452 C 380 472, 214 430, 186 320 C 162 224, 178 118, 236 96 Z"
              fill="var(--n-0)" opacity="0.97" />
        <path d="M 160 520 C 380 486, 520 520, 720 502 C 920 484, 1000 540, 966 640 C 936 726, 740 760, 520 748 C 320 736, 150 720, 122 640 C 100 574, 116 534, 160 520 Z"
              fill="var(--n-0)" opacity="0.96" />
      </g>

      <!-- ③ 残笔：擦不掉的那几段 -->
      <g
        v-for="(r, i) in REST"
        :key="i"
        class="rest"
        :style="{ color: r.tone, animationDelay: `${r.delay}s` }"
      >
        <SketchPath :ops="r.ops" />
      </g>

    </svg>
  </div>
</template>

<style scoped>
.sheet { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.sheet__svg { width: 100%; height: 100%; display: block; }

/* 线场：很淡，只在没被擦到的地方露出来 */
.field {
  position: absolute; inset: 0;
  opacity: 0.5;
  mask-image: linear-gradient(158deg, transparent 2%, #000 26%, #000 74%, transparent 98%);
  -webkit-mask-image: linear-gradient(158deg, transparent 2%, #000 26%, #000 74%, transparent 98%);
  animation: field-in 1600ms var(--mo-out) 200ms both;
}
@keyframes field-in { from { opacity: 0 } to { opacity: 0.5 } }

/* 旧笔迹：画出来之后一直很淡 */
.ghost :deep(path) {
  color: var(--ink-1);
  opacity: 0.12;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: ghost-draw 1400ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes ghost-draw { to { stroke-dashoffset: 0; opacity: 0.1; } }

/* 补丁自己轻轻落下来 —— 像把橡皮按上去 */
.erase { opacity: 0; animation: erase-in 900ms cubic-bezier(0.16, 1, 0.3, 1) 700ms forwards; }
@keyframes erase-in { from { opacity: 0 } to { opacity: 1 } }

/* 残笔：后出现，比旧笔迹清楚一档 */
.rest { opacity: 0; animation: rest-in 900ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
.rest :deep(path) { opacity: 0.5; }
@keyframes rest-in { from { opacity: 0; transform: translateY(4px) } to { opacity: 1; transform: none } }

@media (prefers-reduced-motion: reduce) {
  .ghost :deep(path), .erase, .rest { animation: none; opacity: 1; stroke-dashoffset: 0; }
  .field { animation: none; }
}
</style>
