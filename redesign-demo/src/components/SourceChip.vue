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
 * 七个来源只用蓝灰两支色相，差异全部由下面三样承载：
 *   ① 底色深浅（--c-primary-strong 实心 / --c-primary-weak 浅蓝 / --c-surface-3 灰 / 透明）
 *   ② 边框语法（实线 / 虚线 —— 虚线只给"推断"，见 behavior_inference）
 *   ③ **圆角形状 + 左侧标记 + 字形**（灰度截图与色觉障碍下唯一还在的信号）
 * 七个来源的形状各不相同，形状本身就是签名：见 SOURCE_META。
 * ========================================================================== */

interface SourceMeta {
  /** 界面上的字。用学生能懂的话，不用枚举名（DESIGN.md 口径：界面不出现内部词） */
  label: string
  /** 一句话解释"这个来源意味着什么"，进 title，不占版面 */
  why: string
  /** 形态档：决定底色/边框/圆角，见 <style> 里的 .src--* */
  shape: 'verified' | 'stated' | 'measured' | 'inferred' | 'attested' | 'ledger' | 'edited'
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
    /** 后端 ProfileSource 枚举（backend-types.ts:335）。必填 —— 来源不许不写 */
    source: ProfileSource
    /** 来源时间。ISO 字符串或 `YYYY-MM-DD`。默认可见（审计要求） */
    at?: string | null
    size?: 'sm' | 'md'
  }>(),
  { at: null, size: 'sm' },
)

const meta = computed(() => SOURCE_META[props.source] ?? SOURCE_META.user_edit)

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
    :class="[`src--${meta.shape}`, `src--${size}`]"
    :title="`${meta.label} · ${meta.why}`"
  >
    <!-- 字形：七个形状各不同，是灰度下仍在的签名 -->
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
      <template v-else>
        <path d="M11.2 2.3 13.7 4.8 6 12.5l-3.2.7.7-3.2z" />
        <path d="M9.6 3.9 12.1 6.4" />
      </template>
    </svg>

    <span class="src__label">{{ meta.label }}</span>

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
