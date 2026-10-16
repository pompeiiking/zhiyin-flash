<script setup lang="ts">
import DetailPopover from './DetailPopover.vue'
defineProps<{title:string;reason:string}>()
</script>
<template><DetailPopover :title="title" :label="title+'：查看待支持原因'" side="right"><template #trigger>{{title}} · 待支持</template><p>{{reason}}</p><p class="ws-muted">该功能保留在补齐清单中，目前不会生成模拟结果。</p><slot/></DetailPopover></template>
