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
import { computed, inject, nextTick, onMounted, provide, ref, useId, watch } from 'vue'
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
  /**
   * 静态形态的标题档位。缺省 3（16px，升级前那一档，观感不变）。
   *
   * 【2026-10-14 · wave2】为什么要这一档：`static` 原来**只有**一个 16px 的 `<h3>` 档。
   * 于是"这一段是主信息容器、但它没有标题 / 标题只是一行弱眉标"的调用方，
   * 只能写 `:title="''"` 再在 slot 里自己造一个 12px 的眉标 —— 组件被绕过，
   * 页面上就多出一套各页自己写的头。给档位之后这条明路才成立：
   *   2 → 整页主信息段（与页面 h2 同级）
   *   4 → 附属说明段（比正文小一级）
   */
  titleLevel?: 2 | 3 | 4
  /**
   * 静态形态**完全不要头**：连标题元素都不渲染。
   *
   * 【2026-10-14 · wave2】它与 `:title="''"` 的区别不是省几个字节：
   * 传空标题时 `fold__static-head` 仍然渲染成一个**空的 h3**（flex 容器、0 高），
   * 读屏会念到一个空标题，DOM 里也留着一条"这里本该有标题"的痕迹。
   * `headless` 明确表达"这一段就是正文，没有头"。
   * 优先级高于 `titleLevel`（没有头就无所谓档位）；此时若传了 `count`，
   * 计数徽标会下沉到内容区顶部，不丢信息。
   */
  headless?: boolean
}>(), {
  count: null,
  defaultOpen: false,
  modelValue: undefined,
  open: undefined,
  forceOpen: false,
  variant: 'section',
  actions: false,
  static: false,
  titleLevel: 3,
  headless: false,
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
 * 只在开发期、且只在这个组件自己身上警告一次，不递归、不影响生产包（import.meta.env.DEV 会被摇掉）。
 *
 * 【2026-10-14 · wave2】判据从「数 `.fold`」改成「只数**可折叠的** `.fold`」（排除 `.fold--static`）。
 * 为什么这是 bug 不是口味：`static` 形态**不是折叠** —— 它的根渲染成 <section>、没有可展开控件、
 * 内容永远可见（见模板 `:is="static ? 'section' : 'div'"`，以及 `.fold--static` 的样式）。
 * 所以 `.fold--static` 只是"这段文字始终可见"的容器，把它算成一层折叠是纯粹的误报。
 * 被误报的恰好是**设计语言最推荐的那个组合**：
 *     `Foldable static`（主信息容器）+ 内部 `Foldable variant=inline`（次要详情）
 * —— `PLAN.md:112` 要求"主信息默认可见、折叠只留给次要内容"，这个组合全页正好 1 层折叠。
 * 实测后果不是"多一条 console 警告"：至少一个 agent 因此放弃了按需折叠，把该折的改成了始终展开。
 * **误报会把最该用的那个组合赶出代码库。**
 * 真嵌套（可折叠里套可折叠）仍然照报 —— 判据只去掉 static，没有放松。
 */
const FOLD_DEPTH = Symbol('fold-depth')
const parentDepth = inject<number>(FOLD_DEPTH, 0)
provide(FOLD_DEPTH, parentDepth + 1)

const rootEl = ref<HTMLElement | null>(null)

/*
 * 每个实例唯一的 id —— 用 Vue 3.5 的 `useId()`。
 *
 * 【为什么不能自己数】第一版写的是：
 *     let foldSeq = 0
 *     const bodyId = `fold-body-${++foldSeq}`
 * 那个 `let` 在 `<script setup>` 里是**每个实例重新执行的局部变量**，所以每个实例都
 * 从 0 开始 → 全站 11 个折叠体的 id 全叫 `fold-body-1`。后果不是"不美观"：
 * `aria-controls` 指向的是**文档里第一个**折叠体，屏幕阅读器把每个折叠头都关联到
 * 同一块内容上（实测 `/plan` 里每个头 `targetIsOwnBody: false`）。
 * `useId()` 是 Vue 官方为此提供的 API（3.5+），跨实例稳定唯一，SSR 也安全。
 *
 * 教训：`<script setup>` 里没有"模块作用域"，任何"全局计数/单例缓存/只跑一次"的
 * 写法放进来都会变成"每个实例各来一次"。要模块级状态就得另开一个普通 `<script>` 块。
 */
const bodyId = `fold-body-${useId()}`

onMounted(async () => {
  if (!import.meta.env.DEV || props.static) return
  await nextTick()
  let node: HTMLElement | null = rootEl.value?.parentElement ?? null
  let depth = parentDepth + 1
  while (node) {
    // 只数**可折叠的** `.fold`：`.fold--static` 不是折叠（根是 <section>、永远可见），
    // 把"static 容器 + 内部 inline 折叠"算成第 2 层是误报。见上方长注释。
    if (node.classList?.contains('fold') && !node.classList.contains('fold--static')) depth++
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
      <!-- headless：这一段就是正文，没有头。计数徽标仍在（下沉到内容区顶部），不丢信息 -->
      <p v-if="headless" class="fold__static-bare">
        <span v-if="count !== null && count !== undefined" class="fold__count">{{ count }}</span>
        <span v-if="title" class="fold__static-bare-title"><slot name="title">{{ title }}</slot></span>
      </p>
      <!-- 非 headless：行为与升级前逐字一致（`v-if="title"` 挡住空标题、缺省 h3）。
           唯一的区别是档位可传 titleLevel。 -->
      <component :is="`h${titleLevel}`" v-else-if="title" class="fold__static-head">
        <slot name="title">{{ title }}</slot><span v-if="count !== null && count !== undefined" class="fold__count">{{ count }}</span>
      </component>
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
/* 【2026-10-14 · wave2】这里原来是 `min-height: 40px` —— 实测 40px < 44px 触控硬约束
   （CRAFT-BRIEF:322,389；`/review` 的 <44px 命中数因此从 8 变 9）。
   为什么不是"inline 比别的档轻所以可以小"：触控约束管的是**能不能点到**，不是"看起来多重"。
   44px 是硬约束，档位差异由字色（--c-text-3）和间距承载，不由命中区承载。
   用令牌而不是再写一个字面量：`--fold-head-min-h` 已经是 44px，
   `.fold__head` 的基础规则就是它，这里只是把 inline 的覆盖去掉，让它回到同一个口径。 */
.fold--inline .fold__head { min-height: var(--fold-head-min-h); color: var(--c-text-3); }
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
/* headless：没有头，但**不是没有信息**。空标题不再渲染成一个空 h3，
   计数徽标与可选的弱标题并排落在内容区顶部（一行，不占额外的高度预算）。 */
.fold__static-bare {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
.fold__static-bare-title {
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  color: var(--c-text-3);
}
.fold--static .fold__body { padding-top: var(--sp-3); color: var(--fold-body); }

/* ---- 键盘焦点：四种旧折叠都没有可见焦点环，这里补上 ---- */
.fold__head:focus-visible {
  outline: 2px solid var(--c-focus);
  outline-offset: 2px;
  border-radius: var(--r-sm);
}
</style>
