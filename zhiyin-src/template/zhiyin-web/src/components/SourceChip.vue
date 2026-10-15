<script setup lang="ts">
import { computed } from 'vue'
import type { ProfileSource } from '../api/backend-types'

/* =============================================================================
 * SourceChip —— 「这条信息是哪来的」的可读徽标
 * -----------------------------------------------------------------------------
 * 【病灶】审计三连（COVERAGE.md:180 / :273）：
 *   "溯源/状态一律降级为灰字或折叠 —— 同一套后端字段（source / confidence /
 *    needs_recompute）在三处三种视觉重量"。
 * 设计语言 §4.3 也写着"每条信息剥开能看到来历"，§5 反例表点名"溯源做成一个
 * 折叠的『来源』"不合格。所以来源必须**默认可见、且读得出形态差异**。
 *
 * 【只有三支色相，形态差异得靠别的】令牌硬口径：蓝（主）/ 红（注意）/ 灰（结构），
 * 不允许第四色相。而红在这个产品里专用于"需要你注意"，**拿红去标"导师给的"
 * 会占用注意力预算**（CRAFT-BRIEF §3.4：注意色配额 ≤1%）。所以本组件完全不使用红，
 * 来源只用蓝灰两支色相，差异全部由下面三样承载：
 *   ① 底色深浅（--c-primary-strong 实心 / --c-primary-weak 浅蓝 / --c-surface-3 灰 / 透明）
 *   ② 边框语法（实线 / 虚线 —— 虚线只给"推断"，见 behavior_inference）
 *   ③ **圆角形状 + 左侧标记 + 字形**（灰度截图与色觉障碍下唯一还在的信号）
 * 各来源的形状各不相同，形状本身就是签名：见 SOURCE_META 与 KIND_META。
 *
 * 【2026-10-14 · wave2】补上"自由文本来源"这条逃生口。见下方 EXTERNAL 段的长注释。
 * ========================================================================== */

/**
 * 形态档：决定底色 / 边框 / 圆角，见 <style> 里的 `.src--*`。
 * 七支对应七个 `ProfileSource`；后三支对应非枚举的自由文本来源（见 KIND_META）。
 * 写在**一个**联合类型里而不是两个：形态是同一门图形语言，
 * 拆成两套枚举就会出现"同一个 `.src--*` 被两条分支各写一半"的漂移。
 */
type SourceShape =
  | 'verified' | 'stated' | 'measured' | 'inferred' | 'attested' | 'ledger' | 'edited'
  | 'external' | 'citation' | 'transcript'

interface SourceMeta {
  /** 界面上的字。用学生能懂的话，不用枚举名（docs/前端/历史设计/早期方案/早期视觉设计规范.md 口径：界面不出现内部词） */
  label: string
  /** 一句话解释"这个来源意味着什么"，进 title，不占版面 */
  why: string
  shape: SourceShape
}

/**
 * 七个 `ProfileSource` 枚举值一个不漏（backend-types.ts:335）。
 * 字典是 `Record<ProfileSource, …>` 而不是普通对象 —— 后端加枚举值时，
 * 这里会**编译报错**，而不是默默渲染成一枚"未知来源"。这是防漂移。
 */
const SOURCE_META: Record<ProfileSource, SourceMeta> = {
  resume: {
    label: '简历材料',
    why: '来自你上传的简历文件，是可核对的原始材料',
    shape: 'verified',
  },
  conversation: {
    label: '对话中说的',
    why: '来自你在咨询里说过的话，尚未与材料核对',
    shape: 'stated',
  },
  assessment: {
    label: '测评结果',
    why: '来自一次量表或测评的作答结果',
    shape: 'measured',
  },
  behavior_inference: {
    label: '据行为推断',
    why: '没有直接说过，是根据使用记录推断的 —— 可能不准，可以纠正',
    shape: 'inferred',
  },
  mentor: {
    label: '导师记录',
    why: '来自导师或他人提供的记录',
    shape: 'attested',
  },
  record: {
    label: '教务记录',
    why: '来自教务或学籍系统的记录',
    shape: 'ledger',
  },
  user_edit: {
    label: '你自己改的',
    why: '你手动修改过这一条，以你的填写为准',
    shape: 'edited',
  },
}

