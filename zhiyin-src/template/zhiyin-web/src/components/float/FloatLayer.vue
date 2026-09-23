<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import FloatCard from '@/components/float/FloatCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * 浮窗层 —— 一叠**书签**。
 *
 * 手感是怎么来的（这几条是这一版唯一的重点）：
 *   · **位置固定在右上**：视线扫完标题就往那儿落，不会跑到屏幕下半截；
 *   · **像书签一样叠着**：每条只露出顶栏那一条，指针停在哪片，哪片被抽出来
 *     放到最上面完整显示，其余仍然叠着 —— 一眼能看出"还有几条、各是什么"；
 *   · **整叠可收起**：收起来只剩一枚写着条数的书签签，点它再展开；
 *   · **从上方落下**：新的一条从屏幕上方掉进来，落定带一点回弹；
 *   · **半透明**：盖在内容上，但下面是什么仍然看得见。
 *
 * 两条内容口径没变：
 *   · 消息**只从后端来**（通知 / 智能体判断的下一步），这里不按本地脚本自己往外飘；
 *   · 每条都能单独关掉，关掉之后剩下的自己合拢（TransitionGroup 的 move）。
 */
const session = useSessionStore()
const router = useRouter()

/**
 * **一次只摆一片。**
 *
 * 原来最多摆四片（叠成书签），实测的后果是：后台一次拉回几条（教练提醒 + 集群给的
 * 下一步 + 交接），屏幕右上角**同时跳出来五个**（这层四片 + 轨道播报一片）。
 * 用户的原话是"无论拉取几个信息都只跳一个才对" —— 对。
 *
 * 消息是"顺路看一眼"的东西，不是任务列表：一片一片看，看完了下一条自己顶上来。
 * 还剩几条用一行计数说清楚，点它就直接看下一条。
 *
 * 外部情报（tone=intel）**不归这一层管**：它走右上轨道的实时播报体系
 * （AgentRail 的 pops，和"谁接手了"同一套显示），不再单飞到右下角。
 */
const MAX_OPEN = 1
const mine = computed(() => session.floats.filter((f) => f.tone !== 'intel'))
const visible = computed(() => mine.value.slice(0, MAX_OPEN))
const overflow = computed(() => mine.value.slice(MAX_OPEN))

/*
 * 哪一片被"抽出来"。
 *
 * 指针停在哪片，哪片就到最上面完整显示；没有指针（触屏 / 键盘）时默认第一片。
 * 这是书签叠的核心：不是全部摊开（占满屏幕），也不是全部压住（看不见内容），
 * 而是"看哪片抽哪片"。
 */
const liftedId = ref<string>('')
const focusId = computed(() => liftedId.value || visible.value[0]?.id || '')

/** 整叠收起（只剩一枚写着条数的签）。收起状态记住 —— 用户关一次就是不想再看。 */
const COLLAPSE_KEY = 'zhiyin_floats_collapsed'
const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
}

/**
 * 自动消失。
 *
 * 依据：非关键浮窗应在 3–5 秒后自动消失；长期停留的浮窗会盖住下面的控件，
 * 而 WCAG 2.2 AA「焦点不被遮挡」明确要求持久浮层必须可关闭或让位。
 * 所以这里按类型分档：紧急（alert）与教练提醒留着手动关，其余到点自动收走。
 */
const AUTO_DISMISS_MS: Record<string, number> = {
  alert: 0,     // 0 = 不自动消失（截止提醒必须被看到）
  coach: 0,
  intel: 6000,  // 情报虽不在这层渲染，到点仍由这里收走（AgentRail 只管显示）
  handoff: 7000,
}
const timersByFloat = new Map<string, number>()

watch(
  () => session.floats.map((f) => f.id).join(','),
  () => {
    for (const item of session.floats) {
      if (timersByFloat.has(item.id)) continue
      const wait = AUTO_DISMISS_MS[item.tone] ?? 6000
      if (!wait) continue
      const id = window.setTimeout(() => {
        session.dismissFloat(item.id)
        timersByFloat.delete(item.id)
      }, wait)
      timersByFloat.set(item.id, id)
    }
    // 已经被关掉的，清掉它的定时器
    for (const [id, timer] of timersByFloat) {
      if (!session.floats.some((f) => f.id === id)) {
        window.clearTimeout(timer)
        timersByFloat.delete(id)
      }
    }
  },
  { immediate: true }
)

/** Esc 收起整叠 —— 给键盘用户一条明确的"走开"路径 */
function onKey(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (session.overlay || session.drawer) return
  if (session.floats.length) session.dismissAllFloats()
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  timersByFloat.forEach((id) => window.clearTimeout(id))
  timersByFloat.clear()
  document.removeEventListener('keydown', onKey)
})

