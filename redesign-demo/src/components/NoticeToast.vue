<script setup lang="ts">
import { demo } from '../store'

/**
 * 提醒浮窗。
 *
 * 口径来自文档 7.4：「一次只跳一条」。后台可能一次拉回好几条，
 * 但它们不并列摆出来 —— 右侧任何时候只有一条，多出来的收成一行
 * 「还有 N 条 · 看下一条」。
 *
 * 一条消息只做一件事，并且必须自带动作。
 */
</script>

<template>
  <div class="notice">
    <!-- 触发器：一直在，不抢戏；点开才跳一条 -->
    <button
      v-if="!demo.state.noticeOpen"
      class="notice__trigger"
      @click="demo.openNotice()"
    >
      <span class="notice__badge">{{ demo.state.noticeQueue.length }}</span>
      提醒
    </button>

    <Transition name="notice">
      <aside v-if="demo.state.noticeOpen && demo.use.activeNotice.value" class="notice__panel">
        <header class="notice__head">
          <span class="chip chip--attention">{{ demo.use.activeNotice.value.kind }}</span>
          <button class="notice__close" aria-label="收起" @click="demo.closeNotice()">✕</button>
        </header>

        <h3 class="notice__title">{{ demo.use.activeNotice.value.title }}</h3>
        <p class="notice__body">{{ demo.use.activeNotice.value.body }}</p>

        <div class="notice__actions">
          <button class="btn btn--sm btn--primary" @click="demo.resolveNotice()">
            {{ demo.use.activeNotice.value.action }}
          </button>
          <button
            v-if="demo.use.activeNotice.value.secondary"
            class="btn btn--sm btn--ghost"
            @click="demo.closeNotice()"
          >
            {{ demo.use.activeNotice.value.secondary }}
          </button>
        </div>

        <button
          v-if="demo.use.noticeLeft.value > 0"
          class="notice__more"
          @click="demo.nextNotice()"
        >
          还有 {{ demo.use.noticeLeft.value }} 条 · 看下一条
        </button>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.notice {
  position: fixed;
  right: var(--sp-5);
  bottom: var(--sp-5);
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.notice__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  height: 36px;
  padding: 0 var(--sp-4);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border-strong);
  box-shadow: var(--e-2);
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.notice__trigger:hover {
  border-color: var(--c-primary);
  color: var(--c-primary);
}

.notice__badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: grid;
  place-items: center;
  border-radius: var(--r-pill);
  background: var(--c-attention);
  color: var(--c-on-attention);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
}

.notice__panel {
  width: 340px;
  padding: var(--sp-4);
  background: var(--c-surface);
  border: var(--bw-1) solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--e-3);
}

.notice__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
}

.notice__close {
  width: 22px;
  height: 22px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  font-size: var(--fs-12);
}

.notice__close:hover {
  background: var(--c-surface-3);
  color: var(--c-text);
}

.notice__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-semibold);
  line-height: var(--lh-snug);
}

.notice__body {
  margin-top: var(--sp-2);
  font-size: var(--fs-14);
  color: var(--c-text-2);
}

.notice__actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}

.notice__more {
  width: 100%;
  margin-top: var(--sp-3);
  padding-top: var(--sp-3);
  border-top: var(--bw-1) solid var(--c-border);
  font-size: var(--fs-12);
  color: var(--c-primary);
  text-align: left;
}

.notice__more:hover {
  text-decoration: underline;
}

.notice-enter-active,
.notice-leave-active {
  transition:
    opacity var(--mo-base) var(--mo-ease),
    transform var(--mo-base) var(--mo-ease);
}

.notice-enter-from,
.notice-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
