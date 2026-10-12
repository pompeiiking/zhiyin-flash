<script setup lang="ts">
import { computed, ref } from 'vue'
import { CHAT_TURNS, DIRECTION_PLANS } from '../data/student'
import UiIcon from './UiIcon.vue'

// 实际演示数据的可交互片段；不冒充已生成的个人报告。
const stage = ref(0)
const phases = ['聊清楚', '看依据', '迈一步']
const opening = CHAT_TURNS.find((t) => t.id === 'c1')!
const question = CHAT_TURNS.find((t) => t.id === 'c2')!
const direction = DIRECTION_PLANS[0]
const taskTurn = CHAT_TURNS.find((t) => t.task)!
const task = taskTurn.task!
const nextLabel = computed(() => ['看看如何判断', '看看如何行动', '回到对话片段'][stage.value])
function next() { stage.value = (stage.value + 1) % phases.length }
</script>

<template>
  <section class="pe-story" aria-label="职引如何帮你，一段预置示例">
    <header class="pe-story__head"><span>从一句话，到一小步</span><span class="pe-story__sample">预置示例</span></header>
    <div class="pe-story__choices" aria-label="查看示例阶段">
      <button v-for="(label, i) in phases" :key="label" :aria-pressed="stage === i" @click="stage = i">
        <UiIcon :name="['chat', 'report', 'action'][i]" :size="18" />{{ label }}
      </button>
    </div>
    <div class="pe-story__body" aria-live="polite" aria-atomic="true">
      <Transition name="pe-phase">
        <article :key="stage" class="pe-phase">
          <template v-if="stage === 0">
            <p class="pe-phase__label">你可以这样开口</p>
            <blockquote class="pe-question">{{ opening.text.split('。')[0] }}。</blockquote>
            <div class="pe-answer"><p class="pe-phase__label">了解你情况的人</p><p>{{ question.text.split(' —— ')[1] ?? question.text }}</p></div>
            <p class="pe-phase__note">不需要先想好答案。一次只问一个问题。</p>
          </template>
          <template v-else-if="stage === 1">
            <p class="pe-phase__label">看看一条方向的依据</p>
            <h2 class="pe-direction">{{ direction.title }}</h2>
            <ul class="pe-evidence"><li v-for="e in direction.evidence.slice(0, 2)" :key="e"><UiIcon name="check" :size="16" />{{ e }}</li></ul>
            <p class="pe-risk"><strong>还要补什么</strong>{{ direction.risk.split('，')[0] }}</p>
            <p class="pe-phase__note">选哪条路，始终由你决定。</p>
          </template>
          <template v-else>
            <p class="pe-phase__label">今天，可以先做这一件</p>
            <h2 class="pe-action">{{ task.title.replace('给上一届学长发一条消息，问一句', '给学长发条消息，了解') }}</h2>
            <p class="pe-time"><strong>{{ task.minutes }}</strong><span>分钟<br />完成一个开头</span></p>
            <p class="pe-phase__note">先做一小步，再根据真实行动调整计划。</p>
          </template>
        </article>
      </Transition>
    </div>
    <footer class="pe-story__foot"><span>{{ stage + 1 }} / 3</span><button @click="next">{{ nextLabel }}<UiIcon name="arrow" :size="18" /></button></footer>
  </section>
</template>

<style scoped>
.pe-story { position: relative; width: 100%; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); box-shadow: var(--e-2); }
.pe-story::before { content: ''; position: absolute; inset: -16px 20px 20px -16px; z-index: -1; border: 1px solid var(--c-primary-border); border-radius: var(--r-lg); background: var(--c-primary-weak); transform: rotate(-3deg); }
.pe-story__head { display: flex; justify-content: space-between; gap: 16px; padding: 24px 28px 20px; color: var(--c-text-2); font-size: var(--fs-14); }
.pe-story__sample { color: var(--c-text-3); font-size: var(--fs-12); }
.pe-story__choices { display: flex; gap: 4px; margin: 0 28px; padding-bottom: 18px; border-bottom: 1px solid var(--c-border); }
.pe-story__choices button { display: inline-flex; justify-content: center; align-items: center; gap: 8px; min-height: 42px; flex: 1; padding: 8px; color: var(--c-text-3); font-size: var(--fs-14); border-radius: var(--r-md); transition: background-color 160ms var(--ease-out), color 160ms var(--ease-out); }
.pe-story__choices button[aria-pressed='true'] { color: var(--c-primary); background: var(--c-primary-weak); font-weight: 600; }
.pe-story__choices button:hover { color: var(--c-primary); }
.pe-story__body { display: grid; min-height: 330px; padding: 28px; }
.pe-phase { grid-area: 1 / 1; }
.pe-phase__label { color: var(--c-text-3); font-size: var(--fs-14); margin-bottom: 12px; }
.pe-question { font-size: var(--fs-20); font-weight: 500; line-height: 1.6; margin-bottom: 24px; }
.pe-answer { padding-left: 18px; border-left: 2px solid var(--c-primary); }
.pe-answer > p:last-child { font-size: var(--fs-16); line-height: 1.85; color: var(--c-text); }
.pe-phase__note { font-size: var(--fs-14); color: var(--c-text-3); margin-top: 24px; }
.pe-direction, .pe-action { font-size: var(--fs-20); line-height: 1.6; }
.pe-evidence { display: flex; flex-direction: column; gap: 12px; margin-top: 18px; }
.pe-evidence li { display: flex; align-items: flex-start; gap: 10px; font-size: var(--fs-14); color: var(--c-text-2); }
.pe-evidence svg { flex: none; color: var(--c-primary); margin-top: 4px; }
.pe-risk { font-size: var(--fs-14); color: var(--c-text-2); line-height: 1.8; margin-top: 20px; }
.pe-risk strong { display: block; font-weight: 500; color: var(--c-text); margin-bottom: 4px; }
.pe-time { display: flex; align-items: center; gap: 16px; color: var(--c-primary); margin-top: 24px; }
.pe-time strong { font-size: var(--fs-38); line-height: 1.2; font-weight: 500; font-variant-numeric: tabular-nums; }
.pe-time span { font-size: var(--fs-14); line-height: 1.6; color: var(--c-text-3); }
.pe-story__foot { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 28px 20px; border-top: 1px solid var(--c-border); font-size: var(--fs-12); color: var(--c-text-3); }
.pe-story__foot button { display: inline-flex; align-items: center; gap: 12px; color: var(--c-primary); font-size: var(--fs-14); font-weight: 500; min-height: 40px; }
.pe-story__foot svg { transition: transform 160ms var(--ease-out); }
.pe-story__foot button:hover svg { transform: translateX(3px); }
.pe-phase-enter-active { transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-out); }
.pe-phase-enter-from { opacity: 0; transform: translateY(6px); }
@media (max-width: 760px) {
  .pe-story__head { padding: 20px 22px 16px; }
  .pe-story__choices { margin: 0 22px; }
  .pe-story__body { min-height: 350px; padding: 24px 22px; }
  .pe-story__foot { padding: 14px 22px 18px; }
  .pe-story::before { inset: -10px 14px 14px -8px; transform: rotate(-2deg); }
}
@media (prefers-reduced-motion: reduce) {
  .pe-phase-enter-active { transition: none; }
  .pe-phase-enter-from { transform: none; }
  .pe-story__choices button { transition: none; }
  .pe-story__foot svg { transition: none; }
  .pe-story__foot button:hover svg { transform: none; }
}
</style>
