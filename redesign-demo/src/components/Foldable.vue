<script setup lang="ts">
/*
 * 为什么要把四种折叠（.ws-fold / .ws-context / .plan-stage / .ws-task__details）收成一个组件：
 *
 * 审计「折叠失控」给的量化是——4 种折叠组件、深度 1~3 层；`/plan` 单页 21 处折叠、
 * 20 处默认收起、嵌套 3 层（RoadmapView 的阶段里塞 ws-context，ws-context 里再塞 ws-fold）。
 * 四处 `<details>` 各写各的 summary 高度、箭头旋转、内距，于是"哪一层更重要"在视觉上根本分不出来。
 *
 * 这个组件做四件事：
 *   1. 用 variant 把"密度"变成显式选择（inline / section / group），而不是各页抄一段 CSS；
 *   2. 用 provide/inject 数层级，**嵌套即开发期警告**（PLAN §4.4：一页最多 1 层折叠）；
 *   3. 给主信息留一条明路：`static` 形态——标题是普通文字、内容永远可见。
 *      审计点名的反例是"溯源做成一个折叠的来源"（DESIGN-LANGUAGE §5）与
 *      "报告页把 46/50 同刻度压进最后一层折叠"（AssessmentView.vue:88）：
 *      这些内容不该被折叠，迁移时用 static 表达"它始终可见"，而不是忘记加折叠。
 *   4. 受控 / 非受控都行：绑 v-model（或 modelValue）就是受控，不绑就自己管。
 *      旧写法 `:open="i===0"`（非受控默认开）与 `:open="printing"`（外部强制开）
 *      分别对应 `defaultOpen` 与 `forceOpen`。
 */
import { computed, inject, nextTick, onMounted, provide, ref, watch } from 'vue'
import UiIcon from './UiIcon.vue'

const props = withDefaults(defineProps<{
  title: string
  /** 计数徽标，例如「已完成 · 3 条」。审计里四类折叠有三类都带计数，所以做成内建能力 */
  count?: string | number | null
  /** 非受控初始开合 */
  defaultOpen?: boolean
  /** 受控（v-model）；不传即非受控 */
  modelValue?: boolean
  /** @deprecated 旧写法的直译；优先级低于 modelValue，用于迁移期，避免页面为了去掉它而改逻辑 */
  open?: boolean
  /** 外部强制展开（例如打印时 `:open="printing"`）。只强制开，不强制关 */
  forceOpen?: boolean
  /** 密度：inline 任务内详情 / section 页内一段依据 / group 阶段与分组 */
  variant?: 'inline' | 'section' | 'group'
  /** 内容是否属于"动作区"（ActionsSheet 那一类：按钮与后续操作）。
   *  动作区需要更清楚的边界，且折叠起来＝用户找不到动作，所以它会多一条提示性的视觉线。 */
  actions?: boolean
  /** 静态形态：不可折叠，内容永远可见。**主信息（结论、当前任务、关键字段）用它** */
  static?: boolean
}>(), {
  count: null,
  defaultOpen: false,
  modelValue: undefined,
  open: undefined,
  forceOpen: false,
  variant: 'section',
  actions: false,
  static: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  toggle: [value: boolean]
}>()

/* ---- 层级检测：一页最多一层折叠 ----
 * 这里踩过一个坑，值得写下来：**provide/inject 跨不过默认插槽**。
 * 插槽内容在"定义它的组件"的作用域里求值，所以 <Foldable><Foldable/></Foldable>
 * 里那个内层组件 inject 到的是外层 Foldable 的**父组件**提供的深度（也就是没有，
 * 实测两个组件的 parentDepth 都是 0）—— 靠它做判据，警告永远不会触发。
 *
 * 所以：provide 仍保留（给"以子组件形式挂进去"的用法，以及未来给其他组件读层级），
 * 但真正的判据是**挂载后沿 DOM 祖先链数** —— 渲染位置才代表视觉嵌套。
 * 只在开发期、且只在这个组件自己身上警告一次，不递归、不影响生产包（import.meta.env.DEV 会被摇掉）。 */
const FOLD_DEPTH = Symbol('fold-depth')
const parentDepth = inject<number>(FOLD_DEPTH, 0)
provide(FOLD_DEPTH, parentDepth + 1)

const rootEl = ref<HTMLElement | null>(null)

/* 组件实例序号：只要保证 aria-controls 能对上就行，不需要全局唯一。 */
let foldSeq = 0
const bodyId = `fold-body-${++foldSeq}`

onMounted(async () => {
  if (!import.meta.env.DEV || props.static) return
  await nextTick()
  let node: HTMLElement | null = rootEl.value?.parentElement ?? null
  let depth = parentDepth + 1
  while (node) {
    if (node.classList?.contains('fold')) depth++
    node = node.parentElement
  }
  if (depth > 1) {
    console.warn(
      `[Foldable] 折叠被嵌套在第 ${depth} 层：「${props.title}」。` +
      'PLAN §4.4 要求一页最多 1 层折叠——请把内层内容改成始终可见（static 形态），' +
      '或让它回到与外层同级。',
    )
  }
})

/* ---- 受控 / 非受控 ---- */
const isControlled = computed(() => props.modelValue !== undefined)
const inner = ref(props.modelValue ?? props.open ?? props.defaultOpen)
watch(() => props.modelValue, v => { if (v !== undefined) inner.value = v })
watch(() => props.open, v => { if (v !== undefined && !isControlled.value) inner.value = v })

const expanded = computed(() => (props.static || props.forceOpen ? true : inner.value))

function toggle() {
  if (props.static) return
  const next = !inner.value
  if (!isControlled.value) inner.value = next
  else emit('update:modelValue', next)
  emit('toggle', next)
}
</script>

<template>
  <!-- 静态形态不是"折叠"，所以根节点也换成语义化的 section：读屏不会把它读成一个可展开控件 -->
  <component :is="static ? 'section' : 'div'" ref="rootEl" class="fold" :class="[`fold--${variant}`, { 'fold--static': static, 'fold--actions': actions, 'fold--open': expanded }]">
    <template v-if="static">
      <h3 v-if="title" class="fold__static-head"><slot name="title">{{ title }}</slot><span v-if="count !== null && count !== undefined" class="fold__count">{{ count }}</span></h3>
    </template>
    <button
      v-else
      class="fold__head"
      type="button"
      :aria-expanded="expanded"
      :aria-controls="bodyId"
      @click="toggle"
    >
      <span class="fold__label"><slot name="title">{{ title }}</slot></span>
      <span v-if="count !== null && count !== undefined" class="fold__count">{{ count }}</span>
      <UiIcon class="fold__chevron" name="chevron" :size="16" />
    </button>

    <div
      v-if="expanded"
      :id="bodyId"
      class="fold__body"
      :class="{ 'fold__body--actions': actions }"
    >
      <slot />
    </div>
  </component>
</template>

<style scoped>
/* ===========================================================================
 * 一个组件、三档密度、一条铁律
 * 铁律：折叠只说"这里还有更多"，不说"这里更重要"。主信息用 static 形态。
 * ========================================================================= */
.fold { min-width: 0; }

/* ---- 头部：44px 触控目标 + 一致的箭头位置 ---- */
.fold__head {
  display: flex;
  align-items: center;
  gap: var(--fold-head-gap);
  width: 100%;
  min-height: var(--fold-head-min-h);
  padding: 0;
  color: var(--fold-head);
  font-size: var(--fs-14);
  text-align: left;
  background: none;
  border: 0;
  cursor: pointer;
}
.fold__label { flex: 1; min-width: 0; }
.fold__chevron { flex: none; transition: transform var(--dur-2) var(--ease-out); }
.fold--open .fold__chevron { transform: rotate(180deg); }
.fold__count {
  flex: none;
  padding: 0 var(--sp-2);
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--c-border);
  border-radius: var(--r-pill);
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
  color: var(--c-text-3);
}
.fold--open .fold__count { color: var(--c-text-2); border-color: var(--c-border-strong); }

