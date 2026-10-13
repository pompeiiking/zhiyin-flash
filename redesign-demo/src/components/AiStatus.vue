<script setup lang="ts">
defineProps<{ busy: boolean; error: string; progress: string }>()
defineEmits<{ cancel: []; retry: [] }>()
</script>
<template>
  <div v-if="busy" class="inline-status" role="status"><span>{{ progress }}</span><button class="ws-text-button" @click="$emit('cancel')">停止生成</button></div>
  <div v-else-if="error" class="inline-status inline-status--error" role="alert"><span>{{ error }}</span><button class="btn" @click="$emit('retry')">重试</button></div>
</template>
