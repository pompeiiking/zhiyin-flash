<!--
  vue-bits · VariableProximity  （DavidHDev/vue-bits, MIT）
  原件取自 https://vue-bits.dev/textanimations/VariableProximity
  本项目改动（原件是给拉丁文写的，中文要改三处）：
    1. 字体不再是写死的 'Roboto Flex'，改成 fontFamily prop，默认吃 --font-var
       （我们自托管的 Noto Sans SC 可变子集，带 wght 100–900 轴）
    2. 词盒从 white-space: nowrap 改成可换行 —— 中文句子没有空格，
       整句会被当成一个"词"，nowrap 会直接冲出容器
    3. 无样式类名（sr-only / 任意 className），屏幕阅读器那半段改成内联隐形样式
-->
<template>
  <span
    ref="rootRef"
    :class="[props.className]"
    :style="{
      display: 'inline',
      fontFamily: props.fontFamily,
      ...props.style
    }"
    @click="props.onClick"
  >
    <span
      v-for="(word, wordIndex) in words"
      :key="wordIndex"
      :style="{ display: 'inline', whiteSpace: props.nowrap ? 'nowrap' : 'normal' }"
    >
      <span
        v-for="(letter, lIdx) in word.split('')"
        :key="getLetterKey(wordIndex, lIdx)"
        :ref="el => setLetterRef(el as HTMLElement | null, wordIndex, lIdx)"
        :style="{
          display: 'inline-block',
          fontVariationSettings: fromFontVariationSettings
        }"
        aria-hidden="true"
      >
        {{ letter }}
      </span>
      <span v-if="wordIndex < words.length - 1" style="display: inline">&nbsp;</span>
    </span>
    <!-- 视觉上是逐字拆开的，读屏要听整句 -->
    <span :style="srOnly">{{ props.label }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, type CSSProperties } from 'vue';

export type FalloffType = 'linear' | 'exponential' | 'gaussian';

interface VariableProximityProps {
  label: string;
  fromFontVariationSettings: string;
  toFontVariationSettings: string;
  containerRef?: HTMLElement | null;
  radius?: number;
  falloff?: FalloffType;
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
  /** 用哪套字体：必须是带可变轴的，否则轴推不动 */
  fontFamily?: string;
  /** 拉丁文短语才需要；中文默认允许逐个字换行 */
  nowrap?: boolean;
}

const props = withDefaults(defineProps<VariableProximityProps>(), {
  radius: 50,
  falloff: 'linear',
  className: '',
  style: () => ({}),
  onClick: undefined,
  fontFamily: 'var(--font-var)',
  nowrap: false
});

const srOnly: CSSProperties = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
  borderWidth: 0
};

const rootRef = ref<HTMLElement | null>(null);
const letterRefs = ref<(HTMLElement | null)[]>([]);
const mousePositionRef = { x: 0, y: 0 };
const lastPositionRef = { x: null as number | null, y: null as number | null };

let animationFrameId: number | null = null;
/** 每个字母相对容器的中心点（缓存；尺寸变化时才重量） */
let letterBoxes: { x: number; y: number }[] = [];

function measureLetters() {
  const container = props.containerRef;
  if (!container) return;
  const containerRect = container.getBoundingClientRect();
  letterBoxes = letterRefs.value.map(el => {
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - containerRect.left,
      y: rect.top + rect.height / 2 - containerRect.top
    };
  });
}

const words = computed(() => props.label.split(' '));

