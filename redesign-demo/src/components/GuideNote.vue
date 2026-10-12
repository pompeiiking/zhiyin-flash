<script setup lang="ts">
import { computed } from 'vue'
import { demo } from '../store'

/**
 * 操作引导 —— 评审硬要求。
 *
 * 每进入一处功能，先说清"这里是干什么的、下一步去哪"，
 * 用户收起后不再打扰（记住收起了哪几处），但可以一次恢复。
 */
const props = defineProps<{
  /** 唯一 key：同一页可以有两条引导 */
  gkey: string
  text: string
  /** 下一步去哪（可选） */
  to?: string
  toLabel?: string
}>()

const closed = computed(() => demo.state.guidesClosed[props.gkey] === true)
</script>

<template>
  <Transition name="guide">
    <div v-if="!closed" class="guide">
      <span class="guide__mark" aria-hidden="true">i</span>
      <p class="guide__text">{{ text }}</p>
      <RouterLink v-if="to" class="guide__to" :to="to">{{ toLabel ?? '去下一步' }} →</RouterLink>
      <button class="guide__close" aria-label="收起这条引导" @click="demo.closeGuide(gkey)">
        ✕
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.guide {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  /* 中性底 + 一道主色左线。
     不用主色浅底：主色换成河大红之后，整条提示会变成红的，读起来像警告 ——
     而它只是"这里是干什么的"。主色底只留给"选中/交互"。 */
  background: var(--c-surface-2);
  border: var(--bw-1) solid var(--c-border);
  border-left: 3px solid var(--c-primary);
}

.guide__mark {
  width: 16px;
  height: 16px;
  flex: none;
  margin-top: 1px;
  display: grid;
  place-items: center;
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: var(--fs-12);
  font-weight: var(--fw-semibold);
  font-style: italic;
}

.guide__text {
  flex: 1;
  font-size: var(--fs-14);
  color: var(--c-text);
  line-height: var(--lh-snug);
}

.guide__to {
  flex: none;
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  white-space: nowrap;
}

.guide__close {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: var(--r-sm);
  color: var(--c-text-3);
  font-size: var(--fs-12);
  line-height: 1;
}

.guide__close:hover {
  background: var(--c-surface-3);
  color: var(--c-text);
}

.guide-enter-active,
.guide-leave-active {
  transition: opacity var(--mo-base) var(--mo-ease);
}

.guide-enter-from,
.guide-leave-to {
  opacity: 0;
}
</style>
