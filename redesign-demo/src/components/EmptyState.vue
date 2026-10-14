<script lang="ts">
/**
 * 空态 · 类型出口（审计 D8 / PLAN §4.4）
 *
 * `kind` 必须覆盖**全站真实场景**，而不是只覆盖已经有调用的那三种。
 * 原来只有 'chat' | 'notes' | 'intel'，于是 `StudentView` 传不出 kind 就落到默认值，
 * 结果"暂无个人信息"配了一张便签图形 —— 这一类错误只有把 kind 枚举按场景铺开才能避免：
 * 调用方要写空态时，先被迫回答"这是哪一类空"。
 */
export type EmptyStateKind =
  | 'chat' // 还没有对话
  | 'notes' // 待办 / 个人目标为空
  | 'intel' // 岗位资讯为空
  | 'profile' // 个人画像还没有已知信息
  | 'report' // 还没有诊断报告
  | 'academic' // 学籍与资料为空
  | 'schedule' // 日历与课表空
  | 'review' // 还没有复盘记录
  | 'search-empty' // 筛选或检索没有命中（不是"没有内容"，是"条件太窄"）

export type EmptyStateHeadingLevel = 2 | 3 | 4
export type EmptyStateSize = 'md' | 'sm'

/** 图形字形：三种沿用 WorkspaceMotif，其余在本组件内按同一套几何补 */
export type EmptyStateMotif = 'chat' | 'notes' | 'intel' | 'canvas'
</script>

<script setup lang="ts">
import { computed, useId } from 'vue'
import WorkspaceMotif from './WorkspaceMotif.vue'
// EmptyStateKind / EmptyStateMotif / … 声明在本文件上方那个 <script> 块里（同一模块作用域）

/**
 * 空态 · 升级说明
 *
 * 1. **标题只有一档：`h3`（可用 headingLevel 覆盖）。**
 *    全站空态 20+ 处里 h2/h3 混用，起因是没人定过"空态属于几级标题"。
 *    定论：空态**替换的是某个区块的内容**，与它并列的是同级内容的标题 —— 所以是 h3。
 *    只有"整个页面正文都被空态顶掉"（如异常页、整页无数据）才提到 h2，用 headingLevel 显式说明理由。
 * 2. **每个 kind 都带下一步。** 位置永远存在（`__next`），内容优先级：
 *    具名/默认插槽 → actionLabel + actionTo/actionHref → kind 预设。
 *    预设只用两种形态：跨页的 `link`，和指向页内既有入口的 `hint`（不造没人接的按钮）。
 * 3. **图形与语义对齐。** WorkspaceMotif 只有 chat / notes / intel 三种字形，
 *    这里对语义不符的六类（profile / report / academic / schedule / review / search-empty）
 *    按**它同一套几何**（240×160、20px 点阵、同一条路径骨架与节点位）补语义字形。
 *    待 WorkspaceMotif 扩容后，应删掉下面的 canvas 分支改回 `<WorkspaceMotif :kind>`。
 */
type NextStep = { type: 'link'; label: string; to: string } | { type: 'hint'; text: string }

const props = withDefaults(
  defineProps<{
    title: string
    description: string
    kind?: EmptyStateKind
    /** 标题层级：默认 3（空态替换的是区块内容）。整页无内容时才用 2 */
    headingLevel?: EmptyStateHeadingLevel
    /** 显式动作：站内路由。给了 actionLabel 才会出现按钮 */
    actionTo?: string
    /** 显式动作：外链 */
    actionHref?: string
    /** 显式动作文案；不给目标时渲染为按钮并 emit('action')，由调用方接手（聚焦输入框、清除筛选…） */
    actionLabel?: string
    /** 紧凑形态：抽屉、卡片内部 */
    size?: EmptyStateSize
    /** 关掉 kind 预设的下一步（保留空位，等调用方自己补） */
    next?: boolean
  }>(),
  { kind: 'notes', headingLevel: 3, size: 'md', next: true }
)

const emit = defineEmits<{ action: [] }>()

/**
 * 每种 kind 的"下一步"。
 * 只用跨页 link 与页内 hint 两种 —— 预设里不放按钮，
 * 因为预设拿不到调用方的处理函数，会造出一个点了没反应的按钮。
 */
