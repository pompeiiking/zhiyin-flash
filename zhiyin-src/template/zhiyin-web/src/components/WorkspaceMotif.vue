<script setup lang="ts">
import { useId } from 'vue'
withDefaults(defineProps<{ kind?: 'chat' | 'notes' | 'intel' }>(), { kind: 'chat' })
const patternId = 'motif-grid-' + useId()
</script>
<template>
  <svg class="exp-motif" viewBox="0 0 240 160" aria-hidden="true" fill="none">
    <defs><pattern :id="patternId" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="currentColor" opacity=".18" /></pattern></defs>
    <rect x="0" y="0" width="240" height="160" :fill="'url(#' + patternId + ')'" />
    <path class="exp-motif__path" d="M45 108H83C98 108 104 95 104 81V67C104 54 113 45 126 45H195" stroke="currentColor" stroke-width="1.5" />
    <path d="M104 81H149C161 81 170 90 170 102V112H195" stroke="currentColor" stroke-opacity=".25" stroke-width="1.5" />
    <rect x="25" y="88" width="40" height="40" rx="12" fill="var(--c-surface)" stroke="currentColor" stroke-opacity=".3" />
    <path v-if="kind === 'chat'" d="M35 100h20v13H44l-6 4v-4h-3z" stroke="currentColor" stroke-linejoin="round" />
    <path v-else-if="kind === 'notes'" d="M37 98h16v21H37zM41 104h8m-8 5h8m-8 5h5" stroke="currentColor" />
    <path v-else d="M45 98v20m-10-10h20M38 101l14 14m-14 0 14-14" stroke="currentColor" />
    <circle cx="195" cy="45" r="19" fill="var(--c-primary-weak)" /><path d="m188 45 5 5 9-10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="195" cy="112" r="12" fill="var(--c-surface)" stroke="currentColor" stroke-opacity=".3" /><circle cx="195" cy="112" r="3" fill="currentColor" opacity=".4" />
  </svg>
</template>