const props = withDefaults(
  defineProps<{
    /**
     * 后端 ProfileSource 枚举（backend-types.ts:335）。
     *
     * 【2026-10-14 · wave2】从「必填」放宽为「可选」，**但语义没有放宽**：
     * 只要这条信息的来历是画像字段，就必须继续传它（既有 7 值用法一字未改，见交付说明）。
     * 改成可选只为一件事：给下面的 `label` 让路。见 `label` 的注释。
     */
    source?: ProfileSource | null
    /**
     * 自由文本来源名 —— 不是 ProfileSource 时的逃生口。
     *
     * 【为什么必须有这条口子】三路 agent 独立撞上同一件事：
     *   · 资讯页的 `source_name`（外部媒体名，如「中国教育在线」）
     *   · AI 结果的 `citation.source`（后端自由文本）
     *   · 对话方法卡的来源（同上）
     * 三者**都是自由文本**，喂不进 `Record<ProfileSource, …>`（编译报错），
     * 于是它们只能退回 `<p class="ws-muted">` 灰字 —— 正是 `DESIGN-LANGUAGE.md:102`
     * 点名的"溯源一律降级为灰字"。**组件的能力边界成了设计语言的执行边界。**
     * 所以逃生口不是"妥协"，是把"来源必须可见"这条规则从"只有画像字段能享受"
     * 扩到"所有来源"。
     *
     * 相容规则（实测三种写法都成立）：
     *   · 只传 `source` → 与升级前逐像素一致（label 缺省 null，走 SOURCE_META）
     *   · 只传 `label` → 自由文本，`kind` 决定形态（缺省 'external'）
     *   · 两个都传 → `label` 覆盖显示文字，**形态仍走 `source` 的语义**
     *     （所以"这条来自教务记录、但界面要显示某个外部系统名"是合法组合）
     */
    label?: string | null
    /**
     * 非 ProfileSource 来源的语义档 —— 决定形态（底色/边框/圆角/字形），
     * 与 `SOURCE_META.shape` 是同一套图形语言里的另外三支。
     * 缺省 `external`（外部文本来源）。
     */
    kind?: ExternalSourceKind
    /** 来源时间。ISO 字符串或 `YYYY-MM-DD`。默认可见（审计要求） */
    at?: string | null
    size?: 'sm' | 'md'
  }>(),
  { source: null, label: null, kind: 'external', at: null, size: 'sm' },
)

/**
 * 三支"不是 ProfileSource"的来源语义档。
 *
 * 为什么是三支而不是一支 `raw`：形态差异是**唯一的**信号来源（不允许第四色相），
 * 把「外部媒体」「第三方引用」「转录文本」压成一个 `raw` 会让这三种在灰度下完全同形，
 * 等于把"读不出来历"从"缺组件"变成"组件里缺形状"。三支各自有底色 + 圆角 + 字形。
 * 为什么三支都**不用虚线**：虚线在全站是 `behavior_inference`（"这是推的"）的签名，
 * 借用会让"推断"与"外部来源"混淆 —— 这是本组件最不该发生的混淆。
 * 为什么三支都**不用红**：见文件头，红是"需要你注意"的专属配额。
 */
export type ExternalSourceKind =
  | 'external' // 外部媒体 / 网站（资讯 source_name）—— 灰底 + 方角 + 地球
  | 'citation' // 第三方引用（AI citation.source）—— 浅蓝底 + 圆角 md + 引号
  | 'transcript' // 转录 / 口述文本（对话方法卡来源）—— 灰底 + 小圆角 + 对话线

