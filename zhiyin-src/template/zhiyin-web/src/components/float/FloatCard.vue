<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FloatItem } from '@/data/content'
import { useSessionStore } from '@/stores/session'

/**
 * 一块浮窗。两种内容共用一套外观：
 *   消息（notice）  —— 有事发生，带一个可以直接做完的动作
 *   提问（question）—— AI 有事想确认，回答完就自己消失
 *
 * 手感来自四件事：从右侧滑入 + 缩放、进出过程带模糊对焦、回弹落位、
 * 以及半透明材质 —— 它盖在内容上，但你能看见下面是什么。
 */
const props = defineProps<{
  item: FloatItem
  index: number
  /** 这一片被抽出来了（指针停着 / 键盘焦点在里面）：完整显示 */
  lifted?: boolean
  /** 叠在别人下面：只露顶栏，正文压暗 */
  pinned?: boolean
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'action', kind: string): void }>()
const session = useSessionStore()

const answered = ref(false)
const showWhy = ref(false)

const tone = computed(() => props.item.tone)

function answer(option: string) {
  session.answerQuestion(props.item.id, option)
  answered.value = true
  // 回答完停一下让用户看到反馈，然后自己消失
  window.setTimeout(() => emit('close'), 3200)
}
</script>

<template>
  <article
    class="float"
    :class="[`tone-${tone}`, { 'is-lifted': props.lifted, 'is-pinned': props.pinned && !props.lifted }]"
    :tabindex="0"
    :style="{ '--rot': (props.index % 2 === 0 ? -0.4 : 0.45) + 'deg' }"
  >
    <header class="float__bar">
      <span class="float__dot" aria-hidden="true" />
      <span class="label float__kicker">{{ props.item.kicker }}</span>
      <button class="float__close" type="button" aria-label="关掉这条" @click="emit('close')">
        <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" stroke-width="1.5"
                stroke-linecap="round" />
        </svg>
      </button>
    </header>

    <!-- 消息 -->
    <template v-if="props.item.type === 'notice'">
      <h3 class="float__title">{{ props.item.title }}</h3>
      <p class="float__body">{{ props.item.body }}</p>

      <footer v-if="props.item.action" class="float__foot">
        <button
          v-if="session.acceptedNotices.includes(props.item.id)"
          class="chip live"
          type="button"
          @click="emit('close')"
        >
          已排进今天
        </button>
        <button
          v-else
          class="btn primary float__cta"
          type="button"
          @click="emit('action', props.item.action.kind)"
        >
          {{ props.item.action.label }}
        </button>
      </footer>
    </template>

    <!-- 提问 -->
    <template v-else>
      <h3 class="float__title">{{ props.item.question }}</h3>

      <div v-if="!answered" class="float__options">
        <button
          v-for="opt in props.item.options"
          :key="opt"
          class="opt"
          type="button"
          @click="answer(opt)"
        >
          {{ opt }}
        </button>
      </div>

      <template v-else>
        <p class="float__picked">
          <span class="label">你的回答</span>{{ session.answered[props.item.id] }}
        </p>
        <p class="float__reply">{{ props.item.reply }}</p>
      </template>

      <footer class="float__foot">
        <button class="float__why label" type="button" :aria-expanded="showWhy" @click="showWhy = !showWhy">
          {{ showWhy ? '收起' : '为什么问这个' }}
        </button>
      </footer>
      <p v-if="showWhy" class="float__reason">{{ props.item.why }}</p>
    </template>
  </article>
</template>

<style scoped>
.float {
  position: relative;
  pointer-events: auto;
  display: flex; flex-direction: column; gap: var(--s2);
  padding: var(--s4) var(--s4) var(--s4) var(--s5);
  border-radius: var(--r-md);
  /*
   * 玻璃再透一点：用户要的是"整体半透明"—— 盖在内容上，但下面是什么看得见。
   * 太实就变成一块挡视线的板子。
   */
  background: color-mix(in srgb, var(--n-0) 82%, transparent);
  backdrop-filter: blur(16px) saturate(1.15);
  border: var(--bw) solid var(--line-2);
  box-shadow: var(--e-4), var(--inner-hi);
  /*
   * 叠着的时候不旋转：书签叠要的是"齐边压住"，转着放会互相咬在一起。
   * 倾斜只在被抽出来的那一片上留一点点，像刚从叠里抽出来的纸。
   */
  transform: rotate(0deg);
  transform-origin: right center;
  will-change: transform, opacity;
  transition: transform var(--dur) var(--ease-spring),
              box-shadow var(--dur) var(--ease-out),
              border-color var(--dur) var(--ease-out),
              background var(--dur) var(--ease-out);
}

