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
  /* ---- 【2026-10-14 · wave2】补齐三路 agent 分别借用过的四个语义档 ----
   * 为什么必须补：这四个场景**都只能借用语义不符的 kind**，而每个借用都留下一条注释，
   * 说明写它的人知道不对但没办法 —— 注释不是解法，是缺口在代码里的化石：
   *   plan      RoadmapView 的"阶段计划还没有形成"借用了 `report`
   *             → 代价不是图形错，是 `NEXT.report` 说"在上方生成第一份诊断"，
   *               在计划页上这句话指着一个不存在的入口（plan 页没有生成诊断的按钮）
   *   direction LiveDirectionCompare 的"尚未取得方向方案"借用了 `report`
   *             → 同上，方向没有"生成报告"这个动作
   *   notice    InboxSheet 的"提醒为空"借用了 `notes`
   *             → `NEXT.notes` 说"在上方写下第一件要做的事"，在提醒弹层里是错的
   *   tools     ModuleCatalog 的"工具目录为空"借用了 `search-empty`
   *             → `search-empty` 的语义是"条件太窄"，而这里是"服务没返回"，
   *               让用户去改关键词是**指错方向**（没有可改的条件）
   * 这四档的 `NEXT` 都指向**页内已有入口或明确的等待语义**，不造没人接的按钮
   * （与既有 9 档同一口径，见下方 NEXT 的注释）。
   * 既有 9 档的 kind / 图形 / NEXT 一个字都没动 —— 新增 key 不改旧值。
   */
  | 'plan' // 阶段计划还没有形成
  | 'direction' // 还没有可比较/确认的方向方案
  | 'notice' // 提醒 / 通知为空
  | 'tools' // 服务还没有返回可用的工具目录

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
  intel: { type: 'hint', text: '更新一次真实职业资料，或使用当前画像发起匹配。' },
  profile: { type: 'link', label: '去咨询里补充这项信息', to: '/chat' },
  report: { type: 'hint', text: '在上方生成第一份诊断；依据不足时它会先说明缺口。' },
  academic: { type: 'hint', text: '在上方导入学校资料，或手动补录这一项。' },
  schedule: { type: 'hint', text: '在上方添加一项安排，日历会按时间排开。' },
  review: { type: 'hint', text: '先记下今天发生的一件事，稍后再回来归因。' },
  'search-empty': { type: 'hint', text: '换个关键词，或清除筛选条件后重试。' },
  /* wave2 新增四档。每一条都刻意不写"在上方……"（前三档的毛病就是假设页面上方有个生成按钮）：
     · plan 的任务只能从咨询里来 —— 所以给 link 而不是 hint（hint 会指向一个不存在的入口）
     · direction 与 plan 同源（方向也是咨询形成的），但此刻**不该**给第二个 /chat 链接：
       方向页下方已有"比较后确认"的动作区，重复的出口会把注意力从确认动作上分走
     · notice 的出口是"下一条提醒"的语义，不是"写一件事"
     · tools 是"服务没返回"，让用户等或重试，不能说"换个关键词"（没有可换的条件） */
  plan: { type: 'link', label: '去咨询里定下一步', to: '/chat' },
  direction: { type: 'hint', text: '方向会随咨询里的结论形成；形成后这里会出现可比较的方案。' },
  notice: { type: 'hint', text: '现在没有待处理的提醒。有新提醒时会显示在这里。' },
  tools: { type: 'hint', text: '服务还没有返回可用工具；稍后重新读取一次。' }
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
  'search-empty': 'canvas',
  // wave2 新增四档同样走本组件内的语义字形（WorkspaceMotif 只有 chat/notes/intel 三种）
  plan: 'canvas',
  direction: 'canvas',
  notice: 'canvas',
  tools: 'canvas'
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
        <!-- 统一的是线条、点阵和品牌色；各业务使用自己的信息构图，不再共用一条路线骨架。 -->
        <g v-if="kind === 'profile'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="120" cy="72" r="28" fill="var(--c-primary-weak)" stroke="none" />
          <circle cx="120" cy="66" r="9" fill="var(--c-surface)" />
          <path d="M101 96c2.8-12 10-18 19-18s16.2 6 19 18" fill="var(--c-surface)" />
          <path d="M92 74H63M148 66h29M99 99l-21 17M141 98l22 18" stroke-opacity=".38" />
          <rect x="37" y="62" width="27" height="24" rx="8" fill="var(--c-surface)" />
          <rect x="176" y="54" width="29" height="24" rx="8" fill="var(--c-surface)" />
          <rect x="52" y="108" width="31" height="22" rx="8" fill="var(--c-surface)" />
          <rect x="160" y="107" width="34" height="22" rx="8" fill="var(--c-surface)" />
          <path d="M44 73h13M183 65h15M59 119h17M167 118h20" stroke-opacity=".5" />
        </g>

        <g v-else-if="kind === 'report'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M68 28h75l29 29v79H68z" fill="var(--c-surface)" />
          <path d="M143 28v29h29" fill="var(--c-primary-weak)" />
          <path d="M88 58h31M88 70h48" stroke-opacity=".35" />
          <path d="M89 113 104 96l14 8 23-25 13 11" />
          <circle cx="89" cy="113" r="3" fill="var(--c-primary)" stroke="none" />
          <circle cx="118" cy="104" r="3" fill="var(--c-primary)" stroke="none" />
          <circle cx="154" cy="90" r="3" fill="var(--c-primary)" stroke="none" />
          <path d="M88 124h66" stroke-opacity=".25" />
        </g>

        <g v-else-if="kind === 'academic'" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round">
          <rect x="42" y="32" width="156" height="96" rx="11" fill="var(--c-surface)" />
          <path d="M42 58h156M88 32v96M158 32v96" />
          <path d="M55 45h20M101 45h35M171 45h14" stroke-opacity=".42" />
          <path d="M55 72h19M101 72h38M171 72h13M55 91h19M101 91h31M171 91h13M55 110h19M101 110h42M171 110h13" stroke-opacity=".3" />
          <circle cx="181" cy="72" r="4" fill="var(--c-primary)" stroke="none" />
          <circle cx="181" cy="91" r="4" fill="var(--c-primary-weak)" />
          <circle cx="181" cy="110" r="4" fill="var(--c-primary)" stroke="none" />
        </g>

        <g v-else-if="kind === 'schedule'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="45" y="35" width="150" height="96" rx="12" fill="var(--c-surface)" />
          <path d="M45 61h150M75 28v14M165 28v14" />
          <path d="M82.5 61v70M120 61v70M157.5 61v70M45 84h150M45 107h150" stroke-opacity=".25" />
          <rect x="87" y="67" width="28" height="12" rx="4" fill="var(--c-primary-weak)" stroke="none" />
          <rect x="125" y="89" width="27" height="13" rx="4" fill="var(--c-primary-weak)" stroke="none" />
          <rect x="163" y="112" width="26" height="12" rx="4" fill="var(--c-primary-weak)" stroke="none" />
        </g>

        <g v-else-if="kind === 'review'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M72 89a49 49 0 1 0 13-38" />
          <path d="m66 50 20 1-5 18" fill="var(--c-surface)" />
          <circle cx="120" cy="82" r="27" fill="var(--c-primary-weak)" stroke="none" />
          <path d="M120 67v17l13 9" />
          <circle cx="120" cy="84" r="3" fill="currentColor" stroke="none" />
          <path d="M67 113h31M142 124h31" stroke-opacity=".3" />
        </g>

        <g v-else-if="kind === 'plan'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M38 126h40V99h42V73h42V44h40" stroke-opacity=".32" />
          <circle cx="58" cy="126" r="10" fill="var(--c-surface)" />
          <circle cx="99" cy="99" r="10" fill="var(--c-surface)" />
          <circle cx="141" cy="73" r="10" fill="var(--c-surface)" />
          <circle cx="182" cy="44" r="14" fill="var(--c-primary-weak)" stroke="none" />
          <path d="m175 44 5 5 9-10" />
          <path d="M52 126h12M93 99h12M135 73h12" stroke-opacity=".55" />
        </g>

        <g v-else-if="kind === 'direction'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="54" cy="80" r="13" fill="var(--c-surface)" />
          <path d="M67 80h34M101 80c18 0 21-31 39-31h27M101 80c18 0 21 31 39 31h27" />
          <rect x="167" y="34" width="40" height="30" rx="9" fill="var(--c-primary-weak)" stroke="none" />
          <rect x="167" y="96" width="40" height="30" rx="9" fill="var(--c-surface)" />
          <path d="M177 49h20M177 111h20" stroke-opacity=".52" />
          <path d="m48 80 4 4 8-9" />
        </g>

        <g v-else-if="kind === 'notice'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="120" cy="78" r="45" fill="var(--c-primary-weak)" stroke="none" />
          <path d="M92 103h56M98 103v-31a22 22 0 0 1 44 0v31M120 43v-8M112 112a8 8 0 0 0 16 0" fill="var(--c-surface)" />
          <path d="M78 62c-6 10-6 23 0 33M162 62c6 10 6 23 0 33" stroke-opacity=".35" />
        </g>

        <g v-else-if="kind === 'tools'" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="48" y="35" width="58" height="40" rx="10" fill="var(--c-surface)" />
          <rect x="134" y="35" width="58" height="40" rx="10" fill="var(--c-surface)" />
          <rect x="48" y="91" width="58" height="40" rx="10" fill="var(--c-surface)" />
          <rect x="134" y="91" width="58" height="40" rx="10" fill="var(--c-primary-weak)" stroke="none" />
          <path d="M64 55h26M150 55h26M64 111h26M150 111h26" stroke-opacity=".45" />
          <circle cx="77" cy="55" r="4" fill="var(--c-primary)" stroke="none" />
          <circle cx="163" cy="111" r="4" fill="var(--c-primary)" stroke="none" />
        </g>

        <g v-else stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="105" cy="72" r="38" fill="var(--c-surface)" />
          <circle cx="105" cy="72" r="24" stroke-opacity=".3" />
          <path d="m133 100 35 35" stroke-width="8" stroke-opacity=".28" />
          <path d="M82 72h46" stroke-opacity=".36" />
          <circle cx="68" cy="35" r="6" fill="var(--c-primary-weak)" stroke="none" />
          <circle cx="172" cy="55" r="9" fill="var(--c-primary-weak)" stroke="none" />
          <circle cx="55" cy="118" r="5" fill="var(--c-primary-weak)" stroke="none" />
        </g>
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
 *
 * 【2026-10-14 · 从 experience.css 搬进来的那一族】
 * 全局 `.exp-empty` 一族已删除：它是 check-classes.mjs 报的两条硬失败之一（全局那条含
 * padding，会从 scoped 的缝里漏进组件根盒子）。逐条对应（左 = 改前 experience.css:104-108,155-156）：
 *   .exp-empty { text-align:center; padding: 28px 12px 36px }                → 下面 .exp-empty
 *   @media ≤760: .exp-empty { padding: 20px 0 28px }                         → 下面的 ≤760 块
 *   .exp-empty .exp-motif { width:180px; display:block; margin:0 auto 12px } → 下面 :deep(.exp-motif)
 *   @media ≤760: .exp-empty .exp-motif { width: 140px }                      → 下面的 ≤760 块
 *   .exp-empty h2 { font-size: var(--fs-20); font-weight: 500 }              → **不搬**：.exp-empty__title
 *                                                                             同值（20px/500）且特异度更高
 *   .exp-empty p { font-size / color / max-width }                           → **不搬**：__desc 与 __next
 *                                                                             逐条盖住（含 max-width 34em > 32em）
 *   ↑ 那条 p 里唯一还有效的部分是**左右 auto 外边距** → 并入 .exp-empty__desc 的 margin 简写
 *   .exp-empty__actions { margin-top: 16px }                                 → **不搬**：scoped 的 var(--sp-4)
 *                                                                             本来就赢（同一元素、特异度更高）
 * 两条纪律：
 *   ① 图形必须用 :deep()。.exp-motif 可能来自子组件 WorkspaceMotif 的**根元素**（它带的是父组件的
 *      scope 属性），而 :deep() 编译出的特异度（0,2,0）与改前那条全局规则完全相同 ——
 *      所以 StudentView 的 `.p7-group__empty[data-v] .exp-motif`（0,3,0，宽 120px）仍然压得住它。
 *      写成不带 :deep 的 `.exp-empty .exp-motif` 会变成（0,3,0），与它打平、靠加载顺序决胜。
 *   ② ≤760 的 padding 覆盖必须排在本文件 `.exp-empty--sm` **之前**：改前那条是全局规则（特异度更低），
 *      盖不住 sm 档；顺序反了就会把 sm 档的内距也一起改掉。
 * ========================================================================= */