const parsedSettings = computed(() => {
  const parseSettings = (settingsStr: string) => {
    const result = new Map<string, number>();
    settingsStr.split(',').forEach(s => {
      const parts = s.trim().split(' ');
      if (parts.length === 2) {
        result.set(parts[0].replace(/['"]/g, ''), parseFloat(parts[1]));
      }
    });
    return result;
  };

  const fromSettings = parseSettings(props.fromFontVariationSettings);
  const toSettings = parseSettings(props.toFontVariationSettings);

  return Array.from(fromSettings.entries()).map(([axis, fromValue]) => ({
    axis,
    fromValue,
    toValue: toSettings.get(axis) ?? fromValue
  }));
});

const calculateDistance = (x1: number, y1: number, x2: number, y2: number) =>
  Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);

const calculateFalloff = (distance: number) => {
  const norm = Math.min(Math.max(1 - distance / props.radius, 0), 1);
  switch (props.falloff) {
    case 'exponential':
      return norm ** 2;
    case 'gaussian':
      return Math.exp(-((distance / (props.radius / 2)) ** 2) / 2);
    case 'linear':
    default:
      return norm;
  }
};

const getLetterKey = (wordIndex: number, letterIndex: number) => `${wordIndex}-${letterIndex}`;

const getGlobalLetterIndex = (wordIndex: number, letterIndex: number) => {
  let globalIndex = 0;
  for (let i = 0; i < wordIndex; i++) {
    globalIndex += words.value[i].length;
  }
  return globalIndex + letterIndex;
};

const setLetterRef = (el: HTMLElement | null, wordIndex: number, lIdx: number) => {
  const globalIndex = getGlobalLetterIndex(wordIndex, lIdx);
  letterRefs.value[globalIndex] = el;
};

const updatePosition = (x: number, y: number) => {
  if (props.containerRef) {
    const rect = props.containerRef.getBoundingClientRect();
    mousePositionRef.x = x - rect.left;
    mousePositionRef.y = y - rect.top;
  } else {
    mousePositionRef.x = x;
    mousePositionRef.y = y;
  }
};

const handleMouseMove = (ev: MouseEvent) => updatePosition(ev.clientX, ev.clientY);

const handleTouchMove = (ev: TouchEvent) => {
  const touch = ev.touches[0];
  updatePosition(touch.clientX, touch.clientY);
};

const animationLoop = () => {
  if (!props.containerRef) {
    animationFrameId = requestAnimationFrame(animationLoop);
    return;
  }

  const { x, y } = mousePositionRef;
  if (lastPositionRef.x === x && lastPositionRef.y === y) {
    animationFrameId = requestAnimationFrame(animationLoop);
    return;
  }

  lastPositionRef.x = x;
  lastPositionRef.y = y;

  /*
   * 本项目改动（性能）：原件每一帧对每个字母调一次 getBoundingClientRect()，
   * 20 个字母就是每帧 20 次布局查询。改成缓存中心点：只在尺寸变化和
   * 字体加载完成之后重新量一次。
   */
  for (let i = 0; i < letterRefs.value.length; i++) {
    const letterEl = letterRefs.value[i];
    const box = letterBoxes[i];
    if (!letterEl || !box) continue;

    const distance = calculateDistance(mousePositionRef.x, mousePositionRef.y, box.x, box.y);

    if (distance >= props.radius) {
      letterEl.style.fontVariationSettings = props.fromFontVariationSettings;
      continue;
    }

    const falloffValue = calculateFalloff(distance);
    const newSettings = parsedSettings.value
      .map(({ axis, fromValue, toValue }) => {
        const interpolatedValue = fromValue + (toValue - fromValue) * falloffValue;
        return `'${axis}' ${interpolatedValue}`;
      })
      .join(', ');

    letterEl.style.fontVariationSettings = newSettings;
  }

  animationFrameId = requestAnimationFrame(animationLoop);
};

onMounted(() => {
  nextTick(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('touchmove', handleTouchMove);
    window.addEventListener('resize', measureLetters);
    /* 字体换上去之后字宽会变，量一次；之后就不需要再量了 */
    measureLetters();
    document.fonts?.ready.then(measureLetters).catch(() => {});
    animationFrameId = requestAnimationFrame(animationLoop);
  });
});

onUnmounted(() => {
  window.removeEventListener('mousemove', handleMouseMove);
  window.removeEventListener('touchmove', handleTouchMove);
  window.removeEventListener('resize', measureLetters);
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId);
  }
});
</script>

