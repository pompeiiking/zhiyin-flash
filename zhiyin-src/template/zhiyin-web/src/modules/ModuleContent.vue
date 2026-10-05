<script setup lang="ts">
import { computed, onErrorCaptured, ref, watch } from 'vue'
import { moduleComponent } from './registry'
import type { ModuleView, ModuleResult } from './client'
const props = defineProps<{ module: ModuleView; result: ModuleResult; slotName?: 'card' | 'detail' | 'conversation'; readonly?: boolean; busy?: boolean }>()
const emit = defineEmits<{ action: [name: string, payload: Record<string, unknown>] }>()
const fault = ref('')
const declared = computed(() => props.module.manifest[props.slotName || 'card'])
const view = computed(() => moduleComponent(props.module, props.slotName || 'card'))
watch(() => [props.module.manifest.id, props.result], () => { fault.value = '' })
onErrorCaptured((error) => { fault.value = `组件暂时无法显示：${error.message}`; return false })
</script>
<template>
  <div class="module-content-surface" :data-module-surface="slotName || 'card'">
    <p v-if="fault" role="alert">{{ fault }}</p>
    <component v-else-if="view" :is="view" :result="result" :readonly="readonly" :busy="busy" @action="(name: string, payload: Record<string, unknown>) => emit('action', name, payload)" />
    <p v-else-if="declared" role="alert">当前构建缺少这个模块的组件。</p>
  </div>
</template>
<style scoped>
.module-content-surface { display:contents; }
</style>
