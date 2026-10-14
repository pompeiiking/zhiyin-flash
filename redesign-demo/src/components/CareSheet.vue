<script setup lang="ts">
/*
 * MIGRATION §1.3 D7（COVERAGE.md:132 点名）：删掉「为什么是现在」的折叠，改正文。
 *   ① 它本身是**弹层内的折叠**＝第 2 层（弹层是第一层），违反 PLAN §4.4「一页最多 1 层」；
 *   ② 折叠下方就是两个动作按钮，用户读完正文**还得点一次**才看得到按钮；
 *   ③ 折叠后弹层第一屏只有结论没有理由 —— 而这条理由正是"为什么现在提醒你"。
 * 形态：`shape="sheet"`。它是"提醒"（一次独立的注意事件），不是"停一下的确认"；
 *   `dialog` 会让移动端的「提醒」和「删除确认」占屏形态完全一样（审计 D10）。
 */
import InfoSheet from './InfoSheet.vue'
defineProps<{ host: string; title: string; body: string; action: string; secondary: string; rules: string[] }>()
const emit = defineEmits<{ close: []; action: [] }>()
</script>
<template>
  <InfoSheet :open="true" shape="sheet" :title="title" @close="emit('close')">
    <p class="ws-muted">{{ host }}</p><p style="margin-top: var(--sp-5)">{{ body }}</p>
    <h3 class="ws-section-title care-reason__head">为什么是现在</h3><ul class="ws-mini-list care-reason__list"><li v-for="r in rules" :key="r">{{ r }}</li></ul>
    <div class="ws-inline-actions"><button class="btn btn--primary" @click="emit('action')">{{ action }}</button><button class="ws-text-button" @click="emit('close')">{{ secondary }}</button></div>
    <p class="ws-demo-note">这是一次陪伴提醒的示例。选择第一步，会加入当前演示的今日任务。</p>
  </InfoSheet>
</template>

<style scoped>
/* 理由从折叠里出来之后需要自己的层次：与正文分开、与动作按钮靠近 */
.care-reason__head { margin-top: var(--sp-6); }
.care-reason__list { margin-top: var(--sp-3); }
</style>
