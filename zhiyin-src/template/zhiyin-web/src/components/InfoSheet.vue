<script setup lang="ts">
/*
 * 为什么这样写（对照审计 D10 / D11 / 共性问题 2）：
 *
 * D10 的原话是「移动端抽屉不是底部面板」——12 处弹层只有 `--inspector` 一个变体有小屏底部化，
 * 于是 390×844 上「提醒」和「删除确认」占屏形态一模一样（实测 dialog 盒 352×763、y=41、radius 12px，
 * 与桌面同样是居中盒）。根因不是尺寸没调，是**形态没有语义**：
 * 确认/表单 / 抽屉面板 / 大面板 三种意图共用了一个居中盒子。
 * 所以这里把形态提到 props 上（shape），三种形态各自有桌面与小屏两套形状：
 *   dialog → 桌面居中窄盒；小屏仍是居中盒（确认类就该"停在你手指上方"，底部化反而像抽屉）
 *   sheet  → 桌面右侧抽屉；小屏底部面板（滑入、圆角在上、贴底、安全区、可下拉关闭）
 *   panel  → 桌面居中宽盒；小屏全屏（大面板在小屏没有"框"的意义，占地越多越好读）
 *
 * D11 是焦点：关闭后 activeElement 回落到 BODY。原生 <dialog> 只管"打开时把焦点移进来"，
 * 关闭时浏览器只把焦点丢回 body（Chrome 对 showModal 的既有行为），所以**不能依赖原生机制**，
 * 必须打开时显式记住 document.activeElement、关闭时显式还回去。
 *
 * 【2026-10-14 · wave2】`wide` / `inspector` 两个 @deprecated prop 与 `resolvedShape` 已删除。
 * 为什么必须删（两条实测，缺一条都会让删 prop 看起来"还能用"）：
 *   ① `wide` **静默盖过** `shape`：写 `shape="sheet" wide` 时 DOM 拿到的是 `ws-sheet--panel`，
 *      几何实测 800×852 居中 —— 传 shape 的人以为形态改了，其实没改；
 *   ② Vue 对 Boolean prop 的处理是「属性存在即为真」：`:wide="false"` 会渲染成 `wide="false"`
 *      **属性**，属性存在即被当作 true → **想关也关不掉**。
 * 全站 4 个曾经的调用点（AcademicView / IntelView / ProfileInsights / ConversationView）
 * 都已物理删除这两个 prop；删 prop 前 grep 复核这两个 prop 的用法命中数 = 0（见交付说明）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'

type Shape = 'dialog' | 'sheet' | 'panel'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  /** 形态：dialog 确认/表单（居中窄）、sheet 抽屉/面板（桌面右侧、小屏底部）、panel 大面板（桌面宽、小屏全屏） */
  shape?: Shape
  /** 是否允许向下拖拽关闭（只有 sheet / panel 在底部面板形态下生效） */
  draggable?: boolean
  /** 说明文字，挂到 aria-describedby，让读屏先听到"这个弹层是干什么的" */
  description?: string
}>(), {
  shape: 'dialog',
  draggable: true,
  description: '',
})

const emit = defineEmits<{ close: []; opened: [] }>()

const el = ref<HTMLDialogElement | null>(null)
const inner = ref<HTMLElement | null>(null)
const bodyId = `info-sheet-body-${Math.random().toString(36).slice(2, 8)}`

/* 形态只有一个来源：`shape`。旧的 `wide` / `inspector` 与它们组成的优先级链整体删除
   （见文件头两条实测）。删掉这一层不只是清理：它原来是一条**静默覆盖**链，
   留着就等于给"以后有人传了 shape 又被旧 prop 盖掉"留了入口。 */
const resolvedShape = computed<Shape>(() => props.shape)

/* 是否为"小屏底部面板形态"。用 JS 判断只为手势；视觉全在 CSS 媒体查询里，
   这样窗口在 768px 边界来回拖时不会出现"JS 说底部、CSS 说右侧"的错位。 */
const mq = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(max-width: 768px)')
  : null
const narrow = ref(mq ? mq.matches : false)
function onMqChange(e: MediaQueryListEvent) { narrow.value = e.matches }

/* 底部面板：sheet 在小屏、panel 在小屏都贴底；dialog 永远居中（确认类不贴底） */
const bottomForm = computed(() => narrow.value && resolvedShape.value !== 'dialog')

/* ---- 焦点：打开时记住触发元素，关闭时显式还回去（D11） ---- */
let restoreTo: HTMLElement | null = null

