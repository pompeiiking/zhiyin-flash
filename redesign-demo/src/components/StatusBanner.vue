<script lang="ts">
/**
 * 状态条 · 类型出口（审计 D9）
 *
 * 四态**只有三支色相**（tokens.css 硬口径：进行中·信息 → 蓝；需要你注意 → 红；完成·中性 → 灰）。
 * 所以四态的区分不能靠颜色，靠的是下面这一组形态差异 —— 静图截图、灰度打印、色盲用户都必须还分得清：
 *
 *   tone     | 左侧竖线        | 底            | 图标             | 标题色        | 动作位 | 读屏   | 消失
 *   ---------|----------------|---------------|-----------------|--------------|-------|--------|------------------
 *   success  | 1px 灰          | 中性面        | 描边圆 ✓        | 次级文字      | 无    | status | 4s 自动 + 可关
 *   info     | 2px 蓝          | 极浅蓝        | 描边圆 i        | 次级文字      | 可选  | status | 只能手动关
 *   warning  | 2px 红          | 极浅红        | 描边三角 !      | 注意红（重）  | 无    | status | 只能手动关
 *   error    | 3px 红（最重）  | 极浅红        | **实心**红圆 !  | 注意红（重）  | 必有重试 | alert  | 只能手动关
 *
 * 六个维度里只有三个是颜色，其余是线宽、图标形状（描边/实心）、动作位、读屏角色与消失策略。
 * 红主色皮肤（data-accent=red）下 info 与 attention 同为红相，靠的就是这组非颜色差异区分。
 */
export type StatusTone = 'success' | 'error' | 'info' | 'warning'
export type StatusSize = 'md' | 'sm'
</script>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 状态条 · 三条设计决定
 *
 * 1. **成功的反馈不该常驻。** `success` 默认 4s 自动消失（可关掉），其余三态必须由人来关 ——
 *    需要你处理的错误不该自己溜走。鼠标悬停或键盘焦点进入时倒计时暂停（WCAG 2.2.1）。
 * 2. **错误态必须有动作位。** 只报错不给下一步，等于把问题丢回给用户；
 *    默认给一个「重试」，`retrying` 期间它自己进入"正在重试…"状态。
 * 3. **不做入场动画以外的任何动效。** 这条状态条唯一的动效是"出现/消失"（150ms 透明度），
 *    它传达的是"这里多了一条信息 / 这条信息结束了"；reduced-motion 下连这一条也去掉。
 *    浮层形态由 InfoSheet 负责，这里只保证"放在白底、灰底、浮层里都读得清"（floating）。
 */
const props = withDefaults(
  defineProps<{
    tone?: StatusTone
    /** 正文。一句话说清"发生了什么 / 你的东西还在不在" */
    message: string
    /** 可选短标题，用来把"状态"和"细节"分两行 */
    title?: string
    /** 关闭按钮。默认开：成功的反馈常驻不消失正是审计 D9 的病灶 */
    dismissible?: boolean
    /** 毫秒；0 = 不自动消失。不给就按 tone 定：success 4000，其余 0 */
    autoDismiss?: number
    /** 错误态的重试按钮：**错误态一定有**（只报错不给下一步等于把问题丢回用户）；
     *  其余三态想给动作位就显式打开 */
    retryable?: boolean
    retryLabel?: string
    /** 重试进行中：按钮进入"正在重试…"并禁用，避免连点 */
    retrying?: boolean
    /** 通用次要动作（如"查看详情"），由调用方接手 */
    actionLabel?: string
    /** 外部控制显隐（受控用法）；不传则组件自己管自己 */
    open?: boolean
    size?: StatusSize
    /** 悬在内容之上使用（toast 容器里）。这里只加一层影，不负责定位于层级 */
    floating?: boolean
  }>(),
  {
    tone: 'info',
    dismissible: true,
    retryable: false,
    retrying: false,
    size: 'md',
    floating: false,
    // 默认必须写出来：Vue 对 Boolean 类型的 prop 会把"没传"转成 false，
    // 于是 `open?: boolean` 不写默认值时等于"默认关闭"，整条状态条直接不渲染。
    open: true
  }
)

const emit = defineEmits<{ dismiss: []; retry: []; action: [] }>()

