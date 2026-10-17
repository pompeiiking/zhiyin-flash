<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { PopoverClose, PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import UiIcon from './UiIcon.vue'
import { vScrollFade } from '../lib/scroll-fade'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  modelValue?: boolean
  title: string
  label?: string
  side?: 'top' | 'bottom' | 'left' | 'right'
  align?: 'start' | 'center' | 'end'
  size?: 'normal' | 'wide'
}>(), { modelValue: undefined, side: 'bottom', align: 'end', size: 'normal' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const localOpen = ref(false)
const open = computed({
  get: () => props.modelValue ?? localOpen.value,
  set: value => { localOpen.value = value; emit('update:modelValue', value) },
})
const id = useId()
const trigger = ref<HTMLButtonElement | null>(null)
const portalTarget = computed(() => trigger.value?.closest('dialog') ?? undefined)
</script>

<template>
  <PopoverRoot v-model:open="open" :modal="false">
    <PopoverTrigger as-child>
      <button
        ref="trigger"
        v-bind="$attrs"
        type="button"
        class="anchored-card__trigger"
        :aria-label="label || title"
        :aria-expanded="open"
        :aria-controls="open ? id : undefined"
        aria-haspopup="dialog"
      >
        <slot name="trigger" />
      </button>
    </PopoverTrigger>
    <PopoverPortal :to="portalTarget">
      <PopoverContent
        :id="id"
        class="anchored-card"
        :class="`anchored-card--${size}`"
        :side="side"
        :align="align"
        :side-offset="10"
        :collision-padding="12"
        :aria-label="title"
      >
        <header class="anchored-card__header">
          <h2>{{ title }}</h2>
          <PopoverClose class="anchored-card__close" :aria-label="`关闭${title}`"><UiIcon name="close" :size="17" /></PopoverClose>
        </header>
        <div v-scroll-fade class="anchored-card__body"><slot /></div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
.anchored-card__trigger { font:inherit; }
.anchored-card { box-sizing:border-box; z-index:120; display:flex; flex-direction:column; width:min(360px,calc(100vw - 24px)); max-height:min(680px,calc(100dvh - 92px)); overflow:hidden; border:1px solid color-mix(in srgb,var(--c-primary) 12%,var(--c-border)); border-radius:18px; background:var(--c-surface); color:var(--c-text); box-shadow:0 20px 54px rgb(18 36 61 / 18%),0 3px 12px rgb(18 36 61 / 8%); transform-origin:var(--reka-popover-content-transform-origin); animation:anchored-card-in .16s ease-out; }
.anchored-card--wide { width:min(620px,calc(100vw - 24px)); }
.anchored-card__header { display:flex; align-items:center; justify-content:space-between; min-height:56px; padding:8px 10px 8px 18px; border-bottom:1px solid var(--c-border); }
.anchored-card__header h2 { margin:0; font-size:15px; font-weight:600; letter-spacing:.01em; }
.anchored-card__close { display:grid; place-items:center; width:44px; height:44px; border:0; border-radius:12px; background:transparent; color:var(--c-text-2); cursor:pointer; }
.anchored-card__close:hover { background:var(--c-surface-2); color:var(--c-text); }
.anchored-card__body { min-height:0; overflow:auto; padding:14px 18px 18px; }
@keyframes anchored-card-in { from { opacity:0; transform:scale(.97) translateY(-4px); } }
@media (max-width:767px) {
  .anchored-card,.anchored-card--wide { width:min(460px,calc(100vw - 20px)); max-height:calc(100dvh - 112px); border-radius:17px; }
  .anchored-card__body { padding:12px 14px 16px; }
}
@media (prefers-reduced-motion:reduce) { .anchored-card { animation:none; } }
</style>
