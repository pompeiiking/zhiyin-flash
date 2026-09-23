<script setup lang="ts">
/**
 * 采集动线详情：一条一条说清楚"缺什么、从哪来、为什么要它"。
 *
 * 这一层是"动态采集策略"的说明书。用户在这里能看到的不只是待办清单，
 * 而是**系统为什么向你开这个口** —— 每一条后面那句 why 都是从画像状态推出来的，
 * 不是通用文案。这才是"采集策略跟着画像走"能被用户看见的地方。
 */
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const plan = computed(() => session.collection)

const SOURCE_LABEL: Record<string, string> = {
  chsi: '学信网',
  conversation: '问你一句',
  academic: '教务系统',
}

const SOURCE_NOTE: Record<string, string> = {
  chsi: '用学信档案的在线验证码核验，一次拿全 —— 不要账号密码。',
  conversation: '只有你自己答得上来，问一句就有。',
  academic:
    '课表与成绩在学校的教务系统里（学信网没有这两个数据）。' +
    '你在教务系统里全选复制，贴进来就行 —— 我们不登录、也不要你的账号。',
}

/** 缺的排前面，按后端给的顺序（那就是"先补哪条"） */
const missing = computed(() => (plan.value?.items ?? []).filter((i) => !i.got))
const got = computed(() => (plan.value?.items ?? []).filter((i) => i.got))

/**
 * 核验一次能补几条 —— **数出来的**，不是写死的。
 * 写死一个"8 条"的按钮文案，改一条采集规则就会变成对用户撒谎。
 */
const chsiCount = computed(() => missing.value.filter((i) => i.source === 'chsi').length)

/** 还要问几句 —— 数字是数出来的，不是写死的 */
const conversationCount = computed(() => missing.value.filter((i) => i.source === 'conversation').length)

/**
 * 这两个入口**只要还有缺口就摆出来** —— 它们不跟着"下一个该取谁"走。
 *
 * 以前的写法只渲染 nextSource 那一条：新用户看到的永远是「去核验学籍」，
 * 想导入课表就得先猜"是不是得先弄完学籍"，实测就是找不到入口。
 * 推荐顺序是推荐，不该变成门禁。
 */
const chsiOpen = computed(() => missing.value.some((i) => i.source === 'chsi'))
const academicOpen = computed(() => missing.value.some((i) => i.source === 'academic'))

function act() {
  const next = plan.value?.nextSource
  if (next === 'chsi') {
    session.bindMode = 'chsi'
    session.openOverlay('bind')
  } else if (next === 'academic') {
    session.bindMode = 'academic'
    session.openOverlay('bind')
  } else if (next === 'conversation') {
    /*
     * "去回答这几句"点下去，问的必须是**清单里最前面那条缺口**的问题，
     * 而不是一句泛泛的"说说你自己"。泛泛那句说不了"这一条在补哪个字段"，
     * 用户答完也不知道自己补上了什么（见 `askFor`）。
     */
    const first = missing.value.find((i) => i.source === 'conversation' && i.ask)
    session.askChat(first?.ask || '说说你自己：你在意什么、喜欢做什么？一句就行。')
  }
}

/**
 * 一条 conversation 缺口的直接动作：把**这条字段的追问**带进对话。
 *
 * 为什么必须逐条给：清单上"价值取向""兴趣""经历""能力自评"是四条不同的缺口，
 * 共用一个入口时，用户点下去根本不知道自己在补哪一条 —— 而采集这一环
 * 恰恰是"一次只问一件事"。问题本身来自后端（`CollectionStep.ask`），
 * 界面只负责把它带过去。
 */
function askFor(ask: string) {
  session.askChat(ask)
}

/** 每一条的入口：点哪条就去取哪条，不强迫用户跟着"下一步"走 */
function goSource(source: string) {
  if (source === 'chsi') {
    session.bindMode = 'chsi'
    session.openOverlay('bind')
  } else if (source === 'academic') {
    session.bindMode = 'academic'
    session.openOverlay('bind')
  }
}
</script>