function rememberFocus() {
  const active = document.activeElement
  // 已经是 body（例如初次进入页面还没点过任何东西）就不记，免得把焦点"还"给一个没意义的节点
  restoreTo = active instanceof HTMLElement && active !== document.body ? active : null
}

/**
 * 把焦点还给触发元素。
 *
 * 为什么不能只靠"关闭时调一次"：门户登录这条路径的关闭顺序是
 *   按 Esc → 原生 cancel → emit('close') → App 把 signin 参数删掉 → AuthLayer 被 v-if 摘掉
 * 也就是**组件在关闭的微任务之前就被卸载了**，浏览器卸载一个处于 open 状态的 <dialog>
 * 会把焦点丢回 body —— 这正是审计 D11 实测到的现象。
 * 所以：① onBeforeUnmount 里先行处理；② 同步调 focus()，不排下一帧
 * （卸到一半的元素再等一帧，焦点会被卸掉的 dialog 一并带走）；
 * ③ 同步没吃住（被 dialog 的焦点陷阱弹回 body）时，再在微任务里补一次并退到兜底节点。
 */
function focusBack(target: HTMLElement | null) {
  // 触发元素已经不在 DOM 里（例如点完确认后那一行被删掉了）：
  // 退回到"看起来像触发点"的元素，再退到主内容区，**绝不留在 body**
  const fallback = (): HTMLElement | null => document.querySelector<HTMLElement>('[data-sheet-trigger]:not([disabled])')
    ?? document.querySelector<HTMLElement>('main, [role="main"], .ws-page, .pf-main')

  if (target && document.contains(target)) target.focus({ preventScroll: true })
  else fallback()?.focus?.({ preventScroll: true })

  /* 兜底确认：关闭一个 open 的 dialog 时，浏览器有可能在微任务里才把焦点搬回 body，
     所以这里再看一眼——只有在焦点真的丢了（落在 body）时才补，
     否则不要多按一次，免得把用户自己 Tab 走的焦点抢回来。 */
  queueMicrotask(() => {
    if (document.activeElement !== document.body) return
    if (target && document.contains(target)) target.focus({ preventScroll: true })
    else fallback()?.focus?.({ preventScroll: true })
  })
}

function restoreFocus() {
  const target = restoreTo
  // 已经把焦点还过了（例如 onBeforeUnmount 先还了一次，紧接着 props 的 watcher 才跑到）：
  // 这里再"还"一次就会因为触发元素已被清空而落到兜底节点上，把正确的焦点抢走 —— 所以只还一次。
  if (!target) return
  restoreTo = null
  focusBack(target)
}

/* ---- 打开 / 关闭 ---- */
async function sync() {
  await nextTick()
  if (props.open && el.value && !el.value.open) {
    rememberFocus()
    el.value.showModal()
    emit('opened')
  }
  if (!props.open && el.value?.open) {
    el.value.close()
    restoreFocus()
  }
}
watch(() => props.open, sync)
onMounted(() => { mq?.addEventListener('change', onMqChange); sync() })
onBeforeUnmount(() => {
  // 卸载前先还焦点：卸载一个 open 的 dialog 会把焦点丢给 body（D11 的实测路径就是这么来的）
  if (el.value?.open) { el.value.close(); restoreFocus() }
  else if (restoreTo) restoreFocus()
  mq?.removeEventListener('change', onMqChange)
})

/** 原生 dialog 负责真正的关闭动作，但这个 close 事件也要兜住焦点：
 *  用户按 Esc / 点 backdrop 时我们只是 emit('close')，最终关闭由父组件改 prop 触发；
 *  若父组件没改（受控方忽略），焦点也必须已经回去，所以这里再挂一次。 */
function onNativeClose() { restoreFocus() }

