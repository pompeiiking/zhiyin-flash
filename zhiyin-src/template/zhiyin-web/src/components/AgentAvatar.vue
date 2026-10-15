<script setup lang="ts">
import RobotAvatar from './RobotAvatar.vue'
withDefaults(defineProps<{ agent?: string; size?: number; state?: 'idle' | 'thinking' | 'speaking' | 'done'; showName?: boolean }>(), { size: 40, state: 'idle', showName: false })
</script>
<template><RobotAvatar v-bind="$props" /></template>