function onAction(kind: string, id: string) {
  if (kind === 'accept') {
    session.acceptNotice(id)
    window.setTimeout(() => session.dismissFloat(id), 700)
    return
  }
  if (kind === 'tasks') {
    session.openOverlay('tasks')
    return
  }
  if (kind === 'report') {
    router.push('/report')
    return
  }
  if (kind === 'chat') {
    session.callTalk()
    return
  }
  if (kind === 'ask') {
    // 集群判断的"下一步"：把它要去的地方打开，并顺手收掉这条
    session.goToNextAsk()
    session.dismissFloat(id)
    return
  }
  if (kind === 'intel') {
    // 外部情报：摊开这一批公开事实（连来源与原页面）
    session.dismissFloat(id)
    session.openOverlay('intel')
  }
}
</script>

<template>
  <!--
    一条自己的消息都没有时整层不渲染 ——
    情报归队到右上轨道之后，这层常会是空的；空层若只渲染一个"消息"表头，
    那两个字就孤零零地压在画布内容上（用户实测撞到的就是它）。
  -->
  <div v-if="mine.length" class="layer" aria-label="浮窗" :class="{ 'is-collapsed': collapsed }">
    <!-- 收起状态：只剩一枚书签签，写着还有几条 -->
    <button
      v-if="collapsed && mine.length"
      class="layer__tab"
      type="button"
      :aria-expanded="false"
      @click="toggleCollapse"
    >
      <span class="layer__tabdot" aria-hidden="true" />
      有 {{ mine.length }} 条消息
    </button>

    <template v-else>
      <div class="layer__head">
        <span class="label layer__k">消息</span>
        <button
          v-if="mine.length"
          class="label layer__toggle"
          type="button"
          :aria-expanded="true"
          @click="toggleCollapse"
        >收起</button>
      </div>

      <!-- 书签叠：整体只有这一处会动，每片之间靠负边距叠着 -->
      <TransitionGroup
        name="drop"
        tag="div"
        class="stack"
        :duration="{ enter: 420, leave: 200 }"
        @mouseleave="liftedId = ''"
      >
        <FloatCard
          v-for="(item, i) in visible"
          :key="item.id"
          :item="item"
          :index="i"
          :lifted="focusId === item.id"
          :pinned="i > 0"
          @mouseenter="liftedId = item.id"
          @focusin="liftedId = item.id"
          @close="session.dismissFloat(item.id)"
          @action="(kind: string) => onAction(kind, item.id)"
        />
      </TransitionGroup>

      <div v-if="overflow.length" class="layer__foot">
        <!--
          一次只摆一片，前提是"还剩几条"必须看得见，而且得能接着看。
          所以这一行的两条动作是：**看下一条**（把当前这条收掉，下一条自己顶上来）
          与**全部收掉**（用户不想一条条看的时候）。
        -->
        <button
          class="layer__more label"
          type="button"
          @click="session.dismissFloat(visible[0]?.id ?? '')"
        >
          还有 {{ overflow.length }} 条 · 看下一条
        </button>
        <button
          class="layer__clear label"
          type="button"
          @click="mine.forEach((f) => session.dismissFloat(f.id))"
        >
          全部收掉（{{ mine.length }}）
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.layer {
  /*
   * 位置：**右上角**，不拉到底。
   *
   * 之前写的是 `top..bottom` 拉满整列，于是内容一多就变成"一屏浮窗"；
   * 而且它跟着浏览器窗口一路往下长，看起来像侧边栏，不像"飘过来的消息"。
   */
  position: fixed;
  /*
   * 74px 是让开顶部那两片浮岛（账号 / 轨道把手）之后的位置。
   * 加上 `--rail-pops-h` 是让开**播报**（谁接手了 / 新到的情报）——
   * 两块推送都在右上角，不让位就会叠在一起：上面的消息卡会把播报的按钮吃掉，
   * 表现是"播报看得见、点不动"。高度由 AgentRail 量出来写进这个变量。
   */
  top: calc(74px + var(--rail-pops-h, 0px));
  right: 22px;
  width: min(336px, 32vw);
  max-height: calc(100vh - 140px);
  z-index: var(--z-drawer);
  display: flex; flex-direction: column;
  gap: var(--s2);
  pointer-events: none;   /* 只有浮窗本身接事件 */
}

/*
 * 书签叠。
 *
 * 片与片之间用**负边距**互相压住：每片只露出顶栏那一条，
 * 指针停上去的那片（`.is-lifted`）往上抽出来，完整显示。
 * 这样"有几条、各是什么"一眼可见，又不会占满屏幕。
 */
