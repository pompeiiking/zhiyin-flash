<script setup lang="ts">
import crest from '../assets/brand/hbu-crest.png'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
</script>

<template>
  <span class="brand-mark" :class="{ 'brand-mark--compact': compact }">
    <img :src="crest" alt="" aria-hidden="true" />
    <span v-if="!compact" class="brand-mark__name">职引</span>
  </span>
</template>

<style scoped>
.brand-mark { display:inline-flex; align-items:center; gap:10px; min-width:0; }
.brand-mark img { width:36px; height:36px; object-fit:contain; flex:none; }
.brand-mark__name { color:var(--c-text); font-size:18px; font-weight:650; letter-spacing:.02em; line-height:1; white-space:nowrap; }
.brand-mark--compact img { width:30px; height:30px; }
@media (max-width: 767px) {
  .brand-mark { gap:7px; }
  .brand-mark img { width:30px; height:30px; }
  .brand-mark__name { font-size:16px; }
}
</style>
