<script setup lang="ts">
import { demo } from '../store'
import { SCENARIOS } from '../data/scenarios'

/**
 * 场景化设计的开关：切年级，整套内容跟着换。
 *
 * 上一版这里是 4 个并排的按钮块 —— 顶栏一共 5 个控件，视觉上太重。
 * 现在收成一个下拉：控件数从 5 降到 4，用的还是原生 select（键盘与读屏都免费拿到）。
 */
const grades = SCENARIOS
</script>

<template>
  <label class="grade">
    <span class="sr-only">切换使用场景（年级）</span>
    <select
      class="grade__select"
      :value="demo.state.grade"
      @change="demo.setGrade(($event.target as HTMLSelectElement).value as never)"
    >
      <option v-for="g in grades" :key="g.id" :value="g.id">
        {{ g.grade }} · {{ g.focus }}
      </option>
    </select>
  </label>
</template>

<style scoped>
.grade {
  display: inline-flex;
}

.grade__select {
  height: var(--btn-h-md);
  max-width: 220px;
  padding: 0 var(--sp-3);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--btn-radius);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: var(--fs-12);
  cursor: pointer;
  transition:
    border-color var(--dur-1) ease,
    color var(--dur-1) ease;
}

.grade__select:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text);
}

@media (max-width: 900px) {
  .grade__select {
    max-width: 130px;
  }
}
</style>
