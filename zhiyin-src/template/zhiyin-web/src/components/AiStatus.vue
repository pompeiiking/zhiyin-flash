<script setup lang="ts">
/*
 * AiStatus —— 6 个 AI 面板共用的「进行中 / 出错」共用件。
 *
 * 为什么先重构它（MIGRATION §6 阶段 4.1 / §4.3 B10、B16）：
 *   1. 它是 `TaskBrief` / `TimetableAdvice` / `TodoSuggestions` / `ProfileInsights` /
 *      `CareerMatchPanel` / `DayAdvicePanel`（另加 `AcademicVerification`）共用的唯一反馈出口，
 *      改这一处 = 6 个面板同时拿到统一形态。
 *   2. 老写法是自制 `.inline-status` 两行 div，而 `redesign.css:96` 在窄屏把它
 *      `display:none !important` —— 手机上"AI 正在生成"和"出错了"整条消失（§4.3 B11）。
 *      换成 `StatusBanner` 后自带窄屏 `size="sm"` 形态，不再需要那条隐藏规则。
 *   3. 审计要求形态差异不能只靠颜色：`StatusBanner` 用「竖线宽度 + 图标形状（描边/实心）
 *      + 动作位 + 读屏角色」四件事把 busy 与 error 分开，色盲与灰度截图下仍可辨。
 *
 * 这里保留的语义（不许被"换成组件"抹掉）：
 *   · `busy`  → `tone="info"`：只能手动关（其实是"不能关"，见下），动作位是「停止生成」
 *   · `error` → `tone="error"`：必有重试动作位（StatusBanner 内建）
 *   · 成功时整块不渲染 —— 成功的反馈由页面级 `StatusBanner tone="success"` 负责，
 *     这里不自造第三套"已完成"文案（否则同屏两条反馈在说同一件事）。
 *
 * `dismissible=false`：这两条都不是"读完了可以关掉的通知"，而是**当前状态**。
 * 允许关掉会造成"看起来没在生成/没出错"的假象（父组件持有 error/busy，关掉它也会立刻回来）。
 */
import StatusBanner from './StatusBanner.vue'

defineProps<{ busy: boolean; error: string; progress: string }>()
defineEmits<{ cancel: []; retry: [] }>()
</script>

<template>
  <div v-if="busy" class="ai-status" role="status" aria-live="polite">
    <StatusBanner
      tone="info"
      size="sm"
      :open="true"
      :dismissible="false"
      :message="progress || '正在生成…'"
      action-label="停止生成"
      @action="$emit('cancel')"
    />
  </div>
  <div v-else-if="error" class="ai-status">
    <StatusBanner
      tone="error"
      size="sm"
      :open="true"
      :dismissible="false"
      :message="error"
      retry-label="重试"
      @retry="$emit('retry')"
    />
  </div>
</template>

<style scoped>
/* 两条状态条各自占一行，与它上面的按钮、下面的内容保持同一段间距 */
.ai-status {
  margin-top: var(--sp-4);
}

.ai-status + * {
  margin-top: var(--sp-3);
}
</style>