/*
 * 被压住的那几片：只露顶栏那一条。
 *
 * 露出来的那一条正好是 bar（圆点 + 类别 + 关闭键）—— 用户扫一眼就知道
 * "还有几条、都是哪一类"，想细看就把指针移上去。
 * `height` 由内容决定，所以这里用 `max-height` 卡住"露多少"。
 */
.is-pinned {
  max-height: 52px;
  overflow: hidden;
}
.is-pinned::after { opacity: 0; }
.is-pinned .float__title,
.is-pinned .float__body,
.is-pinned .float__foot,
.is-pinned .float__options,
.is-pinned .float__reason,
.is-pinned .float__picked,
.is-pinned .float__reply { visibility: hidden; }

/* 抽出来的那一片：完整显示，并轻轻抬起（像从叠里抽出来） */
.is-lifted {
  transform: translateY(-2px) rotate(var(--rot));
  border-color: var(--line-3);
  box-shadow: none;
  z-index: 3;
}

/* 左侧一道语义色条，一眼分清是哪一类消息 */
.float::before {
  content: "";
  position: absolute; left: 12px; top: var(--s4); bottom: var(--s4);
  width: 3px; border-radius: 3px;
  background: var(--line-3);
}
.tone-alert::before { background: var(--warn); color: var(--warn); }
.tone-intel::before { background: var(--fact); color: var(--fact); }
.tone-coach::before { background: var(--accent); color: var(--accent); }
.tone-handoff::before { background: var(--violet); color: var(--violet); }

.float:hover {
  transform: translateX(-7px) scale(1.016) rotate(0deg);
  border-color: var(--line-3);
}

.float__bar { display: flex; align-items: center; gap: var(--s2); }
.float__dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--line-3);
}
.tone-alert .float__dot { background: var(--warn); color: var(--warn); }
.tone-intel .float__dot { background: var(--fact); color: var(--fact); }
.tone-coach .float__dot { background: var(--accent); color: var(--accent); }
.tone-handoff .float__dot { background: var(--violet); color: var(--violet); }
.float__kicker { color: var(--ink-3); }
.float__close {
  margin-left: auto;
  width: 24px; height: 24px; border-radius: 50%;
  display: grid; place-items: center; color: var(--ink-3);
  transition: color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out);
}
.float__close:hover { color: var(--ink-1); background: var(--fill-press); }

.float__title {
  font-family: var(--font-display);
  font-size: var(--t-body); line-height: 1.45; letter-spacing: -0.012em;
  position: relative; z-index: 1;
  /* 不再截断：这条是"展开给你看的"，宁可卡片高一点也要话说全 */
}
.float__body {
  font-size: var(--t-sm); color: var(--ink-2); line-height: 1.75; position: relative; z-index: 1;
}
.float__foot { display: flex; align-items: center; gap: var(--s2); margin-top: var(--s1); }
.float__cta { height: 32px; padding: 0 var(--s4); font-size: var(--t-xs); }

.float__options { display: flex; flex-wrap: wrap; gap: 6px; }
.opt {
  padding: 7px 13px; border-radius: var(--r-pill);
  border: 1px solid var(--line-3);
  background: var(--fill-subtle);
  font-size: var(--t-sm); color: var(--ink-2);
  transition: color var(--dur-micro) var(--ease-out),
              border-color var(--dur-micro) var(--ease-out),
              background var(--dur-micro) var(--ease-out),
              transform var(--dur-micro) var(--ease-out);
}
.opt:hover {
  color: var(--ink-1); border-color: var(--accent);
  background: var(--accent-soft); transform: translateY(-1px);
}

.float__picked { font-size: var(--t-sm); color: var(--ink-1); }
.float__picked .mono { margin-right: 6px; color: var(--accent); }
.float__reply { font-size: var(--t-sm); color: var(--ink-2); }
.float__why { color: var(--ink-3); }
.float__why:hover { color: var(--ink-1); }
.float__reason { font-size: var(--t-sm); color: var(--ink-3); }
</style>

