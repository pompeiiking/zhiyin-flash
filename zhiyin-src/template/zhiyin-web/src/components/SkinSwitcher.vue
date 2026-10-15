<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { useRoute } from 'vue-router'
import { skin, type Accent, type StyleId, type ThemeMode } from '../lib/theme'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui'

/**
 * 皮肤开关。
 *
 * 三条轴：主题（浅/深/跟随系统）、主色（河大蓝 / 河大红）、风格（极简/柔和/紧凑）。
 * 18 种组合，全部只换令牌 —— 结构一行不动。
 *
 * 曾经还有第四条轴「动效（完整/克制）」，2026-10-11 删除 —— 理由写在 lib/theme.ts 的
 * 文件头（与 prefers-reduced-motion 重复、用户看不出差别、还把门户搞白过）。
 * 减少动效现在只有一个来源：系统的 prefers-reduced-motion。
 *
 * 唯一的入口现在是**账号菜单 → 外观**（PLAN §3.5）：顶栏那颗「皮肤」按钮已移除，
 * 这是全站唯一一处能改外观的地方。
 *
 * 浮层位置：默认贴触发点右上；在账号抽屉里（触发器在抽屉下半部）改挂左侧 ——
 * 往下弹会被弹窗外沿裁掉，往左弹落在抽屉外的空白，整块都看得见。
 * 手机上宽度收到 `calc(100vw - 40px)`，不会顶出屏幕。
 *
 * 浮层动效：180ms ease-out，从触发点展开（transform-origin 在右上角，
 * 不是 center —— 浮层从它被点的地方长出来才说得通）；缩放从 0.97 起，不是 0。
 */

const props = defineProps<{ side?: 'top' | 'right' | 'bottom' | 'left' }>()
const open = ref(false)
const titleId = useId()
const route = useRoute()
watch(() => route.path, () => { open.value = false })

const themeOptions: { id: ThemeMode; label: string }[] = [
  { id: 'light', label: '浅色' },
  { id: 'dark', label: '深色' },
  { id: 'system', label: '跟随系统' },
]

const accentOptions: { id: Accent; label: string; hint: string }[] = [
  { id: 'blue', label: '河大蓝', hint: '蓝做主色，红只作提醒' },
  { id: 'red', label: '河大红', hint: '校色红做主色，蓝退为信息色' },
]

const styleOptions: { id: StyleId; label: string; hint: string }[] = [
  { id: 'plain', label: '极简', hint: '小圆角、无阴影、1px 描边' },
  { id: 'soft', label: '柔和', hint: '大圆角、轻影、更松的内距' },
  { id: 'dense', label: '紧凑', hint: '更小圆角与内距，一屏多看几条' },
]

const summary = computed(() => {
  const t = skin.state.theme === 'system' ? '跟随系统' : skin.state.theme === 'dark' ? '深色' : '浅色'
  const a = skin.state.accent === 'red' ? '河大红' : '河大蓝'
  const s = styleOptions.find((o) => o.id === skin.state.style)?.label ?? '极简'
  return `${t} · ${a} · ${s}`
})

</script>

