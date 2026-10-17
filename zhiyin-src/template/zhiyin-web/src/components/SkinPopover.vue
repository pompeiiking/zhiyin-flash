<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { skin, type Accent, type ThemeMode } from '../lib/theme'
import DetailPopover from './DetailPopover.vue'
import SegmentedChoice from './SegmentedChoice.vue'
import UiIcon from './UiIcon.vue'

const route = useRoute()
const open = ref(false)
watch(() => route.fullPath, () => { open.value = false })

const themeOptions: { id: ThemeMode; label: string }[] = [
  { id: 'light', label: '浅色' },
  { id: 'dark', label: '深色' },
  { id: 'system', label: '跟随系统' },
]
const accentOptions: { id: Accent; label: string }[] = [
  { id: 'blue', label: '蓝色' },
  { id: 'red', label: '红色' },
]
</script>

<template>
  <DetailPopover v-model="open" title="外观与主题" label="设置外观与主题" side="bottom" class="skin-trigger">
    <template #trigger><UiIcon name="settings" :size="17" /><span>外观</span></template>
    <div class="skin-picker">
      <section>
        <div class="skin-picker__heading"><strong>品牌色</strong><span>用于导航、主要操作与强调状态</span></div>
        <SegmentedChoice :model-value="skin.state.accent" :options="accentOptions" label="品牌色" @update:model-value="skin.setAccent" />
      </section>
      <section>
        <div class="skin-picker__heading"><strong>明暗</strong><span>跟随系统会随设备外观自动变化</span></div>
        <SegmentedChoice :model-value="skin.state.theme" :options="themeOptions" label="明暗模式" @update:model-value="skin.setTheme" />
      </section>
      <button class="skin-picker__reset" type="button" @click="skin.reset()">恢复默认外观</button>
    </div>
  </DetailPopover>
</template>

<style scoped>
:deep(.skin-trigger) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-width: 64px;
  min-height: 44px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--c-text-2);
  font-size: 12px;
}
:deep(.skin-trigger:hover), :deep(.skin-trigger[aria-expanded='true']) {
  border-color: var(--c-border);
  background: var(--c-surface-2);
  color: var(--c-primary);
}
.skin-picker { display: grid; gap: 20px; width: min(330px, calc(100vw - 88px)); max-width: 100%; overflow-x: clip; }
.skin-picker section { display: grid; gap: 9px; }
.skin-picker__heading { display: grid; gap: 2px; }
.skin-picker__heading strong { font-size: 14px; font-weight: 600; }
.skin-picker__heading span { color: var(--c-text-3); font-size: 12px; line-height: 1.55; }
.skin-picker__reset { min-height: 44px; border-top: 1px solid var(--c-border); color: var(--c-text-2); font-size: 13px; text-align: left; }
@media (max-width: 520px) {
  :deep(.skin-trigger) { min-width: 44px; width: 44px; padding: 0; }
  :deep(.skin-trigger span) { display: none; }
  :deep(.detail-popover__body) { max-width: calc(100vw - 24px); overflow-x: hidden; }
  .skin-picker { width: min(306px, calc(100vw - 64px)); }
}
</style>