<template>
  <Overlay
    title="采集动线"
    :subtitle="plan ? `还差 ${plan.missing} 条 · 每条都写着为什么需要它` : '正在整理这份清单'"
    from="collect"
    size="mid"
    @close="session.closeOverlay()"
  >
    <div class="wrap">
      <!-- 左：这份清单是怎么来的 -->
      <aside class="how sheet sheet--quiet">
        <span class="label how__k">这份清单怎么来的</span>
        <h3 class="how__t">不是固定流程，是照你的画像算的。</h3>
        <p class="how__d">
          系统拿你现在的画像对一遍：<b>缺什么</b>、这条<b>挡着哪一步判断</b>、<b>有没有源头能取</b>。
          已经有的不再问你，取不到的不装作能取。
        </p>
        <ul class="how__rules">
          <li><span class="label">缺不缺</span>对照你的画像</li>
          <li><span class="label">挡着谁</span>决定先补哪一条</li>
          <li><span class="label">有没有源</span>决定能不能自动补</li>
        </ul>
        <p class="label how__foot">补完一条，这份清单自己会变 —— 少一条，或者换一条排到前面。</p>
      </aside>

      <!-- 右：清单 -->
      <section class="list sheet">
        <template v-if="plan">
          <ol v-if="missing.length" class="rows">
            <li v-for="item in missing" :key="item.key" :class="{ blocked: !item.available }">
              <span class="rows__dot" aria-hidden="true" />
              <span class="rows__label">{{ item.label }}</span>
              <span class="label rows__src">{{ SOURCE_LABEL[item.source] ?? item.source }}</span>
              <span class="rows__why">{{ item.why }}</span>
              <!--
                每一条能取的数据都要自带"去哪儿取"。
                以前只有页脚那一个按钮（它只指"下一步最该做的"）——
                于是"课表在教务系统里"这件事根本没有入口，用户只能干看着。
              -->
              <button
                v-if="item.available && (item.source === 'chsi' || item.source === 'academic')"
                class="label rows__go"
                type="button"
                @click="goSource(item.source)"
              >
                {{ item.source === 'chsi' ? '去核验 →' : '去导入 →' }}
              </button>
              <!--
                "问一句"那几条也要各自带一个入口，且点开就问**这一条**：
                一条缺口对应一个动作，用户答完能立刻看到清单少一条。
              -->
              <button
                v-else-if="item.available && item.source === 'conversation' && item.ask"
                class="label rows__go"
                type="button"
                :title="item.ask"
                @click="askFor(item.ask)"
              >
                去回答 →
              </button>
              <span v-if="!item.available" class="label rows__no">没有源头</span>
            </li>
          </ol>
          <p v-else class="rows__done">该有的都有了 —— 这一轮没有要补的。</p>

          <!-- 已经拿到的：它是记录，不是待办，所以沉到下面、缩小 -->
          <details v-if="got.length" class="have">
            <summary class="label">已经拿到的 {{ got.length }} 条</summary>
            <ul>
              <li v-for="item in got" :key="item.key">
                <span class="have__ok" aria-hidden="true">✓</span>
                <span>{{ item.label }}</span>
                <span class="label have__src">{{ SOURCE_LABEL[item.source] ?? item.source }}</span>
              </li>
            </ul>
          </details>

          <div v-if="plan.blocked.length" class="note">
            <span class="label note__k">暂时取不到</span>
            <p>
              {{ plan.blocked.join(' / ') }}：这两项学信网没有，要学校的教务系统给。
              没有源头的缺口我们不会替你猜 —— 这一格先空着。
            </p>
          </div>

          <footer class="foot">
            <!--
              动作与说明**分两行**。

              以前是同一行 flex：三颗按钮 + 一段会自动换行的说明挤在一起，
              居中后又各占一行的一半 —— 看起来就是"按钮文字错位"。
              现在按钮自己一行（可换行），说明单独一行，左对齐。
            -->
            <div class="foot__acts">
              <button v-if="plan.nextSource === 'chsi'" class="btn primary" type="button" @click="act">
                去核验学籍{{ chsiCount ? `（一次补 ${chsiCount} 条）` : '' }}
              </button>
              <button
                v-else-if="plan.nextSource === 'academic'"
                class="btn primary"
                type="button"
                @click="act"
              >
                导入课表与成绩
              </button>
              <button v-else-if="plan.nextSource === 'conversation'" class="btn primary" type="button" @click="act">
                去回答{{ conversationCount ? `这 ${conversationCount} 句` : '几句' }}
              </button>
              <!--
                另外两条路**始终**摆出来，不跟着"下一个该取谁"走。
                以前只显示 nextSource 那一条：新用户看到的永远是「去核验学籍」，
                想导入课表就得先猜"是不是要先把学籍弄完" —— 实测用户就是找不到入口。
                推荐顺序是推荐，不是门禁。
              -->
              <button
                v-if="plan.nextSource !== 'academic' && academicOpen"
                class="btn ghost"
                type="button"
                @click="goSource('academic')"
              >
                导入课表与成绩
              </button>
              <button
                v-if="plan.nextSource !== 'chsi' && chsiOpen"
                class="btn ghost"
                type="button"
                @click="goSource('chsi')"
              >
                核验学籍
              </button>
            </div>
            <p class="label foot__note">
              {{ plan.nextSource ? (SOURCE_NOTE[plan.nextSource] ?? '照上面那条补上就行。') : '没有可自动补的项了。' }}
            </p>
          </footer>
        </template>

        <p v-else class="rows__done">清单还没算出来。</p>
      </section>
    </div>
  </Overlay>
