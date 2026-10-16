<script setup lang="ts">
/*
 * InboxSheet —— 提醒弹层（每条提醒是一个独立的注意事件）。
 *
 * 对应 MIGRATION：
 *   · §2.2 第 3 条：现状是缺省 `dialog`（桌面居中窄盒 + 小屏仍居中），
 *     而它是"提醒列表"，还有"下一条"的连续浏览语义 → `shape="sheet"`
 *     （桌面右侧抽屉、小屏底部面板、可下拉关闭、稳定高度）。
 *     **注意 `InfoSheet.vue:54-58` 的 `resolvedShape` 里 `wide`/`inspector`
 *     优先级高于 `shape`** —— 这一处原来两个都没传，所以 `shape` 是直接生效的
 *     （实测计算样式见交付说明）。
 *   · §4.2 E8 + U2：空态是手写的 `<div class="ws-empty"><h3>…`，
 *     `kind` 枚举里**没有 `notice`**（第三处缺口，见 U2/E8），借用 `notes`；
 *     并且**显式传 `headingLevel="3"`**（弹层内的窄空态；MIGRATION §4.2 的三条收尾
 *     要求"整块被顶掉才用 2"，这里是弹层内的一块，所以是 3 —— 显式写出来，
 *     不靠默认值，避免以后 `EmptyState` 默认档变化时静默改变层级）。
 */
import { demo } from '../store'
import EmptyState from './EmptyState.vue'
import InfoSheet from './InfoSheet.vue'
import UiIcon from './UiIcon.vue'
</script>
<template>
  <InfoSheet :open="demo.state.noticeOpen" shape="sheet" title="提醒" @close="demo.closeNotice()">
    <template v-if="demo.use.activeNotice.value">
      <p class="ws-muted">{{ demo.use.activeNotice.value.kind }}</p><h3 class="ws-section-title" style="margin-top: var(--sp-4)">{{ demo.use.activeNotice.value.title }}</h3><p style="margin-top: var(--sp-4)">{{ demo.use.activeNotice.value.body }}</p>
      <div class="ws-inline-actions"><button class="btn btn--primary" @click="demo.resolveNotice()">{{ demo.use.activeNotice.value.action }}</button><button class="ws-text-button" @click="demo.dismissNotice()">{{ demo.use.activeNotice.value.secondary ?? '先不安排' }}</button></div>
      <button v-if="demo.use.noticeLeft.value" class="ws-text-button" @click="demo.nextNotice()">还有 {{ demo.use.noticeLeft.value }} 条，看下一条<UiIcon name="arrow" :size="16" /></button>
    </template>
    <EmptyState
      v-else
      class="inbox-empty"
      kind="notes"
      size="sm"
      :heading-level="3"
      title="眼前没有需要处理的提醒"
      description="有重要时间节点时，会在这里告诉你；到期的提醒按时间先后排。"
      :next="false"
    >
      <button class="btn" @click="demo.closeNotice()">先去处理当前任务</button>
    </EmptyState>
    <RouterLink class="ws-text-link" to="/reminders" @click="demo.closeNotice()">打开提醒管理与搜索</RouterLink>
  </InfoSheet>
</template>

<style scoped>
.inbox-empty { padding-top: var(--sp-4); }
</style>
