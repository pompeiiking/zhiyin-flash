<script setup lang="ts">
import { useRoute } from 'vue-router'
const route=useRoute()
</script>
<template><nav class="ws-subnav" aria-label="行动计划视图"><RouterLink to="/home" :aria-current="route.path==='/home'?'page':undefined">今日行动</RouterLink><RouterLink to="/plan" :aria-current="route.path==='/plan'?'page':undefined">阶段计划</RouterLink></nav></template>