.stack {
  display: flex; flex-direction: column;
  gap: 0;
  /* 叠起来的深度感：越靠后越轻 */
  pointer-events: none;
}
.stack > * {
  pointer-events: auto;
  transition: margin 320ms var(--ease-spring), transform 320ms var(--ease-spring);
}
.stack > * + * { margin-top: -46px; }
.stack > *:hover,
.stack > *:focus-within { margin-top: 6px; z-index: 3; }
/*
 * 抽出来那一片**下面**的书签要留出空档。
 *
 * 不留的后果实测过：展开的那片会把下一片的签头压住，鼠标够不到它 ——
 * 于是这叠书签只能翻第一片，后面的全是死的。
 */
.stack > .is-lifted + * { margin-top: 10px; }

.layer__head {
  /*
   * 表头做成**一枚小签**，不再是一行裸字。
   *
   * 这里踩过一个观感问题：这一层是浮在画布上面的，表头那两个字（"消息 / 收起"）
   * 背后正好压着画布右上角那块卡片 —— 于是它读起来像"那张卡上多出来两个字的乱码"，
   * 而不像"这里有一叠消息"。给它自己的底与边之后，它和下面的书签是一件事。
   */
  align-self: flex-end;
  display: inline-flex; align-items: center; gap: var(--s2);
  padding: 3px 6px 3px 12px;
  border-radius: var(--r-pill);
  border: var(--bw) solid var(--line-2);
  background: var(--glass-2);
  backdrop-filter: blur(12px);
  box-shadow: var(--e-1), var(--inner-hi);
  pointer-events: auto;
}
.layer__k { color: var(--ink-faint); }
.layer__toggle {
  color: var(--ink-faint);
  padding: 2px 8px; border-radius: var(--r-pill);
  pointer-events: auto;
}
.layer__toggle:hover { color: var(--ink); background: var(--fill-hover); }

/* 收起状态的那枚签：贴着右上角，写着还有几条 */
.layer__tab {
  pointer-events: auto;
  display: flex; align-items: center; gap: var(--s2);
  align-self: flex-end;
  padding: 8px 14px 8px 12px;
  border-radius: var(--r-pill);
  border: var(--bw) solid var(--line-2);
  background: var(--glass-2);
  box-shadow: var(--e-3), var(--inner-hi);
  font-size: var(--fs-small); color: var(--ink-2);
  backdrop-filter: blur(14px) saturate(1.1);
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.layer__tab:hover { transform: translateY(-2px); color: var(--ink-1); }
.layer__tabdot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent);
}

.layer__foot {
  display: flex; align-items: center; justify-content: flex-end; gap: var(--s3);
  flex-wrap: wrap;
  padding: 2px 2px 0;
}
.layer__clear, .layer__more {
  pointer-events: auto;
  color: var(--ink-faint);
  padding: 2px 8px; border-radius: var(--r-pill);
  transition: color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out);
}
.layer__more { margin-right: auto; }
.layer__clear:hover, .layer__more:hover { color: var(--ink); background: var(--fill-hover); }

/*
 * 从**上方**掉下来，落定带回弹。
 *
 * 用户要的是"从上往下跳出"：不是从右边滑进来 —— 右边滑进来像抽屉，
 * 从上往下掉才像"有人把一张便签拍在你桌上"。
 * move 负责"关掉一片，剩下的自己合拢"。
 */
.drop-enter-active {
  transition:
    transform 420ms var(--ease-spring),
    opacity 260ms var(--ease-out),
    filter 420ms var(--ease-out);
}
.drop-leave-active {
  transition:
    transform 200ms var(--ease-out),
    opacity 180ms var(--ease-out);
  position: absolute;
  width: min(336px, 32vw);
}
.drop-enter-from {
  opacity: 0;
  transform: translateY(-26px) scale(0.96);
  filter: blur(10px);
}
.drop-leave-to {
  opacity: 0;
  transform: translateY(-14px) scale(0.97);
}
/* 补位动效：剩下的书签带一点回弹地合拢 */
.drop-move { transition: transform 380ms var(--ease-spring); }

@media (max-width: 900px), (max-height: 620px) {
  /* 窄屏：横排会挡住内容，改成贴底的一条带，仍然叠着 */
  .layer {
    position: fixed; top: auto; bottom: 12px; right: 12px; left: 12px;
    width: auto; max-height: 62vh;
  }
  .stack > * + * { margin-top: -52px; }
  .drop-leave-active { position: static; width: auto; }
}
</style>