/* ---- 变体一 · inline：任务行里的"详情"。最轻，跟标题同一行读 ---- */
.fold--inline { margin-top: var(--sp-2); }
.fold--inline .fold__head { min-height: 40px; color: var(--c-text-3); }
.fold--inline .fold__head:hover { color: var(--c-primary); }
.fold--inline .fold__body { padding-top: var(--sp-3); color: var(--fold-body); }
.fold--inline .fold__body > :deep(p) { margin-top: var(--sp-3); max-width: 38em; }

/* ---- 变体二 · section：页内一段依据 / 相关资料。带一条上发丝线，与正文分开 ---- */
.fold--section { margin-top: var(--sp-7); padding-top: var(--sp-2); border-top: 1px solid var(--fold-rule); }
.fold--section .fold__body { padding: var(--fold-body-pad-y) 0 var(--sp-2); color: var(--fold-body); font-size: var(--fs-14); line-height: 1.8; }
.fold--section .fold__body :deep(h2),
.fold--section .fold__body :deep(h3) { font-size: var(--fs-16); margin-bottom: var(--sp-3); }

/* ---- 变体三 · group：阶段 / 分组。最重，整行是标题加副标题 ---- */
.fold--group { border-top: 1px solid var(--fold-rule); }
.fold--group .fold__head { padding: var(--sp-5) 0; gap: var(--sp-5); min-height: 64px; }
.fold--group .fold__label { font-size: var(--fs-16); color: var(--c-text); }
.fold--group .fold__body { padding: 0 0 var(--sp-6) 0; font-size: var(--fs-14); line-height: 1.85; color: var(--fold-body); }
/* 阶段序号之类的"行首方块"由 slot 传入，这里给统一尺寸，免得每个页面各画一个 */
.fold--group .fold__head :deep(.fold-index) {
  flex: none;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--r-sm);
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

/* ---- 动作区：折叠里装着"按钮"时，展开后要能一眼看到动作，所以加一条主色线做落点 ---- */
.fold--actions .fold__body--actions { border-left: var(--bw-2) solid var(--c-primary-border); padding-left: var(--sp-4); }

/* ---- 静态形态：不是折叠，是"原文照排" ---- */
.fold--static { background: var(--fold-static-bg); }
.fold__static-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-16);
  font-weight: var(--fw-medium);
  color: var(--c-text);
}
.fold--static .fold__body { padding-top: var(--sp-3); color: var(--fold-body); }

/* ---- 键盘焦点：四种旧折叠都没有可见焦点环，这里补上 ---- */
.fold__head:focus-visible {
  outline: 2px solid var(--c-focus);
  outline-offset: 2px;
  border-radius: var(--r-sm);
}
</style>
