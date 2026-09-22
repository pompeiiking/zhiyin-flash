<script setup lang="ts">
/**
 * 导览 —— 常驻左下角的那张便签。
 *
 * 它替代了原来那个"聊天窗"。为什么不是聊天窗：
 *
 *   1. 原来那个位置放的是**业务对话**，也就是五个主理。可左下角是"边角料"的位置，
 *      把最需要专注的对话塞在角落里，用户自然找不到、也不觉得它重要；
 *   2. 更要紧的是**角色混了**。用户想问的经常不是"我该怎么选专业"，
 *      而是"这块是什么、我该点哪" —— 那是关于软件的问题，五个主理谁都答不了，
 *      它们只会继续采集你的信息。两件事挤在同一个输入框里，谁都不好使。
 *
 * 所以这里只留一件事：**告诉你这个软件怎么用**。它的形态是便签，不是对话框 ——
 * 对话在画布上那块"和主理聊聊"里，需要的时候再进去。
 *
 * 灵动来自"它会看着你的状态改口"：没建档、学籍没核验、缺几条、在哪一页，
 * 它说的话都不一样。但它**只说它确实知道的事**，不替你判断。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { buildGuide, GUIDE_NOTE, GUIDE_TITLE } from '@/lib/guide'
import NextAsk from '@/components/console/NextAsk.vue'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const open = ref(false)

const view = computed(() =>
  buildGuide({
    route: route.path,
    hasProfile: (session.profile?.dimensions.length ?? 0) > 0,
    fieldCount: session.profile?.dimensions.length ?? 0,
    gapCount: session.profile?.gaps.length ?? 0,
    chsiBound: session.chsiBound,
    askLabel: session.nextAsk?.label ?? null,
  })
)

function go(tip: { kind: string; to: string }) {
  open.value = false
  if (tip.kind === 'route') router.push(tip.to)
  else session.openOverlay(tip.to as 'portrait' | 'tasks' | 'bind' | 'talk')
}
</script>

<template>
  <div class="dock" :class="{ 'dock--open': open }">
    <!-- 收起：一行字。它会随状态改口，这是"导览在看着你"最轻的表达 -->
    <button class="note" type="button" :aria-expanded="open" @click="open = !open">
      <span class="note__mark" aria-hidden="true" />
      <span class="note__k label">{{ GUIDE_TITLE }}</span>
      <transition name="say" mode="out-in">
        <span :key="view.line" class="note__line">{{ view.line }}</span>
      </transition>
      <svg class="note__caret" width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M2.6 4.4 6 7.8l3.4-3.4" fill="none" stroke="currentColor" stroke-width="1.6"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <transition name="unfold">
      <div v-if="open" class="sheet">
        <p class="where">{{ view.where }}</p>

        <!-- 索引：这一屏能去哪。导览的核心职责就是把路指清楚 -->
        <div class="index">
          <span class="label index__k">能去哪</span>
          <ul class="rows">
            <li v-for="tip in view.tips" :key="tip.id">
              <button class="row" type="button" @click="go(tip)">
                <span class="row__label">{{ tip.label }}</span>
                <span class="row__note">{{ tip.note }}</span>
                <span class="row__arrow" aria-hidden="true">→</span>
              </button>
            </li>
          </ul>
        </div>

        <!-- 下一步：AI 在等的那件事。导览只负责把它摆出来，不抢它的话 -->
        <div class="next">
          <span class="label index__k">现在最好先做</span>
          <NextAsk />
        </div>

        <p class="foot label">{{ GUIDE_NOTE }}</p>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/*
 * 定位与原来那个角落入口一致（左下），但形态换了：
 * 它不再是一个"待打开的聊天窗"，而是一张**便签** —— 纸面、轻微倾斜、没有输入框。
 */
.dock {
  position: fixed; left: 20px; bottom: 18px; z-index: var(--z-drawer);
  display: flex; flex-direction: column; gap: var(--s2);
  align-items: flex-start;
  max-width: min(420px, calc(100vw - 40px));
}

