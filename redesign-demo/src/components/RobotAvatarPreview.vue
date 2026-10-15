<script setup lang="ts">
import { ref } from 'vue'
import AgentAvatar from './AgentAvatar.vue'
const state = ref<'idle' | 'thinking' | 'speaking' | 'done'>('idle')
const states = [{key:'idle',label:'待命'},{key:'thinking',label:'思考'},{key:'speaking',label:'回复'},{key:'done',label:'完成'}] as const
const robots = [{key:'career_advisor',name:'职业分析顾问'},{key:'path_planner',name:'行动规划顾问'},{key:'companion_coach',name:'行动支持顾问'},{key:'info_scout',name:'就业资讯顾问'}]
</script>
<template>
  <section class="ws-paper robot-preview"><div class="ws-section-head"><h2>对话机器人</h2><div class="c2-lensbar" role="group" aria-label="机器人状态"><button v-for="item in states" :key="item.key" :aria-pressed="state === item.key" @click="state = item.key">{{ item.label }}</button></div></div><div class="robot-preview__figures"><figure v-for="robot in robots" :key="robot.key"><AgentAvatar :agent="robot.key" :size="96" :state="state"/><figcaption>{{ robot.name }}</figcaption></figure></div><p class="ws-muted">实际对话由处理状态驱动。系统开启减少动态效果后，头像保持静态。</p></section>
</template>
<style scoped>
.robot-preview__figures { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 24px; padding-block: 32px; }
.robot-preview__figures figure { display: flex; align-items: center; flex-direction: column; gap: 14px; margin: 0; }
.robot-preview__figures figcaption { font-size: 14px; color: var(--c-text-2); }
@media(max-width:767px) { .robot-preview__figures { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 32px 16px; } }
</style>