/** 非枚举来源与枚举来源共用同一套形态元数据（同一门图形语言，不另立一套）。 */
type ExternalMeta = SourceMeta

/**
 * 三支非枚举来源的元数据。
 * 「为什么是 Record<ExternalSourceKind, …> 而不是普通对象」与 SOURCE_META 同理：
 * 以后加档位时这里会编译报错，而不是静默渲染成一枚"未知来源"。
 */
const KIND_META: Record<ExternalSourceKind, ExternalMeta> = {
  external: {
    label: '外部来源',
    why: '来自产品之外的一份材料或网站，未经核对',
    shape: 'external',
  },
  citation: {
    label: '引用来源',
    why: '由生成结果引用的一段外部材料，可回看原文',
    shape: 'citation',
  },
  transcript: {
    label: '转录文本',
    why: '来自一段记录或转录的文字，可能有听写误差',
    shape: 'transcript',
  },
}

/**
 * 形态的唯一解析入口。
 * 优先级：`source` 的语义 → `kind` 的语义。这条顺序与"label 只覆盖文字、不覆盖语义"一致。
 * 返回类型直接用 `SourceShape`，于是 `.src--*` 的类名在模板里是被类型检查的
 * （写错档位名会在 `Record<ExternalSourceKind, …>` 那里先报出来）。
 */
const isEnumSource = computed(() => !!props.source && props.source in SOURCE_META)

const meta = computed<SourceMeta>(() =>
  isEnumSource.value ? SOURCE_META[props.source as ProfileSource] : KIND_META[props.kind] ?? KIND_META.external,
)

const shape = computed<SourceShape>(() => meta.value.shape)

/**
 * 显示文字，三层显式覆盖，没有隐式兜底：
 *   `label`（调用方给的自由文本）→ 枚举字典 → kind 字典。
 */
const text = computed(() => props.label || meta.value.label)

/**
 * title（鼠标悬停可读的一句话）。
 * `label` 覆盖时把**原始语义**也带上：否则"显示成外部系统名、语义其实是教务记录"
 * 这条组合在悬停时看不出语义，溯源又变回一次猜测。
 */
const hint = computed(() =>
  isEnumSource.value && props.label
    ? `${props.label}（${meta.value.label}） · ${meta.value.why}`
    : `${meta.value.label} · ${meta.value.why}`,
)

/**
 * 时间**只做去掉噪音**，不做本地化推算：
 * 后端给的是哪一天，就印哪一天。日期里的 `T` 后面是时刻，与"哪次说的"无关，
 * 印出来只会让一行里多出 8 个不参与判断的字符（CRAFT-BRIEF §4.2 规则 3：日期写
 * 2026-10-14 而不是 2026/10/14，等宽下字符数一致，列表不抖）。
 * 解析不出来时**原样显示**，不静默吞掉 —— 宁可见到脏数据，也不要"来源没有时间"
 * 这种假象。
 */
function displayAt(raw: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : raw
}
</script>

