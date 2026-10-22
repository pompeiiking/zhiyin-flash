<script setup lang="ts">
import { ref } from 'vue'
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal, DropdownMenuContent, DropdownMenuItem } from 'reka-ui'
import UiIcon from './UiIcon.vue'

defineProps<{ label: string; items: { id: string; label: string; disabled?: boolean; danger?: boolean }[]; disabled?: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()
const trigger = ref<HTMLButtonElement | null>(null)
</script>

<template>
  <DropdownMenuRoot :modal="false">
    <DropdownMenuTrigger as-child>
      <button ref="trigger" type="button" class="btn action-menu-trigger" :aria-label="label" :disabled="disabled"><UiIcon name="more" :size="18" /><span>更多</span></button>
    </DropdownMenuTrigger>
    <DropdownMenuPortal :to="trigger?.closest('dialog') ?? undefined">
      <DropdownMenuContent class="action-menu" align="end" :side-offset="6" :collision-padding="12" :aria-label="label">
        <DropdownMenuItem v-for="item in items" :key="item.id" class="action-menu__item" :class="{ 'action-menu__item--danger': item.danger }" :disabled="item.disabled" @select="emit('select', item.id)">{{ item.label }}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<style>
.action-menu-trigger { flex: none; white-space: nowrap; }
.action-menu { z-index: 130; min-width: 184px; max-width: calc(100vw - 24px); max-height: var(--reka-dropdown-menu-content-available-height); overflow-y: auto; padding: 6px; border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-surface); color: var(--c-text); box-shadow: 0 12px 30px -16px rgb(18 36 61 / 28%); }
.action-menu__item { display: flex; align-items: center; min-height: 44px; padding: 8px 12px; border-radius: 6px; font-size: 14px; cursor: pointer; outline: none; }
.action-menu__item[data-highlighted] { background: var(--c-primary-weak); color: var(--c-primary); }
.action-menu__item--danger { color: var(--c-attention-strong); }
.action-menu__item--danger[data-highlighted] { background: var(--c-attention-weak); color: var(--c-attention-strong); }
.action-menu__item[data-disabled] { opacity: .5; cursor: default; }
</style>