/** 用户自己关掉的那一次。用内部状态而不是 v-model：不依赖调用方回写也能关掉 */
const closed = ref(false)

const visible = computed(() => props.open && !closed.value)
/** 错误态必须有动作位；其余三态由调用方显式打开 */
const showRetry = computed(() => props.tone === 'error' || props.retryable)
const resolvedAutoDismiss = computed(() => props.autoDismiss ?? (props.tone === 'success' ? 4000 : 0))
/** 错误态打断读屏（alert），其余排到当前朗读之后（status） */
const role = computed(() => (props.tone === 'error' ? 'alert' : 'status'))

function close() {
  stopTimer()
  closed.value = true
  emit('dismiss')
}

function retry() {
  if (props.retrying) return
  emit('retry')
}

/* ---- 倒计时：可暂停，可恢复 ---- */
let timer: number | undefined
let deadline = 0
let remaining = 0

function stopTimer() {
  if (timer !== undefined) {
    window.clearTimeout(timer)
    timer = undefined
  }
}

function startTimer(ms: number) {
  remaining = ms
  deadline = Date.now() + ms
  timer = window.setTimeout(close, ms)
}

function pauseTimer() {
  if (timer === undefined) return
  stopTimer()
  remaining = Math.max(0, deadline - Date.now())
}

function resumeTimer() {
  if (timer !== undefined || !visible.value) return
  const budget = resolvedAutoDismiss.value
  if (budget <= 0) return
  startTimer(remaining > 0 ? remaining : budget)
}

// 换了一条新反馈就把"关掉了"复位：同一个位置重新出现，用户不会以为它没生效
watch(
  () => [props.message, props.tone] as const,
  () => {
    closed.value = false
  }
)

watch(
  () => [resolvedAutoDismiss.value, visible.value] as const,
  ([budget, isVisible]) => {
    stopTimer()
    if (!isVisible || budget <= 0) return
    startTimer(budget)
  },
  { immediate: true }
)

onBeforeUnmount(stopTimer)
</script>

<template>
  <Transition name="status-banner-fade">
    <div
      v-if="visible"
      class="status-banner"
      :class="[`status-banner--${tone}`, `status-banner--${size}`, { 'status-banner--floating': floating }]"
      :role="role"
      @mouseenter="pauseTimer"
      @mouseleave="resumeTimer"
      @focusin="pauseTimer"
      @focusout="resumeTimer"
    >
      <span class="status-banner__icon" aria-hidden="true">
        <!-- 图标形状本身就是四态的第一个差异：圆/圆/三角/实心圆 + ✓/i/!/! -->
        <svg v-if="tone === 'success'" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8.2" stroke="currentColor" stroke-width="1.6" />
          <path d="m6.4 10.3 2.4 2.4 4.8-5.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <svg v-else-if="tone === 'info'" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8.2" stroke="currentColor" stroke-width="1.6" />
          <path d="M10 9v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          <circle cx="10" cy="6.4" r="1.05" fill="currentColor" />
        </svg>
        <svg v-else-if="tone === 'warning'" viewBox="0 0 20 20" fill="none">
          <path d="M10 3.2 18 17H2z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
          <path d="M10 8.2v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          <circle cx="10" cy="14.4" r="1.05" fill="currentColor" />
        </svg>
        <svg v-else viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8.6" fill="currentColor" />
          <path d="M10 5.4v5.2" stroke="var(--status-icon-on)" stroke-width="1.9" stroke-linecap="round" />
          <circle cx="10" cy="14.1" r="1.2" fill="var(--status-icon-on)" />
        </svg>
      </span>

      <div class="status-banner__body">
        <p v-if="title" class="status-banner__title">{{ title }}</p>
        <p class="status-banner__message">
          <slot>{{ message }}</slot>
        </p>
        <div v-if="showRetry || actionLabel" class="status-banner__actions">
          <button
            v-if="showRetry"
            class="btn status-banner__retry"
            type="button"
            :disabled="retrying"
            @click="retry"
          >
            {{ retrying ? '正在重试…' : retryLabel || '重试' }}
          </button>
          <button v-if="actionLabel" class="ws-text-button" type="button" @click="emit('action')">
            {{ actionLabel }}
          </button>
        </div>
      </div>

      <button
        v-if="dismissible"
        class="status-banner__close"
        type="button"
        aria-label="关闭这条提示"
        @click="close"
      >
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="m6 6 8 8m0-8-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </Transition>
</template>