const NEXT: Record<EmptyStateKind, NextStep> = {
  chat: { type: 'hint', text: '在下方说出你的第一个问题，从这里开始。' },
  notes: { type: 'hint', text: '在上方写下第一件要做的事。' },
  intel: { type: 'hint', text: '在上方检索一次最新资讯，或先加载示例看看格式。' },
  profile: { type: 'link', label: '去咨询里补充这项信息', to: '/chat' },
  report: { type: 'hint', text: '在上方生成第一份诊断；依据不足时它会先说明缺口。' },
  academic: { type: 'hint', text: '在上方导入学校资料，或手动补录这一项。' },
  schedule: { type: 'hint', text: '在上方添加一项安排，日历会按时间排开。' },
  review: { type: 'hint', text: '先记下今天发生的一件事，稍后再回来归因。' },
  'search-empty': { type: 'hint', text: '换个关键词，或清除筛选条件后重试。' }
}

/** 图形字形：能对上 WorkspaceMotif 的三种就直接用，其余走本组件的语义字形 */
const MOTIF: Record<EmptyStateKind, EmptyStateMotif> = {
  chat: 'chat',
  notes: 'notes',
  intel: 'intel',
  profile: 'canvas',
  report: 'canvas',
  academic: 'canvas',
  schedule: 'canvas',
  review: 'canvas',
  'search-empty': 'canvas'
}

const patternId = 'empty-grid-' + useId()

const motif = computed<EmptyStateMotif>(() => MOTIF[props.kind])
const nextStep = computed<NextStep | null>(() => (props.next ? NEXT[props.kind] : null))
const headingTag = computed(() => `h${props.headingLevel}`)
const actionTarget = computed<'none' | 'link' | 'href' | 'button'>(() => {
  if (!props.actionLabel) return 'none'
  if (props.actionTo) return 'link'
  if (props.actionHref) return 'href'
  return 'button'
})
</script>