<template>
  <PopoverRoot v-model:open="open">
  <div class="skin">
    <PopoverTrigger as-child>
    <button
      class="skin__trigger"
      :aria-expanded="open"
      aria-haspopup="dialog"
    >
      <span class="skin__dots" aria-hidden="true">
        <i class="skin__dot skin__dot--1" />
        <i class="skin__dot skin__dot--2" />
      </span>
      皮肤
    </button>
    </PopoverTrigger>

    <PopoverPortal>
      <PopoverContent class="skin__pop" :side="props.side ?? 'bottom'" align="end" :side-offset="8" :collision-padding="12" role="dialog" :aria-labelledby="titleId" aria-label="选择皮肤">
        <h2 :id="titleId" class="sr-only">选择皮肤</h2>
        <header class="skin__head">
          <span class="t-label">皮肤</span>
          <span class="t-note">{{ summary }}</span>
        </header>

        <section class="skin__group">
          <p class="skin__group-title">主题</p>
          <div class="seg">
            <button
              v-for="o in themeOptions"
              :key="o.id"
              class="seg__btn"
              :class="{ 'seg__btn--on': skin.state.theme === o.id }"
              :aria-pressed="skin.state.theme === o.id"
              @click="skin.setTheme(o.id)"
            >
              {{ o.label }}
            </button>
          </div>
        </section>

        <section class="skin__group">
          <p class="skin__group-title">主色</p>
          <div class="seg">
            <button
              v-for="o in accentOptions"
              :key="o.id"
              class="seg__btn"
              :class="{ 'seg__btn--on': skin.state.accent === o.id }"
              :aria-pressed="skin.state.accent === o.id"
              @click="skin.setAccent(o.id)"
            >
              {{ o.label }}
            </button>
          </div>
          <p class="skin__hint">
            {{ accentOptions.find((o) => o.id === skin.state.accent)?.hint }}
          </p>
        </section>

        <section class="skin__group">
          <p class="skin__group-title">风格</p>
          <div class="seg">
            <button
              v-for="o in styleOptions"
              :key="o.id"
              class="seg__btn"
              :class="{ 'seg__btn--on': skin.state.style === o.id }"
              :aria-pressed="skin.state.style === o.id"
              @click="skin.setStyle(o.id)"
            >
              {{ o.label }}
            </button>
          </div>
          <p class="skin__hint">
            {{ styleOptions.find((o) => o.id === skin.state.style)?.hint }}
          </p>
        </section>

        <!--
          曾经这里有第四条轴「动效」（完整 / 克制），已删除。
          减少动效不再是一个风格选项，只跟随系统的 prefers-reduced-motion ——
          那是无障碍刚需，不该被当成皮肤卖（细节见 lib/theme.ts 文件头）。
        -->

        <footer class="skin__foot">
          <button class="btn btn--sm btn--block" @click="skin.reset()">
            恢复默认外观
          </button>
          <p class="t-note">选择记在本地，下次打开还是这套；改的只是令牌，页面结构不动。</p>
        </footer>
      </PopoverContent>
    </PopoverPortal>
  </div>
  </PopoverRoot>
</template>

<style scoped>
.skin {
  position: relative;
}

.skin__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  height: var(--btn-h-md);
  padding: 0 var(--sp-3);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--btn-radius);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  transition:
    border-color var(--dur-1) ease,
    color var(--dur-1) ease,
    background-color var(--dur-1) ease;
}

.skin__trigger:hover {
  border-color: var(--c-border-strong);
  color: var(--c-text);
}

.skin__dots {
  display: inline-flex;
}

.skin__dot {
  width: 10px;
  height: 10px;
  border-radius: var(--r-pill);
  border: 1px solid var(--c-surface);
}

.skin__dot--1 {
  background: var(--c-primary);
}

.skin__dot--2 {
  margin-left: -4px;
  background: var(--c-attention);
}

.skin__scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-drawer);
}

/*
 * 浮层挂在 body 上（Portal），而账号抽屉是 `<dialog>`（top layer）。
 * top layer 盖过一切 z-index，所以皮肤浮层必须**不往下弹** —— 在账号菜单里
 * 用 `side="left"` 落到抽屉外的空白上，手机端则收窄到屏幕内。
 */
:global(.skin__pop) {
  z-index: calc(var(--z-drawer) + 1);
  width: min(320px, calc(100vw - 40px));
  max-height: var(--reka-popover-content-available-height);
  overflow-y: auto;
  padding: var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
  transform-origin: top right; /* 从触发点长出来，不是从中心 */
}

.skin__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-3);
  padding-bottom: var(--sp-3);
  border-bottom: var(--bw-1) solid var(--c-border);
}

.skin__group {
  margin-top: var(--sp-4);
}

.skin__group-title {
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  color: var(--c-text-2);
  margin-bottom: var(--sp-2);
}

.seg {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: var(--c-surface-3);
  border-radius: var(--r-md);
}

.seg__btn {
  flex: 1;
  height: 28px;
  border-radius: var(--r-sm);
  font-size: var(--fs-12);
  color: var(--c-text-2);
  transition:
    background-color var(--dur-1) ease,
    color var(--dur-1) ease;
}

.seg__btn:hover {
  color: var(--c-text);
}

.seg__btn--on {
  background: var(--c-surface);
  color: var(--c-primary);
  font-weight: var(--fw-semibold);
  box-shadow: var(--e-1);
}

.skin__hint {
  margin-top: var(--sp-2);
  font-size: var(--fs-12);
  color: var(--c-text-3);
}

.skin__foot {
  margin-top: var(--sp-5);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
}

.skin__foot .t-note {
  margin-top: var(--sp-2);
}

/* 浮层：180ms ease-out，0.97 → 1 */
.skin-pop-enter-active {
  transition:
    opacity var(--dur-2) var(--ease-out),
    transform var(--dur-2) var(--ease-out);
}

.skin-pop-leave-active {
  transition:
    opacity var(--dur-1) ease,
    transform var(--dur-1) ease;
}

.skin-pop-enter-from,
.skin-pop-leave-to {
  opacity: 0;
  transform: scale(0.97) translateY(-2px);
}
</style>
