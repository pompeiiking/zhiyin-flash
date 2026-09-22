<!--
  vue-bits · BlurText  （DavidHDev/vue-bits, MIT）
  原件取自 https://vue-bits.dev/textanimations/BlurText
  本项目对原件的两处改动（都在下面注释标出）：
    1. 去掉 Tailwind 类名，换成 scoped CSS —— 本仓库没有 Tailwind
    2. 新增 as / markIndex 两个 prop：as 让我们能渲染 h1/span 保住语义，
       markIndex 把某个词标出来，交给 rough-notation 在外面画手绘圈
-->
<template>
  <component :is="as" ref="rootRef" class="bt" :class="className">
    <Motion
      v-for="(segment, index) in elements"
      :key="index"
      tag="span"
      :initial="fromSnapshot"
      :animate="inView ? buildKeyframes(fromSnapshot, toSnapshots) : fromSnapshot"
      :transition="getTransition(index)"
      @animation-complete="handleAnimationComplete(index)"
      class="bt__seg"
      :class="{ 'bt__seg--mark': index === markIndex }"
    >
      {{ segment === ' ' ? '\u00A0' : segment }}
      <template v-if="animateBy === 'words' && index < elements.length - 1">&nbsp;</template>
    </Motion>
  </component>
</template>

<script setup lang="ts">
import { Motion, type Transition } from 'motion-v';
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue';

type BlurTextProps = {
  text?: string;
  delay?: number;
  className?: string;
  animateBy?: 'words' | 'letters';
  direction?: 'top' | 'bottom';
  threshold?: number;
  rootMargin?: string;
  animationFrom?: Record<string, string | number>;
  animationTo?: Array<Record<string, string | number>>;
  easing?: (t: number) => number;
  onAnimationComplete?: () => void;
  stepDuration?: number;
  /** 渲染成什么标签：门户里用 h1 / span，保住标题语义 */
  as?: string;
  /** 标出第几段（默认不标） */
  markIndex?: number;
};

const buildKeyframes = (
  from: Record<string, string | number>,
  steps: Array<Record<string, string | number>>
): Record<string, Array<string | number>> => {
  const keys = new Set<string>([...Object.keys(from), ...steps.flatMap(s => Object.keys(s))]);

  const keyframes: Record<string, Array<string | number>> = {};
  keys.forEach(k => {
    keyframes[k] = [from[k], ...steps.map(s => s[k])];
  });
  return keyframes;
};

const props = withDefaults(defineProps<BlurTextProps>(), {
  text: '',
  delay: 200,
  className: '',
  animateBy: 'words',
  direction: 'top',
  threshold: 0.1,
  rootMargin: '0px',
  easing: (t: number) => t,
  stepDuration: 0.35,
  as: 'p',
  markIndex: -1
});

const emit = defineEmits<{ done: [] }>();

const inView = ref(false);
const rootRef = useTemplateRef<HTMLParagraphElement>('rootRef');
let observer: IntersectionObserver | null = null;

onMounted(() => {
  if (!rootRef.value) return;

  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        inView.value = true;
        observer?.unobserve(rootRef.value as Element);
      }
    },
    {
      threshold: props.threshold,
      rootMargin: props.rootMargin
    }
  );

  observer.observe(rootRef.value);
});

onBeforeUnmount(() => {
  observer?.disconnect();
});

watch(
  () => [props.text, props.animateBy, props.direction, props.delay],
  () => {
    inView.value = false;
    if (rootRef.value) {
      observer?.observe(rootRef.value);
    }
  }
);

const elements = computed(() => (props.animateBy === 'words' ? props.text.split(' ') : props.text.split('')));

const defaultFrom = computed(() =>
  props.direction === 'top' ? { filter: 'blur(10px)', opacity: 0, y: -50 } : { filter: 'blur(10px)', opacity: 0, y: 50 }
);

const defaultTo = computed(() => [
  {
    filter: 'blur(5px)',
    opacity: 0.5,
    y: props.direction === 'top' ? 5 : -5
  },
  {
    filter: 'blur(0px)',
    opacity: 1,
    y: 0
  }
]);

const fromSnapshot = computed(() => props.animationFrom ?? defaultFrom.value);
const toSnapshots = computed(() => props.animationTo ?? defaultTo.value);

const stepCount = computed(() => toSnapshots.value.length + 1);
const totalDuration = computed(() => props.stepDuration * (stepCount.value - 1));

const times = computed(() =>
  Array.from({ length: stepCount.value }, (_, i) => (stepCount.value === 1 ? 0 : i / (stepCount.value - 1)))
);

const getTransition = (index: number): Transition => ({
  duration: totalDuration.value,
  times: times.value,
  delay: (index * props.delay) / 1000,
  ease: props.easing
});

const handleAnimationComplete = (index: number) => {
  if (index === elements.value.length - 1) {
    props.onAnimationComplete?.();
    emit('done');
  }
};
</script>

<style scoped>
/* 原件这里是 Tailwind 的 flex flex-wrap；没有 Tailwind，就用同义的两行 CSS */
.bt { display: flex; flex-wrap: wrap; margin: 0; }
.bt__seg {
  display: inline-block;
  will-change: transform, filter, opacity;
}
/* 被标出来的那一段：抬成定位父级，给外面的手绘标注当坐标系 */
.bt__seg--mark { position: relative; }
</style>

