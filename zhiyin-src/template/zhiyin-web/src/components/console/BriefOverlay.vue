<script setup lang="ts">
import { computed } from 'vue'
import Overlay from '@/components/console/Overlay.vue'
import AiFrame from '@/components/ai/AiFrame.vue'
import { briefTask, type BriefToday } from '@/ai/registry'
import { useSessionStore } from '@/stores/session'

/**
 * 今日简报 —— 打招呼那块点开要看的东西。
 *
 * 它不列任务（任务是"我的任务"那块的事）。它回答三个更值钱的问题：
 *   1. **为什么是这两件** —— 每条理由都挂着来源，能点开
 *   2. **从上次到现在变了什么** —— 让"画像是活的"这件事被看见
 *   3. **如果我今天不做会怎样** —— 把代价说清楚，选择才是真的选择
 *
 * 整块内容是模型算出来的，所以套 AiFrame：它会先显示"正在算什么"，
 * 算完给一个可点的标记（几条依据、花了多久、谁算的）。
 */
const session = useSessionStore()
const task = () => briefTask() as never

const chosen = computed(() => session.stageChoice)

function pick(id: string, label: string) {
  session.chooseStage(label)
  if (id === 't3') return
  window.setTimeout(() => session.closeOverlay(), 620)
}

function showSource(text: string, from: string) {
  session.openDrawer('这条判断的依据', from, [
    { source: from, detail: text, confidence: 0.86, at: '今天' },
    { source: '影响面', detail: '这一条变了，今日排期与两套方案会跟着重算。', confidence: 0.9, at: '规则' },
  ])
}
</script>

<template>
  <Overlay
    title="今天为什么是这两件"
    subtitle="由你的画像、窗口期和最近的变化推出来"
    from="greet"
    size="mid"
    @close="session.closeOverlay()"
  >
    <div class="brief">
      <AiFrame :task="task">
        <template #default="{ data }">
          <div v-if="data" class="brief__body">
            <!--
              两张浮空的薄片，而不是一整块底板：上面那张说"为什么是它"，
              下面那张是"所以今天动哪一件"。中间留一段空气，读起来是两件事。
            -->
            <section class="card sheet">
              <h3 class="brief__head editorial">{{ (data as BriefToday).headline }}</h3>

              <div class="sec">
              <span class="label sec__label">因为</span>
              <ul class="reasons">
                <li v-for="(r, i) in (data as BriefToday).because" :key="i">
                  <button class="reason" type="button" @click="showSource(r.text, r.from)">
                    <span class="reason__text">{{ r.text }}</span>
                    <span class="reason__from label">{{ r.from }}</span>
                  </button>
                </li>
              </ul>
              </div>

              <div v-if="(data as BriefToday).changed.length" class="sec">
                <span class="label sec__label">从上次到现在</span>
                <ul class="changed">
                  <li v-for="(c, i) in (data as BriefToday).changed" :key="i">
                    <span class="label changed__at">{{ c.at }}</span>
                    <span class="changed__text">{{ c.text }}</span>
                  </li>
                </ul>
              </div>
            </section>

            <section class="card sheet">
              <div class="sec">
                <span class="label sec__label">如果你今天不做</span>
                <p class="skip">{{ (data as BriefToday).ifYouSkip }}</p>
              </div>

              <div class="sec">
                <span class="label sec__label">从哪儿开始</span>
                <div class="opts">
                  <button
                    v-for="o in (data as BriefToday).next"
                    :key="o.id"
                    class="opt"
                    type="button"
                    :aria-pressed="chosen === o.label"
                    @click="pick(o.id, o.label)"
                  >
                    <span class="opt__label">{{ o.label }}</span>
                    <span class="opt__why">{{ o.why }}</span>
                  </button>
                </div>
              </div>
            </section>
          </div>
        </template>
      </AiFrame>
    </div>
  </Overlay>
</template>

<style scoped>
/*
 * 浮层的底板已经拿掉（见 Overlay.vue），所以这里自己出纸：
 * 两张薄片 + 中间一段空气。原来它是"一整块大板上的几段文字"。
 */
.brief { flex: 1; min-height: 0; overflow: auto; padding: var(--s2) 0 var(--s1); }
.brief__body { display: flex; flex-direction: column; gap: var(--s4); }
.card { display: flex; flex-direction: column; gap: var(--s4); padding: var(--s5) var(--s6); }
.brief__head { font-size: var(--t-h2); line-height: 1.35; max-width: 34ch; }

.sec { display: flex; flex-direction: column; gap: var(--s2); }
.sec__label { color: var(--ink-3); }

/* 理由：整条可点，点开看它从哪来 */
.reasons { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.reason {
  width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline; gap: var(--s3);
  padding: var(--s3) var(--s3) var(--s3) var(--s4);
  border-left: 3px solid var(--mk-green);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  text-align: left;
  transition: background var(--mo-fast) var(--mo-out);
}
.reason:hover { background: var(--fill-hover); }
.reason__text { font-size: var(--fs-small); line-height: 1.7; color: var(--ink-1); }
.reason__from { color: var(--ink-3); flex: 0 0 auto; }

.changed { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.changed li { display: grid; grid-template-columns: 104px minmax(0, 1fr); gap: var(--s3); align-items: baseline; }
.changed__at { color: var(--ink-3); }
.changed__text { font-size: var(--fs-small); line-height: 1.7; color: var(--ink-2); }

.skip {
  padding: var(--s3) var(--s4);
  border: 2px dashed var(--mk-orange);
  border-radius: var(--r-md);
  background: var(--mk-orange-soft);
  font-size: var(--fs-small); line-height: 1.75; color: var(--ink-1);
}

.opts { display: grid; gap: var(--s2); }
.opt {
  display: grid; gap: 2px; text-align: left;
  padding: var(--s3) var(--s4);
  border: var(--bw) solid var(--line-2); border-radius: var(--r-md);
  background: var(--n-1);
  transition: border-color var(--mo-fast) var(--mo-out), transform var(--mo-fast) var(--mo-out), background var(--mo-fast) var(--mo-out);
}
.opt:hover { border-color: var(--ink-1); transform: translateY(-1px); }
.opt[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-soft); }
.opt__label { font-size: var(--fs-body); color: var(--ink-1); }
.opt__why { font-size: var(--fs-small); color: var(--ink-3); line-height: 1.6; }
</style>