.note {
  display: flex; align-items: center; gap: var(--s2);
  max-width: 100%;
  padding: 9px 14px 9px 12px;
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-md);
  /*
   * 便签的质地：受光的纸 + 一点点倾斜。
   * 轻，不能晃 —— 它是常驻的，晃久了会烦。
   * （原来是写死的一对暖黄渐变色，现在走 --paper-lit-soft：受光还在，黄味没有了。）
   */
  background: var(--paper-lit-soft);
  box-shadow: var(--e-3), var(--inner-hi);
  transform: rotate(-0.35deg);
  transition: border-color var(--dur-micro) var(--ease-out),
              transform var(--dur) var(--ease-spring),
              box-shadow var(--dur) var(--ease-out);
}
.note:hover {
  border-color: var(--accent);
  transform: rotate(0deg) translateY(-2px);
  box-shadow: var(--e-4), var(--inner-hi);
}
.dock--open .note { border-color: var(--accent); transform: rotate(0deg); }

/* 铅笔头那一点：它一直在呼吸，是这张便签"活着"的唯一动作 */
.note__mark {
  width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%;
  background: var(--mk-orange);
  animation: mo-breathe 2.6s var(--ease-out) infinite;
}
.note__k { color: var(--mk-orange); flex: 0 0 auto; }
.note__line {
  font-size: var(--fs-small); color: var(--ink-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 34ch;
}
.note__caret { color: var(--ink-3); flex: 0 0 auto; transition: transform var(--dur) var(--ease-out); }
.note[aria-expanded="true"] .note__caret { transform: rotate(180deg); }

/* 说话换气：改口的时候淡出淡入，不是硬切 */
.say-enter-active { transition: opacity 220ms var(--ease-out), transform 220ms var(--ease-out); }
.say-leave-active { transition: opacity 140ms var(--ease-in); }
.say-enter-from { opacity: 0; transform: translateY(3px); }
.say-leave-to { opacity: 0; }

/* 展开：一张更大的便签，往上长，不改变左下角的锚点 */
.sheet {
  width: min(420px, calc(100vw - 40px));
  padding: var(--s4);
  display: flex; flex-direction: column; gap: var(--s4);
  border: var(--bw) solid var(--line-2);
  border-radius: var(--r-lg);
  background: var(--paper-lit-soft);
  box-shadow: var(--e-4), var(--inner-hi);
  transform: rotate(-0.2deg);
  animation: sheet-in 360ms var(--ease-expo) both;
}
.where { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.75; }

.index { display: flex; flex-direction: column; gap: 6px; }
.index__k { color: var(--ink-3); }
.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 1px; }
.row {
  width: 100%;
  display: grid; grid-template-columns: 76px minmax(0, 1fr) auto;
  align-items: baseline; gap: var(--s3);
  padding: 7px 8px;
  border-radius: var(--r-sm);
  text-align: left;
  transition: background var(--dur-micro) var(--ease-out);
}
.row:hover { background: var(--fill-hover); }
.row__label { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.row__note { font-size: var(--t-xs); color: var(--ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row__arrow { color: var(--ink-3); transition: transform var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out); }
.row:hover .row__arrow { color: var(--accent); transform: translateX(2px); }

.next {
  display: flex; flex-direction: column; gap: 6px;
  padding-top: var(--s3);
  border-top: 1px dashed var(--line-2);
}
.foot { color: var(--ink-faint); line-height: 1.6; }

.unfold-enter-active { transition: opacity 220ms var(--ease-out), transform 280ms var(--ease-expo); }
.unfold-leave-active { transition: opacity 140ms var(--ease-in), transform 140ms var(--ease-in); }
.unfold-enter-from, .unfold-leave-to { opacity: 0; transform: translateY(8px) scale(0.99); }

@media (max-width: 720px) {
  .dock { left: 12px; right: 12px; bottom: 12px; max-width: none; }
  .sheet { width: 100%; }
  .note__line { max-width: 22ch; }
}
</style>
