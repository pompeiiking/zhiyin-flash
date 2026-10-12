<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  chat: 'M5 5h14v10H9l-4 4V5Z M9 9h6 M9 12h3',
  action: 'M9 6h11 M9 12h11 M9 18h11 M3 6l1 1 2-2 M3 12l1 1 2-2 M3 18l1 1 2-2',
  profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M4 21v-2a8 8 0 0 1 16 0v2',
  report: 'M6 3h9l4 4v14H6V3Z M14 3v5h5 M9 12h7 M9 16h7',
  review: 'M4 8a8 8 0 1 1-1 7 M4 3v5h5 M12 8v5l3 2',
  arrow: 'M5 12h14 M14 7l5 5-5 5',
  back: 'M19 12H5 M10 7l-5 5 5 5',
  chevron: 'M7 10l5 5 5-5',
  close: 'M6 6l12 12 M18 6 6 18',
  check: 'M5 12l4 4L19 6',
  plus: 'M12 5v14 M5 12h14',
  more: 'M5 12h.01 M12 12h.01 M19 12h.01',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z M15 15l6 6',
  bell: 'M6 9a6 6 0 0 1 12 0v7l2 2H4l2-2V9Z M10 21h4',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z M12 10v6 M12 6h.01',
  calendar: 'M4 5h16v16H4V5Z M8 3v4 M16 3v4 M4 10h16',
}
</script>
<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path :d="paths[name] || paths.arrow" />
  </svg>
</template>
