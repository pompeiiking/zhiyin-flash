<script setup lang="ts">
import crest from '../assets/brand/hbu-crest.png'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
</script>

<template>
  <span class="brand-mark" :class="{ 'brand-mark--compact': compact }">
    <span class="brand-mark__crest" aria-hidden="true">
      <img :src="crest" alt="" />
      <span class="brand-mark__pulse" />
    </span>
    <span v-if="!compact" class="brand-mark__lockup">
      <strong class="brand-mark__name">职引</strong>
      <span class="brand-mark__meta">HBU CAREER</span>
    </span>
  </span>
</template>

<style scoped>
.brand-mark { display:inline-flex; align-items:center; gap:11px; min-width:0; }
.brand-mark__crest { position:relative; display:grid; place-items:center; width:42px; height:42px; flex:none; border:1px solid var(--c-border); border-radius:13px; background:var(--gray-0); box-shadow:var(--e-1); }
.brand-mark__crest img { width:34px; height:34px; object-fit:contain; }
.brand-mark__pulse { position:absolute; right:-2px; bottom:5px; width:8px; height:8px; border:2px solid var(--gray-0); border-radius:50%; background:var(--c-primary); }
.brand-mark__lockup { display:grid; gap:4px; min-width:0; }
.brand-mark__name { color:var(--c-text); font-family:var(--font-title); font-size:20px; font-weight:700; letter-spacing:.01em; line-height:1; white-space:nowrap; }
.brand-mark__meta { color:var(--c-primary); font-size:9px; font-weight:700; letter-spacing:.12em; line-height:1; white-space:nowrap; }
.brand-mark--compact { gap:0; }
.brand-mark--compact .brand-mark__crest { width:36px; height:36px; border-radius:11px; }
.brand-mark--compact .brand-mark__crest img { width:29px; height:29px; }
@media (max-width: 767px) {
  .brand-mark { gap:7px; }
  .brand-mark__crest { width:36px; height:36px; border:0; border-radius:10px; box-shadow:none; }
  .brand-mark__crest img { width:30px; height:30px; }
  .brand-mark__pulse { right:0; bottom:3px; width:7px; height:7px; }
  .brand-mark__lockup { gap:2px; }
  .brand-mark__name { font-size:17px; }
  .brand-mark__meta { display:none; }
}
</style>
