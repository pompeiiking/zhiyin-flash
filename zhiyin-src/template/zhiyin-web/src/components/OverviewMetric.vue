<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
defineProps<{ label: string }>()
</script>
<template><DetailPopover :title="label" :label="label + '，查看说明'" class="overview-metric"><template #trigger><span class="overview-metric__label">{{ label }}</span><span class="overview-metric__value"><slot name="value" /></span></template><slot /></DetailPopover></template>