/* ---- Tab 环绕：原生 dialog 在 Chrome 已有，但 Firefox/Safari 的历史行为不一致，显式兜一层 ---- */
function trapTab(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !el.value?.open) return
  const targets = [...el.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]',
  )].filter(e => e.getClientRects().length)
  const first = targets[0]
  const last = targets[targets.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

/* ---- 手势：按住把手/头部向下拖即关闭 ----
 * 只在"底部面板形态"上生效，且只从头部起手 —— 主体区是要滚动的，从主体起手会把滚动吃掉。
 * 位移 1:1 跟手（空间关系：面板跟着手指走），超过阈值（面板高度的 28% 或 120px）或甩得够快（>0.6px/ms）就关。
 * 用 rubber band 只保留 25% 位移给出"到头了"的手感，不是装饰，是在说"不能再往下拖了"。 */
const dragY = ref(0)
const dragging = ref(false)
let dragStart = 0
let dragT = 0
const dragOffset = computed(() => (dragging.value ? dragY.value : 0))

function dragEnabled() { return props.draggable && bottomForm.value }

function onDragStart(event: PointerEvent) {
  if (!dragEnabled()) return
  if (event.target instanceof Element && event.target.closest('button,a,input,select,textarea,[role="button"]')) return
  if (event.pointerType === 'mouse' && event.button !== 0) return
  const host = event.currentTarget as HTMLElement
  dragStart = event.clientY
  dragT = event.timeStamp
  dragging.value = true
  dragY.value = 0
  host.setPointerCapture?.(event.pointerId)
}

function onDragMove(event: PointerEvent) {
  if (!dragging.value) return
  const delta = event.clientY - dragStart
  if (delta <= 0) { dragY.value = 0; return }
  const limit = (el.value?.offsetHeight ?? 400) * 0.4
  dragY.value = delta <= limit ? delta : limit + (delta - limit) * 0.25
}

function onDragEnd(event: PointerEvent) {
  if (!dragging.value) return
  const host = event.currentTarget as HTMLElement
  host.releasePointerCapture?.(event.pointerId)
  const height = el.value?.offsetHeight ?? 400
  const fast = dragY.value / Math.max(1, event.timeStamp - dragT) > 0.6
  dragging.value = false
  if (dragY.value > Math.max(120, height * 0.28) || (fast && dragY.value > 40)) {
    dragY.value = 0
    emit('close')
    return
  }
  dragY.value = 0
}
</script>

<template>
  <dialog
    ref="el"
    class="ws-sheet"
    :class="[
      `ws-sheet--${resolvedShape}`,
      { 'is-dragging': dragging },
    ]"
    :aria-label="title"
    :aria-describedby="description ? `${bodyId}-desc` : undefined"
    @keydown="trapTab"
    @cancel.prevent="emit('close')"
    @close="onNativeClose"
    @click="($event.target === el) && emit('close')"
  >
    <div
      ref="inner"
      class="ws-sheet__inner"
      :style="dragOffset ? { transform: `translateY(${dragOffset}px)` } : undefined"
    >
      <!-- 底部面板的把手：既是"可以下拉"的可见提示，也是手势起手区（44px 命中高度） -->
      <div
        v-if="resolvedShape !== 'dialog'"
        class="ws-sheet__grabber"
        aria-hidden="true"
        @pointerdown="onDragStart"
        @pointermove="onDragMove"
        @pointerup="onDragEnd"
        @pointercancel="onDragEnd"
      ><span /></div>
      <header
        class="ws-sheet__head"
        @pointerdown="onDragStart"
        @pointermove="onDragMove"
        @pointerup="onDragEnd"
        @pointercancel="onDragEnd"
      >
        <h2>{{ title }}</h2>
        <button class="ws-icon-button" aria-label="关闭面板" @click="emit('close')"><UiIcon name="close" /></button>
      </header>
      <p v-if="description" :id="`${bodyId}-desc`" class="ws-sheet__desc">{{ description }}</p>
      <div :id="bodyId" class="ws-sheet__body"><slot /></div>
    </div>
  </dialog>
</template>

<style scoped>
/* ===========================================================================
 * 0 · 基础形态：把 workspace.css 的全局 `.ws-sheet` 一族**整体搬进来**（2026-10-14）
 * ---------------------------------------------------------------------------
 * 为什么必须搬（不是顺手清理）：check-classes.mjs 报的 `.ws-sheet__head` 硬撞车只是**症状**。
 * 机制是 scoped 的 `.ws-sheet--x[data-v-*]` 只赢下它自己声明过的属性，而
 * `background` / `box-shadow` / `color` / `::backdrop` **只在全局声明过** ——
 * 所以"删掉全局一族"这一步如果不同时搬，18 个弹层会一起变透明、无遮罩（HANDOFF §6.4 原话）。
 * 搬法：全局那几条原样搬过来，能令牌化的一律走令牌（tokens.css:411-421 本来就是按它们的值定的）。
 * 逐条对应（左 = 改前全局 workspace.css:420-422 / 右 = 这里）：
 *   width: min(540px, calc(100vw - 32px)) → var(--sheet-dialog-w)，同一个 540px
 *   max-height: calc(100dvh - 48px)       → var(--sheet-dialog-max-h)，同一个值
 *   padding: 0 · border: 0 · border-radius: var(--r-lg) · overflow: auto
 *   color: var(--c-text) · background: var(--c-surface) · box-shadow: var(--e-3)
 * 顺序写在三种形态**之前**：base 与 `.ws-sheet--x[data-v-*]` 的特异度相同（0,2,0），
 * 靠"谁更靠后"取胜 —— 与改前（全局 0,1,0 输给 scoped）的逐属性结果一致。
 * ========================================================================= */