<template>
  <span
    class="src"
    :class="[`src--${shape}`, `src--${size}`]"
    :title="hint"
  >
    <!-- 字形：每种来源各不同，是灰度下仍在的签名 -->
    <svg class="src__glyph" viewBox="0 0 16 16" aria-hidden="true">
      <!-- 简历：一页纸，右上折角 -->
      <template v-if="source === 'resume'">
        <path d="M4 1.5h5l3 3v10H4z" />
        <path d="M9 1.5v3h3" />
        <path d="M6 8h4M6 10.5h4" />
      </template>
      <!-- 对话：两个叠着的对话泡 -->
      <template v-else-if="source === 'conversation'">
        <path d="M2.5 3.5h8v5h-4l-2.5 2v-2h-1.5z" />
        <path d="M11.5 6.5h2v4.2h-1.6l-2 1.6v-1.6" />
      </template>
      <!-- 测评：三个刻度块，高低不同（量表） -->
      <template v-else-if="source === 'assessment'">
        <path d="M3 13V9M8 13V4M13 13V6.5" />
        <path d="M2 13.5h12" />
      </template>
      <!-- 推断：一条虚线连着一个空心点 —— "没直接说过，是推的" -->
      <template v-else-if="source === 'behavior_inference'">
        <circle cx="3.5" cy="12.5" r="1.5" />
        <path d="M5.5 11.2 8 8M6 6.5h4.5M12.5 4.5h1" stroke-dasharray="2 1.6" />
        <circle cx="10.5" cy="6.5" r="1.5" />
      </template>
      <!-- 导师：一个人形 + 一条"批注"线（有人签过字） -->
      <template v-else-if="source === 'mentor'">
        <circle cx="5.5" cy="5" r="2.5" />
        <path d="M1.5 14c0-2.5 1.8-4 4-4s4 1.5 4 4" />
        <path d="M11.5 4.5h3M11.5 7.5h3" />
      </template>
      <!-- 教务记录：一张表，横竖各一条线 -->
      <template v-else-if="source === 'record'">
        <rect x="2" y="3" width="12" height="10" />
        <path d="M2 6.5h12M6.5 3v10" />
      </template>
      <!-- 自己改的：一支笔 -->
      <template v-else-if="source === 'user_edit'">
        <path d="M11.2 2.3 13.7 4.8 6 12.5l-3.2.7.7-3.2z" />
        <path d="M9.6 3.9 12.1 6.4" />
      </template>

      <!-- ===== 以下三支给"非 ProfileSource 的自由文本来源"（wave2 新增） ===== -->

      <!-- 外部：地球，经纬各一条 —— "这是外面的" -->
      <template v-else-if="shape === 'external'">
        <circle cx="8" cy="8" r="6" />
        <path d="M2 8h12M8 2c3.2 3.4 3.2 8.6 0 12-3.2-3.4-3.2-8.6 0-12z" />
      </template>
      <!-- 引用：一对引号 —— "这是别人说的原话" -->
      <template v-else-if="shape === 'citation'">
        <path d="M3.2 6.2h3v3.6c0 1.5-.9 2.6-2.4 3.2" />
        <path d="M9.4 6.2h3v3.6c0 1.5-.9 2.6-2.4 3.2" />
      </template>
      <!-- 转录：三条不等长的横线（一段被记下来的话） -->
      <template v-else>
        <path d="M2.5 5h11M2.5 8h8M2.5 11h10" />
      </template>
    </svg>

    <span class="src__label">{{ text }}</span>

    <!-- 来源与时间默认同时可见（审计要求），中间用一条细线分开 -->
    <template v-if="at">
      <span class="src__sep" aria-hidden="true" />
      <time class="src__at t-num" :datetime="at">{{ displayAt(at) }}</time>
    </template>
  </span>
</template>

<style scoped>
/* 底与形都是令牌：组件里不出现颜色字面量（tokens.css 的头号口径） */
.src {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 7px 1px 5px;
  border: var(--bw-1) solid transparent;
  border-radius: var(--r-md);
  font-size: var(--fs-12);
  line-height: 1.65;
  white-space: nowrap;
  vertical-align: middle;
}

.src__glyph {
  width: 11px;
  height: 11px;
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.3;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.9;
}

.src__label {
  font-weight: var(--fw-medium);
}

.src__sep {
  width: 1px;
  height: 9px;
  background: currentColor;
  opacity: 0.35;
}

.src__at {
  font-variant-numeric: tabular-nums;
  opacity: 0.82;
}

/* ---------- 七种形态：底色 + 边框 + 圆角，三者组合各不相同 ---------- */

/* ① 简历（原始材料）：最深的一档 —— 实心浅蓝 + 实线边 + 圆角 md */
.src--verified {
  background: var(--c-primary-weak-2);
  border-color: var(--c-primary-border);
  border-radius: var(--r-md);
  color: var(--c-primary);
}

