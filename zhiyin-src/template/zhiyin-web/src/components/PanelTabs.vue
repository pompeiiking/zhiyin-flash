<script setup lang="ts">
import { TabsRoot, TabsList, TabsTrigger, TabsIndicator, TabsContent } from 'reka-ui'
defineProps<{ modelValue: string; label: string; items: readonly { key: string; label: string; count?: number }[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <TabsRoot :model-value="modelValue" @update:model-value="value => emit('update:modelValue', String(value))" class="exp-tabs">
    <div class="exp-tabs__scroll"><TabsList :aria-label="label" class="exp-tabs__list"><TabsIndicator class="exp-tabs__indicator" /><TabsTrigger v-for="item in items" :key="item.key" :value="item.key" class="exp-tabs__trigger">{{ item.label }}<span v-if="item.count !== undefined">{{ item.count }}</span></TabsTrigger></TabsList></div>
    <TabsContent :key="modelValue" :value="modelValue" class="exp-tabs__panel"><slot /></TabsContent>
  </TabsRoot>
</template>