<template>
  <!-- exp-empty / exp-empty__actions 是老类名：三处既有调用不传新参数也要长得和以前一样 -->
  <div class="exp-empty" :class="[`exp-empty--${kind}`, `exp-empty--${size}`]">
    <slot name="motif">
      <WorkspaceMotif v-if="motif !== 'canvas'" :kind="motif" />
      <!--
        canvas：WorkspaceMotif 没有对应字形时的语义字形。
        几何常量与 WorkspaceMotif 完全一致，只是把中间那个图形换成语义相符的一个。
      -->
      <svg v-else class="exp-motif" viewBox="0 0 240 160" aria-hidden="true" fill="none">
        <defs>
          <pattern :id="patternId" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r=".7" fill="currentColor" opacity=".18" />
          </pattern>
        </defs>
        <rect x="0" y="0" width="240" height="160" :fill="'url(#' + patternId + ')'" />
        <path
          d="M45 108H83C98 108 104 95 104 81V67C104 54 113 45 126 45H195"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path d="M104 81H149C161 81 170 90 170 102V112H195" stroke="currentColor" stroke-opacity=".25" stroke-width="1.5" />
        <rect x="25" y="88" width="40" height="40" rx="12" fill="var(--c-surface)" stroke="currentColor" stroke-opacity=".3" />
        <g stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <!-- 画像：一个人，不是一张便签 -->
          <template v-if="kind === 'profile'">
            <circle cx="45" cy="104" r="5" />
            <path d="M35.5 118.5c1.4-5.2 5-7.8 9.5-7.8s8.1 2.6 9.5 7.8" />
          </template>
          <!-- 报告：带折角的文档 + 一条走势线 -->
          <template v-else-if="kind === 'report'">
            <path d="M36 97h13l7 7v16H36z" />
            <path d="M49 97v7h7" />
            <path d="M40 115l3.5-3.5 3 3 4.5-5.5" />
          </template>
          <!-- 学籍与资料：一张表，左列是字段名 -->
          <template v-else-if="kind === 'academic'">
            <rect x="35" y="98" width="20" height="20" rx="2.5" />
            <path d="M42 98v20" />
            <path d="M46 104h6m-6 4h6m-6 4h3" />
          </template>
          <!-- 日历与课表：格子，不是文档 -->
          <template v-else-if="kind === 'schedule'">
            <rect x="35" y="99" width="20" height="19" rx="3" />
            <path d="M35 105.5h20" />
            <path d="M41 95.5v6m8-6v6" />
            <rect x="39.5" y="109" width="4" height="4" rx="1" />
            <rect x="46.5" y="109" width="4" height="4" rx="1" />
          </template>
          <!-- 复盘：一条折返的箭头（回看已经发生的事） -->
          <template v-else-if="kind === 'review'">
            <path d="M52 100v8a6 6 0 0 1-6 6H38" />
            <path d="M41.5 99.5 36 104l5.5 4.5" />
          </template>
          <!-- 筛选无结果：放大镜里的那道斜线才是"没有命中"，不是"什么都没有" -->
          <template v-else>
            <circle cx="43.5" cy="105" r="6.5" />
            <path d="M48.5 110 54.5 116" />
            <path d="M41 102.5 46 107.5" />
          </template>
        </g>
        <circle cx="195" cy="45" r="19" fill="var(--c-primary-weak)" />
        <path d="m188 45 5 5 9-10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx="195" cy="112" r="12" fill="var(--c-surface)" stroke="currentColor" stroke-opacity=".3" />
        <circle cx="195" cy="112" r="3" fill="currentColor" opacity=".4" />
      </svg>
    </slot>

    <component :is="headingTag" class="exp-empty__title">
      <slot name="title">{{ title }}</slot>
    </component>
    <p class="exp-empty__desc">
      <slot name="description">{{ description }}</slot>
    </p>

    <!-- 下一步动作的位置：这个容器永远在，空态不允许没有出口 -->
    <div class="exp-empty__actions">
      <slot>
        <template v-if="actionTarget !== 'none'">
          <RouterLink v-if="actionTarget === 'link'" class="btn btn--primary" :to="actionTo!">{{ actionLabel }}</RouterLink>
          <a v-else-if="actionTarget === 'href'" class="btn btn--primary" :href="actionHref" target="_blank" rel="noopener noreferrer">{{ actionLabel }}</a>
          <button v-else class="btn btn--primary" type="button" @click="emit('action')">{{ actionLabel }}</button>
        </template>
        <p v-else-if="nextStep" class="exp-empty__next">
          <template v-if="nextStep.type === 'link'">
            <RouterLink class="ws-text-link" :to="nextStep.to">{{ nextStep.label }}</RouterLink>
          </template>
          <template v-else>
            <span class="exp-empty__next-label">下一步</span>{{ nextStep.text }}
          </template>
        </p>
      </slot>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================================
 * 空态
 * 说明文字停在 34em：超出这个宽度，一行会开始"扫读不回来"。
 * 图形沿用 .exp-motif 的既有尺寸（宽屏 180 / 窄屏 140），不改全局规则。
 * ========================================================================= */
.exp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.exp-empty--sm {
  padding: var(--sp-5) var(--sp-3) var(--sp-6);
}

/* 标题只有一档（h3），字号沿用升级前那一档，页面观感不变 */
.exp-empty__title {
  font-size: var(--fs-20);
  font-weight: var(--fw-medium);
  line-height: var(--lh-snug);
  color: var(--c-text);
}

.exp-empty__desc {
  max-width: 34em;
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.exp-empty__actions {
  margin-top: var(--sp-4);
}

/* 预设的"下一步"：一条安静的路标，不是一个抢视线的按钮 */
.exp-empty__next {
  display: flex;
  align-items: baseline;
  justify-content: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  max-width: 34em;
  margin: 0 auto;
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.exp-empty__next-label {
  flex: none;
  padding: 2px var(--sp-2);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  letter-spacing: 0.06em;
  color: var(--c-text-3);
}

.exp-empty--sm .exp-empty__title {
  font-size: var(--fs-16);
}

.exp-empty--sm .exp-empty__desc,
.exp-empty--sm .exp-empty__next {
  font-size: var(--fs-12);
}

/* 窄屏：图形收一档，说明文字不再靠 max-width 撑（父容器本来就窄） */
@media (max-width: 760px) {
  .exp-empty__desc,
  .exp-empty__next {
    max-width: none;
  }
}
</style>