/* ② 对话（本人陈述）：浅蓝底 + 左侧一道竖条，形状就已经在说"这是一个人说的" */
.src--stated {
  background: var(--c-primary-weak);
  border-color: var(--c-primary-border);
  border-left-width: 3px;
  border-radius: var(--r-sm);
  color: var(--c-primary);
}

/* ③ 测评（测量值）：灰底 + 药丸形。药丸在本项目里只给"已定型的读数" */
.src--measured {
  background: var(--c-surface-3);
  border-color: var(--c-border-strong);
  border-radius: var(--r-pill);
  color: var(--c-text);
}

/* ④ 推断：白底 + **虚线**边（全站唯一的虚线来源语法）。
   虚线 = "这是推的，还不结实"，与"实线 = 有出处"对撞。 */
.src--inferred {
  background: transparent;
  border-style: dashed;
  border-color: var(--c-border-strong);
  border-radius: var(--r-sm);
  color: var(--c-text-2);
}

/* ⑤ 导师（有第三方背书）：白底 + 2px 实线边 + 左侧一道粗竖条，重量仅次于简历 */
.src--attested {
  background: var(--c-surface);
  border-color: var(--c-text-3);
  border-left-width: 3px;
  border-radius: var(--r-sm);
  color: var(--c-text);
}

/* ⑥ 教务记录（台账）：灰底 + 小圆角（方一点，像表格里的格子） */
.src--ledger {
  background: var(--c-surface-3);
  border-color: var(--c-border);
  border-radius: 3px;
  color: var(--c-text);
}

/* ⑦ 用户手改（以你为准）：浅灰底 + 药丸，重量最轻 —— 它不需要被强调 */
.src--edited {
  background: var(--c-surface-2);
  border-color: var(--c-border);
  border-radius: var(--r-pill);
  color: var(--c-text-2);
}

/* ---------- 三支"非 ProfileSource 的自由文本来源"（wave2 新增） ----------
 * 硬约束重申：不加色相（仍是蓝/灰两支）、不用虚线（虚线是 behavior_inference 的签名）、
 * 不用红（注意色配额 ≤1%）。所以三支的差异全在**底色深浅 + 圆角 + 字形**上：
 *   external    灰底 + 方角（3px，像表里的格子）—— 与 ledger 同族但更浅，
 *               表达"外面来的、我们没核对过"
 *   citation    浅蓝底 + 圆角 md —— 蓝 = 由本产品引用进来的，所以比 external 近一层
 *   transcript  灰底 + 小圆角 —— 介于"记录"与"外部"之间：是我们记下来的，但会有听写误差
 */

/* ⑧ 外部来源：最浅的灰底 + 方角 */
.src--external {
  background: var(--c-surface-2);
  border-color: var(--c-border);
  border-radius: 3px;
  color: var(--c-text-2);
}

/* ⑨ 引用来源：浅蓝底 + 圆角 md（与"简历"同底色，但字形是引号，不混淆） */
.src--citation {
  background: var(--c-primary-weak);
  border-color: var(--c-primary-border);
  border-radius: var(--r-md);
  color: var(--c-primary);
}

/* ⑩ 转录文本：灰底 + 小圆角 + 左侧一道细竖条（"这是一段被记下来的话"） */
.src--transcript {
  background: var(--c-surface-3);
  border-color: var(--c-border);
  border-left-width: 3px;
  border-radius: var(--r-sm);
  color: var(--c-text-2);
}

/* ---------- 两档尺寸 ---------- */
.src--md {
  gap: 6px;
  padding: 2px 9px 2px 6px;
  font-size: var(--fs-14);
}
.src--md .src__glyph {
  width: 13px;
  height: 13px;
}

/* 窄屏：`来源 + 时间` 一条可以换行，不能让徽标撑破 390px 的行 */
@media (max-width: 480px) {
  .src {
    max-width: 100%;
  }
  .src__label {
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
</style>