.ws-sheet {
  width: min(var(--sheet-dialog-w), calc(100vw - 32px));
  max-height: var(--sheet-dialog-max-h);
  padding: 0;
  border: 0;
  border-radius: var(--r-lg);
  overflow: auto;
  color: var(--c-text);
  background: var(--c-surface);
  box-shadow: var(--e-3);
}

/* 遮罩也只在全局定义过。scoped 里的 ::backdrop 会被编译成 `.ws-sheet[data-v-*]::backdrop`
   （Vue 把 scope 属性插在最后一个非伪元素节点之后），<dialog> 是组件根节点、带得到它。 */
.ws-sheet::backdrop {
  background: var(--overlay-mask);
}

/* ===========================================================================
 * 形态一 · dialog（确认 / 表单）
 * 桌面与移动端都是居中窄盒：确认类需要"手指停一下"，底部化会把它读成抽屉。
 * ========================================================================= */
.ws-sheet--dialog {
  width: min(var(--sheet-dialog-w), calc(100vw - 32px));
  max-height: min(var(--sheet-dialog-max-h), calc(100dvh - 32px));
  padding: 0;
  border: 0;
  border-radius: var(--r-lg);
  overflow: hidden;
}

/* ===========================================================================
 * 形态二 · sheet（抽屉 / 侧面板）
 * 桌面：贴右侧、整高、左圆角；移动端：底部面板（见下方媒体查询）。
 * ========================================================================= */
.ws-sheet--sheet {
  position: fixed;
  inset: 12px 12px 12px auto;
  margin: 0;
  width: min(var(--sheet-drawer-w), calc(100vw - 24px));
  max-width: none;
  height: calc(100dvh - 24px);
  max-height: none;
  padding: 0;
  border: 1px solid var(--c-border);
  border-radius: var(--sheet-radius);
  overflow: hidden;
}
.ws-sheet--sheet .ws-sheet__inner { height: 100%; }

/* ===========================================================================
 * 形态三 · panel（大面板）
 * 桌面宽盒居中；小屏全屏。
 * ========================================================================= */
.ws-sheet--panel {
  width: min(var(--sheet-panel-w), calc(100vw - 32px));
  max-height: min(var(--sheet-panel-max-h), calc(100dvh - 32px));
  padding: 0;
  border: 0;
  border-radius: var(--r-lg);
  overflow: hidden;
}

/* ---- 内部结构：头固定、体可滚（滚动交给内容层，弹层自己不再滚） ----
 * 【2026-10-14】头与体的版式原来也只在全局（workspace.css:424-427），那正是门禁报的硬撞车
 * （全局那条含 display / gap / padding，会从 scoped 的缝里漏进组件）。声明原样搬过来。 */
.ws-sheet__inner {
  display: flex;
  flex-direction: column;
  max-height: inherit;
  min-height: 0;
}
.ws-sheet--sheet .ws-sheet__inner { max-height: 100%; }
/* Panel height is content-driven: 100% cannot resolve against an auto-height dialog.
   Inherit its viewport limit so the body scrolls and actions remain reachable. */
.ws-sheet--panel .ws-sheet__inner { max-height: inherit; }
.ws-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px 18px;
  flex: none;
}
.ws-sheet__head h2 { font-size: var(--fs-20); }
.ws-sheet__desc { flex: none; padding: 0 28px 4px; margin: 0; font-size: var(--fs-14); color: var(--c-text-3); }
.ws-sheet__body {
  padding: 8px 28px 32px;
  overflow-y: auto;
  overscroll-behavior: contain;
  min-height: 0;
}
/* `.ws-tabs` 是**插槽内容**（它的类名挂在调用方组件上，带的是调用方的 scope 属性），
   所以这一条必须写 :deep() —— 写成 `.ws-sheet__body .ws-tabs` 会编译成
   `.ws-sheet__body .ws-tabs[data-v-*]`，插槽内容拿不到那个属性，规则会静默失效
   （实测：学术页导入面板里 .ws-tabs 的 computed margin-bottom 必须是 24px）。 */
