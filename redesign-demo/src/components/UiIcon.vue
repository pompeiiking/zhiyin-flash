<script setup lang="ts">
import type { Component } from 'vue'
import { PhChatCircleDots, PhList, PhListChecks, PhUserCircle, PhFileText, PhClockCounterClockwise, PhArrowRight, PhArrowLeft, PhCaretDown, PhX, PhCheck, PhPlus, PhDotsThree, PhMagnifyingGlass, PhBell, PhInfo, PhCalendarBlank, PhCompass, PhNotePencil, PhPaperclip, PhUploadSimple, PhGraduationCap, PhTrash, PhSquaresFour, PhShieldCheck, PhMapTrifold, PhCopy, PhArrowDown, PhSidebarSimple, PhPath, PhTrophy } from '@phosphor-icons/vue'
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const icons: Record<string, Component> = {
  chat: PhChatCircleDots, action: PhListChecks, profile: PhUserCircle, report: PhFileText, review: PhClockCounterClockwise,
  arrow: PhArrowRight, back: PhArrowLeft, chevron: PhCaretDown, close: PhX, check: PhCheck, plus: PhPlus,
  more: PhDotsThree, search: PhMagnifyingGlass, bell: PhBell, info: PhInfo, calendar: PhCalendarBlank,
  directions: PhMapTrifold, compass: PhCompass, notes: PhNotePencil, attachment: PhPaperclip, upload: PhUploadSimple,
  academic: PhGraduationCap, trash: PhTrash, apps: PhSquaresFour, shield: PhShieldCheck, copy: PhCopy, down: PhArrowDown, sidebar: PhSidebarSimple,
  path: PhPath, trophy: PhTrophy, menu: PhList, download: PhArrowDown,
}
</script>
<template>
  <component :is="icons[name] || PhArrowRight" :size="size" weight="regular" aria-hidden="true" />
</template>
