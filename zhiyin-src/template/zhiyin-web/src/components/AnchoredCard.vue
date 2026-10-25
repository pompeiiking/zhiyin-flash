<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
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
/**
 * 锚点不可见时（例如桌面侧栏展开时头部按钮被隐藏，而侧栏"管理"链接仍会
 * 通过 ?history=1 把卡片打开），弹层会锚到 (0,0) 顶在屏幕左上角。
 * 此时回退为**居中弹窗**：同样的内容，独立的关闭按钮与遮罩。
 */
const anchorHidden = ref(false)
// immediate：?history=1 这类入口在挂载前就把 open 置真，挂载后也要补一次检测。
watch(open, value => {
  if (!value) { anchorHidden.value = false; return }
  void nextTick(() => {
    const rect = trigger.value?.getBoundingClientRect()
    anchorHidden.value = !rect || rect.width === 0 || rect.height === 0
  })
}, { immediate: true })
function close() { open.value = false }
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
        :aria-expanded="open && !anchorHidden"
        :aria-controls="open && !anchorHidden ? id : undefined"
        aria-haspopup="dialog"
      >
        <slot name="trigger" />
      </button>
    </PopoverTrigger>
    <PopoverPortal :to="portalTarget">
      <PopoverContent
        v-if="!anchorHidden"
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
  <Teleport to="body">
    <div v-if="open && anchorHidden" class="anchored-card-backdrop" @click="close()">
      <div
        :id="id"
        class="anchored-card anchored-card--modal"
        :class="`anchored-card--${size}`"
        role="dialog"
        :aria-label="title"
        @click.stop
      >
        <header class="anchored-card__header">
          <h2>{{ title }}</h2>
          <button type="button" class="anchored-card__close" :aria-label="`关闭${title}`" @click="close()"><UiIcon name="close" :size="17" /></button>
        </header>
        <div v-scroll-fade class="anchored-card__body"><slot /></div>
      </div>
    </div>
  </Teleport>
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
.anchored-card-backdrop { position:fixed; inset:0; z-index:119; background:var(--overlay-mask); }
.anchored-card--modal { position:fixed; inset:0; margin:auto; height:max-content; max-height:min(680px,calc(100dvh - 48px)); }
@keyframes anchored-card-in { from { opacity:0; transform:scale(.97) translateY(-4px); } }
@media (max-width:767px) {
  .anchored-card,.anchored-card--wide { width:min(460px,calc(100vw - 20px)); max-height:calc(100dvh - 112px); border-radius:17px; }
  .anchored-card__body { padding:12px 14px 16px; }
}
@media (prefers-reduced-motion:reduce) { .anchored-card { animation:none; } }
</style>
