<script setup lang="ts">
defineProps<{rows:{label:string;mine:string;latest:string}[];busy?:boolean}>()
defineEmits<{confirm:[]}>()
</script>
<template><section class="form-conflict" aria-label="核对保存冲突"><strong>请核对两边的修改</strong><p>未修改的内容会沿用最新记录。下面是你准备提交的内容，不会自动覆盖。</p><dl><div v-for="row in rows" :key="row.label"><dt>{{row.label}}</dt><dd><span>最新记录</span>{{row.latest}}</dd><dd><span>你的填写</span>{{row.mine}}</dd></div></dl><button type="button" class="btn" :disabled="busy" @click="$emit('confirm')">确认这些修改并保存</button></section></template>
<style scoped>.form-conflict{padding:16px;border:1px solid var(--c-border);border-radius:12px;margin-top:16px;background:var(--field-bg)}.form-conflict p,.form-conflict dd span{font-size:12px;color:var(--c-text-3)}.form-conflict dl{display:grid;gap:12px}.form-conflict dd{margin:4px 0;overflow-wrap:anywhere}.form-conflict dd span{display:inline-block;min-width:72px}.form-conflict dt{font-weight:600}</style>