<style scoped>
/* ============================================================================
 * 状态条
 * 底/边/字色全部走 --status-* 令牌（tokens.css 追加段），组件里不出现颜色字面量，
 * 于是换主题、换主色（data-accent=red）都不用改这里。
 * ========================================================================= */
.status-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-3) var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  border-left-style: solid;
  line-height: var(--lh-normal);
  overflow-wrap: anywhere;
}

.status-banner--sm {
  padding: var(--sp-2) var(--sp-2) var(--sp-2) var(--sp-3);
  font-size: var(--fs-12);
}

/* 浮层里用：只负责"读得清"，定位与层级归调用方（浮层形态是 InfoSheet 的事） */
.status-banner--floating {
  background-clip: padding-box;
  box-shadow: var(--e-2);
}

.status-banner__icon {
  flex: none;
  display: flex;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}

.status-banner__icon svg {
  width: 100%;
  height: 100%;
}

.status-banner__body {
  flex: 1;
  min-width: 0;
}

.status-banner__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  line-height: var(--lh-snug);
}

.status-banner__message {
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.status-banner__title + .status-banner__message {
  margin-top: var(--sp-1);
}

.status-banner__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2) var(--sp-4);
  margin-top: var(--sp-3);
}

.status-banner__close {
  flex: none;
  position: relative;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  transition: color var(--dur-1) var(--ease-out), background-color var(--dur-1) var(--ease-out);
}

/* 视觉上是 28px（状态条不该被一个关闭按钮撑高），但触控目标补到 44px：
   审计已经记录"多页触控目标 <44px"是全站系统性缺陷，新组件不再犯。 */
.status-banner__close::after {
  content: '';
  position: absolute;
  inset: -8px;
}

.status-banner__close:hover {
  color: var(--c-text);
  background: var(--c-surface-3);
}

.status-banner__close svg {
  width: 18px;
  height: 18px;
}

/* ---- 四态：竖线宽度 + 底 + 图标风格 + 字色，六个维度里只有三个是颜色 ---- */
.status-banner--success {
  border-left-width: var(--bw-1);
  border-left-color: var(--status-success-border);
  background: var(--status-success-bg);
  color: var(--status-success-text);
}

.status-banner--success .status-banner__icon,
.status-banner--success .status-banner__title {
  color: var(--status-success-text);
}

.status-banner--info {
  border-left-width: var(--bw-2);
  border-left-color: var(--status-info-border);
  background: var(--status-info-bg);
  color: var(--status-info-text);
}

.status-banner--info .status-banner__icon {
  color: var(--status-info-border);
}

.status-banner--warning {
  border-left-width: var(--bw-2);
  border-left-color: var(--status-warning-border);
  background: var(--status-warning-bg);
  color: var(--status-warning-text);
}

.status-banner--warning .status-banner__icon,
.status-banner--warning .status-banner__title {
  color: var(--status-warning-text);
}

/* 错误：竖线最粗 + 图标实心 = 不改色相也能一眼和"注意"分开 */
.status-banner--error {
  border-left-width: 3px;
  border-left-color: var(--status-error-border);
  background: var(--status-error-bg);
  color: var(--status-error-text);
}

.status-banner--error .status-banner__icon {
  color: var(--status-error-border);
}

.status-banner--error .status-banner__title {
  color: var(--status-error-text);
}

.status-banner--error .status-banner__message {
  color: var(--c-text);
}

/* 出现/消失：唯一一条动效，承载"多了一条信息 / 这条信息结束了" */
.status-banner-fade-enter-active,
.status-banner-fade-leave-active {
  transition: opacity var(--dur-1) var(--ease-out);
}

.status-banner-fade-enter-from,
.status-banner-fade-leave-to {
  opacity: 0;
}

/* reduced-motion：去掉淡入淡出，信息本身一条不少 */
@media (prefers-reduced-motion: reduce) {
  .status-banner-fade-enter-active,
  .status-banner-fade-leave-active {
    transition: none;
  }

  .status-banner__close {
    transition: none;
  }
}
</style>
