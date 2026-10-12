<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useCountUp } from '../../lib/motion'

/**
 * 一条维度：结论一句 + 分值条 + 门槛线。
 *
 * 门槛线是这份报告最值钱的那句话的可视化版本：
 * "你的呈现能力是 46 分，两条主攻方向都要求 50 分以上 —— 差 4 分"。
 * 所以门槛必须画出来，而不是只写在文字里。
 *
 * 动效：分值从 0 滚到实际值（420ms ease-out），条子同步用 transform 长出来。
 * 这是"状态指示"—— 让"你差 4 分"这个结论被看见，而不是一行静态数字。
 */
const props = defineProps<{
  label: string
  score: number
  thresholdAt?: number
  /** 主攻方向的要求分值 */
  requirement?: number
}>()

const scoreRef = toRef(props, 'score')
const { shown } = useCountUp(scoreRef)

const display = computed(() => Math.round(shown.value))
const ratio = computed(() => Math.max(0, Math.min(1, shown.value / 100)))
const belowRequirement = computed(() => props.requirement != null && props.score < props.requirement)
</script>

<template>
  <div class="meter-row">
    <div class="meter-row__head">
      <span class="meter-row__label">{{ label }}</span>
      <span class="meter-row__score t-num">{{ display }}</span>
    </div>

    <div class="meter-row__track">
      <div
        class="meter-row__fill"
        :class="{ 'meter-row__fill--attention': belowRequirement }"
        :style="{ '--meter': ratio }"
      />
      <div
        v-if="requirement != null"
        class="meter-row__req"
        :style="{ left: `${requirement}%` }"
        :title="`主攻方向要求 ${requirement} 分`"
      />
      <div
        v-if="thresholdAt != null"
        class="meter-row__threshold"
        :style="{ left: `${thresholdAt}%` }"
      />
    </div>

    <div v-if="requirement != null" class="meter-row__legend">
      <span>你 {{ score }}</span>
      <span class="meter-row__gap" :class="{ 'meter-row__gap--short': score >= requirement }">
        {{ score >= requirement ? `已过门槛 ${requirement}` : `差 ${requirement - score} 分到门槛 ${requirement}` }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.meter-row__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--sp-2);
}

.meter-row__label {
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.meter-row__score {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  color: var(--c-text);
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
  /* transform 而不是 width：宽度动画触发布局，transform 只走合成层 */
  transform-origin: left center;
  transform: scaleX(var(--meter, 0));
  transition: transform var(--dur-4) var(--ease-out);
}

.meter-row__fill--attention {
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

.meter-row__threshold {
  position: absolute;
  top: 0;
  width: 1px;
  height: 8px;
  background: var(--c-border-strong);
}

.meter-row__legend {
  display: flex;
  justify-content: space-between;
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.meter-row__gap--short {
  color: var(--c-attention-strong);
  font-weight: var(--fw-medium);
}
</style>