.exp-empty {
  display: grid;
  grid-template-columns: minmax(112px, 156px) minmax(0, 1fr);
  grid-template-rows: auto auto 1fr;
  align-items: center;
  gap: 5px 26px;
  min-height: 190px;
  padding: 24px 28px;
  border: 1px solid var(--c-border);
  border-radius: 16px;
  background:
    linear-gradient(120deg, color-mix(in srgb, var(--c-primary) 7%, transparent), transparent 48%),
    var(--c-surface);
  text-align: left;
}

/* 图形尺寸沿用 .exp-motif 的既有口径（宽屏 200 → 空态 180 / 窄屏 140），不改全局那条。 */
.exp-empty :deep(.exp-motif) {
  grid-column: 1;
  grid-row: 1 / 4;
  width: 100%;
  max-width: 156px;
  display: block;
  margin: 0;
  color: var(--c-primary);
}

/* 窄屏：内距与图形各收一档（原来都在 experience.css 的 ≤760 里） */
@media (max-width: 760px) {
  .exp-empty {
    grid-template-columns: 76px minmax(0, 1fr);
    min-height: 150px;
    gap: 4px 16px;
    padding: 18px 16px;
  }
  .exp-empty :deep(.exp-motif) { width: 88px; transform: translateX(-6px); }
}

