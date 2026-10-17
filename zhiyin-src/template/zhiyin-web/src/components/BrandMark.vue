<script setup lang="ts">
import crest from '../assets/brand/hbu-crest.png'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
</script>

<template>
  <span class="brand-mark" :class="{ 'brand-mark--compact': compact }">
    <span class="brand-mark__crest" aria-hidden="true">
      <img :src="crest" alt="" />
    </span>
    <span v-if="!compact" class="brand-mark__lockup">
      <strong class="brand-mark__name">职引</strong>
      <span class="brand-mark__rule" aria-hidden="true"><i /></span>
    </span>
  </span>
</template>

<style scoped>
.brand-mark { display:inline-flex; align-items:center; gap:10px; min-width:0; }
.brand-mark__crest { display:grid; place-items:center; width:39px; height:39px; flex:none; }
.brand-mark__crest img { width:38px; height:38px; object-fit:contain; }
.brand-mark__lockup { display:grid; gap:6px; min-width:0; }
.brand-mark__name { color:var(--c-primary); font-family:'FZLanTingHeiS-DB-GB','FZLanTingHeiS-B-GB','Source Han Sans SC','Microsoft YaHei UI',sans-serif; font-size:21px; font-weight:600; letter-spacing:.09em; line-height:.9; white-space:nowrap; }
.brand-mark__rule { display:flex; align-items:center; width:39px; height:3px; border-radius:3px; background:color-mix(in srgb,var(--c-primary) 20%,transparent); overflow:hidden; }
.brand-mark__rule i { display:block; width:23px; height:100%; border-radius:inherit; background:var(--c-primary); }
.brand-mark--compact { gap:0; }
.brand-mark--compact .brand-mark__crest { width:35px; height:35px; }
.brand-mark--compact .brand-mark__crest img { width:34px; height:34px; }
@media (max-width: 767px) {
  .brand-mark { gap:7px; }
  .brand-mark__crest { width:34px; height:34px; }
  .brand-mark__crest img { width:33px; height:33px; }
  .brand-mark__lockup { gap:4px; }
  .brand-mark__name { font-size:19px; }
  .brand-mark__rule { width:34px; }
  .brand-mark__rule i { width:20px; }
}
</style>
