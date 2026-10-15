<script setup lang="ts">
import { computed, useId } from 'vue'
import { agentOf, agentVars } from '../lib/agents'
import UiIcon from './UiIcon.vue'
import career from '../assets/robots/career.svg?raw'
import planner from '../assets/robots/planner.svg?raw'
import coach from '../assets/robots/coach.svg?raw'
import scout from '../assets/robots/scout.svg?raw'

const props = withDefaults(defineProps<{ agent?: string; size?: number; state?: 'idle' | 'thinking' | 'speaking' | 'done'; showName?: boolean }>(), { size: 40, state: 'idle', showName: false })
const identity = computed(() => agentOf(props.agent))
const neutral = computed(() => ['me', 'system'].includes(identity.value.key))
const uid = useId().replace(/[^a-z0-9_-]/gi, '')
const stateLabel = { idle: '待命', thinking: '思考中', speaking: '正在回复', done: '已完成' }
// The additional collection role remains a distinct assistant instead of sharing
// another role's face or silently removing an identity registered by the API.
const collection = career.replace('width="182" height="146" rx="31"', 'width="182" height="146" rx="53"').replaceAll('#8ecbff', '#bed2ec').replace('M160 82V48', 'M160 82V56').replace('cy="43" r="11"', 'cy="51" r="8"').replace('cy="40" r="3"', 'cy="49" r="2"')
const art = computed(() => {
  const source = ({ career_advisor: career, path_planner: planner, companion_coach: coach, info_scout: scout, profile_analyst: collection } as Record<string, string>)[identity.value.key] ?? collection
  // Every rendered instance owns its SVG paint servers. Part names are data
  // attributes, so the LED glow duplicate never introduces duplicate DOM ids.
  return source.replace(/<title[^>]*>.*?<\/title>/s, '').replace(/\srole="img"|\saria-labelledby="[^"]*"/g, '')
    .replace('viewBox="0 0 320 300"', 'viewBox="26 24 268 240" aria-hidden="true" focusable="false"')
    .replace(/id="([^"]+)"/g, (_, key: string) => ['shell', 'edge', 'screen', 'metal', 'shadow', 'led'].includes(key) ? `id="${uid}-${key}"` : `data-part="${key}"`)
    .replace(/url\(#([^)]+)\)/g, (_, key: string) => `url(#${uid}-${key})`)
})
const style = computed(() => ({ width: `${props.size}px`, height: `${props.size}px`, '--robot-period': agentVars(props.agent).period, '--robot-shift': agentVars(props.agent).shift }))
</script>
<template>
  <span class="ag robot-avatar" :class="['robot-avatar--' + identity.key, 'robot-avatar--' + state, {'robot-avatar--neutral': neutral}]" :style="style" :data-agent="identity.key" :data-state="state" role="img" :aria-label="identity.name + ' · ' + stateLabel[state]" :title="identity.name + ' · ' + identity.role">
    <UiIcon v-if="neutral" :name="identity.key === 'me' ? 'profile' : 'apps'" :size="Math.max(18, size * .55)" />
    <span v-else class="robot-art" aria-hidden="true" v-html="art" />
    <span v-if="!neutral && state === 'speaking'" class="robot-signal" aria-hidden="true"><i/><i/><i/></span>
    <span v-if="showName" class="robot-name">{{ identity.name }}</span>
  </span>
</template>
<style scoped>
.robot-avatar { position: relative; display: inline-flex; flex: none; align-items: center; justify-content: center; vertical-align: middle; line-height: 1; isolation: isolate; }
.robot-art { display: block; width: 100%; height: 100%; }
.robot-art :deep(svg) { display: block; width: 100%; height: 100%; overflow: visible; }
.robot-art :deep([data-part='eyes']) { transform-box: fill-box; transform-origin: center; animation: robot-blink calc(5.6s + var(--robot-period)) var(--robot-shift) infinite; }
.robot-avatar--thinking .robot-art :deep([data-part='eyes']) { animation: robot-consider 1.8s ease-in-out infinite; }
.robot-avatar--thinking .robot-art :deep([data-part='antenna']) { transform-box: fill-box; transform-origin: bottom; animation: robot-antenna 1.6s ease-in-out infinite; }
.robot-avatar--speaking .robot-art :deep([data-part='mouth']) { transform-box: fill-box; transform-origin: center; animation: robot-speak .42s ease-in-out infinite alternate; }
.robot-avatar--done .robot-art :deep([data-part='head']) { transform-box: fill-box; transform-origin: 50% 85%; animation: robot-nod .65s ease-out 1; }
.robot-avatar--done .robot-art :deep([data-part='eyes']) { animation: none; }
.robot-avatar--neutral { border-radius: 10px; color: var(--c-text-3); background: var(--c-surface-3); }
.robot-signal { position: absolute; right: 1px; bottom: 18%; display: flex; gap: 2px; align-items: center; height: 12px; color: var(--c-primary); }
.robot-signal i { display: block; width: 2px; height: 8px; background: currentColor; border-radius: 1px; animation: robot-sound .6s ease-in-out infinite alternate; }
.robot-signal i:nth-child(2) { height: 12px; animation-delay: -.2s; }
.robot-signal i:nth-child(3) { animation-delay: -.4s; }
.robot-name { position: absolute; top: calc(100% + 6px); left: 50%; transform: translateX(-50%); font-size: 12px; white-space: nowrap; color: var(--c-text-2); }
@keyframes robot-blink { 0%,42%,46%,100% { transform: scaleY(1); } 44% { transform: scaleY(.12); } }
@keyframes robot-consider { 0%,100% { transform: translateX(-3px); } 50% { transform: translateX(3px) translateY(-2px); } }
@keyframes robot-antenna { 0%,100% { transform: rotate(-3deg); } 50% { transform: rotate(3deg); } }
@keyframes robot-speak { from { transform: scale(1,.75); } to { transform: scale(1.15,2.2); } }
@keyframes robot-nod { 0%,100% { transform: rotate(0); } 45% { transform: rotate(5deg) translateY(3px); } }
@keyframes robot-sound { to { transform: scaleY(.35); } }
@media (prefers-reduced-motion: reduce) { .robot-art :deep(*),.robot-signal i { animation: none !important; } }
</style>
