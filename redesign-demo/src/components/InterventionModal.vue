<script setup lang="ts">
/**
 * 主动干预。
 *
 * 产品口径（第 9 幕）：全产品只有"陪你推进的人"能主动开口，
 * 而且受三个参数约束 —— 停滞 3 天、同一条冷却 48 小时、7 天最多 2 次。
 * 话术不施压、不追究：停滞归到任务 / 方法 / 方向，不归到人。
 *
 * 这里把三个参数**显示给用户看**，因为"为什么现在来打扰我"本身要被回答。
 */
defineProps<{
  host: string
  title: string
  body: string
  action: string
  secondary: string
  rules: string[]
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div class="layer" @click.self="emit('close')">
    <div class="sheet" role="dialog" aria-modal="true" aria-label="来自陪伴教练的消息">
      <div class="sheet__host">
        <span class="dot dot--live" />
        {{ host }}
      </div>

      <h2 class="sheet__title">{{ title }}</h2>
      <p class="sheet__body">{{ body }}</p>

      <div class="sheet__rules">
        <span class="t-label">为什么是现在</span>
        <ul class="rules">
          <li v-for="r in rules" :key="r" class="rules__item">
            <span class="dot" />
            {{ r }}
          </li>
        </ul>
      </div>

      <div class="sheet__foot">
        <button class="btn" @click="emit('close')">{{ secondary }}</button>
        <button class="btn btn--primary" @click="emit('close')">{{ action }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.layer {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: var(--sp-5);
  background: var(--overlay-mask);
}

.sheet {
  width: min(460px, 100%);
  padding: var(--sp-5);
  background: var(--c-surface);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
}

.sheet__host {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
  margin-bottom: var(--sp-4);
}

.dot--live {
  color: var(--c-done);
  box-shadow: 0 0 0 3px var(--c-done-weak);
}

.sheet__title {
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
}

.sheet__body {
  margin-top: var(--sp-3);
  font-size: var(--fs-14);
  color: var(--c-text-2);
  line-height: var(--lh-normal);
}

.sheet__rules {
  margin-top: var(--sp-5);
  padding-top: var(--sp-4);
  border-top: var(--bw-1) solid var(--c-border);
}

.rules {
  margin-top: var(--sp-2);
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.rules__item {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 2px var(--sp-3);
  border-radius: var(--r-pill);
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.rules__item .dot {
  color: var(--c-text-4);
}

.sheet__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  margin-top: var(--sp-5);
}
</style>