.ws-sheet__body :deep(.ws-tabs) { margin-bottom: 24px; }

/* 全局那一族的 767px 覆盖（原 workspace.css:732-733，它落在 max-width:767px 那一档里）。
   断点保持 767 不合并到本组件的 768：两档并存是改前的实际行为，搬动不顺手改口径。 */
@media (max-width: 767px) {
  .ws-sheet__head { padding: 20px; }
  .ws-sheet__body { padding: 0 20px 24px; }
}

/* 把手：只在非 dialog 形态出现；桌面鼠标下不显示（桌面用不到下拉） */
.ws-sheet__grabber {
  display: none;
  flex: none;
  height: 22px;
  align-items: center;
  justify-content: center;
  cursor: grab;
  touch-action: none;
}
.ws-sheet__grabber > span {
  width: 36px;
  height: var(--sheet-grabber-h);
  border-radius: var(--r-pill);
  background: var(--sheet-grabber);
}

/* 拖拽中：跟手期间不要过渡（有过渡就会"追"手指），也不要选中文字 */
.ws-sheet.is-dragging { user-select: none; }
.ws-sheet.is-dragging .ws-sheet__inner { transition: none; }

/* ---- 入场动效：只有"空间关系变化"才动 ----
 * sheet/panel 在小屏是底部面板 → 从底部滑入（说明"它从下面来，可以推回去"）；
 * sheet 在桌面是侧抽屉 → 从右侧滑入；dialog 只是浮起来（位移 10px，无空间含义，只做落点）。
 * 全部包在 prefers-reduced-motion: no-preference 里 —— 降级后是"直接出现"，不是隐藏。 */
@media (prefers-reduced-motion: no-preference) {
  .ws-sheet--dialog[open] { animation: sheet-rise var(--dur-2) var(--ease-out); }
  .ws-sheet--panel[open] { animation: sheet-rise var(--dur-2) var(--ease-out); }
  .ws-sheet--sheet[open] { animation: sheet-slide-in var(--dur-3) var(--ease-drawer); }
  .ws-sheet--sheet .ws-sheet__inner,
  .ws-sheet--panel .ws-sheet__inner { transition: transform var(--dur-2) var(--ease-out); }
}
@keyframes sheet-rise { from { opacity: .6; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes sheet-slide-in { from { opacity: .5; transform: translateX(18px); } to { opacity: 1; transform: none; } }

/* ===========================================================================
 * 移动端（768 及以下）· 底部面板
 * 圆角只在上缘、贴底不留缝、把手可见、安全区用 env(safe-area-inset-bottom) 垫在内容之后。
 * ========================================================================= */
@media (max-width: 768px) {
  .ws-sheet--sheet,
  .ws-sheet--panel {
    position: fixed;
    inset: auto 0 0;
    margin: 0;
    width: 100%;
    max-width: none;
    height: auto;
    border: 0;
    border-radius: var(--sheet-radius-mobile);
    overflow: hidden;
    max-height: var(--sheet-mobile-max-h);
  }
  .ws-sheet--panel { max-height: 100dvh; }
  .ws-sheet--sheet .ws-sheet__inner,
  .ws-sheet--panel .ws-sheet__inner { max-height: var(--sheet-mobile-max-h); }
  .ws-sheet--panel .ws-sheet__inner { max-height: calc(100dvh - env(safe-area-inset-top)); }

  /* 安全区：垫在可滚动内容的末尾而不是弹层外框上，
     这样"最后一屏内容"不会压进 Home 指示条，而滚动区高度也仍然正确。 */
  .ws-sheet--sheet .ws-sheet__body { padding-bottom: calc(var(--sp-6) + env(safe-area-inset-bottom)); }
  .ws-sheet--panel { padding-top: env(safe-area-inset-top); }

  .ws-sheet__grabber { display: flex; }
  .ws-sheet__head { cursor: grab; touch-action: none; }

  /* 底部面板从底部滑入（含 dialog 之外的两种形态） */
  @media (prefers-reduced-motion: no-preference) {
    .ws-sheet--sheet[open],
    .ws-sheet--panel[open] { animation: sheet-slide-up var(--dur-3) var(--ease-drawer); }
  }
}
@keyframes sheet-slide-up { from { opacity: .6; transform: translateY(100%); } to { opacity: 1; transform: none; } }
</style>