</template>

<style scoped>
.wrap {
  height: 100%; min-height: 0;
  display: grid; grid-template-columns: 264px minmax(0, 1fr); gap: var(--s3);
}

.how {
  padding: var(--s4) var(--s4) var(--s5);
  margin: 32px 0 88px;
  display: flex; flex-direction: column; gap: var(--s3);
  overflow: auto;
  animation: sheet-in-left 520ms var(--ease-expo) 60ms both;
}
.how__k { color: var(--accent); }
.how__t { font-size: var(--t-h4); line-height: 1.36; }
.how__d { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.75; }
.how__rules { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.how__rules li {
  display: grid; gap: 2px;
  padding-top: var(--s2);
  border-top: 1px dashed var(--line-2);
  font-size: var(--fs-small); color: var(--ink-1);
}
.how__rules li:first-child { padding-top: 0; border-top: 0; }
.how__foot { margin-top: auto; color: var(--ink-faint); line-height: 1.65; }

.list {
  padding: var(--s4) var(--s5) var(--s5);
  margin-bottom: 48px;
  display: flex; flex-direction: column; gap: var(--s4);
  overflow: auto;
  animation: sheet-in 460ms var(--ease-expo) both;
}

.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.rows li {
  display: grid;
  grid-template-columns: 8px 76px 84px minmax(0, 1fr) auto;
  align-items: baseline; gap: var(--s3);
  padding: var(--s3) var(--s3) var(--s3) var(--s2);
  border-radius: var(--r-sm);
}
.rows li:nth-child(odd) { background: var(--fill-subtle); }
.rows__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); align-self: center; }
/* 没有源头的：虚线点 + 降一级颜色，一眼看出"这条现在动不了" */
.rows li.blocked .rows__dot { background: transparent; box-shadow: inset 0 0 0 1.5px var(--line-4); }
.rows li.blocked .rows__label { color: var(--ink-3); }
.rows__label { font-size: var(--fs-small); font-weight: 600; color: var(--ink-1); }
.rows__src { color: var(--ink-3); }
.rows__why { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.65; }
.rows__no { color: var(--ink-faint); white-space: nowrap; }
.rows__go { color: var(--accent); white-space: nowrap; }
.rows__go:hover { text-decoration: underline; }
.rows__done { font-size: var(--fs-small); color: var(--ink-3); }

.have summary { color: var(--ink-3); cursor: pointer; }
.have ul { list-style: none; margin: var(--s3) 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.have li {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px;
  border: 1px solid var(--line-1); border-radius: var(--r-pill);
  font-size: var(--t-xs); color: var(--ink-2);
}
.have__ok { color: var(--mk-green); }
.have__src { color: var(--ink-faint); }

.note {
  display: grid; gap: 4px;
  padding: var(--s3) var(--s4);
  border: 2px dashed var(--line-3); border-radius: var(--r-md);
  background: var(--n-3);
}
.note__k { color: var(--ink-faint); }
.note p { font-size: var(--fs-small); color: var(--ink-2); line-height: 1.7; }

/*
 * 动作一行、说明一行。
 * `display: grid` 而不是 flex：两行之间不需要"垂直居中"，
 * 按钮换行时也不会把说明挤到半截高度上。
 */
.foot { display: grid; gap: var(--s2); margin-top: auto; padding-top: var(--s4); }
.foot__acts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s2); }
.foot__acts .btn { flex: 0 0 auto; }
.foot__note { color: var(--ink-3); line-height: 1.7; }

@media (max-width: 900px) {
  .wrap { grid-template-columns: minmax(0, 1fr); height: auto; }
  .how { margin: 0 0 var(--s3); }
  .list { margin-bottom: 0; }
}
</style>