.exp-empty--sm {
  grid-template-columns: 82px minmax(0,1fr);
  min-height: 132px;
  gap: 3px 14px;
  padding: 16px;
}
.exp-empty--sm :deep(.exp-motif) {
  width: 90px;
  transform: translateX(-6px);
}

/* 标题只有一档（h3），字号沿用升级前那一档，页面观感不变 */
.exp-empty__title {
  grid-column: 2;
  font-size: var(--fs-20);
  font-weight: var(--fw-semibold);
  line-height: var(--lh-snug);
  color: var(--c-text);
}

/* margin 用简写不是风格问题：改前 desc 的左右外边距来自全局 `.exp-empty p { margin: 10px auto 0 }`
   （auto），那条规则随全局一族删掉了。写成 `margin-top` 会把左右外边距退回 0px，
   computed 从 241px/auto 掉成 0px —— 虽然 flex 下 align-items:center 也能居中，
   但那是"另一个理由得到同一个像素"，不是"外观不变"。 */
.exp-empty__desc {
  grid-column: 2;
  max-width: 34em;
  margin: var(--sp-1, 4px) 0 0;
  font-size: var(--fs-14);
  line-height: var(--lh-normal);
  color: var(--c-text-3);
}

.exp-empty__actions {
  grid-column: 2;
  align-self: start;
  margin-top: 10px;
}

/* 预设的"下一步"：一条安静的路标，不是一个抢视线的按钮 */
.exp-empty__next {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: var(--sp-2);
  max-width: 34em;
  margin: 0;
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
